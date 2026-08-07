# Phase 1 U3 — Sharding design (Q4), measured locally

**Date:** 2026-08-07
**Commit:** `14979d633` (origin/main at measurement time)
**Runner:** `tools/wasm/run_wasm_tests.mjs --repeat K` (fresh module
instantiation per repetition, Node/V8 — the Phase 0-sanctioned workerd
substitution)
**Artifact:** `target-shared/wasm32-unknown-unknown/release/deps/temper_wasm_test_runner.wasm`

## The measurement

Full 95-test suite, `--repeat 1000` (91,000 test invocations):

| Metric | Value |
|---|---|
| Total wall | 30,274 ms |
| rep median | 27.13 ms |
| rep p95 | 46.71 ms |
| rep max | 186.47 ms |
| Passed / failed | 91,000 / 0 |
| Per-test median | 0.0013 ms |
| Per-test p95 | 0.37 ms |
| Per-test max | 175.57 ms |

From the U1 baseline (single run): cold compile 2.98 ms, cold instantiate
0.37 ms, cold start ~3.35 ms, mean per-test 0.48 ms, median per-test
0.019 ms, peak linear memory 1.75 MiB, mean reinstantiate 0.11 ms.

## What this means for Q4 sharding

**The per-invocation cost model (one test per Worker invocation, D9/R17):**

- A test invocation on the tier costs roughly `cold start (~3.3 ms)` +
  `per-test run time` (median sub-millisecond; p95 0.37 ms; the single
  slowest test in the suite peaked at 175 ms).
- The suite of 95 tests is **30.3 s of total CPU** at K=1000, i.e.
  ~30 ms per full pass at one invocation per test. On Cloudflare's
  CPU-time-billed model this is negligible at any realistic cadence — even
  10 full passes/hour is under 2 CPU-seconds/hour before platform overhead.

**Shard-unit recommendation: one test per Worker invocation, unbatched.**
- The plan's D9/R17 already commit to this shape; the measurement supports
  it — a test is sub-millisecond median, so batching buys nothing on CPU and
  forfeits the natural isolation granularity (a trapping test only takes
  down its own isolate, per the runner's panic→abort→trap protocol).
- The N=94 shard unit (one suite = 94 runnable tests + 1 infra/expected-fail
  set) is the right scheduling unit: a full suite sweep is one "job" of ~30 ms
  of compute spread across ~95 isolates.
- **The dominant cost is cold start, not compute.** 3.35 ms cold start vs
  0.3 ms median test. Track D (the Worker) should amortize instantiation
  (warm isolates, or per-test reuse of a module instance where isolation
  allows) — but that is a Track D optimization, not a Phase-1 blocker.

**Platform overhead factor (Node → workerd) is unmeasured** (workerd is not
installed here; Node/V8 is the sanctioned substitution). Track D's U8
measures the real factor. Nothing in these numbers suggests it changes the
sharding shape.

## Verdict

Q4 is answered: **one test per Worker invocation, one suite (~95 tests) as
the scheduling unit, no batching.** Cold-start amortization is the only
cost lever, and it is Track D's concern.
