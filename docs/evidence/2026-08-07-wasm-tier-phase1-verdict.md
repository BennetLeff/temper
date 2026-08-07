<!-- provenance: commit=f7a1fbf8fd155a0c303462717d531f8ae7606b7f dirty=false -->

# WASM Verification Tier — Phase 1 Verdict (U9)

**Date:** 2026-08-07
**Base:** `origin/main` @ `f7a1fbf8fd155a0c303462717d531f8ae7606b7f`
**Branch:** `wasm/p1-u9-verdict`
**Unit:** U9 "The Phase 1 verdict" of
`docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md`
**Scope:** this document only. No source, CI, baseline, or plan document was
touched; `git status` is clean apart from this file.
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0 (HEAD ==
`origin/main` at dispatch).

This document consolidates the Phase 1 verdict from the evidence produced by
U0 (build fix), U1 (R19 baseline), U2 (local at-scale runner), U3 (sharding
design, Q4), U4 (coverage, R7/R8), U5 (local volume run), and U6 (R19 sustained
agreement). Track D (U7/U8, Cloudflare Worker deployment) is DEFERRED. It does
not edit the parent plan or the Phase 1 plan; it is the recorded verdict that
either licenses Phase 2 or records the preconditions for a re-pull.

---

## 1. The verdict table (plan §U9)

| Unit | Goal | Verdict | Evidence | Consequence |
|---|---|---|---|---|
| U0 | Tier builds on `main` (wasm32 build fix, #879/#880) | PASS | `2026-08-07-phase1-u1-r19-baseline.md`, `2026-08-07-phase1-u6-sustained-agreement.md` | FAIL → nothing runs; all 10 U6 commits built on first attempt |
| U1 | R19 verdict baseline established | PASS | `2026-08-07-phase1-u1-r19-baseline.md` | Agreement 1.0 at `14979d633`; prerequisite for R19 measurement |
| U2 | Local at-scale runner (`--repeat`) | PASS | `2026-08-07-phase1-u3-sharding.md`, `2026-08-07-phase1-u5-volume.md` | 95,000 (U3) and 190,000 (U5) invocations measured; prerequisite for volume run |
| U3 | Sharding design (Q4) | PASS | `2026-08-07-phase1-u3-sharding.md` | One test per Worker invocation; N=95 shard units; K=100 per commit; answers Q4 |
| U4 | Coverage reporting per test/family + canaries (R7, R8) | PARTIAL | `2026-08-07-phase1-u4-coverage.md` | Machinery complete, non-vacuity proven — but family coverage thin (drc 1, routing 2 of 95; erc 0 registered tests). The gap is the Phase 2 precondition |
| U5 | Local volume run ≥ 10^4 invocations | PASS | `2026-08-07-phase1-u5-volume.md` | 190,000 invocations deterministic, ~3,379 inv/s, 1.75 MiB peak memory; stretch target (94,000) exceeded 2× |
| U6 | R19 sustained agreement | PASS (SUSTAINED) | `2026-08-07-phase1-u6-sustained-agreement.md` | R19 SUSTAINED: agreement 1.0 across 10 consecutive commits; licenses later gating under R15 |
| U7 | Worker deployed | DEFERRED | — | No Cloudflare account provisioned; un-deferred by account + token provisioning |
| U8 | Worker volume run + cost ceiling | DEFERRED | — | Gated on U7; cost model stands as an estimate (~$0.12/month, plan §U8/U3), not a measurement |

U0–U6 are the critical path (Tracks A+B+C) and are complete. U3's verdict is
the plan's "COMPLETE" (Q4 answered); U6's is the plan's "R19 SUSTAINED." The
only PARTIAL is U4, and it is a coverage *spread* gap, not a vacuity gap: the
reporting and canary machinery is in place and every exercised family carries
a demonstrated failing case, but the per-family test distribution is thin —
`drc` has 1 registered test, `routing` has 2, and `erc` has 0 of the 95 total.

---

## 2. The Phase 1 verdict sentence (plan §U9)

> **Phase 1 complete (Worker deferred).** The tier's first payload — the
> existing portable Rust test suite — is established at scale locally: one test
> per Worker invocation, 190,000 invocations deterministic with zero unexpected
> verdicts, and R19 sustained agreement 1.0 across 10 consecutive commits on
> `origin/main` — with the family-coverage gap (U4: `drc` 1 and `routing` 2 of
> 95 tests, `erc` 0) named as the precondition for Phase 2's
> manufacturing-variation work, and the Worker deploy (Track D, U7/U8) as the
> open external dependency, deferred on Cloudflare account provisioning.

---

## 3. Stand-alone evidence (headline numbers, inline)

The referenced evidence docs merge via PRs #876/#882/#874/#885/#886/#889/#890.
Until they are re-read, this section keeps the verdict self-contained.

### U0 — the wasm32 build is fixed on `main`

- The `PYO3_CROSS_PYTHON_VERSION` cross-compile failure is gone: #879 made
  `temper-geometry` `optional` (bound to the `python` feature, removing pyo3
  from the wasm32 graph) and #880 gated `copper_reach.rs`'s un-`cfg`'d pyo3.
- U1's baseline and U6's build verification both build the module at HEAD
  cleanly; **all 10 of U6's observation-window commits built on the first
  attempt, zero exclusions** — including three wave4 Rust-migration merges
  (#886, #889, #890) that changed other crates, confirming the fixes isolate
  the wasm32 graph.
- Module: **1,183,875–1,183,876 bytes, zero imports**, 95 registered tests.

### U1 — R19 verdict baseline

- At commit `14979d6330c463f78e04597f7872e979aca06cee`: native
  `--no-default-features` 95/95 pass; wasm32 **91 pass + 4 expected-fail, 0
  unexpected**. **Agreement rate 1.000000** (91 agree-pass + 0 agree-fail + 4
  expected-fail; 0 disagree, 0 unexpected-pass, 0 native-only, 0 wasm32-only).

### U2 — local at-scale runner

- `tools/wasm/run_wasm_tests.mjs --repeat K` reinstantiates a fresh module per
  repetition (the Workers one-isolate-per-invocation model). U3 measured
  **95,000 invocations at ~3,166 inv/s**; U5 measured **190,000 at ~3,379
  inv/s**. Reinstantiation after each expected-fail trap is counted and costs
  ~0.1–0.2 ms.

### U3 — sharding design (Q4)

- Shard unit: **one test function per Worker invocation** (`temper_run_test(i)`,
  R17). Dimensions: by test index, by repetition, by commit.
- **K=100 repetitions per commit recommended**: 9,500 invocations/commit,
  ~$0.003/commit and ~$0.12/month at 40 commits/month on Workers — within D3's
  $5–7 estimate. Per-test execution is O(0.02–0.06 ms); instantiation (~0.1 ms)
  dominates in the one-test-per-isolate model.

### U4 — coverage reporting and non-vacuity (R7, R8)

- `tools/wasm/test_family_map.json` maps all 95 tests to 8 families;
  `tools/wasm/coverage_report.py` emits per-family pass/fail/canary reports.
- **Every exercised family carries a demonstrated failing case**: 4 existing
  expected-fail tests (`dfm`, `types`) + 5 planted-defect canaries proven to
  trap on 2026-08-07 (`drc`, `emc`, `placement`, `routing`, `safety`) +
  transitive coverage for `integration`.
- **The gap:** per-family distribution is thin — `drc` 1, `routing` 2 of 95
  tests, and **`erc` has 0 registered wasm32 tests** (its rule modules exist
  but have no test modules in `gen_wasm_test_registry.py`'s eligible list).
  This is the named precondition for Phase 2's manufacturing-variation work,
  not a vacuity problem.

### U5 — local volume run

- At commit `be7e25538`: **190,000 invocations** (95 tests × 2,000
  repetitions), **56.2 s total, ~3,379 invocations/second** — 2× the plan's
  94,000 stretch target.
- **Determinism:** 182,000 pass + 8,000 expected-fail, **0 unexpected, 0
  non-deterministic verdicts** across all 2,000 repetitions.
- **Memory:** peak linear 1.75 MiB (1.4% of the 128 MiB limit), constant across
  repetitions — no growth, no leak. Agreement rate 1.000000.

### U6 — R19 sustained agreement

- Observation window: **10 consecutive commits `cdc463746` → `947820962`**.
  **Agreement rate 1.000000 at every commit** (91 agree-pass + 4 expected-fail,
  0 disagree, 0 unexpected-pass, 0 native-only/wasm32-only).
- Expected-failure manifest **byte-identical across the window** (sha256
  `534e98b8…`); no new failure classes. Module size/imports/memory stable
  across all 10 commits.
- **R19 SUSTAINED.** This is the bar that licenses later gating under R15
  (Phase 5, descoped from the parent plan) — it does not itself gate merges in
  Phase 1.

### Track D — Worker deployment (U7/U8), DEFERRED

- **Reason:** the Cloudflare account is not provisioned — no account, no
  `wrangler` API token, no subdomain. This is the same upstream-scheduling
  deferral pattern as Phase 0's R3 BLOCKED-UPSTREAM; per the Phase 1 plan §3 it
  is an **acceptable Phase 1 exit** (the local volume run and R19 agreement
  measurement are the gating milestones; Track D is not on the critical path).
- **What un-deferring requires:** the maintainer provisions (1) a Cloudflare
  account with Workers enabled, (2) a `wrangler` API token with Workers deploy
  permission, (3) a subdomain (`temper-wasm.workers.dev` or a custom route).
  Then U7 deploys `wrangler.toml` + `worker.js` and measures cold start and
  per-invocation CPU time; U8 runs ≥10^4 invocations against the Worker and
  replaces the cost model with measurement (the platform overhead factor,
  Worker wall vs. local Node wall).
- **Deferred, not descoped.** A re-pull of Track D does not re-run U0–U6.

---

## 4. Evidence sources

| Row | Verdict source |
|---|---|
| U0 | `docs/evidence/2026-08-07-phase1-u1-r19-baseline.md` (build at `14979d633`; #879/#880 merged) + `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` (10/10 commits built first attempt) |
| U1 | `docs/evidence/2026-08-07-phase1-u1-r19-baseline.md` |
| U2 | `docs/evidence/2026-08-07-phase1-u3-sharding.md` (K=1000 measurements) + `docs/evidence/2026-08-07-phase1-u5-volume.md` (K=2000 measurements) |
| U3 | `docs/evidence/2026-08-07-phase1-u3-sharding.md` |
| U4 | `docs/evidence/2026-08-07-phase1-u4-coverage.md` |
| U5 | `docs/evidence/2026-08-07-phase1-u5-volume.md` |
| U6 | `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` |
| U7/U8 | None — no Worker deployment was possible without a Cloudflare account; the deferral is recorded here |

Cross-referenced plans: `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md`
(§1 U9, §3 sequencing, §4 non-goals) and the Phase 0 verdict
`docs/evidence/2026-08-05-wasm-tier-phase0-verdict.md` (R1/R2 PASS, R3
BLOCKED-UPSTREAM, D3 stands — the precedent for a deferred-but-accepted exit).

Tracked issues carried by this verdict: **#872** feature unification (fixed by
U0), **#873** routing-data gap in the `BoardState` bridge (out of Phase 1
scope, deferred per plan U3), **#871** route OOM (R3, not Phase 1 scope).

---

## 5. What could not be verified from source docs

- U2 has no standalone evidence doc on `origin/main`; its verdict is carried by
  the U3 and U5 measurements that its `--repeat` runner produced.
- The Worker cost numbers ($0.003/commit, ~$0.12/month at 40 commits/month) are
  **estimates** from U3's local measurements — U8's real-platform measurement
  is the un-deferred follow-on. The platform overhead factor (Worker vs. Node)
  remains unmeasured until Track D runs.
- The `erc` family's 0 registered tests and the thin `drc`/`routing` counts are
  read from `2026-08-07-phase1-u4-coverage.md`; the dispatch's summary
  characterized the U4 gap more broadly than the evidence doc records, and this
  verdict follows the evidence doc's own numbers.
