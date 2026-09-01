#!/usr/bin/env node
/**
 * FAULT-INJECTION TEST for R22/R23 (tools/wasm/sweep_durability.mjs and its
 * wiring into tools/wasm/sweep_multi_worker.mjs).
 *
 *   node tools/wasm/test_sweep_durability.mjs
 *
 * A durability claim without an injected fault is not evidence (this is the
 * explicit standard this file is held to). Every case below either drives
 * sweep_multi_worker.mjs as a real subprocess against a tiny fixture
 * topology with a deliberately faulty `fetch` (lost responses, a hung
 * response, a transient failure that recovers, a permanently unreachable
 * family), or exercises sweep_durability.mjs's exported primitives directly
 * for the edge cases a full sweep cannot reach on its own by construction
 * (see section "UNIT" below for why).
 *
 * Two halves:
 *
 *   UNIT   — sweep_durability.mjs's exports, called directly, in-process.
 *            Table-driven, exhaustive on the idempotent-ledger and
 *            reconciliation edge cases, the same "anti-vacuity" discipline
 *            test_check_deployed_freshness.mjs uses: this file must be able
 *            to make each check fail, not just assert it looks correct.
 *
 *   FAULT  — sweep_multi_worker.mjs run as a real subprocess (spawnSync)
 *            against a fixture topology (mkdtempSync'd, never the committed
 *            wasm_tier_topology.json — this stays fast and does not depend
 *            on 4500+ deployed tests) with `globalThis.fetch` replaced by a
 *            fault-injecting stub, exactly the substitution mechanism
 *            test_check_deployed_freshness.mjs already uses via `--import`.
 *            Nothing in the sweep script is modified, mocked out, or
 *            bypassed — same CLI, same argument parsing, same exit codes.
 */

import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  workKey,
  ResultLedger,
  reconcile,
  fetchJsonWithRetry,
  ReplicaLog,
  writeReplicatedSummary,
  writeDeadLetter,
} from "./sweep_durability.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SWEEPER = join(HERE, "sweep_multi_worker.mjs");
const TMP = mkdtempSync(join(tmpdir(), "sweep-durability-test-"));

let failures = 0;
function expect(label, actual, wanted, describe = (x) => JSON.stringify(x)) {
  const ok = JSON.stringify(actual) === JSON.stringify(wanted);
  if (ok) {
    console.log(`  PASS  ${label}`);
    return;
  }
  failures += 1;
  console.log(`  FAIL  ${label}`);
  console.log(`        wanted: ${describe(wanted)}`);
  console.log(`        got:    ${describe(actual)}`);
}

function expectTrue(label, cond, detail = "") {
  if (cond) {
    console.log(`  PASS  ${label}`);
    return;
  }
  failures += 1;
  console.log(`  FAIL  ${label} ${detail}`);
}

// ===========================================================================
// UNIT — sweep_durability.mjs's exported primitives, direct and in-process.
// ===========================================================================
console.log("UNIT: workKey / ResultLedger / reconcile / fetchJsonWithRetry / ReplicaLog");

// --- workKey --------------------------------------------------------------
expect("workKey is family#index", workKey("drc", 3), "drc#3");
expect("workKey distinguishes families", workKey("drc", 3) !== workKey("emc", 3) ? "distinct" : "same", "distinct");
expect("workKey distinguishes indices", workKey("drc", 3) !== workKey("drc", 30) ? "distinct" : "same", "distinct");

// --- ResultLedger: the idempotent-key property (R22) ----------------------
{
  const l = new ResultLedger();
  expect("empty ledger: size 0", l.size(), 0);
  const r1 = l.record("drc#0", { status: "pass", name: "t0" });
  expect("first record -> recorded", r1, "recorded");
  expect("size after first record", l.size(), 1);
}
{
  // A retry whose original attempt's response arrives late must not double-
  // count: the SAME verdict recorded twice for the SAME key is a no-op.
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass", name: "t0" });
  const r2 = l.record("drc#0", { status: "pass", name: "t0" });
  expect("duplicate identical delivery -> duplicate", r2, "duplicate");
  expect("size stays 1 after duplicate", l.size(), 1);
  expect("duplicatesIgnored increments", l.duplicatesIgnored, 1);
  expect("no conflict recorded for an identical duplicate", l.conflicts.length, 0);
}
{
  // A DIFFERENT verdict for the same key is a corruption risk, not a benign
  // duplicate: must not corrupt (silently overwrite) and must not vanish.
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass", name: "t0" });
  const r2 = l.record("drc#0", { status: "fail", name: "t0" });
  expect("conflicting delivery -> conflict", r2, "conflict");
  expect("size stays 1 (first verdict kept)", l.size(), 1);
  expect("first verdict is the one retained", l.get("drc#0").status, "pass");
  expect("conflict recorded", l.conflicts.length, 1);
  expect("conflict names the key", l.conflicts[0].key, "drc#0");
}
{
  // Multiple independent keys never interfere with each other's idempotency.
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass", name: "t0" });
  l.record("emc#0", { status: "fail", name: "u0" });
  l.record("drc#0", { status: "pass", name: "t0" }); // duplicate of drc#0
  l.record("emc#1", { status: "pass", name: "u1" });
  expect("size counts distinct keys only", l.size(), 3);
  expect("values() has one entry per key", l.values().length, 3);
}
{
  // A name mismatch under the same status is still treated as a genuine
  // conflict, not a benign duplicate — the ledger must not decide "close
  // enough" for two different tests landing on the same key (which would
  // itself indicate a dispatch bug worth surfacing, not hiding).
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass", name: "t0" });
  const r = l.record("drc#0", { status: "pass", name: "t0_renamed" });
  expect("same status, different name -> conflict", r, "conflict");
}

// --- reconcile(): dispatched == accounted-for, and this file can make it fail ---
{
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass" });
  l.record("drc#1", { status: "pass" });
  expect("reconcile: nothing missing when all dispatched keys are recorded", reconcile(["drc#0", "drc#1"], l), []);
}
{
  const l = new ResultLedger();
  l.record("drc#0", { status: "pass" });
  // drc#1 was dispatched (it is in the caller's key list) but NEVER recorded
  // — the exact shape of a silently dropped result. This is the case the
  // whole reconciliation pass exists to catch; proving reconcile() actually
  // returns it (not an empty array) is the anti-vacuity check for R22's
  // core invariant.
  expect("reconcile: a dispatched-but-unrecorded key is reported missing", reconcile(["drc#0", "drc#1"], l), ["drc#1"]);
}
{
  const l = new ResultLedger();
  expect("reconcile: everything missing when the ledger is empty", reconcile(["a#0", "a#1", "a#2"], l), ["a#0", "a#1", "a#2"]);
}
expect("reconcile: no dispatched keys -> nothing missing (vacuously)", reconcile([], new ResultLedger()), []);

// --- fetchJsonWithRetry -----------------------------------------------------
function fakeOkResponse(body) {
  return { ok: true, status: 200, json: async () => body };
}
function fakeBadResponse(status, body) {
  return { ok: false, status, json: async () => body };
}

{
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return fakeOkResponse({ verdict: "pass", index: 0, name: "t" });
  };
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, { fetchImpl, maxRetries: 2 });
  expect("fetchJsonWithRetry: success on first attempt -> ok", r.ok, true);
  expect("  ...attempts == 1", r.attempts, 1);
  expect("  ...exactly one fetch call made", calls, 1);
}
{
  let calls = 0;
  const sleeps = [];
  const fetchImpl = async () => {
    calls += 1;
    if (calls === 1) throw new Error("simulated network fault");
    return fakeOkResponse({ verdict: "pass", index: 0, name: "t" });
  };
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, {
    fetchImpl, maxRetries: 2, backoffMs: 10, sleepImpl: async (ms) => sleeps.push(ms),
  });
  expect("fetchJsonWithRetry: fails once, recovers on retry -> ok", r.ok, true);
  expect("  ...attempts == 2 (one retry)", r.attempts, 2);
  expect("  ...backoff slept once before the retry", sleeps.length, 1);
}
{
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    throw new Error("permanent network fault");
  };
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, {
    fetchImpl, maxRetries: 2, backoffMs: 1, sleepImpl: async () => {},
  });
  expect("fetchJsonWithRetry: exhausts retries -> not ok (dead-letter case)", r.ok, false);
  expect("  ...attempts == maxRetries+1", r.attempts, 3);
  expect("  ...exactly maxRetries+1 fetch calls made", calls, 3);
  expectTrue("  ...error message is preserved", r.error.includes("permanent network fault"), r.error);
}
{
  const fetchImpl = async () => fakeBadResponse(500, { status: "error", message: "boom" });
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, { fetchImpl, maxRetries: 0 });
  expect("fetchJsonWithRetry: non-2xx with no verdict -> not ok", r.ok, false);
  expectTrue("  ...error names the HTTP status", r.error.includes("500"), r.error);
}
{
  const fetchImpl = async () => fakeOkResponse({ status: "ok" }); // 200 but no "verdict"
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, { fetchImpl, maxRetries: 0 });
  expect("fetchJsonWithRetry: 2xx body with no verdict field -> not ok", r.ok, false);
  expectTrue("  ...error says so", r.error.includes("verdict"), r.error);
}
{
  const fetchImpl = async () => ({ ok: true, status: 200, json: async () => { throw new Error("bad json"); } });
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, { fetchImpl, maxRetries: 0 });
  expect("fetchJsonWithRetry: unparsable JSON body -> not ok", r.ok, false);
  expectTrue("  ...error mentions the parse failure", r.error.includes("unparsable"), r.error);
}
{
  let calls = 0;
  const fetchImpl = async () => { calls += 1; throw new Error("x"); };
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, { fetchImpl, maxRetries: 0, sleepImpl: async () => {} });
  expect("fetchJsonWithRetry: maxRetries=0 -> exactly one attempt, no retry", calls, 1);
  expect("  ...still fails cleanly", r.ok, false);
}
{
  // A hung request (never settles) must still resolve, bounded by the
  // client-side timeout, even if the fetch implementation ignores the
  // AbortSignal entirely — see sweep_durability.mjs's fetchOnce() comment
  // for why this is a Promise.race, not a bare AbortSignal.timeout().
  const fetchImpl = () => new Promise(() => {}); // never resolves, ignores signal
  const t0 = Date.now();
  const r = await fetchJsonWithRetry("http://x/run-test", { index: 0 }, {
    fetchImpl, maxRetries: 0, timeoutMs: 60,
  });
  const elapsedMs = Date.now() - t0;
  expect("fetchJsonWithRetry: a hang that ignores AbortSignal still fails", r.ok, false);
  expectTrue("  ...bounded by the timeout, not left hanging", elapsedMs < 2000, `took ${elapsedMs}ms`);
  expectTrue("  ...error names it a timeout", r.error.includes("timeout"), r.error);
}

// --- ReplicaLog: incremental, flushed durability (R23) ----------------------
{
  const path = join(TMP, "replica.ndjson");
  const log = new ReplicaLog(path, { flushEvery: 3 });
  log.append({ a: 1 });
  log.append({ a: 2 });
  expectTrue("ReplicaLog: nothing flushed before flushEvery is reached", !existsSync(path) || readFileSync(path, "utf8") === "", "file has content early");
  log.append({ a: 3 }); // hits flushEvery=3
  let lines = readFileSync(path, "utf8").trim().split("\n").filter(Boolean);
  expect("ReplicaLog: auto-flush at flushEvery writes exactly the batch", lines.length, 3);
  log.append({ a: 4 });
  expect("ReplicaLog: a partial batch is NOT written until flush()", readFileSync(path, "utf8").trim().split("\n").filter(Boolean).length, 3);
  log.flush();
  lines = readFileSync(path, "utf8").trim().split("\n").filter(Boolean);
  expect("ReplicaLog: flush() writes the remaining partial batch", lines.length, 4);
  expect("ReplicaLog: each line is independently valid JSON", lines.map((l) => JSON.parse(l).a), [1, 2, 3, 4]);
}
{
  const path = join(TMP, "replica_truncate.ndjson");
  writeFileSync(path, "STALE CONTENT FROM A PREVIOUS RUN\n");
  new ReplicaLog(path, { flushEvery: 1 });
  expect("ReplicaLog: constructing truncates any stale file at the same path", readFileSync(path, "utf8"), "");
}
{
  const log = new ReplicaLog(null);
  expectTrue("ReplicaLog: a null path is a safe no-op (append)", (() => { log.append({ a: 1 }); return true; })());
  expectTrue("ReplicaLog: a null path is a safe no-op (flush)", (() => { log.flush(); return true; })());
}

// --- writeReplicatedSummary / writeDeadLetter --------------------------------
{
  const primary = join(TMP, "summary.json");
  const replica = join(TMP, "summary.replica.json");
  writeReplicatedSummary(primary, replica, { ok: true, n: 42 });
  const p = readFileSync(primary, "utf8");
  const r = readFileSync(replica, "utf8");
  expect("writeReplicatedSummary: primary and replica are byte-identical", p, r);
  expectTrue("  ...content round-trips", JSON.parse(p).n === 42);
}
{
  // Same path for both: must not error, and must not double-write garbage.
  const path = join(TMP, "summary_same.json");
  writeReplicatedSummary(path, path, { ok: true });
  expect("writeReplicatedSummary: primary === replica path is a safe no-op for the second write", JSON.parse(readFileSync(path, "utf8")).ok, true);
}
{
  const path = join(TMP, "deadletter.json");
  writeDeadLetter(path, {
    deliveryFailed: [{ key: "drc#5", message: "boom" }],
    missing: [{ key: "drc#9" }],
    conflicts: [],
  });
  const dl = JSON.parse(readFileSync(path, "utf8"));
  expect("writeDeadLetter: total sums the three categories", dl.total, 2);
  expect("writeDeadLetter: delivery_failed entries preserved", dl.delivery_failed.length, 1);
  expect("writeDeadLetter: missing_from_ledger entries preserved", dl.missing_from_ledger.length, 1);
}
{
  const before = existsSync(join(TMP, "should_not_exist.json"));
  writeDeadLetter(null, { deliveryFailed: [], missing: [], conflicts: [] });
  expect("writeDeadLetter: a null path writes nothing (no throw)", before, false);
}

// ===========================================================================
// FAULT — sweep_multi_worker.mjs as a real subprocess, fetch faulted.
// ===========================================================================
console.log("\nFAULT: sweep_multi_worker.mjs against a fixture topology, fetch faulted");

/**
 * A small fixture topology: two tiers, three families, 18 tests total.
 * Deliberately NOT the committed wasm_tier_topology.json (4500+ tests) —
 * this exercises the same code path at a size that keeps each fault-
 * injection case fast and its expected counts easy to verify by hand.
 */
const FIXTURE_TOPOLOGY = {
  base_domain: "fixture.invalid",
  abi_version: 1,
  tiers: [
    {
      crate: "fixture-alpha",
      cargo_features: "fixture",
      staged_module: "fixture_alpha.wasm",
      full_corpus_worker: "fixture-worker-alpha-full",
      wrangler_dir: "tools/wasm/__fixture_alpha__",
      expected_failures: "tools/wasm/__fixture_none__.json",
      shards: [
        { family: "alpha1", worker: "fixture-worker-alpha1", cargo_features: "fixture", staged_module: "fixture_alpha1.wasm", wrangler_dir: "tools/wasm/__fixture_alpha1__" },
        { family: "alpha2", worker: "fixture-worker-alpha2", cargo_features: "fixture", staged_module: "fixture_alpha2.wasm", wrangler_dir: "tools/wasm/__fixture_alpha2__" },
      ],
    },
    {
      crate: "fixture-beta",
      cargo_features: "fixture",
      staged_module: "fixture_beta.wasm",
      full_corpus_worker: "fixture-worker-beta1",
      wrangler_dir: "tools/wasm/__fixture_beta1__",
      expected_failures: "tools/wasm/__fixture_none__.json",
      shards: [
        { family: "beta1", worker: "fixture-worker-beta1", cargo_features: "fixture", staged_module: "fixture_beta.wasm", wrangler_dir: "tools/wasm/__fixture_beta1__" },
      ],
    },
  ],
};
const TOPOLOGY_PATH = join(TMP, "fixture_topology.json");
writeFileSync(TOPOLOGY_PATH, JSON.stringify(FIXTURE_TOPOLOGY, null, 2));

// alpha1: 6 tests, alpha2: 4 tests, beta1: 8 tests -> 18 total.
const FIXTURE_CENSUS = {
  "fixture-worker-alpha1": { family: "alpha1", count: 6, abi_version: 1 },
  "fixture-worker-alpha2": { family: "alpha2", count: 4, abi_version: 1 },
  "fixture-worker-beta1": { family: "beta1", count: 8, abi_version: 1 },
};
const TOTAL = 18;

/**
 * Fetch stub, imported via `--import` (same mechanism
 * test_check_deployed_freshness.mjs uses). Reads FAKE_CENSUS (worker ->
 * {family, count, abi_version}) and FAKE_FAULTS (workKey -> fault spec) from
 * the environment and answers `/health` and `/run-test` accordingly. This is
 * the ONLY thing substituted — sweep_multi_worker.mjs's argument parsing,
 * retry logic, ledger, reconciliation and file writes all run for real.
 */
const STUB = join(TMP, "fetch_stub.mjs");
writeFileSync(
  STUB,
  `const CENSUS = JSON.parse(process.env.FAKE_CENSUS);
const FAULTS = JSON.parse(process.env.FAKE_FAULTS || "{}");
const REQUIRED_CAPABILITY = process.env.REQUIRE_CAPABILITY || null;
const attempts = new Map();

globalThis.fetch = async (url, init) => {
  if (REQUIRED_CAPABILITY && init?.headers?.["x-temper-preview-capability"] !== REQUIRED_CAPABILITY) {
    return new Response(JSON.stringify({ error: "capability denied" }), { status: 403 });
  }
  const u = new URL(url);
  const script = u.hostname.split(".")[0];
  const entry = CENSUS[script];
  if (!entry) {
    return new Response(JSON.stringify({ error: "unknown script " + script }), { status: 404 });
  }
  if (u.pathname === "/health") {
    return new Response(
      JSON.stringify({ status: "ok", test_count: entry.count, abi_version: entry.abi_version }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
  if (u.pathname === "/run-test") {
    const body = init && init.body ? JSON.parse(init.body) : {};
    const index = body.index;
    const family = entry.family;
    const key = family + "#" + index;
    const n = (attempts.get(key) ?? 0) + 1;
    attempts.set(key, n);
    const spec = FAULTS[key];

    if (spec) {
      if (spec.type === "always-fail") {
        throw new Error("simulated permanent network fault (attempt " + n + ")");
      }
      if (spec.type === "hang") {
        return new Promise(() => {}); // never resolves; client-side timeout must bound this
      }
      if (spec.type === "transient-then-ok" && n <= (spec.failCount ?? 1)) {
        throw new Error("simulated transient network fault (attempt " + n + ")");
      }
      if (spec.type === "http-500") {
        return new Response(JSON.stringify({ status: "error", message: "boom" }), {
          status: 500,
          headers: { "content-type": "application/json" },
        });
      }
    }
    return new Response(
      JSON.stringify({ verdict: "pass", index, name: family + "::test_" + index, message: null, abi_version: 1, ms: 1, family }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
  return new Response("not found", { status: 404 });
};
`,
);

function runSweep(extraArgs, { census = FIXTURE_CENSUS, faults = {}, env = {} } = {}) {
  const args = ["--import", STUB, SWEEPER, "--topology", TOPOLOGY_PATH];
  if (!extraArgs.includes("--concurrency")) args.push("--concurrency", "8");
  args.push(...extraArgs);
  const res = spawnSync(
    process.execPath,
    args,
    {
      env: { ...process.env, FAKE_CENSUS: JSON.stringify(census), FAKE_FAULTS: JSON.stringify(faults), ...env },
      encoding: "utf8",
      timeout: 30000,
    },
  );
  let summary = null;
  try {
    summary = JSON.parse(res.stdout);
  } catch {
    // some cases (reconciliation-level exit 2 paths) still print valid JSON;
    // leave summary null if parsing genuinely fails and let the case's own
    // assertions on res.status/res.stderr carry it.
  }
  return { code: res.status, out: `${res.stdout}\n${res.stderr}`, summary };
}

console.log("\nPREVIEW: explicit immutable URL, capability, and budgets");
{
  const previewService = "fixture-worker-beta1";
  const previewUrl = `https://12345678-${previewService}.fixture.workers.dev`;
  const previewCensus = {
    [`12345678-${previewService}`]: FIXTURE_CENSUS[previewService],
  };
  const ok = runSweep(
    ["--tier", "fixture-beta", "--preview-url", previewUrl, "--warmup", "--json", join(TMP, "preview.json")],
    { census: previewCensus, env: { TEMPER_PREVIEW_CAPABILITY: "cap", REQUIRE_CAPABILITY: "cap" } },
  );
  expect("immutable preview sweep exits 0", ok.code, 0);
  expect("preview URL is recorded", ok.summary?.preview_url, previewUrl);
  const missing = runSweep(
    ["--tier", "fixture-beta", "--preview-url", previewUrl],
    { census: previewCensus },
  );
  expectTrue("missing capability fails closed", missing.code !== 0);
  const alias = runSweep(["--tier", "fixture-beta", "--preview-url", `https://${previewService}.fixture.workers.dev`]);
  expectTrue("mutable production URL is rejected", alias.code !== 0);
  const overConcurrency = runSweep(["--tier", "fixture-beta", "--concurrency", "65"]);
  expectTrue("concurrency over budget is rejected", overConcurrency.code !== 0);
  const largeProduction = runSweep(["--tier", "fixture-beta"], {
    census: { [previewService]: { ...FIXTURE_CENSUS[previewService], count: 10_001 } },
  });
  expect("the preview census ceiling does not regress deployed mode", largeProduction.code, 0);
}

// ---------------------------------------------------------------------------
// F1. Green path: without this, the rest of the file could be satisfied by a
//     sweep that always fails.
// ---------------------------------------------------------------------------
console.log("\nF1. clean sweep, no faults -> exit 0, everything accounted for");
{
  const jsonOut = join(TMP, "f1_summary.json");
  const r = runSweep(["--json", jsonOut]);
  expect("clean sweep exits 0", r.code, 0);
  expectTrue("all 18 dispatched", r.summary?.durability?.dispatched === TOTAL, JSON.stringify(r.summary?.durability));
  expectTrue("all 18 accounted for", r.summary?.durability?.accounted_for === TOTAL);
  expect("reconciliation_ok", r.summary?.durability?.reconciliation_ok, true);
  expect("no dead letters", r.summary?.durability?.dead_letter_count, 0);
  expect("tally.pass == total", r.summary?.tally?.pass, TOTAL);
}

// ---------------------------------------------------------------------------
// F2. THE CENTRAL CLAIM: a single request permanently lost to a "network
//     fault" (all retries exhausted) must NOT be silently absorbed into a
//     green result over the rest of the corpus. This is the exact failure
//     mode named in this task: "3 of 27,000 lost, harness reports PASS on
//     the 26,997 it heard back from."
// ---------------------------------------------------------------------------
console.log("\nF2. one request permanently lost -> loud failure, not a silent PASS");
{
  const jsonOut = join(TMP, "f2_summary.json");
  const deadLetterPath = join(TMP, "f2_dead_letter.json");
  const r = runSweep(["--json", jsonOut, "--dead-letter-json", deadLetterPath, "--max-retries", "2", "--retry-backoff-ms", "5"], {
    faults: { "alpha1#3": { type: "always-fail" } },
  });
  expect("sweep with one permanently-lost test exits nonzero", r.code !== 0, true);
  expectTrue("NOT exit 0 (would be the false-green failure mode)", r.code !== 0, `exit code was ${r.code}`);
  expect("reconciliation still OK (the loss was accounted-for, not missing)", r.summary?.durability?.reconciliation_ok, true);
  expect("dispatched == accounted_for == 18, never fewer", r.summary?.durability?.accounted_for, TOTAL);
  expect("exactly one dead letter", r.summary?.durability?.dead_letter_count, 1);
  expect("tally shows the loss as an explicit error, not an omission", r.summary?.tally?.error, 1);
  expect("the other 17 tests still passed", r.summary?.tally?.pass, TOTAL - 1);
  expectTrue("total tally sums to 18, not 17", Object.values(r.summary?.tally ?? {}).reduce((a, b) => a + b, 0) === TOTAL);

  const dl = JSON.parse(readFileSync(deadLetterPath, "utf8"));
  expect("dead-letter file names exactly the lost test", dl.delivery_failed.map((d) => d.key), ["alpha1#3"]);
  expectTrue("dead-letter file is recoverable (names family+index)", dl.delivery_failed[0].family === "alpha1" && dl.delivery_failed[0].index === 3);
}

// ---------------------------------------------------------------------------
// F3. Multiple losses scattered across different families in the same
//     sweep — proves the accounting holds per-family, not just in aggregate,
//     and scales past a single lost test.
// ---------------------------------------------------------------------------
console.log("\nF3. three requests lost across three different families -> all three caught");
{
  const jsonOut = join(TMP, "f3_summary.json");
  const deadLetterPath = join(TMP, "f3_dead_letter.json");
  const r = runSweep(["--json", jsonOut, "--dead-letter-json", deadLetterPath, "--max-retries", "1", "--retry-backoff-ms", "5"], {
    faults: {
      "alpha1#0": { type: "always-fail" },
      "alpha2#2": { type: "always-fail" },
      "beta1#7": { type: "always-fail" },
    },
  });
  expect("exits nonzero", r.code !== 0, true);
  expect("all 18 still accounted for", r.summary?.durability?.accounted_for, TOTAL);
  expect("reconciliation still OK", r.summary?.durability?.reconciliation_ok, true);
  expect("exactly 3 dead letters", r.summary?.durability?.dead_letter_count, 3);
  expect("tally: 3 errors, 15 passes, sums to 18", [r.summary?.tally?.error, r.summary?.tally?.pass], [3, 15]);
  const dl = JSON.parse(readFileSync(deadLetterPath, "utf8"));
  expect(
    "dead-letter names exactly the three lost tests",
    dl.delivery_failed.map((d) => d.key).sort(),
    ["alpha1#0", "alpha2#2", "beta1#7"],
  );
}

// ---------------------------------------------------------------------------
// F4. A TRANSIENT fault (one failed attempt, then success) must be RESCUED
//     by the retry — proving retries do real work, not just that failures
//     get recorded.
// ---------------------------------------------------------------------------
console.log("\nF4. transient fault recovers within the retry budget -> clean pass, no dead letter");
{
  const jsonOut = join(TMP, "f4_summary.json");
  const r = runSweep(["--json", jsonOut, "--max-retries", "2", "--retry-backoff-ms", "5"], {
    faults: { "beta1#1": { type: "transient-then-ok", failCount: 1 } },
  });
  expect("sweep exits 0 (the retry rescued the transient fault)", r.code, 0);
  expect("no dead letters", r.summary?.durability?.dead_letter_count, 0);
  expect("tally.pass == total (the rescued test still counts as a pass)", r.summary?.tally?.pass, TOTAL);
}

// ---------------------------------------------------------------------------
// F5. A HUNG response (never resolves) must not hang the sweep forever — the
//     client-side timeout bounds it, and after retries it is dead-lettered
//     like any other undeliverable request.
// ---------------------------------------------------------------------------
console.log("\nF5. a response that never arrives -> bounded by timeout, dead-lettered, not an infinite hang");
{
  const jsonOut = join(TMP, "f5_summary.json");
  const t0 = Date.now();
  const r = runSweep(
    ["--json", jsonOut, "--request-timeout-ms", "80", "--max-retries", "1", "--retry-backoff-ms", "5"],
    { faults: { "alpha2#0": { type: "hang" } } },
  );
  const elapsedMs = Date.now() - t0;
  expect("sweep exits nonzero", r.code !== 0, true);
  expectTrue("sweep terminates in bounded time, not hung forever", elapsedMs < 15000, `took ${elapsedMs}ms`);
  expect("the hung test is accounted for (errored), not missing", r.summary?.durability?.accounted_for, TOTAL);
  expect("exactly one dead letter (the hung test)", r.summary?.durability?.dead_letter_count, 1);
}

// ---------------------------------------------------------------------------
// F6. An entire family permanently unreachable — every test in it lost.
//     Proves accounting holds even when the loss is concentrated, not just
//     when it is one test scattered among many healthy ones.
// ---------------------------------------------------------------------------
console.log("\nF6. an entire family (alpha2, 4 tests) is permanently unreachable");
{
  const jsonOut = join(TMP, "f6_summary.json");
  const faults = {};
  for (let i = 0; i < 4; i += 1) faults[`alpha2#${i}`] = { type: "always-fail" };
  const r = runSweep(["--json", jsonOut, "--max-retries", "0", "--retry-backoff-ms", "1"], { faults });
  expect("exits nonzero", r.code !== 0, true);
  expect("all 18 still accounted for (none silently dropped)", r.summary?.durability?.accounted_for, TOTAL);
  expect("dead-letter count == 4 (the whole family)", r.summary?.durability?.dead_letter_count, 4);
  expect("per-family breakdown: alpha2 is 4 errors, 0 passes", r.summary?.per_family?.alpha2, { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 4, other: 0 });
  expect("per-family breakdown: alpha1 (unaffected) is still 6 passes", r.summary?.per_family?.alpha1?.pass, 6);
  expect("per-family breakdown: beta1 (unaffected) is still 8 passes", r.summary?.per_family?.beta1?.pass, 8);
}

// ---------------------------------------------------------------------------
// F7. --max-retries 0: a single transient fault gets no rescue, so it must
//     be dead-lettered on the first miss rather than silently tolerated.
// ---------------------------------------------------------------------------
console.log("\nF7. --max-retries 0 gives a transient fault no rescue -> dead-lettered immediately");
{
  const jsonOut = join(TMP, "f7_summary.json");
  const deadLetterPath = join(TMP, "f7_dead_letter.json");
  const r = runSweep(["--json", jsonOut, "--dead-letter-json", deadLetterPath, "--max-retries", "0"], {
    faults: { "beta1#4": { type: "transient-then-ok", failCount: 1 } },
  });
  expect("exits nonzero", r.code !== 0, true);
  expect("exactly one dead letter", r.summary?.durability?.dead_letter_count, 1);
  const dl = JSON.parse(readFileSync(deadLetterPath, "utf8"));
  expect("dead-lettered after exactly 1 attempt (no retry budget)", dl.delivery_failed[0].attempts, 1);
}

// ---------------------------------------------------------------------------
// F8. Durability is ON BY DEFAULT the moment --json is passed — no extra
//     flag required. This is what makes the two existing CI callers
//     (wasm-tier-nightly.yml, wasm-tier-pr.yml) get R22/R23 for free without
//     a workflow edit (out of scope for this change — see the boundary in
//     the plan this work answers).
// ---------------------------------------------------------------------------
console.log("\nF8. durability outputs are derived automatically from --json, no extra flags");
{
  const jsonOut = join(TMP, "f8_summary.json");
  const r = runSweep(["--json", jsonOut, "--max-retries", "1", "--retry-backoff-ms", "5"], {
    faults: { "alpha1#5": { type: "always-fail" } },
  });
  expect("exits nonzero", r.code !== 0, true);
  const expectedDeadLetter = `${jsonOut}.dead-letter.json`;
  const expectedReplicaJson = `${jsonOut}.replica.json`;
  const expectedReplicaLog = `${jsonOut}.replica.ndjson`;
  expectTrue("default dead-letter file exists without --dead-letter-json", existsSync(expectedDeadLetter));
  expectTrue("default replica JSON exists without --replica-json", existsSync(expectedReplicaJson));
  expectTrue("default replica NDJSON log exists without --replica-log", existsSync(expectedReplicaLog));

  // R23: the replica is a genuine second copy, not a stub — same content as
  // the primary, on-disk independently of it.
  const primary = readFileSync(jsonOut, "utf8");
  const replica = readFileSync(expectedReplicaJson, "utf8");
  expect("replica JSON is byte-identical to the primary", replica, primary);

  const dl = JSON.parse(readFileSync(expectedDeadLetter, "utf8"));
  expect("default dead-letter file has the right content", dl.delivery_failed.map((d) => d.key), ["alpha1#5"]);

  const ndjsonLines = readFileSync(expectedReplicaLog, "utf8").trim().split("\n").filter(Boolean);
  expect("replica NDJSON log has one line per accounted-for result", ndjsonLines.length, TOTAL);
  const parsedKeys = ndjsonLines.map((l) => JSON.parse(l).key).sort();
  const expectedKeys = [];
  for (let i = 0; i < 6; i += 1) expectedKeys.push(`alpha1#${i}`);
  for (let i = 0; i < 4; i += 1) expectedKeys.push(`alpha2#${i}`);
  for (let i = 0; i < 8; i += 1) expectedKeys.push(`beta1#${i}`);
  expect("replica NDJSON log covers exactly the dispatched keys, once each", parsedKeys, expectedKeys.sort());
}

// ---------------------------------------------------------------------------
// F9. The dead-letter file must be genuinely RECOVERABLE, not just
//     descriptive: replay exactly the lost keys via --only and confirm the
//     recovery loop actually closes. This is the concrete form of R22's
//     "lands somewhere recoverable" — a file nobody can act on is not
//     dead-letter handling, it is a log message with extra steps.
// ---------------------------------------------------------------------------
console.log("\nF9. dead-letter recovery loop: --only replays exactly the lost keys");
{
  const jsonOut = join(TMP, "f9_initial.json");
  const deadLetterPath = join(TMP, "f9_dead_letter.json");
  const initial = runSweep(
    ["--json", jsonOut, "--dead-letter-json", deadLetterPath, "--max-retries", "0", "--retry-backoff-ms", "1"],
    { faults: { "beta1#2": { type: "always-fail" }, "alpha1#4": { type: "always-fail" } } },
  );
  expect("initial sweep exits nonzero (2 lost)", initial.code !== 0, true);
  expect("initial sweep dead-letters exactly the 2 lost tests", initial.summary?.durability?.dead_letter_count, 2);

  const dl = JSON.parse(readFileSync(deadLetterPath, "utf8"));
  const lostKeys = dl.delivery_failed.map((d) => d.key).sort();
  expect("dead-letter file names the 2 lost keys", lostKeys, ["alpha1#4", "beta1#2"]);

  // Recovery run: the transient fault has since cleared (no faults injected
  // this time), and --only replays PRECISELY the dead-lettered keys — not
  // the other 16 tests, which already have a good verdict from the initial
  // run and should not be re-dispatched.
  const recoveryJson = join(TMP, "f9_recovery.json");
  const recovery = runSweep(["--json", recoveryJson, "--only", lostKeys.join(",")], { faults: {} });
  expect("recovery sweep exits 0 (the fault has cleared)", recovery.code, 0);
  expect("recovery sweep dispatches ONLY the 2 replayed keys, not all 18", recovery.summary?.dispatched_total, 2);
  expect("recovery sweep's durability.dispatched matches the replay size", recovery.summary?.durability?.dispatched, 2);
  expect("both replayed tests now pass", recovery.summary?.tally?.pass, 2);
  const recoveredKeys = recovery.summary?.results?.map((r) => `${r.family}#${r.index}`).sort();
  expect("the exact keys replayed are the exact keys that were lost", recoveredKeys, lostKeys);
}
{
  // --only naming a key that does not exist in this tier's census (e.g. a
  // stale dead-letter file from a different tier, or a typo) must fail
  // loudly rather than silently replaying nothing or a wrong subset.
  const r = runSweep(["--json", join(TMP, "f9_bad_only.json"), "--only", "nonexistent-family#999"], {});
  expect("--only with an unknown key exits nonzero (usage error)", r.code !== 0, true);
  expectTrue("  ...names the unknown key", r.out.includes("nonexistent-family#999"), r.out.slice(-400));
}

console.log(
  failures === 0
    ? "\nAll cases passed: the sweep accounts for every dispatched test under a lost response, a " +
        "duplicate/conflicting delivery, a hung response, a transient fault, and a partial outage — " +
        "and reports it, rather than reporting green on an incomplete corpus."
    : `\n${failures} case(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
