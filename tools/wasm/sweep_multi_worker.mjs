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
 *
 * The Worker inventory is NOT hardcoded here: it is read from
 * tools/wasm/wasm_tier_topology.json, the same file the staging script, the
 * deploy workflow and the freshness checker read, so a Worker cannot be swept
 * without also being built, deployed and checked.
 *
 * ## --tier, and why the default is not what CI should use
 *
 * The tier carries six crates (temper-drc-rs, temper-geometry, temper-thermal,
 * temper-design-bundle, temper-rust-router-core and temper-constraint-compiler)
 * across 12 shard Workers. With no `--tier` this sweeps every shard of every
 * tier, which is the right thing for an ad-hoc "is the whole thing up?" run and
 * the wrong thing for R19: the output feeds tools/wasm/r19_compare.py, which
 * joins wasm32 verdicts against ONE `cargo test` invocation's verdicts by test
 * name. Handing it a sweep that mixes crates would leave the other crates'
 * tests as `wasm32_only` -- counted nowhere, failing nothing, which is
 * precisely the "reports green over a corpus nobody compared" failure this tier
 * exists to rule out, and at six crates a merged sweep compared against
 * temper-drc-rs would absolve 1069 of 2788 verdicts. So wasm-tier-nightly.yml
 * passes `--tier` explicitly, in a loop over the topology, and compares each
 * tier against its own crate's native run.
 */

import { loadTopology, tierByCrate, workerUrl } from "./tier_topology.mjs";

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}

const topology = loadTopology();
const BASE_DOMAIN = topology.base_domain;
const TIER_ARG = arg("--tier", null);
const SELECTED_TIERS = TIER_ARG ? [tierByCrate(topology, TIER_ARG)] : topology.tiers;
// Shards, deduplicated by family across the selected tiers. A family name is
// unique across the topology (validated in tier_topology.mjs), so the family
// remains a usable key in the per-family breakdown below.
const SHARDS = SELECTED_TIERS.flatMap((t) =>
  t.shards.map((s) => ({ ...s, crate: t.crate })),
);
const FAMILIES = SHARDS.map((s) => s.family);
const CONCURRENCY = Math.max(1, parseInt(arg("--concurrency", "64"), 10));
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

async function run() {
  const workerUrls = {};
  for (const shard of SHARDS) {
    workerUrls[shard.family] = workerUrl(topology, shard.worker);
  }

  // Phase 1: fetch health from each family to discover test counts.
  const families = {};
  let total = 0;
  console.error(
    `=== Family census (tiers: ${SELECTED_TIERS.map((t) => t.crate).join(", ")}) ===`,
  );
  for (const fam of FAMILIES) {
    try {
      const r = await (await fetch(`${workerUrls[fam]}/health`)).json();
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

  if (WARMUP) {
    // One warm-up request per family to amortize cold-start.
    console.error("=== Warm-up (one request per family) ===");
    for (const fam of FAMILIES) {
      const r = await fetch(`${workerUrls[fam]}/health`);
      console.error(`  ${fam}: ${r.status}`);
    }
  }

  // Phase 2: Build work queue — one entry per (family, index)
  const work = [];
  for (const [fam, info] of Object.entries(families)) {
    if (info.count === 0) continue;
    for (let i = 0; i < info.count; i++) {
      work.push({ family: fam, url: info.url, index: i });
    }
  }

  // Phase 3: Fan out with bounded concurrency.
  const results = [];
  let done = 0;
  const t0 = Date.now();

  async function runOne(task) {
    let body;
    try {
      const r = await fetch(`${task.url}/run-test`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(
          BOARD_SHA256
            ? { index: task.index, boardSha256: BOARD_SHA256 }
            : { index: task.index },
        ),
      });
      body = await r.json();
      body._family = task.family;
      body._status = r.status;
    } catch (e) {
      body = {
        verdict: "error",
        index: task.index,
        name: null,
        message: e.message,
        _family: task.family,
        _status: 0,
      };
    }
    results.push(body);
    done += 1;
    if (done % 20 === 0) console.error(`  ${done}/${total}`);
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

  const wallMs = Date.now() - t0;
  const wallSec = (wallMs / 1000).toFixed(2);

  // Tally
  const tally = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
  const failures = [];
  for (const r of results) {
    const v = r.verdict;
    if (v in tally) tally[v] += 1;
    else { tally.other += 1; failures.push(r); }
    if (v === "fail" || v === "error") failures.push(r);
  }

  // Per-family breakdown
  const perFamily = {};
  for (const fam of FAMILIES) {
    perFamily[fam] = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
  }
  for (const r of results) {
    const fam = r._family || "?";
    if (!perFamily[fam]) perFamily[fam] = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, error: 0, other: 0 };
    const v = r.verdict;
    if (v in perFamily[fam]) perFamily[fam][v] += 1;
    else perFamily[fam].other += 1;
  }

  // Full per-test verdict list, in the {name, status} shape r19_compare.py's
  // --wasm-json consumes (same convention run_wasm_tests.mjs's --json output
  // already uses). "verdict" is renamed to "status" here to match that
  // schema; nothing upstream is renamed, so run_wasm_tests.mjs's own JSON
  // output is unaffected.
  const fullResults = results.map((r) => ({
    index: r.index,
    name: r.name,
    status: r.verdict,
    family: r._family,
  }));

  const summary = {
    mode: "multi-worker-parallel",
    tiers: SELECTED_TIERS.map((t) => t.crate),
    concurrency: CONCURRENCY,
    warmup: WARMUP,
    board_sha256: BOARD_SHA256,
    total,
    wall_ms: wallMs,
    wall_sec: wallSec,
    throughput_per_s: (total / (wallMs / 1000)).toFixed(1),
    families: Object.fromEntries(
      Object.entries(families).map(([k, v]) => [k, v.count ?? v.error ?? "?"])
    ),
    tally,
    per_family: perFamily,
    results: fullResults,
    failures,
    worker_urls: workerUrls,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (JSON_OUT) (await import("node:fs")).writeFileSync(JSON_OUT, JSON.stringify(summary, null, 2));

  process.exit(failures.length ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
