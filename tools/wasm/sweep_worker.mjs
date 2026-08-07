#!/usr/bin/env node
// Sweep the deployed WASM tier Worker by sharding every registered test to a
// separate concurrent invocation (one test per Worker invocation per the R5/
// Q4 sharding design). Aggregates verdicts and reports the suite result.
//
// Usage:
//   node tools/wasm/sweep_worker.mjs [--base https://temper-wasm-tier.bennetleff.workers.dev]
//                                    [--concurrency 32] [--json out.json]
//
// Verdicts: pass | expected-fail | fail | bad-index. The Worker already
// reclassifies expected-fails against its bundled manifest, so a "fail" here
// is a genuine divergence.

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}
const BASE = arg("--base", "https://temper-wasm-tier.bennetleff.workers.dev");
const CONCURRENCY = Math.max(1, parseInt(arg("--concurrency", "32"), 10));
const JSON_OUT = arg("--json", null);

async function run() {
  // Census: test_count from /health.
  const health = await (await fetch(`${BASE}/health`)).json();
  const count = health.test_count;
  if (!count) throw new Error(`health did not return test_count: ${JSON.stringify(health)}`);

  const results = new Array(count);
  let done = 0;
  const t0 = Date.now();

  async function worker(i) {
    const r = await fetch(`${BASE}/run-test`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ index: i }),
    });
    const body = await r.json();
    results[i] = body;
    done += 1;
    if (done % 50 === 0) console.error(`  ${done}/${count}`);
  }

  // Simple concurrency-bounded pool: launch up to CONCURRENCY at a time.
  let cursor = 0;
  async function pump() {
    const tasks = [];
    while (cursor < count && tasks.length < CONCURRENCY) {
      const idx = cursor++;
      tasks.push(worker(idx));
    }
    if (tasks.length) await Promise.all(tasks);
  }
  while (cursor < count) await pump();

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
    concurrency: CONCURRENCY,
    total: count,
    wall_ms: wallMs,
    throughput_per_s: count / (wallMs / 1000),
    tally,
    failures,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (JSON_OUT) (await import("node:fs")).writeFileSync(JSON_OUT, JSON.stringify(summary, null, 2));
  process.exit(failures.length ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
