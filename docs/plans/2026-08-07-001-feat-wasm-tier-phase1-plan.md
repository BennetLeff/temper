---
title: WASM Verification Tier — Phase 1 Implementation Plan
type: feat
date: 2026-08-07
topic: wasm-tier-phase1
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan
execution: code
status: draft
---

# WASM Verification Tier — Phase 1 Implementation Plan

## Goal Capsule

- **Objective:** Land the tier's first payload — the existing portable Rust test
  suite running at volume on Cloudflare Workers, one test function per
  invocation, with per-test verdicts compared against GitHub Actions for the
  same commit. Sustained agreement licenses later gating under R15. This is
  Phase 1 of `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`,
  whose Phase 0 verdict (`docs/evidence/2026-08-05-wasm-tier-phase0-verdict.md`)
  recorded R1 PASS / R2 PASS / R3 BLOCKED-UPSTREAM and concluded **D3 stands —
  Phase 1 may be pulled.**
- **Product authority:** temper maintainer. This plan owns the *execution shape*
  of Phase 1 — what is built, in what order, what evidence closes each unit. It
  does not own the parent plan's content, D3's disposition, or anything in
  Phases 2–4.
- **Open blockers:** Four, none of which reopen D3 but all of which gate Phase 1
  units.
  1. **The wasm32 build is broken on `origin/main`.** A stray
     `#[cfg(feature = "python")]` gate on `wasm_test_registry` landed in commit
     `13aee32b7` (PR #751, "DO NOT MERGE") and makes the module unreachable
     under the documented build command. Diagnosed and recorded in
     `docs/evidence/2026-08-06-wasm32-float-divergence.md` §7. Fix is one line
     in `packages/temper-drc-rs/src/lib.rs`; the tier does not build without it,
     so it is U0, not optional.
  2. **Routing data absent from the `BoardState` bridge (issue #873).** The
     `board_py_bridge` does not emit traces, vias, or zones, so routing-family
     tests execute against an empty board. This bounds what routing-family test
     results can claim; R2's U4 measurement confirms the RSS impact is O(1,000)
     segments and does not threaten the 128 MiB limit. Phase 1 may either close
     this gap (extend the bridge's `board_dict` keys and `build_board_state`) or
     defer it, recording the routing tests as "executed against an empty board"
     rather than "exercised the board's actual routing data." This plan defers
     — see U3.
  3. **The R3 producer is blocked on `route_pcb()` OOM (issue #871).** The
     route stage cannot complete on the production board. R3 is not Phase 1
     scope, but the tier needs a content-addressed board artifact to name in its
     findings per R6. Phase 1 can proceed with the *committed* board (already
     content-addressed via its sha256) rather than a freshly regenerated one.
  4. **No Cloudflare account or `wrangler` token is provisioned.** Phase 0
     deliberately stayed local. Phase 1's Worker deployment units (U7, U8)
     cannot execute until the maintainer provisions an account, API token, and
     subdomain. This is a scheduling dependency, not a technical one; the local
     volume units (U5, U6) are unblocked.

---

## 0. State of Phase 1 on `origin/main` (verified 2026-08-07 at `af5aa02c8`)

This section is measurement, not planning. Every unit below is sized against it.

### What has landed

The Phase 0 substrate is proven. The following are on `origin/main` as
artifacts, not claims:

- `packages/temper-drc-rs` compiles for `wasm32-unknown-unknown` with
  `--no-default-features` and the `wasm-test-registry` feature. All six rule
  families (`drc`, `emc`, `erc`, `safety`, `placement`, `routing`) are reachable
  — no internal `#[cfg]` gates in `rules/`. The portable surface is 576 of 637
  tests (61 gated out behind `#[cfg(feature = "python")]`).
- `packages/temper-wasm-test-runner` is a `cdylib` crate that depends on
  `temper-drc-rs` with `wasm-test-registry` and exposes seven `extern "C"`
  exports: `temper_wasm_abi_version`, `temper_test_count`, `temper_test_name_ptr`/`_len`,
  `temper_run_test`, `temper_panic_message_ptr`/`_len`. Panic → abort → trap.
- The built `.wasm` module is 1,183,886 bytes with **zero imports** —
  deployable to a bare Cloudflare isolate. 95 tests registered; 91 pass, 4
  expected-fail (`dlsym` resolution + B7 pow-divergence), zero unexpected.
- `tools/wasm/run_wasm_tests.mjs` — the Node/V8 host driver. V8 is the engine
  `workerd` embeds, so trap behaviour and instantiation cost here are
  representative. Measures compile/instantiate, per-test wall time, peak linear
  memory, reinstantiation cost after a trap.
- `tools/wasm/run_r1_smoke.py` (branch `origin/wasm/u1-rung23-closing`) — the
  wasmtime harness for the six-family exact-match verification.
- `scripts/gen_wasm_test_registry.py` — generates `WASM_TESTS` consts inside
  each test module and the `wasm_test_registry.rs` aggregator. `--check` gates
  drift in CI. Currently hardcoded to `temper-drc-rs` only.
- `tools/wasm/wasm_expected_failures.json` — the expected-failure manifest:
  4 entries, classes `no-dynamic-loader` and `b7-pow-divergence-absent`.
- **Phase 0 verdict.** R1 PASS, R2 PASS (2.94 MiB RSS, 1.51 ms whole-pass
  median, 42× below the 128 MiB limit), R3 BLOCKED-UPSTREAM. D3 STANDS.

### What is broken — the one-line gate

`packages/temper-drc-rs/src/lib.rs` lines 41-43 (as of `af5aa02c8`):

```rust
#[cfg(feature = "python")]
#[cfg(feature = "wasm-test-registry")]
pub mod wasm_test_registry;
```

Both `cfg`s must be true simultaneously for the module to exist.
`temper-wasm-test-runner` depends on `temper-drc-rs` with
`default-features = false, features = ["wasm-test-registry"]` — `python` is
never on. There is no configuration that satisfies both: enabling `python` for a
`wasm32-unknown-unknown` cross build fails because `pyo3`'s
`extension-module` feature rejects `wasm32` cross-compilation.

`git blame` traces the stray line to commit `13aee32b7` ("DO NOT MERGE" in its
own title, PR #751). PR #800's commits (`2259f8598`, `97dd0fc13`) had the gate
correct (`#[cfg(feature = "wasm-test-registry")]` alone). The documented build
command in the Phase 0 plan has not produced a valid `.wasm` artifact for any
commit since.

### What does not exist yet

- **No other crate has a `wasm-test-registry`.** `temper-geometry`,
  `temper-dsn`, `temper-ipc`, `temper-quality-oracle`, `temper-thermal` — none
  has `WASM_TESTS` consts, a `wasm_test_registry` module, or any entry in
  `gen_wasm_test_registry.py`. Phase 0's U2 census recorded 39
  `temper-geometry` tests gated out. None has been un-gated.
- **No local at-scale runner.** `run_wasm_tests.mjs` runs the suite once, not
  at volume. No driver repeats invocations, measures amortized throughput, or
  stresses reinstantiation paths.
- **No Worker deployment.** No `wrangler.toml`, no Cloudflare account, no
  `workers-rs` dependency. Phase 0 deliberately stayed local.
- **No R19 comparison data.** Per-test verdicts have never been compared between
  the wasm32 run and the same commit's GitHub Actions `cargo test` output.
- **No coverage report.** The 94 drc-rs tests are registered and run, but there
  is no mapping from test name to rule family, and no demonstrated-failing-case
  canary per R8 beyond the expected-failure manifest.

---

## 1. Unit breakdown

Nine units in four tracks. **Track A is the prerequisite — nothing builds or
runs until U0 lands. Track B (local infrastructure) gates Track C (volume and
verdict comparison), which gates Track D (Worker deployment).**

```
Track A (prereq)  U0 ──────────────────────────────────────────────┐
                                                                    │
Track B (local)   U1 ──> U2 ──> U3 ──> U4                         │
                    \              \                                │
Track C (volume)     \              \                               │
                      +──> U5 ──> U6                                │
                                                                   │
Track D (Worker)                                              U7 ──> U8
                                                                   │
                                                                    │
                                                              U9 (verdict — needs U0,U4,U6,U8)
```

Tracks B and C are serial: you cannot measure volume (U5) before you have a
runner that can repeat invocations (U3), and you cannot compare verdicts (U6)
until you have volume data that spans commits (U5). Track D is parallel to C:
Worker deployment can proceed independently of the local volume run, subject to
the Cloudflare-account blocker.

---

### Track A — Prerequisite: fix the build

#### U0. Remove the stray `#[cfg(feature = "python")]` gate

**Goal.** Make the documented build command produce a `.wasm` artifact again.

**Why.** The tier does not build on `origin/main`. The fix is one line; every
other Phase 1 unit depends on it.

**What changes.** `packages/temper-drc-rs/src/lib.rs`: remove line 41
(`#[cfg(feature = "python")]`), leaving only
`#[cfg(feature = "wasm-test-registry")]` as the gate for `pub mod wasm_test_registry;`.
No other source change. No feature-graph change. No API change.

**Risks.** The stray line was added in a commit whose own title says "DO NOT
MERGE." Verify that no module behind `wasm_test_registry` actually *requires*
the `python` feature — it doesn't (the registry explicitly lists only modules
that survive `--no-default-features`). The `wasm-test-registry` feature is
independent by construction: it only activates `#[cfg(any(test, feature =
"wasm-test-registry"))]` on test modules, which are already compilable without
`python` (the whole point of the Phase 0 `--no-default-features` work).

**Verification / evidence that closes U0**
1. `cd packages/temper-wasm-test-runner && cargo build --release --target
   wasm32-unknown-unknown` exits 0 and produces a `.wasm` artifact.
2. `tools/wasm/run_wasm_tests.mjs` against that artifact reports
   `registered == executed >= 90` (the Phase 0 baseline: 94–95 tests).
3. `tools/wasm/run_r1_smoke.py` (from the `wasm/u1-rung23-closing` branch, or
   the equivalent wasmtime invocation) shows zero unexpected failures.
4. A deliberate re-addition of the stray `#[cfg(feature = "python")]` line turns
   the build red — demonstrating the gate is not vacuous. (Commit, verify,
   revert — do not land the re-addition.)

**Blocks:** U1, U2, U3, U4, U5, U6, U7, U8, U9.

---

### Track B — Local at-scale infrastructure

#### U1. Establish the R19 verdict baseline

**Goal.** Produce the per-test pass/fail mapping for the current `origin/main`
HEAD, comparing the wasm32 run against the same commit's native
`cargo test --no-default-features` run. This is the baseline all later R19
comparisons diff against.

**Why.** R19 requires per-test verdict comparison against GitHub Actions for the
same commit. This unit produces the first data point and establishes the
protocol.

**Protocol.**
1. Record the commit SHA at which the comparison is performed.
2. Run `cargo test --no-default-features -p temper-drc-rs` natively. Capture
   the per-test pass/fail list (test name, status) in JSON. Use
   `cargo test -- --format json` with `--report-time` or parse the standard
   libtest output.
3. Build the wasm32 module (`cargo build --release --target
   wasm32-unknown-unknown` in `temper-wasm-test-runner`).
4. Run `tools/wasm/run_wasm_tests.mjs --json /tmp/r19_baseline.json` to produce
   the wasm32 per-test result list.
5. Join the two lists on test name. Classify each test as:
   - **agree-pass** — both pass
   - **agree-fail** — both fail
   - **disagree** — native passes, wasm32 fails OR native fails, wasm32 passes
   - **expected-fail** — in the expected-failure manifest, wasm32 fails, native passes
   - **unexpected-pass** — in the expected-failure manifest, wasm32 *passes*
   - **native-only** — test exists natively but not in the wasm32 registry
   - **wasm32-only** — test exists in the wasm32 registry but not natively
6. Report the matrix. The "agreement rate" is
   `(agree-pass + agree-fail + expected-fail) / (agree-pass + agree-fail + disagree + expected-fail + unexpected-pass)`.
   Native-only and wasm32-only tests are counted separately — they represent
   scope mismatch, not disagreement.

**The expected-failure manifest** (`tools/wasm/wasm_expected_failures.json`) is
the mechanism by which divergence is pre-classified. The 4 current entries
(`host_libm_symbols_actually_resolve`, `pow_is_not_a_multiply_or_a_sqrt`, and
two dfm tests that assert pow-vs-sqrt divergence exists) are **not**
disagreements — they are the tier correctly reporting "this assertion about
native libm behaviour does not hold on wasm32." An expected-fail test that
suddenly *passes* on wasm32 (an "unexpected pass") is a staleness signal: the
exclusion is suppressing a test that would otherwise be doing work, and the
manifest entry must be removed.

**Files touched**
- New: `tools/wasm/r19_compare.py` — runs both native and wasm32, produces the
  per-test matrix in JSON, and reports an agreement rate. Ruff-clean.
- New: `docs/evidence/2026-08-07-r19-baseline.md`.
- May touch: `tools/wasm/run_wasm_tests.mjs` — if the `--json` output format
  needs a field added for commit attribution or native-vs-wasm32 disambiguation.

**Edge cases the protocol must handle:**
- **Test name drift.** A test renamed between native and wasm32 builds would
  appear as "native-only + wasm32-only." Report it; do not silently absorb it.
- **The `--no-default-features` scope difference.** The native run uses
  `--no-default-features` (which disables `python`). The wasm32 build also
  disables `python`. The 61 python-gated tests are absent from both and are
  **not** counted as native-only — they are out of scope for the comparison.
- **`cargo test` includes all workspace crates.** Restrict to `-p
  temper-drc-rs` to match the wasm32 registry's scope.

**Evidence that closes U1:** the comparison matrix exists for a named commit,
the agreement rate is reported, and every disagreement (if any) has a
classification (expected-fail, float divergence, build configuration difference,
or genuine bug).

**Blocked by:** U0. **Blocks:** U6.

---

#### U2. Build the local at-scale runner

**Goal.** Extend the Node host driver to run the wasm32 test suite at volume —
`K` repetitions of the full N-test suite — and measure amortized throughput.

**Why.** D3's pricing model means the per-invocation cost should be understood
before committing Cloudflare spend. A local volume run (10^4–10^5 invocations)
against the same test corpus answers: what is the steady-state throughput, how
much does reinstantiation after a trap cost amortized over a run, and does
linear memory grow across thousands of invocations?

**What changes.**
- Extend `tools/wasm/run_wasm_tests.mjs` (or add a companion script) with:
  - A `--repeat K` flag. Each repetition re-instantiates a fresh module (to
    match the Worker model — each invocation gets a fresh isolate).
  - Per-repetition timing: instantiation, total test wall time, reinstantiation
    count and cost.
  - Cumulative statistics: total invocations, wall-clock duration, invocations
    per second, peak linear memory across all instantiations.
- The runner must **not** reuse an instance across repetitions — the Workers
  model is one invocation per isolate, and reusing would hide the
  instantiation cost that Cloudflare bills as "CPU time."
- Keep the existing single-run behaviour as the default; `--repeat` is additive.

**What "volume" means concretely.**
The 94 drc-rs tests × 1,000 repetitions = 94,000 invocations. At the Phase 0
R2 measurement (1.51 ms whole-pass median), 94,000 invocations is ~142 seconds
of test-execution time plus instantiation overhead. With instantiation at ~0.5
ms/cold (the Phase 0 U1 rung-3 Node measurement — cold instantiate ~0.5 ms),
1,000 reinstantiations add ~0.5 s. **Rough estimate: 3–5 minutes for a 10^5
invocation run locally.** This is comfortably within a single session.

**Evidence that closes U2**
1. `node tools/wasm/run_wasm_tests.mjs --repeat 1000` completes, reports
   `totalInvocations: 94000`, and produces per-repetition statistics.
2. The throughput figure (invocations/second) is reported and stable across
   repetitions — the first repetition may be cache-cold; subsequent ones should
   converge.
3. Peak linear memory across all 1,000 instantiations is well below the 128 MiB
   limit (Phase 0 measured 2.94 MiB RSS natively for the whole pass; linear
   memory in V8 is expected to be comparable).
4. The runner exits non-zero if any test fails unexpectedly (same contract as
   the existing `run_wasm_tests.mjs`).
5. A planted failure — a test that always traps — is caught and correctly
   triggers reinstantiation, and the throughput impact (one
   reinstantiation/trap per repetition for that test) is measured and reported.

**Non-goals for U2:** do not implement sharding logic. That is U3. Do not deploy
to Cloudflare. Do not compare against native verdicts — that's U1 and U6.

**Blocked by:** U0. **Blocks:** U5.

---

#### U3. Sharding design

**Goal.** Answer Q4 — how work is sharded — with measured figures from U2,
and design the shard scheme Phase 1 uses for both local and Worker runs.

**Why.** The parent plan's Q4 defers sharding until R2 has the memory profile.
U2 provides the throughput data; U3 turns it into a shard design. Sharding is
also the answer to the question of whether 94 tests is a meaningful volume: a
single Worker invocation runs *one* test function, not the whole suite, so
"volume" comes from repeated sharded runs across many isolates, not from a
single large test corpus.

**The R2 memory context** (from Phase 0 U4): the full-board rule pass consumes
2.94 MiB RSS natively, 2.3% of the 128 MiB Workers isolate limit. A single test
function exercises a subset of the rules, so per-invocation memory is lower than
the whole-pass figure. The limit does not bind at any shard granularity.

**Shard dimensions — three axes:**
1. **By test index** (already implemented). The natural shard is one test
   function per Worker invocation. `temper_run_test(index)` is the call; the
   test count is `temper_test_count()`. This is what R17 requires.
2. **By repetition.** For volume, distribute `K` repetitions of the N-test
   suite across `M` Workers, each running `(K * N) / M` invocations.
3. **By commit.** Each commit on `origin/main` gets its own run; the R19
   comparison is per-commit, not cumulative.

**The shard unit.** One shard = one Worker invocation running one test function.
The dispatch loop is: for each commit, for each test index `i` in `[0, N)`, run
`K` repetitions. Total invocations per commit = `N * K`. With `N = 94` and
`K = 100`, that's 9,400 invocations per commit.

**Throughput estimate** (from Phase 0 U2/U4 and the expected U2 measurements):
- Per-test wall time: O(1) µs to O(1) ms (most tests are static-data assertions;
  the `clearance` family is the outlier at ~1.2 ms for the full O(n²) all-pairs
  pass but individual tests exercise smaller inputs).
- Instantiation overhead: ~0.5 ms per fresh isolate (cold).
- **With one fresh instantiation per test invocation (the Workers model):**
  94 tests × 100 repetitions = 9,400 instantiations × ~0.5 ms = ~4.7 s
  instantiation overhead + test-execution time. Locally this is seconds to
  minutes; on Workers it is the cost basis.

**Shard distribution across Workers — deferred, not designed yet.**
The parent plan's R5 says "sharded so that no single unit exceeds the isolate's
memory or CPU limits." The memory limit is not at risk (2.94 MiB whole-pass,
individual tests are smaller). The CPU limit is 50 ms per request on the
Workers free tier and 30 s on the paid tier — one test function per invocation
is well within both. **The shard scheme for distributing K repetitions across M
Workers is therefore a scheduling question, not a memory-safety question, and is
deferred to U7 (Worker deployment).** U3's deliverable is the *design*; U7
implements it.

**Evidence that closes U3:** a design document (`docs/design/wasm-tier-sharding.md`
or a section in the U2 evidence doc) recording the shard dimensions, the
measured per-invocation timings from U2, the N=94 test count as the shard-unit
size, and a recommendation for K (repetition count) that balances statistical
confidence (more repetitions per commit → fewer commits needed for sustained
agreement) against Worker cost.

**Blocked by:** U0. **Blocks:** U5, U7.

---

#### U4. Coverage reporting per test and per family (R7, R8)

**Goal.** Produce a mapping from each of the 94 drc-rs wasm32-registered tests
to the rule family (or families) it exercises, and implement the
demonstrated-failing-case canary per R8.

**Why.** R7 requires coverage "per kernel and per rule family, in units of cases
evaluated against the space they sample." R8 requires "a coverage claim is
reported as vacuous unless it carries a demonstrated failing case." The tier
currently runs 94 tests and can report "94 passed," which is an activity metric,
not a coverage metric. U4 closes that gap.

**What is measured.**
- **Per-test → per-family mapping.** Parse each test body (and, transitively,
  every production function it calls) for the rule family it exercises. Tag each
  test with one or more of `drc`, `emc`, `erc`, `safety`, `placement`,
  `routing`, `dfm`, `types`. Report the count of tests per family.
- **Per-family pass/fail.** After each run, report pass/fail per family, not
  just per test. A family with zero tests is a coverage gap; a family whose
  tests all pass is not a vacuous claim if the demonstrated-failing-case canary
  exists.
- **Demonstrated-failing-case canary (R8).** The 4 expected-fail tests are the
  existing canaries — they fail on wasm32 by design. For each rule family,
  assert that at least one test can fail under a planted defect. This extends
  the per-gate canary contract from the validation portfolio (R30, R42) to the
  tier.

**Implementation approach — static, not dynamic.**
The per-test → per-family mapping is a static JSON manifest, not a dynamic
instrument. It is produced once (via grep + manual curation for the 94 tests)
and checked for staleness (a test added to the registry without a mapping entry
is flagged). This is cheaper than runtime instrumentation and sufficient for the
94-test corpus.

Alternative considered and rejected: `#[cfg_attr]` tags on test functions
(the build-time dispatch already tags every test — the mapping could be inlined
in `gen_wasm_test_registry.py`). This is cleaner but requires modifying the
codegen script and every registered test module. **Recommendation: start with
the static manifest; inline into codegen as a follow-on.**

**Files touched**
- New: `tools/wasm/test_family_map.json` — static mapping: test name → family
  list, with a `_comment` field.
- New: `tools/wasm/coverage_report.py` — reads a run's results JSON (from
  `run_wasm_tests.mjs --json`), joins against `test_family_map.json`, emits a
  per-family pass/fail/count report. Ruff-clean.
- May touch: `tools/wasm/run_wasm_tests.mjs` — to add the `--coverage` flag
  that runs `coverage_report.py` as a post-processing step.

**The demonstrated-failing-case canary — protocol.**
1. For each rule family, identify one test that exercises that family.
2. Plant a deliberate defect — a threshold halved, a component count
   decremented — and verify the test fails (traps).
3. Record the planted defect and the resulting trap in
   `tools/wasm/canary_defects.json`.
4. After each volume run, optionally re-plant one canary per family and verify
   it still fails. This is not a per-run requirement for Phase 1 (the cost in
   reinstantiations is negligible but the planted-defect mechanism needs design);
   it is a per-commit requirement for the tier's CI guard.

**Evidence that closes U4:** `test_family_map.json` exists, covers all 94 tests;
`coverage_report.py` runs against a U2 volume-run JSON and produces a per-family
coverage report; at least one canary defect per family is recorded and
demonstrated to trap.

**Blocked by:** U0. **Blocks:** U9.

---

### Track C — Volume run and verdict comparison

#### U5. Local volume run — 10^4 to 10^5 invocations

**Goal.** Run the at-scale runner (U2) at volume — at least 10^4 invocations
(100 repetitions of the 94-test suite) — and measure throughput, memory, and
reinstantiation statistics. This is the local proof that the tier can sustain
the invocation rate R19's sustained-agreement measurement requires.

**Why.** A volume run is the milestone that distinguishes "the substrate works"
(Phase 0) from "the tier can sustain continuous operation" (Phase 1). It also
provides the per-invocation cost data needed for the Worker cost estimate in
U7/U8, without spending a Cloudflare penny.

**Protocol.**
1. Check out a known commit SHA. Record it.
2. Run `node tools/wasm/run_wasm_tests.mjs --repeat 1000` (94,000 invocations).
   If 1,000 repetitions strains memory or time, use `--repeat 100` (9,400
   invocations) as the floor. **N = 9,400 is the minimum; N ≥ 94,000 is the
   target.**
3. Capture: wall-clock duration, invocations/second, peak linear memory (max
   across all instantiations, not just the last), reinstantiation count and mean
   cost, pass/fail/expected-fail counts.
4. **Record the median per-invocation wall time including instantiation.** This
   is the number that feeds the Cloudflare cost estimate — CPU-time billing
   counts the whole isolate lifetime, not just the test function's execution.
5. Run the protocol against **three different commits** on `origin/main`
   (e.g., the current HEAD and two ancestors) to verify the throughput is stable
   across commits and not an artifact of one particular commit's test corpus.
6. For each commit, produce the per-test verdict matrix (U1 protocol) and verify
   that the pass/fail counts are identical across all 1,000 (or 100)
   repetitions — a test whose verdict is non-deterministic across repetitions
   is a finding, not a tolerated property.

**What a non-deterministic test would mean.** The drc-rs rules are deterministic
by construction (no `rand`, no `HashMap` iteration order, no wall-clock
dependence). If a test's verdict varies across repetitions, it indicates either
a V8 JIT non-determinism (unlikely but possible at the margins of trap
semantics) or a test that depends on uninitialized memory (a bug). Either is
worth recording.

**Evidence that closes U5:** the volume-run evidence doc
(`docs/evidence/2026-08-07-r19-volume-run.md`) with:
- The commit SHA(s) tested.
- Throughput: invocations/second, mean/median/p95 per-invocation wall time
  (including instantiation), and the reinstantiation overhead as a percentage of
  total time.
- Memory: peak linear memory, and whether it grows across repetitions (evidence
  of a memory leak).
- Verdict stability: per-test pass/fail counts across repetitions — are they
  deterministic?
- The per-test verdict matrix for each commit (U1 protocol).

**Blocked by:** U2, U3. **Blocks:** U6.

---

#### U6. R19 sustained-agreement measurement

**Goal.** Define "sustained agreement" numerically, and measure it across a
span of commits to either license later gating or identify the tests that
prevent it.

**Why.** R19 says "sustained agreement is the bar for licensing any later gating
under R15." Without a numeric definition and measured evidence, the bar is
unactionable. This unit defines it and provides the first measurement.

**The R19 agreement bar — specified here, not deferred.**
Sustained agreement is:

> All non-expected-fail tests show 100% pass/fail agreement (wasm32 verdict
> identical to native `cargo test --no-default-features` verdict) across 10
> consecutive commits on `origin/main`, AND no expected-fail test produces an
> unexpected pass or a new failure class that was not in the manifest at the
> start of the observation window.

Why 10 commits:
- The drc-rs test surface changes slowly — the crate has had ~12 commits in the
  past week, of which ~4 touched test code. 10 commits is roughly 2–5 days of
  activity, enough to catch a new test or a refactored assertion.
- A single-commit agreement is a point measurement; 10 consecutive commits
  rules out "the one commit I tested happened to agree" and catches the
  first commit that introduces a divergence.
- 10 is small enough that the measurement can complete in a single session
  (U5's protocol × 10 commits ≈ 10 × 3–5 min = 30–50 min locally).
- The number can be raised later (e.g., to 50 commits for Phase 5 gating) if
  the maintainer wants a stronger bar; 10 is the Phase 1 licensing bar.

What "agreement" means per test:
- **agree-pass:** Both pass. Counts as agreement.
- **agree-fail:** Both fail. Counts as agreement. (A test that fails on both
  platforms is a real bug, not a wasm32 divergence — it should be fixed, but it
  does not break the wasm-vs-native agreement claim.)
- **disagree:** Native passes, wasm32 fails OR vice versa. **Breaks agreement.**
  Each such test must be triaged: is it a wasm32 divergence (→ add to
  expected-failure manifest, reset the 10-commit counter, try again) or a bug
  in the wasm32 build (→ fix it, reset the counter) or a test that depends on
  native-host behaviour that wasm32 genuinely cannot provide (→ mark it
  permanently excluded from R19 comparison, analogous to the python-gated set)?
- **expected-fail:** In the manifest, wasm32 fails, native passes. Counts as
  agreement (the divergence is pre-classified).
- **unexpected-pass:** In the manifest, wasm32 *passes*. **Breaks agreement.**
  The exclusion is stale — the test no longer fails on wasm32. Remove it from
  the manifest so the test counts in the agree-pass set.
- **native-only / wasm32-only:** Does not count in the agreement rate. Represents
  scope mismatch — the test was added to one configuration but not the other.
  Flagged for investigation, not treated as a disagreement.

**Protocol.**
1. Select a span of 10 consecutive commits on `origin/main`. Start from the
   current HEAD and walk backwards (or, if the plan lands after U0–U4, walk
   forward from the plan's landing commit).
2. For each commit:
   a. Check out the commit.
   b. Run the U5 volume protocol (N ≥ 9,400 invocations, or at minimum a single
      suite run if volume data already exists for this commit).
   c. Run the U1 comparison protocol — produce the per-test verdict matrix.
   d. Record the agreement rate and any disagreements.
3. If all 10 commits show 100% agreement (per the definition above), record
   **R19 SUSTAINED** and the commit span.
4. If any commit shows a disagreement, record it, classify it, and either reset
   the counter (if the fix is in a subsequent commit) or record the test as
   permanently excluded.

**Evidence that closes U6:** `docs/evidence/2026-08-07-r19-sustained-agreement.md`
with:
- The R19 bar definition (the text above, or a refined version).
- The commit span tested (10 SHAs).
- The per-commit agreement rate and the per-test matrix for every commit.
- The verdict: either R19 SUSTAINED (100% across all 10 commits) or R19 NOT
  YET SUSTAINED (disagreements found, classified, and either fixed or excluded).
- If sustained, the exact commit span that licenses later gating.

**Edge cases.**
- **A new test is added mid-span.** It appears in the native build; if the
  codegen has not been re-run, it is absent from the wasm32 registry (→
  native-only). This does not break agreement — it is scope mismatch.
  Recommendation: re-run `scripts/gen_wasm_test_registry.py` at each commit to
  keep the registry current.
- **The expected-failure manifest changes mid-span.** A test is removed from the
  manifest because it no longer fails. This is a legitimate improvement; the
  test moves from expected-fail to agree-pass. Count it as agreement.
- **A commit introduces a genuine wasm32-only bug** (e.g., re-introduces the
  `#[cfg(feature = "python")]` gate). This breaks agreement and should be
  caught. The 10-commit observation window is the mechanism that catches it
  before it reaches Phase 5 gating.

**Blocked by:** U1, U5. **Blocks:** U9.

---

### Track D — Worker deployment

#### U7. Cloudflare Worker deployment

**Goal.** Deploy `temper_wasm_test_runner.wasm` as a Cloudflare Worker and
measure cold-start, per-invocation wall time, and per-invocation CPU-time cost
(what D3's pricing model actually bills).

**Why.** Phase 0 proved the substrate could compile and run locally. Phase 1
must prove it can run on the actual target platform at a measured cost before
any volume or gating depends on it. A local volume run (U5) establishes the
lower bound; a Worker run establishes the real cost.

**Prerequisites — not this plan's to create:**
1. A Cloudflare account with Workers enabled.
2. A `wrangler` API token with Workers deploy permission.
3. A subdomain (e.g., `temper-wasm.workers.dev`) or a custom route.
4. The `wrangler` CLI installed (`npm install -g wrangler` or equivalent).

These are a scheduling dependency, not a technical one. If they are not
provisioned, U7 and U8 are **deferred, not descoped** — exactly as U7 and U8
were deferred in Phase 0 when U6 recorded BLOCKED-UPSTREAM for R3.

**What is built.**
- `packages/temper-wasm-test-runner/wrangler.toml` — the Worker configuration.
  Minimal: `main = "build/worker.mjs"` (the JavaScript glue), `compatibility_date`,
  `wasm_modules` pointing to the built `.wasm`. No KV, R2, D1, or Durable
  Objects — the Worker is stateless (invoke a test, return a pass/fail, no
  persistence).
- `packages/temper-wasm-test-runner/src/worker.js` — the Worker entry point.
  For each HTTP request (at a `/{test_index}` path), instantiate the module,
  call `temper_run_test(index)`, return JSON `{index, name, status, ms}`. Catch
  traps as `status: "fail"` with the panic message. This is the one-test-per-invocation
  contract (R17).
- The Worker is deployed via `wrangler deploy`.

**The instantiation model — decided here.**
Each HTTP request instantiates a **fresh** module. The Workers runtime compiles
the module once at upload time and instantiates per isolate; this matches
`run_wasm_tests.mjs`'s `WebAssembly.compile` (once) + `WebAssembly.instantiate`
(per invocation). The compile cost is paid once; the instantiate cost is paid
per invocation and is the recurring cost D3's pricing model bills as CPU time.

Alternative considered: instantiate once and reuse the module across requests
(the Workers global scope persists across invocations within the same isolate).
**Rejected** because a panicking test aborts, which poisons the allocator.
`run_wasm_tests.mjs` already reinstantiates after every trap for this reason;
the Worker must do the same. The per-request instantiation model is correct by
construction: each test gets a clean isolate, and a trap in one test cannot
affect the next.

**Cost measurement — the numbers that matter.**
1. **Cold start:** time from request arrival to first instruction, measured as
   the Worker's reported `cpu_time` on the first request after a deploy.
2. **Per-invocation CPU time (median, p95, p99):** the Cloudflare-billed CPU
   time per test invocation. Measured via the Worker's `cf.colo` and
   `request.cf` metadata, or via `wrangler tail`'s reported duration.
3. **Per-invocation wall time:** end-to-end latency from the client's
   perspective. Higher than CPU time due to network and scheduling.
4. **Requests/second sustained:** how many test invocations the Worker can
   handle before hitting rate limits or CPU-time caps. The free tier's
   100,000 requests/day is 1.16 requests/second sustained; the paid tier
   removes the daily cap.

**Evidence that closes U7:**
1. `wrangler deploy` succeeds and the Worker is reachable at a URL.
2. A single-test invocation (`GET /0`) returns `{"index": 0, "name": "...",
   "status": "pass", "ms": ...}`.
3. A known-failing test (`GET /{index_of_expected_fail_test}`) returns
   `{"status": "fail", ...}` with the panic message.
4. A cold-start measurement: the first request after deploy, and the first
   request after a period of inactivity.
5. A per-invocation CPU-time sample (N ≥ 100 invocations) — median, range.
6. The import list from the deployed module — already verified as zero imports
   in Phase 0; re-verify in the deployed context.

**Blocked by:** U0, Cloudflare account provisioning. **Blocks:** U8.

---

#### U8. Worker volume run and cost ceiling

**Goal.** Run a volume of test invocations (≥ 10^4) against the deployed
Worker, measure the real per-invocation cost, and establish the cost ceiling for
Phase 1's continuous-operation model.

**Why.** D3's cost estimate (~$5–7/month) was based on a model, not a
measurement. A volume run replaces the model with data: how much does 10^5
invocations actually cost, what is the sustained throughput, and what rate
limits (if any) does the free tier impose?

**Protocol.**
1. Run the U5 volume protocol **against the Worker** instead of locally.
   N = 10^4 invocations (100 repetitions of 94 tests = 9,400; round to 10,000
   with a few extra repetitions).
2. Use a local client (Python script or `curl` loop) to issue N HTTP requests
   to the Worker, one per test invocation. Do not batch — the tier's model is
   one test per invocation.
3. Measure:
   - **Client-side latency** (median, p95, p99 per request) — this includes
     network round-trip, so it is an upper bound on CPU time.
   - **Throughput** (requests/second from the client's perspective).
   - **Failures** — any HTTP non-200, any Worker timeout, any rate-limit
     response (status 1015 or `cf-1000` error).
   - **Cost** — from the Cloudflare dashboard or API: total CPU time consumed,
     total requests, billed amount. If the free tier's 100,000 requests/day
     covers the run, cost is $0; if not, report the actual cost.
4. Compare the Worker per-invocation wall time against the local Node
   per-invocation wall time (U5). The ratio (Worker/Node) is the "platform
   overhead factor" — how much more CPU time the Workers isolate consumes
   compared to local V8. This factor feeds the continuous-operation cost model.

**Cost model — per D3's pricing (CPU-time + requests billing):**
- Free tier: 100,000 requests/day, 10 ms CPU time/request. Exceeding either
  incurs charges.
- Paid tier: $0.30/million requests, $0.02/million CPU-ms.
- **Phase 1 cost estimate:** 94 tests × 1,000 repetitions = 94,000
  requests/commit. At 10 commits/week (the U6 observation window), that's
  940,000 requests/week ≈ $0.28/week in request charges
  (940,000 × $0.30/1,000,000). CPU-time charges depend on the per-invocation CPU
  time measured in U7. **If the per-invocation CPU time is ≤ 1 ms (as local
  numbers suggest), the CPU-time cost is negligible (≤ $0.02/week). Total:
  $0.30/week, ~$1.20/month** — within D3's $5–7 estimate.

**Evidence that closes U8:**
1. The volume run completes — N invocations, M failures (M should be 0 or equal
   to the expected-fail count × repetitions, since expected-fail tests still
   return HTTP 200 with `status: "fail"` — they trap the WASM but not the
   Worker).
2. The cost report: actual billed amount (or free-tier consumption), total CPU
   time, requests count.
3. The platform overhead factor: Worker wall time / local Node wall time, and
   whether it is stable across repetitions.
4. `docs/evidence/2026-08-07-r19-worker-cost.md` with the raw numbers.

**Blocked by:** U7. **Blocks:** U9.

---

### U9. The Phase 1 verdict

**Goal.** One document, one table, one sentence about whether Phase 1 has
established the tier's first payload at scale.

**Files touched:** new `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`.

**Content.**

| Req / Goal | Verdict | Evidence | Consequence |
|---|---|---|---|
| Tier builds on main | PASS / FAIL | U0 | FAIL → nothing runs |
| R19 baseline established | PASS | U1 doc | Prerequisite for R19 measurement |
| Local at-scale runner | PASS | U2 doc | Prerequisite for volume run |
| Sharding design | COMPLETE | U3 doc | Answers Q4 |
| Coverage reporting (R7, R8) | COMPLETE | U4 doc | Non-vacuity |
| Local volume run ≥ 10^4 invocations | PASS | U5 doc | Throughput data |
| R19 sustained agreement | SUSTAINED / NOT YET | U6 doc | Licenses later gating |
| Worker deployed | DEPLOYED / DEFERRED | U7 doc | Platform proven |
| Worker volume run + cost | MEASURED / DEFERRED | U8 doc | Real cost data |

Followed by exactly one of:

> **Phase 1 complete.** The portable Rust test suite runs at volume on the
> WASM tier. Per-test verdicts agree with GitHub Actions across 10 consecutive
> commits — sustained agreement per R19. The Worker cost ceiling is measured at
> $X/month for the 94-test corpus at Y repetitions per commit. Phase 2 may be
> pulled when capacity allows.

or

> **Phase 1 incomplete.** [Ux] recorded [FAIL / DEFERRED / NOT YET] because:
> ... The tier's first payload is not yet established at scale. The units that
> passed stand; the units that did not are preconditions for a re-pull.

**What "Phase 1 complete" does NOT mean:**
- It does not license merge gating under R15 — that requires Phase 5's
  suite-by-suite transition, which was descoped from the parent plan.
- It does not retire `kicad-cli` — that is R9/R10, not Phase 1.
- It does not mean the tier is catching real bugs — that is Phase 3 (fault
  injection).

**Blocked by:** U0, U4, U6, U8.

---

## 2. The R19 verdict comparison protocol

Stated separately because it is the mechanism every R19-dependent unit uses and
because it is the Phase 1 artifact most likely to be referenced by later phases.

### Test name normalization

The wasm32 registry uses the Rust module path as the test name
(e.g., `board::tests::test_clearance`). Native `cargo test` output uses
the fully qualified path. Normalize by stripping the crate prefix
(`temper_drc_rs::`) from native names to match the wasm32 registry format.
If the native `cargo test` output format differs, normalize both to a
common format.

### Comparison matrix fields

```json
{
  "commit": "<sha>",
  "timestamp": "<ISO 8601>",
  "native": {
    "total": 94,
    "passed": 94,
    "failed": 0,
    "tests": [{"name": "...", "status": "pass"}]
  },
  "wasm32": {
    "total": 94,
    "passed": 90,
    "failed": 0,
    "expected_fail": 4,
    "unexpected": 0,
    "tests": [{"name": "...", "status": "pass"}]
  },
  "comparison": {
    "agree_pass": 90,
    "agree_fail": 0,
    "disagree": 0,
    "expected_fail": 4,
    "unexpected_pass": 0,
    "native_only": 0,
    "wasm32_only": 0,
    "agreement_rate": 1.0,
    "disagreements": []
  },
  "expected_failure_manifest": "tools/wasm/wasm_expected_failures.json",
  "expected_failure_manifest_sha256": "<sha256>"
}
```

### Agreement rate formula

```
agreement_rate = (agree_pass + agree_fail + expected_fail) /
                 (agree_pass + agree_fail + disagree + expected_fail + unexpected_pass)
```

Native-only and wasm32-only tests are excluded from the denominator — they
represent scope mismatch, not disagreement. A test in neither set (present in
both, not expected-fail, not disagreeing) is agree-pass or agree-fail.

### Sustained agreement assertion

```
SUSTAINED when:
  for every commit in the observation window [C_0, ..., C_9]:
    agreement_rate == 1.0
    AND unexpected_pass == 0
    AND no new failure classes appear in the expected-failure manifest
    AND the expected-failure manifest's sha256 matches the committed version
```

---

## 3. Sequencing summary

| Unit | Blocked by | Blocks | Evidence that closes it |
|---|---|---|---|
| U0 fix build | — | U1–U9 | `.wasm` artifact on disk; `run_wasm_tests.mjs` green |
| U1 R19 baseline | U0 | U6 | Per-test comparison matrix at a named commit |
| U2 local at-scale runner | U0 | U5 | `--repeat 1000` throughput report; planted-failure trap test |
| U3 sharding design | U0 | U5, U7 | Design doc with N=94, K recommendation, per-invocation timings |
| U4 coverage (R7, R8) | U0 | U9 | `test_family_map.json` + `coverage_report.py` + canary defects |
| U5 local volume run | U2, U3 | U6 | Throughput, memory, verdict stability across ≥ 9,400 invocations |
| U6 R19 sustained agreement | U1, U5 | U9 | 10-commit matrix; SUSTAINED or NOT YET verdict |
| U7 Worker deployment | U0, account | U8 | Worker reachable; single-test pass + expected-fail verified |
| U8 Worker volume + cost | U7 | U9 | Cost report; platform overhead factor; ≥ 10^4 invocations |
| U9 Phase 1 verdict | U0, U4, U6, U8 | Phase 2 | The verdict document with the summary table and one sentence |

**Critical path to a Phase 1 verdict:** U0 → U1 → U5 → U6 → U9 (Tracks A+C).
Track B (U2–U4) feeds into C. Track D (U7–U8) can run in parallel and is not
on the critical path — it can be deferred without blocking a local-volume
Phase 1 verdict.

**Phase 1 exits** when U9 exists. U7 and U8 may still be outstanding if the
Cloudflare account is not provisioned; that is an acceptable Phase 1 exit — the
local volume run and R19 agreement measurement are the gating milestones.
"Phase 1 complete" requires U0–U6; "Phase 1 complete with Worker deferred"
requires U0–U6 with U7/U8 marked DEFERRED.

---

## 4. Non-goals

Drawn from the parent plan's Scope Boundaries and D9. None of these is in Phase 1:

- **New property or metamorphic kernels.** D9 explicitly chose the existing test
  suite as the first payload over leading with new kernels. Property-based
  testing at volume is Phase 1's *mechanism* (run the suite at volume), not
  Phase 1's *content* (write new property tests).
- **The R3 producer.** Blocked on issue #871 (route OOM). Phase 1 uses the
  committed board — already content-addressed by its sha256 — not a freshly
  regenerated one. The producer remains R3's responsibility.
- **`kicad-cli` on Workers.** R9 keeps it in GitHub Actions.
- **Migration of the Python test suite.** Wave 4 owns it.
- **Suite-by-suite PR-pool relief (formerly Phase 5).** Removed from the parent
  plan in the requirements-update diff (D12–D15, R24–R28 removed). The tier's
  verdicts are advisory; they do not gate merges in Phase 1.
- **Durability machinery (R22, R23).** D10 gates it on gating; the tier is
  advisory in Phase 1, so a lost result costs a data point, not a merge.
- **Any Q7 memory strategy.** U5's verdict (Phase 0): "No memory strategy is
  required for Phase 1." The 2.94 MiB RSS leaves 125 MiB of headroom.
- **Adding `wasm-test-registry` to crates beyond `temper-drc-rs`.** Phase 1
  starts with the proven single-crate dispatch surface. Adding more crates is
  additive work (per the Q8 resolution below), not a redesign.
- **Closing issue #873 (routing-data gap).** See U3 — this plan defers.
- **CP-SAT solve or SAT-backed router.** Out per Scope Boundaries.
- **Editing the parent plan, the Phase 0 plan, any measurement baseline, or
  `power_pcb_dataset/drc_ceiling.json`.** Anything Phase 1 finds goes in the
  verdict document.
- **Phases 2–4.** D5 fixes their order and they are pulled individually.

---

## 5. What is genuinely uncertain

Recorded plainly, because a confident plan step down a dead end costs more than
an admitted unknown.

1. **Whether `workerd` (the open-source Workers runtime) is runnable locally.**
   The Phase 0 evidence doc notes it is not installed in this environment and
   was not tested. Phase 0 substituted Node's V8 (`run_wasm_tests.mjs`) and
   recorded that substitution as sanctioned. Phase 1's Track B continues that
   substitution; Track D measures on the real platform. If `workerd` can be
   installed locally, U2 and U5 could run against it — but this plan does not
   depend on it.

2. **The real per-invocation overhead on Workers vs. Node.** The local Node
   measurements (U2, U5) establish a lower bound. The Worker measurements (U7,
   U8) establish the real cost. The ratio between them — the "platform overhead
   factor" — is unmeasured until U8 completes. It could be 1.0× (identical),
   2.0× (cold-start and scheduling overhead), or 10× (unexpected isolate
   overhead). D3's cost estimate assumes it is small; U8 measures it.

3. **Whether 94 tests × 100–1,000 repetitions is a meaningful volume.**
   The 94 drc-rs tests are a static corpus — running them 1,000 times produces
   94,000 data points about *the same assertions*. Whether this counts as
   "volume" depends on the lens: it is volume in the "the tier sustains N
   invocations without degradation" sense, but it is not volume in the "the tier
   searched a parameter space no human would" sense (which is Phase 3 and 4's
   job). **This plan's answer: it is meaningful for proving the tier can sustain
   the invocation rate, and it is the necessary prerequisite for property-based
   volume in later phases.** The maintainer may disagree and ask for a larger
   corpus; expanding the dispatch surface to more crates (per the Q8 resolution)
   is the available lever.

4. **Whether the expected-failure manifest stays at 4 entries across 10
   commits.** The 4 entries (1 `no-dynamic-loader` + 3 `b7-pow-divergence-absent`)
   are stable for the current `origin/main` tip. A commit that adds a new test
   using `f64::powf(x, 3.0)` (which does NOT fold on wasm32 — see the
   pow-divergence doc §3) could introduce a new wasm32-native divergence. The
   U6 observation window is the mechanism that catches it.

5. **Whether the `#[cfg(feature = "python")]` gate will be re-introduced.**
   PR #751 ("DO NOT MERGE") landed despite its title. The regression guard U0
   fixes is one line; a subsequent PR could re-add it with the same "DO NOT
   MERGE" pattern. The existing `rust-checks` job's `wasm32 substrate guard` (U3
   of the Phase 0 plan, on branch `origin/wasm/u3-ci-guard`) would catch a
   build break, but it is not on `origin/main` yet. **Phase 1 should not gate on
   that guard landing**, but the U0 fix should include a comment at the
   `#[cfg(feature = "wasm-test-registry")]` site explaining the regression risk.

6. **Cost over 10 commits per week for months.** U8 measures the cost of one
   volume run. Extrapolating to continuous operation over months assumes the
   per-invocation cost is stable and that no rate-limit surprise emerges at
   higher sustained throughput. The monthly cost figure in U8 is an estimate, not
   a commitment; continuous operation costs are a Phase 5 concern (beyond even
   the parent plan's descoped Phase 5).

---

## 6. Open questions resolved

### Q8 — one dispatch table vs. per-crate (settled here)

**Recommendation: per-crate dispatch tables, starting with `temper-drc-rs` only
for Phase 1.**

**Evidence:**

1. **Rust privacy forces per-crate ownership.** `WASM_TESTS` consts live inside
   `#[cfg(test)]` modules in each crate. A unified dispatch table spanning
   multiple crates would require every crate to expose its test functions
   publicly, violating the existing privacy pattern and requiring a cross-crate
   re-export mechanism that does not exist.

2. **The existing infrastructure is single-crate.** `gen_wasm_test_registry.py`
   is hardcoded to `temper-drc-rs`. `temper-wasm-test-runner` depends on
   `temper-drc-rs` with `wasm-test-registry`. No other crate has the pattern.

3. **No other crate has proven zero-import `wasm32` builds.** `temper-geometry`
   has `rand`/`getrandom` dependencies on `wasm32` — putting it in the same
   `.wasm` module as `temper-drc-rs` would reintroduce the `getrandom` trap risk
   that Phase 0 eliminated by making the dependency optional.

4. **The 94 drc-rs tests are a meaningful starting volume.** At 100–1,000
   repetitions per commit, they produce 9,400–94,000 invocations — enough to
   measure throughput, verify determinism, and establish sustained agreement
   across 10 commits (94,000–940,000 total invocations over the observation
   window).

5. **Multi-crate is additive, not a redesign.** Adding `wasm-test-registry` to
   `temper-geometry` would follow the same pattern: add the feature flag, gate
   test modules with `#[cfg(any(test, feature = "wasm-test-registry"))]`, run
   `gen_wasm_test_registry.py` on the crate, add a new `temper-wasm-test-runner`
   dependency. The per-crate pattern composes; a unified dispatch table would
   require a new aggregation crate.

**Decision:** Phase 1 starts with `temper-drc-rs` only. The per-crate dispatch
table pattern is the architectural primitive. When capacity allows, additional
crates are added one at a time, each as its own unit — no unified dispatch table
is ever built. This matches the parent plan's Phase 5 suite-by-suite model
(descoped but structurally the same pattern).

### Local-first vs. Worker-first ordering (settled here)

**Recommendation: local volume run (U5) before Worker deployment (U7).**

**Evidence:**
1. **D3's pricing model.** Cloudflare bills CPU time + requests. Measuring
   throughput locally (zero cost) before committing any spend is the prudent
   ordering, and is consistent with D3's cost-conscious framing.
2. **The local runner already exists.** `run_wasm_tests.mjs` is on `main`. It
   needs the `--repeat` flag (U2), not a rewrite. The marginal cost of a local
   volume run is machine time — minutes, not dollars.
3. **A local volume run is a valid Phase 1 milestone on its own.** The tier's
   value is "the same checks at volume without consuming GitHub Actions
   capacity." Running 94,000 invocations locally proves the substrate can
   sustain the rate; deploying to Workers is an incremental step from a proven
   local baseline, not a leap into the unknown.
4. **The Worker units are gated on account provisioning**, which is outside
   this plan's control. The local units are not. Sequencing local-first means
   Phase 1 can deliver a verdict (U9) even if the Cloudflare account arrives
   after the rest of the work is done.

**Decision:** Tracks B and C (local infrastructure + volume) precede Track D
(Worker deployment). U5 gates U6 (R19 sustained agreement), and U6 is the
critical-path milestone. U7 and U8 are parallel and can be deferred without
blocking the Phase 1 verdict.

### The R19 agreement bar (specified in §U6, summarized here)

Sustained agreement = 100% pass/fail agreement (including pre-classified
expected-failures) across 10 consecutive commits on `origin/main`. No
unexpected passes, no new failure classes. A disagreement resets the counter.
The bar licenses later gating under R15 (Phase 5, descoped); it does not itself
gate merges in Phase 1.

---

## 7. What this plan believes is wrong or underspecified upstream

1. **The `#[cfg(feature = "python")]` gate is a regression on `origin/main`.**
   Diagnosed in `docs/evidence/2026-08-06-wasm32-float-divergence.md` §7. This
   plan's U0 fixes it. The parent plan's CI guard (Phase 0 U3, on branch
   `origin/wasm/u3-ci-guard`) would catch a re-introduction — but it is not on
   `main` yet. **Recommendation:** land the CI guard before or with U0.

2. **The parent plan's R17/R18/R19 and Q8 are on branch
   `docs/wasm-tier-requirements-update` (commit `82313a812`), not on
   `origin/main`.** This plan incorporates them as settled per the dispatch
   instructions. The diff also removes D12–D15 and R24–R28 (the suite-by-suite
   PR-pool relief extension), which simplifies Phase 1's scope. If the
   requirements-update branch is not merged before Phase 1 is pulled, the
   executor should verify that D9/R17/R18/R19 remain the governing decisions.

3. **The Phase 0 plan §5 item 5 flagged "the test-dispatch question is
   genuinely unowned today."** This plan's Q8 resolution (§6) provides the
   owner: per-crate dispatch tables, `temper-drc-rs` only for Phase 1,
   additional crates added additively. The question is closed.

4. **No requirement covers the volume-run target.** R17 says "one test per
   Worker invocation" but does not say how many invocations. This plan provides
   the target: N ≥ 9,400 (100 repetitions of 94 tests) for the local volume
   milestone, N ≥ 94,000 (1,000 repetitions) as the stretch target, and the
   10-commit observation window as the sustained-agreement span.

5. **The expected-failure manifest is not referenced by any requirement.** R19
   says "per-test verdicts are compared," but the expected-failure mechanism is
   the necessary complement — without it, every wasm32-native divergence would
   be a "disagreement" that prevents the agreement bar from ever being met. This
   plan formalizes the expected-failure manifest as part of the R19 protocol
   (§2).

---

## Sources / Research

- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — the
  requirements plan this enriches. D3, D4, D5, D6, D9, D10, R4–R23, Q4, Q8.
- `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` — the Phase 0 plan,
  whose structure this plan mirrors.
- `docs/evidence/2026-08-05-wasm-tier-phase0-verdict.md` (branch
  `origin/wasm/u9-phase0-verdict`) — R1 PASS, R2 PASS, R3 BLOCKED-UPSTREAM,
  D3 STANDS.
- `docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md` (branch
  `origin/wasm/u1-rung23-closing`) — U1 rungs 2–3: zero imports, 95 tests
  executed, 91 pass + 4 expected-fail, all six families exact-match.
- `docs/evidence/2026-08-06-wasm32-float-divergence.md` — the B7 pow-divergence,
  the wasm32 build regression diagnosis (§7), and the corpus search finding zero
  DRC verdict flips.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the 43-
  requirement validation menu; portfolio R11, R30, R38, R42 referenced by the
  parent plan.
- `packages/temper-wasm-test-runner/src/lib.rs` — the cdylib entry point; ABI
  v1, one-test-per-invocation, panic→abort→trap signalling.
- `packages/temper-drc-rs/src/wasm_test_registry.rs` — the build-time dispatch
  table: 95 tests across 16 modules, flat-indexable.
- `tools/wasm/run_wasm_tests.mjs` — the Node/V8 host driver; compile,
  instantiate, per-test timing, trap handling, expected-failure reclassification.
- `scripts/gen_wasm_test_registry.py` — the dispatch-table codegen; currently
  hardcoded to `temper-drc-rs`.
- `tools/wasm/wasm_expected_failures.json` — the expected-failure manifest: 4
  entries.
- Git diff `origin/main`..`docs/wasm-tier-requirements-update` — the D9/R17/R18/
  R19/Q8 additions and the D12–D15/R24–R28/Phase 5 removals.
