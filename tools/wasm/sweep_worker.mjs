#!/usr/bin/env node
/**
 * Sweep the deployed per-family WASM tier Worker by sharding every
 * registered test to a separate concurrent invocation, distributed
 * across all family modules in parallel.
 *
 * The client fetches `/families` to discover family→test_count, then
 * fires all tests across all families concurrently (per-test
 * invocations, concurrency-bounded), collecting the aggregate suite
 * verdict.  Cloudflare parallelizes across functions, so the total
 * wall time should be bounded by the slowest family's serial+sweep
 * latency rather than the full 147-test serial wall time.
 *
 * Usage:
 *   node tools/wasm/sweep_worker.mjs [--base https://temper-wasm-tier.workers.dev]
 *                                    [--concurrency 64] [--json out.json]
 *
 * Verdicts: pass | expected-fail | fail | bad-index.  The Worker
 * reclassifies expected-fails against its bundled manifest, so a
 * "fail" here is a genuine divergence.
 */

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}
const BASE = arg("--base", "https://temper-wasm-tier.bennetleff.workers.dev");
const CONCURRENCY = Math.max(1, parseInt(arg("--concurrency", "64"), 10));
const JSON_OUT = arg("--json", null);

async function run() {
  // Phase 1: fetch family census from /families.
  const familiesResp = await (await fetch(`${BASE}/families`)).json();
  const families = familiesResp.families;
  if (!families || Object.keys(families).length === 0) {
    throw new Error(`/families returned empty: ${JSON.stringify(familiesResp)}`);
  }

  // Build the work queue: one entry per (family, index).
  // Skip the 'default' family — it is the full 147-test module present
  // for backward compat; the per-family sweep measures the sharded path.
  const work = [];
  let total = 0;
  for (const [fam, info] of Object.entries(families)) {
    if (fam === "default") continue;
    if (info.error) {
      console.error(`  WARNING: family ${fam} failed census: ${info.error}`);
      continue;
    }
    const count = info.test_count;
    for (let i = 0; i < count; i++) {
      work.push({ family: fam, index: i });
    }
    total += count;
    console.error(`  ${fam}: ${count} tests`);
  }
  console.error(`  total: ${total} tests across ${Object.keys(families).length} families`);

  const results = [];
  let done = 0;
  const t0 = Date.now();

  async function worker(task) {
    const r = await fetch(`${BASE}/run-test`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ family: task.family, index: task.index }),
    });
    const body = await r.json();
    results.push(body);
    done += 1;
    if (done % 50 === 0) console.error(`  ${done}/${total}`);
  }

  // Concurrency-bounded pool: launch up to CONCURRENCY at a time.
  let cursor = 0;
  async function pump() {
    const tasks = [];
    while (cursor < work.length && tasks.length < CONCURRENCY) {
      tasks.push(worker(work[cursor++]));
    }
    if (tasks.length) await Promise.all(tasks);
  }
  while (cursor < work.length) await pump();

  const wallMs = Date.now() - t0;
  const tally = { pass: 0, "expected-fail": 0, fail: 0, "bad-index": 0, other: 0 };
  const failures = [];
  for (const r of results) {
    const v = r.verdict;
    if (v in tally) tally[v] += 1; else tally.other += 1;
    if (v === "fail" || v === "bad-index" || v === "other") failures.push(r);
  }

  const summary = {
    base: BASE,
    mode: "per-family",
    concurrency: CONCURRENCY,
    total,
    wall_ms: wallMs,
    throughput_per_s: total / (wallMs / 1000),
    families: Object.fromEntries(
      Object.entries(families).map(([k, v]) => [k, v.test_count ?? v.error ?? "?"])
    ),
    tally,
    failures,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (JSON_OUT) (await import("node:fs")).writeFileSync(JSON_OUT, JSON.stringify(summary, null, 2));
  process.exit(failures.length ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
