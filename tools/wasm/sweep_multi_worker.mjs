#!/usr/bin/env node
/**
 * Sweep ALL per-family WASM tier Workers concurrently — separate Cloudflare
 * scripts route to separate isolates, so the platform can parallelize
 * across families.
 *
 * Unlike `sweep_worker.mjs` which sends every request to a single Worker
 * (serialized per-isolate), this client fans out to N distinct Workers,
 * each serving one family.  The sweep fires per-test invocations across
 * all families concurrently with a bounded-concurrency pool, measuring
 * true end-to-end parallel wall time.
 *
 * Usage:
 *   node tools/wasm/sweep_multi_worker.mjs [--concurrency 64] [--json out.json]
 *     [--board-sha256 <hex>] [--warmup] [--tier temper-drc-rs]
 *     [--request-timeout-ms 20000] [--max-retries 2] [--retry-backoff-ms 200]
 *     [--dead-letter-json path] [--replica-json path] [--replica-log path]
 *     [--replica-flush-every 25] [--topology path]
 *
 * The Worker inventory is NOT hardcoded here: it is read from
 * tools/wasm/wasm_tier_topology.json, the same file the staging script, the
 * deploy workflow and the freshness checker read, so a Worker cannot be swept
 * without also being built, deployed and checked. `--topology` overrides that
 * path — used by tools/wasm/test_sweep_durability.mjs to point this script at
 * a small fixture topology instead of the real 3000+-test one, so fault
 * injection cases run in milliseconds; production callers never pass it.
 *
 * ## --tier, and why the default is not what CI should use
 *
 * The tier carries nine crates (temper-drc-rs, temper-geometry, temper-thermal,
 * temper-design-bundle, temper-rust-router-core, temper-constraint-compiler,
 * temper-quality-oracle, temper-io-types and temper-pcl-ir) across 16 shard
 * Workers. With no `--tier` this sweeps every shard of every tier, which is
 * the right thing for an ad-hoc "is the whole thing up?" run and the wrong
 * thing for R19: the output feeds tools/wasm/r19_compare.py, which joins
 * wasm32 verdicts against ONE `cargo test` invocation's verdicts by test
 * name. Handing it a sweep that mixes crates would leave the other crates'
 * tests as `wasm32_only` -- counted nowhere, failing nothing, which is
 * precisely the "reports green over a corpus nobody compared" failure this tier
 * exists to rule out, and at nine crates a merged sweep compared against
 * temper-drc-rs would absolve thousands of verdicts (the exact count moves
 * with each crate's own registry -- see tools/wasm/wasm_tier_topology.json's
 * own header for why an absolute total is not worth pinning here). So
 * wasm-tier-nightly.yml passes `--tier` explicitly, in a loop over the
 * topology, and compares each tier against its own crate's native run.
 *
 * ## Durability (R22/R23)
 *
 * See tools/wasm/sweep_durability.mjs's module header for the full design.
 * In one line: every dispatched (family, index) gets bounded retries on
 * delivery failure, an idempotent ledger so a retry cannot double-count or
 * silently overwrite a verdict, a reconciliation pass that fails the sweep
 * loudly if dispatched != accounted-for, a dead-letter file naming exactly
 * what to re-run, and a second on-disk copy of the results (plus an
 * incrementally-flushed NDJSON log) so a crash does not erase a completed
 * run. All of it is on by default the moment `--json` is passed — no new
 * flag is required for the two existing CI callers
 * (wasm-tier-nightly.yml, wasm-tier-pr.yml) to get it.
 */

import { loadTopology, tierByCrate, workerUrl } from "./tier_topology.mjs";
import { PREVIEW_LIMITS, validateImmutablePreviewUrl } from "./preview_version.mjs";
import {
  workKey,
  ResultLedger,
  reconcile,
  fetchJsonWithRetry,
  ReplicaLog,
  writeReplicatedSummary,
  writeDeadLetter,
} from "./sweep_durability.mjs";

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}

const TOPOLOGY_ARG = arg("--topology", null);
const topology = TOPOLOGY_ARG ? loadTopology(TOPOLOGY_ARG) : loadTopology();
const BASE_DOMAIN = topology.base_domain;
const TIER_ARG = arg("--tier", null);
const SELECTED_TIERS = TIER_ARG ? [tierByCrate(topology, TIER_ARG)] : topology.tiers;
const PREVIEW_URL_ARG = arg("--preview-url", null);
const PREVIEW_CAPABILITY = PREVIEW_URL_ARG ? process.env.TEMPER_PREVIEW_CAPABILITY : null;
// Shards, deduplicated by family across the selected tiers. A family name is
// unique across the topology (validated in tier_topology.mjs), so the family
// remains a usable key in the per-family breakdown below.
const SHARDS = SELECTED_TIERS.flatMap((t) =>
  t.shards.map((s) => ({ ...s, crate: t.crate })),
);
const FAMILIES = SHARDS.map((s) => s.family);
const CONCURRENCY = parseInt(arg("--concurrency", "64"), 10);
const JSON_OUT = arg("--json", null);
const WARMUP = process.argv.includes("--warmup");
// R5 (goal-set plan): every finding names the exact artifact it came from by
// content hash. Optional -- the deployed Workers' tests are board-content-
// agnostic today (docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md's R5
// discussion), so this hash is not consumed by the test logic itself. It is
// carried in every dispatched request body (harmless: the Worker ignores
// unrecognized JSON fields, see packages/temper-worker/src/worker_core.js's
// `/run-test` handler) and echoed into every result and the summary, so a
// scheduled run's artifact is traceable to the exact pcb/temper.kicad_pcb
// bytes the sweep ran alongside, even though no single verdict depends on it.
const BOARD_SHA256 = arg("--board-sha256", null);

// --- R22/R23 durability knobs -----------------------------------------
const REQUEST_TIMEOUT_MS = parseInt(arg("--request-timeout-ms", "20000"), 10);
const MAX_RETRIES = parseInt(arg("--max-retries", "2"), 10);
const RETRY_BACKOFF_MS = Math.max(0, parseInt(arg("--retry-backoff-ms", "200"), 10));
const REPLICA_FLUSH_EVERY = Math.max(1, parseInt(arg("--replica-flush-every", "25"), 10));
// Defaults derived from --json so the two existing CI callers (which only
// ever pass --json) get durability outputs for free, with no workflow edit
// required. Explicit flags always win.
const DEAD_LETTER_JSON = arg("--dead-letter-json", JSON_OUT ? `${JSON_OUT}.dead-letter.json` : null);
const REPLICA_JSON = arg("--replica-json", JSON_OUT ? `${JSON_OUT}.replica.json` : null);
const REPLICA_LOG = arg("--replica-log", JSON_OUT ? `${JSON_OUT}.replica.ndjson` : null);
// A dead-letter file is only "somewhere recoverable" (R22) if something can
// actually replay it. --only takes a comma-separated list of workKey()s
// (family#index -- exactly the "key" field tools/wasm/sweep_durability.mjs's
// writeDeadLetter() writes into delivery_failed[]/missing_from_ledger[]), and
// restricts the work queue to just those, so:
//   node tools/wasm/sweep_multi_worker.mjs --tier <crate> \
//     --only "$(node -e '...' dead-letter.json)"
// re-dispatches precisely the lost tests instead of the whole corpus. See
// tools/wasm/test_sweep_durability.mjs's F9 case for this loop exercised
// end-to-end against an injected fault.
const ONLY_ARG = arg("--only", null);
const ONLY_KEYS = ONLY_ARG ? new Set(ONLY_ARG.split(",").map((s) => s.trim()).filter(Boolean)) : null;

function usageError(message) {
  console.error(`::error::${message}`);
  process.exit(2);
}

if (!Number.isSafeInteger(CONCURRENCY) || CONCURRENCY < 1 || CONCURRENCY > PREVIEW_LIMITS.concurrency) {
  usageError(`concurrency must be in [1, ${PREVIEW_LIMITS.concurrency}]`);
}
if (!Number.isSafeInteger(REQUEST_TIMEOUT_MS) || REQUEST_TIMEOUT_MS < 1 || REQUEST_TIMEOUT_MS > PREVIEW_LIMITS.requestTimeoutMs) {
  usageError(`request timeout must be in [1, ${PREVIEW_LIMITS.requestTimeoutMs}]ms`);
}
if (!Number.isSafeInteger(MAX_RETRIES) || MAX_RETRIES < 0 || MAX_RETRIES > PREVIEW_LIMITS.maxRetries) {
  usageError(`max retries must be in [0, ${PREVIEW_LIMITS.maxRetries}]`);
}
if (PREVIEW_URL_ARG) {
  if (!TIER_ARG || SELECTED_TIERS.length !== 1) usageError("--preview-url requires exactly one explicit --tier");
  const tier = SELECTED_TIERS[0];
  if (tier.shards.length !== 1 || tier.shards[0].worker !== tier.full_corpus_worker) {
    usageError("--preview-url is only valid for a single-Worker tier");
  }
  try { validateImmutablePreviewUrl(PREVIEW_URL_ARG, tier.full_corpus_worker); } catch (error) {
    usageError(error.message);
  }
  if (!PREVIEW_CAPABILITY) usageError("TEMPER_PREVIEW_CAPABILITY is required with --preview-url");
}

function previewHeaders() {
  return PREVIEW_URL_ARG ? { "x-temper-preview-capability": PREVIEW_CAPABILITY } : {};
}

function authenticatedFetch(url, init = {}) {
  return fetch(url, { ...init, headers: { ...(init.headers ?? {}), ...previewHeaders() } });
}

async function run() {
  const workerUrls = {};
  for (const shard of SHARDS) {
    workerUrls[shard.family] = PREVIEW_URL_ARG ?? workerUrl(topology, shard.worker);
  }

  // Phase 1: fetch health from each family to discover test counts.
  const families = {};
  let total = 0;
  console.error(
    `=== Family census (tiers: ${SELECTED_TIERS.map((t) => t.crate).join(", ")}) ===`,
  );
  for (const fam of FAMILIES) {
    try {
      const response = await authenticatedFetch(`${workerUrls[fam]}/health`, {
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const r = await response.json();
      const count = r.test_count ?? 0;
      families[fam] = { url: workerUrls[fam], count, abi_version: r.abi_version };
      console.error(`  ${fam}: ${count} tests (abi=${r.abi_version})`);
      total += count;
    } catch (e) {
      console.error(`  ${fam}: ERROR ${e.message}`);
      families[fam] = { url: workerUrls[fam], count: 0, error: e.message };
    }
  }
  console.error(`  total: ${total} tests across ${FAMILIES.length} families`);

  // A census failure used to be survivable here: an unreachable family got
  // `count: 0`, contributed no work items, and if that happened to every family
  // the work queue was empty, `failures` was empty, and this script exited 0
  // having dispatched nothing -- a green sweep over zero tests, which is the
  // exact failure mode the R5.1 staleness check was added to close one layer up.
  // wasm-tier-nightly.yml does run that check first, so this was latent rather
  // than live, but a tool must not depend on its caller to keep it honest.
  const censusErrors = Object.entries(families).filter(([, v]) => v.error);
  if (censusErrors.length) {
    console.error(
      `::error::Family census failed for: ${censusErrors.map(([f, v]) => `${f} (${v.error})`).join(", ")}. ` +
        "Those families' tests would silently contribute nothing to the tally below, so this " +
        "sweep FAILS rather than reporting a verdict for a corpus it could not enumerate.",
    );
    process.exit(2);
  }
  if (total === 0) {
    console.error(
      "::error::Every family reported 0 tests. A sweep of an empty corpus dispatches nothing and " +
        "would otherwise exit 0 with a clean tally — a green result for zero work. Check that the " +
        "deployed modules carry a registry (tools/wasm/check_deployed_freshness.mjs is the control " +
        "that compares their counts against the commit under test).",
    );
    process.exit(2);
  }
  if (PREVIEW_URL_ARG && total > PREVIEW_LIMITS.maxTests) {
    console.error(`::error::census ${total} exceeds the ${PREVIEW_LIMITS.maxTests}-test preview budget`);
    process.exit(2);
  }
  if (PREVIEW_URL_ARG && total * (MAX_RETRIES + 1) > PREVIEW_LIMITS.maxTests * (PREVIEW_LIMITS.maxRetries + 1)) {
    console.error("::error::the declared request and retry budget exceeds the preview maximum");
    process.exit(2);
  }

  if (WARMUP) {
    // One warm-up request per family to amortize cold-start.
    console.error("=== Warm-up (one request per family) ===");
    for (const fam of FAMILIES) {
      const r = await authenticatedFetch(`${workerUrls[fam]}/health`, {
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      console.error(`  ${fam}: ${r.status}`);
    }
  }

  // Phase 2: Build work queue — one entry per (family, index)
  let work = [];
  for (const [fam, info] of Object.entries(families)) {
    if (info.count === 0) continue;
    for (let i = 0; i < info.count; i++) {
      work.push({ family: fam, url: info.url, index: i, key: workKey(fam, i) });
    }
  }

  if (ONLY_KEYS) {
    const before = work.length;
    const fullWork = work;
    work = fullWork.filter((w) => ONLY_KEYS.has(w.key));
    const found = new Set(work.map((w) => w.key));
    const unknown = [...ONLY_KEYS].filter((k) => !found.has(k));
    if (unknown.length) {
      console.error(
        `::error::--only named ${unknown.length} key(s) not present in this tier's census (typo, or a ` +
          `dead-letter file from a different corpus/tier): ${unknown.join(", ")}. Refusing to silently ` +
          "run a partial replay of the wrong set.",
      );
      process.exit(2);
    }
    console.error(`--only: replaying ${work.length} of ${before} dispatched tests: ${[...ONLY_KEYS].join(", ")}`);
  }
  const dispatchedKeys = work.map((w) => w.key);
  // The count this RUN actually dispatches -- equal to `total` (the full
  // census) unless --only narrowed the queue to a replay subset. Used for
  // progress logging and throughput below so a --only replay of 1 test does
  // not report a throughput computed against the whole corpus's `total`.
  const dispatchedTotal = work.length;

  // Phase 3: Fan out with bounded concurrency. Results land in an idempotent
  // ledger (R22) keyed by (family, index), not a plain array — a retry whose
  // original attempt's response arrives late cannot inflate the tally or
  // silently clobber an already-recorded verdict with a different one (see
  // sweep_durability.mjs's ResultLedger).
  const ledger = new ResultLedger();
  const replicaLog = new ReplicaLog(REPLICA_LOG, { flushEvery: REPLICA_FLUSH_EVERY });
  const deadLetterEntries = [];
  let done = 0;
  const t0 = Date.now();

  async function runOne(task) {
    let body;
    let deliveryFailed = false;
    let attempts = 1;
    try {
      const delivered = await fetchJsonWithRetry(
        `${task.url}/run-test`,
        BOARD_SHA256 ? { index: task.index, boardSha256: BOARD_SHA256 } : { index: task.index },
        { fetchImpl: authenticatedFetch, timeoutMs: REQUEST_TIMEOUT_MS, maxRetries: MAX_RETRIES, backoffMs: RETRY_BACKOFF_MS },
      );
      attempts = delivered.attempts;
      if (delivered.ok) {
        body = delivered.body;
        body._family = task.family;
        body._status = 200;
      } else {
        // Dead-letter case (R22): every retry failed to deliver an
        // authoritative outcome. Still recorded as a terminal "error"
        // verdict -- accounted-for, never simply absent -- and separately
        // named in the dead-letter file so it can be re-run precisely.
        deliveryFailed = true;
        body = {
          verdict: "error",
          index: task.index,
          name: null,
          message: `delivery failed after ${attempts} attempt(s): ${delivered.error}`,
          _family: task.family,
          _status: 0,
        };
      }
    } catch (e) {
      // Belt-and-suspenders: fetchJsonWithRetry itself is fully guarded, but
      // if something outside it still throws (a bug, not a network fault),
      // this still records a terminal outcome rather than letting the work
      // item vanish from the ledger -- the case reconcile() exists to catch
      // if this guard is ever wrong.
      deliveryFailed = true;
      body = {
        verdict: "error",
        index: task.index,
        name: null,
        message: `unexpected failure in runOne: ${e.message || e}`,
        _family: task.family,
        _status: 0,
      };
    }

    const record = {
      index: body.index ?? task.index,
      name: body.name ?? null,
      status: body.verdict,
      family: task.family,
      raw: body,
    };
    const outcome = ledger.record(task.key, record);
    if (deliveryFailed && outcome !== "duplicate") {
      deadLetterEntries.push({
        key: task.key,
        family: task.family,
        index: task.index,
        attempts,
        message: body.message,
      });
    }
    if (outcome !== "duplicate") {
      replicaLog.append({ ts: new Date().toISOString(), key: task.key, outcome, ...record });
    }

    done += 1;
    if (done % 20 === 0) console.error(`  ${done}/${dispatchedTotal}`);
  }

  let cursor = 0;
  async function pump() {
    const tasks = [];
    while (cursor < work.length && tasks.length < CONCURRENCY) {
      tasks.push(runOne(work[cursor++]));
    }
    if (tasks.length) await Promise.all(tasks);
  }
  while (cursor < work.length) await pump();
  replicaLog.flush();

  const wallMs = Date.now() - t0;
  const wallSec = (wallMs / 1000).toFixed(2);

  // ---------------------------------------------------------------------
  // Reconciliation pass (R22): dispatched == accounted-for, checked, not
  // assumed. Under this file's retry/dead-letter design `missing` should
  // always be empty -- every code path that can fail to deliver still
  // records a terminal "error" outcome -- so a non-empty result here means
  // that guarantee broke somewhere, and the sweep must not report a verdict
  // for a corpus it cannot account for in full. A conflicting verdict for
  // the same (family, index) is the same class of problem: the tally can no
  // longer be trusted to mean what it claims.
  // ---------------------------------------------------------------------
  const missing = reconcile(dispatchedKeys, ledger);
  const conflicts = ledger.conflicts;
  const reconciliationOk = missing.length === 0 && conflicts.length === 0;

  if (missing.length) {
    console.error(
      `::error::RECONCILIATION FAILURE: ${missing.length} of ${dispatchedKeys.length} dispatched ` +
        `test(s) have NO recorded outcome at all: ${missing.slice(0, 10).join(", ")}` +
        `${missing.length > 10 ? ", ..." : ""}. This sweep dispatched requests it never accounted ` +
        "for -- pass, fail, or explicitly-errored -- and reporting a tally over the remainder would " +
        "be a false green over an incomplete corpus. FAILING rather than reporting on what happened " +
        "to arrive.",
    );
  }
  if (conflicts.length) {
    console.error(
      `::error::RECONCILIATION FAILURE: ${conflicts.length} test(s) received two DIFFERENT verdicts ` +
        `for the same (family, index): ${conflicts.slice(0, 5).map((c) => c.key).join(", ")}` +
        `${conflicts.length > 5 ? ", ..." : ""}. The tally cannot be trusted when a key resolves to ` +
        "more than one outcome. FAILING.",
    );
  }

  if (DEAD_LETTER_JSON) {
    writeDeadLetter(DEAD_LETTER_JSON, {
      deliveryFailed: deadLetterEntries,
      missing: missing.map((key) => ({ key })),
      conflicts,
    });
    if (deadLetterEntries.length || missing.length || conflicts.length) {
      console.error(
        `dead-letter: ${deadLetterEntries.length} delivery failure(s), ${missing.length} missing, ` +
          `${conflicts.length} conflict(s) written to ${DEAD_LETTER_JSON}`,
      );
    }
  }

  // Tally, from the idempotent ledger -- one entry per (family, index), so a
  // retry or a duplicate delivery cannot inflate any count here.
  const results = ledger.values();
  const tally = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
  const failures = [];
  for (const r of results) {
    const v = r.status;
    if (v in tally) tally[v] += 1;
    else { tally.other += 1; failures.push(r.raw); }
    if (v === "fail" || v === "error") failures.push(r.raw);
  }

  // Per-family breakdown
  const perFamily = {};
  for (const fam of FAMILIES) {
    perFamily[fam] = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
  }
  for (const r of results) {
    const fam = r.family || "?";
    if (!perFamily[fam]) perFamily[fam] = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
    const v = r.status;
    if (v in perFamily[fam]) perFamily[fam][v] += 1;
    else perFamily[fam].other += 1;
  }

  // Full per-test verdict list, in the {name, status} shape r19_compare.py's
  // --wasm-json consumes (same convention run_wasm_tests.mjs's --json output
  // already uses).
  const fullResults = results.map((r) => ({
    index: r.index,
    name: r.name,
    status: r.status,
    family: r.family,
  }));

  const summary = {
    mode: "multi-worker-parallel",
    tiers: SELECTED_TIERS.map((t) => t.crate),
    concurrency: CONCURRENCY,
    warmup: WARMUP,
    board_sha256: BOARD_SHA256,
    total,
    only: ONLY_KEYS ? [...ONLY_KEYS] : null,
    dispatched_total: dispatchedTotal,
    wall_ms: wallMs,
    wall_sec: wallSec,
    throughput_per_s: (dispatchedTotal / (wallMs / 1000)).toFixed(1),
    families: Object.fromEntries(
      Object.entries(families).map(([k, v]) => [k, v.count ?? v.error ?? "?"])
    ),
    tally,
    per_family: perFamily,
    results: fullResults,
    failures,
    worker_urls: workerUrls,
    preview_url: PREVIEW_URL_ARG,
    // R22/R23 durability report.
    durability: {
      dispatched: dispatchedKeys.length,
      accounted_for: ledger.size(),
      reconciliation_ok: reconciliationOk,
      missing,
      conflicts,
      duplicates_ignored: ledger.duplicatesIgnored,
      dead_letter_count: deadLetterEntries.length,
      dead_letter_json: DEAD_LETTER_JSON,
      replica_json: REPLICA_JSON,
      replica_log: REPLICA_LOG,
      request_timeout_ms: REQUEST_TIMEOUT_MS,
      max_retries: MAX_RETRIES,
    },
  };
  console.log(JSON.stringify(summary, null, 2));
  writeReplicatedSummary(JSON_OUT, REPLICA_JSON, summary);

  // Reconciliation failure is a harness-level failure -- distinct from (and
  // more severe than) a test genuinely failing, the same way an
  // unenumerable census is (see the exit(2) above): the sweep could not
  // establish what happened to every dispatched request, so it exits 2
  // rather than reporting a tally computed over an incomplete accounting.
  if (!reconciliationOk) process.exit(2);

  process.exit(failures.length ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
