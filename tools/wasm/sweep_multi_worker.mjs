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
 *     [--board-sha256 <hex>] [--warmup]
 *
 * Worker inventory (deployed 2026-08-07, Phase 1 U8 multi-worker):
 *   drc       https://temper-wasm-drc.bennetleff.workers.dev       1 test    77 KB
 *   emc       https://temper-wasm-emc.bennetleff.workers.dev      14 tests  120 KB
 *   erc       https://temper-wasm-erc.bennetleff.workers.dev       9 tests   51 KB
 *   safety    https://temper-wasm-safety.bennetleff.workers.dev    0 tests   17 KB
 *   placement https://temper-wasm-placement.bennetleff.workers.dev 12 tests   83 KB
 *   routing   https://temper-wasm-routing.bennetleff.workers.dev   2 tests   41 KB
 *   infra     https://temper-wasm-infra.bennetleff.workers.dev   109 tests 1197 KB
 */

const BASE_DOMAIN = "bennetleff.workers.dev";
const FAMILIES = ["drc", "emc", "erc", "safety", "placement", "routing", "infra"];

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}
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
  for (const fam of FAMILIES) {
    workerUrls[fam] = `https://temper-wasm-${fam}.${BASE_DOMAIN}`;
  }

  // Phase 1: fetch health from each family to discover test counts.
  const families = {};
  let total = 0;
  console.error("=== Family census ===");
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
