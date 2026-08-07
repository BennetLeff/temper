# Phase 1 U3 — Sharding Design (Q4 Answer)

**Date:** 2026-08-07  
**Commit:** `14979d6330c463f78e04597f7872e979aca06cee` (`origin/main`)

## Q4: How work is sharded

### Measured Throughput (from U2 `--repeat`)

| Metric | Value |
|--------|-------|
| Test corpus | 95 tests (91 pass, 4 expected-fail) |
| Repetitions (K) | 1,000 |
| Total invocations | 95,000 |
| Total wall time | 30,004 ms |
| **Throughput** | **~3,166 invocations/second** |
| Rep mean wall time | 30.004 ms |
| Rep median wall time | 26.938 ms |
| Rep p95 wall time | 47.712 ms |
| Rep max wall time | 176.931 ms |
| Peak linear memory | 1.75 MiB (1.4% of 128 MiB limit) |
| Compile time (one-time) | ~1.3 ms |
| Instantiate time (per-rep) | ~0.1–0.15 ms |

### Per-Test Timings (individual tests, K=100 per test)

| Test | Family | Median (ms) | P95 (ms) |
|------|--------|-------------|-----------|
| `board::tests::edge_distance_is_symmetric` | types | 0.0243 | 0.0366 |
| `dfm::tests::calculate_angle_magnitude...` | dfm | 0.0240 | 0.0433 |
| `dfm::tests::thermal_via_side_round...` (expected-fail) | dfm | 0.0372 | 0.0860 |
| `rules::integration_tests::empty_board_zero_violations` | integration | 0.0605 | 0.1297 |
| `types::clock::tests::test_point_to_point_ok` | placement | 0.0243 | 0.0360 |
| `types::fuse::tests::test_fuse_trace_exact_boundary` | safety | 0.0245 | 0.0294 |
| `types::magnetic::tests::test_magnetic_component_trait` | emc | 0.0236 | 0.0455 |
| `types::vent::tests::test_vent_direction_faces` | placement | 0.0239 | 0.0434 |

**Key observation:** Pure test execution is O(0.02–0.06 ms). Instantiation (~0.1 ms) dominates the per-invocation cost in the one-test-per-isolate model.

### Shard Design

#### Shard Unit: One Test Function per Worker Invocation

Per R17, the natural shard is `temper_run_test(index)` — one test function per Worker invocation. This is the shard unit for all Phase 1 dispatch.

**Shard dimensions:**
1. **By test index** (already implemented). 94 runnable test functions (95 minus 4 expected-fail = 91, plus the 4 expected-fail that still execute). The four expected-fail tests are still dispatched — the Worker returns `{status: "fail"}` rather than trapping the HTTP handler.
2. **By repetition.** For volume, distribute `K` repetitions of the N-test suite across `M` Workers, each running `(K × N) / M` invocations.
3. **By commit.** Each commit on `origin/main` gets its own run; the R19 comparison is per-commit, not cumulative.

#### N=95 Shard Unit Size

The 95 registered tests are dispatched as 95 individual Worker invocations per repetition. No batching — one test per invocation. This is the simplest shard scheme and matches the Workers model (stateless, one invocation per isolate). The 4 expected-fail tests are still dispatched — the Worker returns `{status: "fail"}` rather than trapping the HTTP handler.

Batch alternatives were considered and rejected:
- Batch of N tests per invocation: 30 ms per rep (locally). On the Workers free tier, the 10 ms CPU-time limit would be exceeded for the larger tests (`empty_board_zero_violations` alone is ~1.5 ms in the full suite). Per-test invocation keeps each under 1 ms.
- Batch by family: Adds scheduling complexity with no benefit — the test->family mapping would need to be embedded in the Worker.

#### Per-Invocation Cost Estimate

| Component | Local (Node/V8) | Cloudflare Workers (estimated) |
|-----------|-----------------|-------------------------------|
| Per-invocation wall time (incl. instantiate) | ~0.29 ms (avg) | ~0.3–1.0 ms (estimated) |
| Pure test execution (median) | ~0.024 ms | ~0.024 ms |
| Instantiation overhead | ~0.1 ms | Included in CPU time |
| CPU time per invocation | ~0.29 ms | Cloudflare-billed CPU time |
| Requests per commit (K=100) | 9,500 | 9,500 |
| CPU time per commit | ~2,850 ms | ~2,850–9,500 CPU-ms |
| Request cost per commit | — | $0.00285 (9,500 × $0.30/1M) |
| CPU cost per commit | — | $0.000057–$0.00019 (2,850–9,500 × $0.02/1M CPU-ms) |
| **Total per commit** | — | **~$0.003** |
| **Per week (10 commits)** | — | **~$0.03** |
| **Per month (40 commits)** | — | **~$0.12** |

The per-commit cost is negligible — well within D3's $5–7/month estimate. The free tier (100,000 requests/day) would cover most runs without billing.

#### K Recommendation

**K=100 repetitions per commit** is recommended for Phase 1:
- 9,500 invocations per commit × 10 commits = 95,000 invocations for the U6 observation window
- Local runtime: ~30 seconds per commit, ~5 minutes for 10 commits
- Cost on Cloudflare: ~$0.03/week, $0.12/month
- Statistical confidence: 9,500 data points per commit is more than sufficient for the drc-rs test surface (deterministic, no `rand`, no HashMap iteration order)

### Memory Context

From Phase 0 U4: the full-board rule pass consumes 2.94 MiB RSS natively, 2.3% of the 128 MiB Workers isolate limit. Per-invocation memory with one test function is strictly lower. The limit does not bind at any shard granularity. No memory strategy is required for Phase 1.

### Verdict

**U3 COMPLETE.** The shard design is:
- One test function per Worker invocation (R17)
- N=95 shard units (all registered tests dispatched, including 4 expected-fail)
- K=100 repetitions per commit for sustained agreement measurement
- Per-commit cost: ~$0.003 on Cloudflare Workers
- Monthly cost: ~$0.12 at 40 commits/month
