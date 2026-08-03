---
title: DRC Trio Parallelization - Plan
type: perf
date: 2026-08-03
topic: drc-trio-parallelization
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# DRC Trio Parallelization - Plan

## Goal Capsule

- **Objective:** Parallelize the trio's serial kicad-cli DRC-measurement loops — bounded to core count, with loud timeout handling — so the PR slow lane gains wall-clock margin (5.2-5.8 min serial today, target ~3.5 min) and the nightly hybrid test fits comfortably in its 30-min budget. Fix the slow lane's silent guard failure. Then run an evidence protocol whose step-level <6 min verdict decides whether the Cloudflare containers-as-runners migration becomes the primary follow-up plan.
- **Product authority:** Temper maintainers; scope decisions made in brainstorm dialogue 2026-08-03 and re-scoped at plan time against the live lane shape (hybrid moved to nightly 08-01, commit `a6fafeb7b`).
- **Open blockers:** None.
- **Stop condition:** The verdict doc lands in `docs/evidence/` with run/job IDs and provenance, and the migration decision is recorded there, on speed grounds alone.

---

## Product Contract

### Summary

Restructure the trio's serial DRC-measurement loops (35 kicad-cli subprocesses across the three tests) to run under bounded concurrency with loud failure handling, keeping the measurement design and the current lane placement unchanged. Pair the change with an evidence protocol measuring the PR slow lane's step-level span across N runs; the <6 min verdict parks the Cloudflare migration, a miss makes it the primary follow-up.

### Problem Frame

The cp-sat lane was 20m45s-22m38s with three tests consuming >98% of its pytest span, measured 2026-07-29 and 2026-07-30 (docs/evidence/2026-07-29-extended-suites-timeout-split.md, `.github/workflows/python-tests.yml:1758-1847`). The trio's cost is structural, not solver-bound: serial loops of route + fill + kicad-cli DRC subprocesses, each with per-call timeouts, nothing concurrent (`packages/temper-placer/tests/placer/cp_sat/test_hybrid_pour_stitch_measurement.py:76-163`). The routing path is ortools-free (Rust-backed); other CP-SAT tests solve with `time_limit_s=1-2` and are fast. Prior speedup attempts misattributed the cost to setup duplication; that hypothesis was disproven 2026-07-30 (`.github/workflows/python-tests.yml:1758-1770`).

The lane changed twice since that measurement. Commit `3321510a2` (#485, 07-30) split the trio into `extended-cpsat-slow`. Commit `a6fafeb7b` (08-01) moved the 877-987s hybrid test to nightly `r9-evidence.yml` (schedule 04:15 UTC + `workflow_dispatch`, `r9-evidence.yml:16-18,110`), cutting ~16 min per PR. The PR slow lane today runs the pair — zone-pour XFAIL (~211s) and routing-DRC regression (~102s, flaky) — at a 313-348s pytest span, i.e. 5.2-5.8 min already serial (`.github/workflows/python-tests.yml:2007-2013`).

Three problems remain in the current shape. The slow lane's `pytest_guard --min-tests 2` counts the XFAIL zone test as skipped (JUnit semantics) and exits 3 on every run, masked by `continue-on-error: true` (`.github/workflows/python-tests.yml:2143-2149`). Both in-lane `_run_drc` helpers convert timeouts and missing outputs into silent `pytest.skip`, reporting green (test_zone_pour_production_measurement.py:254-266, test_regression_drc.py:100-115). And `test_regression_drc.py:82` uses `tempfile.mktemp`, a documented race hazard that becomes dangerous once DRC calls run concurrently.

### Key Decisions

- K1. **Lane placement stays as of 2026-08-01: hybrid nightly, pair in the PR slow lane** (session-settled: user-directed — chosen over reverting the 08-01 nightly move: the move saved ~16 min/PR and was deliberate). Governs R4.
- K2. **Parallelize execution, never the measurement design** (session-settled: user-approved — chosen over sample reduction: the R9 evidence base stays statistically identical — 4 seeds x 3 samples x 2 flag configs for the hybrid, 2 arms x 3 samples for zone-pour, 5 samples for routing-DRC). Governs R1, R2.
- K3. **Concurrency bounded to core count, timeouts loud** (session-settled: user-directed — chosen over unbounded parallel DRC: the tests' own 600s timeouts have already fired spuriously under load, and silent skips would corrupt a gate). Governs R3.
- K4. **Evidence decides CPU need** (session-settled: user-directed — chosen over pre-committing to a 4-vCPU migration: if bounded parallelism on 2 CPUs cannot hold the threshold, the migration stops being conditional). Governs R6.
- K5. **Step-level <6 min as the verdict threshold** (session-settled: user-directed — chosen over job-level or delta-only metrics: the job includes ~2.5 min of setup that no test change affects, so the step is the honest lane measure; job-level span is recorded as context). Governs R6.

### Requirements

**Test restructure**

- R1. The zone-pour and routing-DRC tests (PR slow lane) and the hybrid test (nightly) run their per-arm, per-seed, and per-sample DRC work concurrently, with concurrency bounded to the runner's CPU count.
- R2. The measurement design is unchanged: 4 seeds x 3 DRC samples x 2 flag configs for the hybrid test, 2 arms x 3 samples for the zone-pour test, 5 samples for the routing-DRC test; no seeds, sample counts, or flag sets change.
- R3. A DRC subprocess that fails — per-call timeout or missing output — produces a visible, recorded event naming the subprocess, the timeout, and the test; it is never a silent skip that reports green.
- R4. Lane placement is unchanged by this work: hybrid in nightly `r9-evidence.yml`, the pair in the PR `extended-cpsat-slow` lane.
- R5. The slow lane's `pytest_guard` floor accounts for the XFAIL zone test, so the guard passes genuinely instead of failing silently under `continue-on-error`.
- R6. The migration trigger is the slow lane's step-level pytest span against a <6 min threshold: the median of N PR runs (N=5, repo precedent), with the recorded range as context — at or over 6 min → the Cloudflare containers-as-runners migration becomes the primary follow-up plan; under 6 min → it stays parked.
- R7. The verdict and its underlying measurements are recorded in `docs/evidence/` with run/job IDs, a persistent SHA (PR base ref or merge commit, not a squash-orphaned branch SHA), and the board content hash per run, per the repo's measurement-provenance contracts.
- R8. The trigger is speed-only: cost and queue-contention signals are recorded where observed but do not fire the trigger in this plan; they ride into the follow-up migration plan.
- R9. Concurrent DRC calls never share un-reserved temp file names; `tempfile.mktemp` is removed from the trio's DRC paths before any concurrency lands.
- R10. The nightly hybrid test keeps its node ID and invocation flags (`-s -rs`) so `r9-evidence.yml` needs no changes in this work.

### Key Flows

- F1. Measure-verdict flow
  - **Trigger:** The restructure merges and PR runs begin carrying it.
  - **Steps:** PR runs execute the restructured pair → evidence collector gathers the slow lane's step-level span from N runs (gh api job timestamps, `gh run view --log` gap analysis) → verdict computed against the <6 min threshold (R6) → either "fix sufficient" (migration parked; cost/contention notes forwarded per R8) or "migration primary" (follow-up plan opens).
  - **Outcome:** Verdict and measurements recorded in `docs/evidence/` with provenance (R7).
  - **Covered by:** R5-R8.

### Acceptance Examples

- AE1. Covers R1, R2: the zone-pour test completes with the exact same 2 arms and 3 samples per arm, and the routing-DRC test with 5 samples; DRC samples run concurrently rather than serially.
- AE2. Covers R3: a DRC subprocess exceeding its timeout under runner load yields a visible failure naming the subprocess, timeout, and test in the job log, and the run is not reported green with a silent skip.
- AE3. Covers R4, R10: after the change, the pair still executes in `extended-cpsat-slow` and the hybrid still executes in nightly `r9-evidence.yml`; no workflow edit moves a test or renames a job.
- AE4. Covers R6, R7: N PR runs show the slow lane at or over 6 min → a `docs/evidence/` entry records the verdict and the follow-up migration plan opens; N runs show it under 6 min → the entry records "fix sufficient" and no migration plan opens on speed grounds.
- AE5. Covers R5: the slow lane's guard prints a genuine pass (no exit-3 under the mask), verified from the job log.

### Success Criteria

- The slow lane's step-level span is under 6 min across N PR runs, with the parallelization recovering margin over the 5.2-5.8 min serial baseline (target ~3.5 min: `max(211s, 102s)` plus overhead).
- The slow lane runs guard-green without relying on `continue-on-error` masking (R5).
- No change to the measurement design (R2) or the lane placement (R4).
- The verdict entry lands in `docs/evidence/` with run and job IDs, a persistent SHA, and the board hash (R7).

### Scope Boundaries

**Deferred for later**

- The Cloudflare migration itself — containers-as-runners on Cloudflare Containers/Sandboxes (GA 2026-04-13); this plan defines only its trigger (R6).
- Pure-Workers wasm/Pyodide fan-out of the PBT suites — the original brainstorm idea, parked; candidate lane for a later plan.
- Stabilizing `test_production_board_routing_drc_regression`'s flakiness — known issue, marked out of scope for CI-timing work (`.github/workflows/python-tests.yml:1785-1788`); its 5-sample parallelization (R1) must not alter its assertion semantics.
- Whole-PR wall-clock and the other 20+ jobs (setup tax, rust-checks, corpus-batch, firmware) — the target is lane-scoped by decision (K5).
- The 2026-09-01 `continue-on-error` TODO on the cp-sat steps — gate re-hardening is a separate item; this plan adds no new `continue-on-error`.

**Deferred to Follow-Up Work**

- Reverting the 08-01 nightly move of the hybrid test — rejected at plan time (K1).
- A dedicated CI-timing collector script — the repo's manual `gh`/`gh api` evidence method is the established convention (docs/evidence/2026-07-29-*); a script would add a `scripts/manifest.yaml` entry and a sunset clock for no proven gain.

**Outside this plan's identity**

- Changes to the CP-SAT solver, ortools usage, or kicad-cli/DRC engine behavior — the trio's cost is loops plus subprocesses, not the solver.
- Cloudflare Workers Builds — evaluated and rejected as a deploy-only product (build plus `wrangler deploy` for Workers apps), not a general CI platform.

### How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns the trio restructure, the slow-lane guard fix, and the migration trigger. The broader Cloudflare-migration intent from the 2026-08-03 brainstorm is current understanding, not a committed roadmap:

- Cloudflare containers-as-runners migration — Depends on this plan's verdict (R6); tentative
- Pure-Workers wasm/Pyodide PBT fan-out — Still to decide; candidate for a later plan, can proceed independently of this one
- docs/plans/2026-07-23-004-perf-ci-pipeline-speedup-plan.md — Shares the 6-9 min whole-pipeline ambition; partially superseded by this plan's lane-scoped target

### Dependencies / Assumptions

- The repo's evidence discipline (gh api job timestamps, `docs/evidence/` entries with provenance) remains available to whoever runs the protocol.
- The 2-CPU runner profile stays in effect while the verdict is being measured; a runner profile change mid-measurement would invalidate the baseline (R6 assumes a stable runner).
- The kicad-cli per-call latency profile and the 600s/120s timeout ceilings stay as measured.
- The temper-ci container remains the execution environment; no image changes are planned in this work.
- The R9 promotion decision is pending and needs the trio's evidence; the measurement design stays intact until R9 resolves (K2).
- The trio does not consume the netlist build; a netlist cache miss adds setup time but does not affect the trio's correctness.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Bounded in-test `ThreadPoolExecutor` for DRC subprocess calls** (session-settled: user-directed — instantiates K3, governs R1, R3: xdist was explicitly rejected for this lane in docs/evidence/2026-07-29-extended-suites-timeout-split.md — it only parallelizes other tests around the slow ones; unbounded parallel DRC risks the per-call timeouts; `subprocess.run` releases the GIL during the wait, so threads are the correct mechanism for subprocess-bound work, and `os.cpu_count()` bounds to the runner's 2 cores).
- KTD2. **Keep `-n auto --dist loadgroup` on the slow job; in-test concurrency is additive** — `-n` without `loadgroup` turns `xdist_group`-tagged dependents into skips, a hard repo convention (`.github/workflows/python-tests.yml:2133-2134`). Lane-level parallelism stays; in-test concurrency adds a second axis.
- KTD3. **Loud failure = hard failure inside the test** (governs R3: per docs/solutions/best-practices/three-silent-failures-measurement-pipeline-2026-07-07.md, subprocess exit-code discipline means a timeout or missing output raises, naming the subprocess, the timeout value, and the test. No new `continue-on-error` is added — the existing TODO'd flag on the cp-sat steps stays untouched until its 2026-09-01 hard-fail date. A timeout must also kill the kicad-cli process group, not just the direct child, which `subprocess.run(timeout=...)` alone does not do).
- KTD4. **Slow-lane guard floor drops to 1 with explicit XFAIL accounting** (governs R5: pytest reports `xfail(strict)` as JUnit `<skipped>`, so the guard's executed count for a 2-test lane containing the XFAIL zone test is 1, and `--min-tests 2` exits 3 every run. The fix is lane-local — floor 1 with a comment naming the XFAIL test — not a global change to `pytest_guard.py` semantics, which would silently re-base every other lane's floor).
- KTD5. **Evidence doc provenance rides the measurement-provenance contracts** (governs R7: per docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md, a branch SHA is orphaned by squash-merge — stamp the PR base ref or merge commit; the board is mutable, so record its content hash per run via the `drc_ceiling.json` provenance mechanism; `commit=UNKNOWN` without an `.evidence-provenance-allowlist` entry is a deterministic gate failure — PR #435's defect).

### High-Level Technical Design

The approach is a one-paragraph pattern application: wrap each test's serial `_run_drc` loop in a bounded executor (pool size = `os.cpu_count()`), sharing one helper module, and replace silent `pytest.skip` paths with raising failures. No cross-component topology, state machine, or protocol needs a diagram; the KTDs above carry the load-bearing decisions.

---

## Implementation Units

### U1. Shared bounded-concurrency DRC runner helper

- **Goal:** Provide the trio's tests one helper that runs DRC subprocess calls under concurrency bounded to `os.cpu_count()`, with loud failure semantics, and is itself unit-tested.
- **Requirements:** R1, R3, R9
- **Dependencies:** None.
- **Files:**
  - create `packages/temper-placer/tests/placer/cp_sat/_parallel_drc.py`
  - create `packages/temper-placer/tests/placer/cp_sat/test_parallel_drc_helper.py`
- **Approach:**
  1. Model the helper as a small function pair: a bounded map over DRC work items (board path, sample index) and a loud `run_drc` that raises on timeout or missing output instead of returning a skip signal.
  2. Bounds: pool size `min(os.cpu_count(), len(work_items))`; each call site passes its own work list so the measurement design stays at the call site (K2).
  3. Timeout handling: `subprocess.run(..., timeout=..., start_new_session=True)`; on `TimeoutExpired`, kill the process group, then raise with the subprocess name, timeout value, and test name (KTD3).
  4. Temp files: all outputs via `tempfile.mkstemp`; no `mktemp` anywhere in the helper (R9).
  5. Keep the helper stdlib-only (`concurrent.futures`, `subprocess`, `tempfile`) — test-tree modules are outside the import-linter contracts and the coverage gate, but `scripts/check_undeclared_imports.py` still requires stdlib or declared deps.
- **Execution note:** Implement the helper test-first — its scenarios below are the contract; the repo's TDD convention applies.
- **Patterns to follow:** `tools/spice/corner_sweep.py:15,154` is the repo's only process-pool precedent; `tempfile.mkstemp` usage in `test_zone_pour_production_measurement.py:225-273` is the temp-file pattern to mirror.
- **Test scenarios:**
  - Happy path: 4 DRC work items on a 2-CPU machine run with a 2-worker pool and return all results.
  - Bound behavior: more work items than cores never exceed `os.cpu_count()` concurrent subprocesses (verify via a probe that records concurrency).
  - Error path: a fake subprocess that exceeds the timeout raises the loud failure naming the subprocess and timeout (Covers AE2).
  - Error path: a fake subprocess that produces no output raises the loud failure.
  - Isolation: concurrent runs use distinct `mkstemp` paths — no two work items share a path (Covers R9).
  - Orphan reaping: a timed-out fake subprocess's process group is killed, verified via a sentinel file the child would write after the timeout.
- **Verification:** `cd packages/temper-placer && uv run pytest tests/placer/cp_sat/test_parallel_drc_helper.py -v --tb=short` green; helper imports resolve in the synced env (no undeclared imports).

### U2. Zone-pour test adopts the helper

- **Goal:** The PR-lane zone-pour test runs its 2 arms and 6 DRC samples under bounded concurrency, with the measurement design byte-identical.
- **Requirements:** R1, R2, R3
- **Dependencies:** U1
- **Files:**
  - modify `packages/temper-placer/tests/placer/cp_sat/test_zone_pour_production_measurement.py`
- **Approach:**
  1. Replace the serial per-arm `_run_drc` loop (lines ~225-273, ~353-360) with the U1 helper; arm routings stay sequential (they share the parsed stub and must not run concurrently).
  2. Keep `_DRC_SAMPLE_RUNS = 3`, both arms, all flags, and the XFAIL marker verbatim (K2, and the marker's accepted-negative reason at lines 426-435).
  3. The test's `_run_drc` stays as the public seam the nightly hybrid imports (`.github/workflows/r9-evidence.yml` and the hybrid's `from tests.placer.cp_sat.test_zone_pour_production_measurement import ...`); re-export the loud variant so imports keep resolving.
- **Test expectation:** The test's own assertions are the scenarios — it runs unchanged except for wall-clock and failure mode. No new test file.
- **Verification:** `uv run pytest 'tests/placer/cp_sat/test_zone_pour_production_measurement.py::TestZonePourProductionMeasurement::test_zone_pours_reduce_unconnected_items' -v --tb=short` — XFAILs as before (assertion unchanged), completes faster, and the job log shows no silent-skip paths (Covers AE1, AE5).

### U3. Routing-DRC regression test adopts the helper

- **Goal:** The PR-lane routing-DRC test runs its 5 DRC samples under bounded concurrency after removing its `mktemp` race hazard.
- **Requirements:** R1, R2, R3, R9
- **Dependencies:** U1
- **Files:**
  - modify `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`
- **Approach:**
  1. Replace `tempfile.mktemp(suffix=".json")` (line 82) with `mkstemp` before anything else (R9) — this is the race hazard that becomes live the moment samples run concurrently.
  2. Route `_drc_median`'s 5 samples (PRODUCTION_DRC_SAMPLE_RUNS, lines ~612, ~797-835) through the U1 helper; the median computation stays serial over the collected samples so assertions are unchanged.
  3. Do not touch the test's assertion baselines, the baseline-shape guard, or the known flakiness (out of scope; `.github/workflows/python-tests.yml:1785-1788`).
- **Test expectation:** The test's own assertions are the scenarios — unchanged semantics, faster wall-clock, no silent-skip path. No new test file.
- **Verification:** `uv run pytest 'tests/placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression' -v --tb=short` — passes or fails on the same baselines as before, without the `mktemp` path (grep for `mktemp` returns no match in the trio).

### U4. Nightly hybrid test adopts the helper

- **Goal:** The nightly hybrid test (8 routings, 8 fills, 24 DRC samples) runs its sample loops under bounded concurrency so it fits its 30-min budget with margin.
- **Requirements:** R1, R2, R3, R10
- **Dependencies:** U1
- **Files:**
  - modify `packages/temper-placer/tests/placer/cp_sat/test_hybrid_pour_stitch_measurement.py`
- **Approach:**
  1. Replace the import seam from `test_zone_pour_production_measurement` (lines 29-33) with the U1 helper for DRC samples; routings stay sequential per seed (they share the parsed stub).
  2. Parallelize the DRC sample loop within each seed (lines ~105-115, ~150-160) via the helper; keep seeds sequential so the per-seed evidence ordering in the report stays readable.
  3. Keep the node ID, `-s -rs` invocation, docstring, and soft-report shape verbatim; no `r9-evidence.yml` change (R10).
- **Test expectation:** The test's own soft-report structure is the scenario — same seeds/samples/configs, same printed report shape, faster completion. No new test file.
- **Verification:** `uv run pytest 'tests/placer/cp_sat/test_hybrid_pour_stitch_measurement.py::TestHybridPourStitchVerification::test_hybrid_pour_reduces_unconnected_without_shorting_regression' -v --tb=short -s -rs` completes within the 30-min budget on a 2-CPU machine (locally or via `workflow_dispatch`).

### U5. Slow-lane guard floor fix

- **Goal:** The `extended-cpsat-slow` lane stops failing its guard silently on every run.
- **Requirements:** R5
- **Dependencies:** U2, U3 (the lane's tests change in the same PR)
- **Files:**
  - modify `.github/workflows/python-tests.yml` (the `extended-cpsat-slow` job invocation)
- **Approach:**
  1. Change the slow lane's `pytest_guard.py --min-tests 2` to `--min-tests 1` with an inline comment: the zone test is `xfail(strict)`, pytest counts it as JUnit-skipped, so the lane's executed count is the routing test alone (KTD4).
  2. Audit the other guard floors in the same file (requirements-tests 240, extended-cpsat 400, invariant groups 1-3 500, invariant group 4 3, invariant-rest 1200) for the same XFAIL-vs-floor interaction; fix only lanes where a scoped XFAIL test exists, with the same lane-local treatment.
  3. No job renames — `required-checks.json` matches by job `name:` and must not change (`.github/required-checks.json:88-106`).
- **Test expectation:** none — workflow configuration; verified by reading the job log.
- **Verification:** `actionlint` on the workflow change (`brew install actionlint`, `SHELLCOPE_OPTS='--severity=error' actionlint -ignore 'constant expression "false" in condition'`); on the next PR run, the job log shows `[pytest-guard] PASS` instead of the exit-3 FAIL line (Covers AE5).

### U6. Evidence protocol and verdict doc

- **Goal:** Measure the restructured slow lane across N PR runs and record the verdict with provenance, per the repo's evidence conventions.
- **Requirements:** R6, R7, R8
- **Dependencies:** U1-U5 (verdict measures the restructured lane)
- **Files:**
  - create `docs/evidence/2026-08-XX-slow-lane-verdict.md` (date and name at write time)
- **Approach:**
  1. Method (repo precedent, no new script): per PR run, `gh api repos/BennetLeff/temper/actions/jobs/<id>` for step `started_at`/`completed_at`; `gh run view <job-id> --log` timestamp-gap analysis for the pytest step span; record queue time separately from execution time (R8).
  2. N=5 PR runs on the same runner class; record each run's board content hash (measurement-provenance contract) and note any board changes mid-protocol.
  3. Verdict against R6: step-level span < 6 min across the runs → "fix sufficient"; at or over 6 min → "migration primary".
  4. Provenance: stamp the doc with the PR's `baseRefOid` or merge commit SHA — never a branch SHA that squash-merge orphans (KTD5) — or add an `.evidence-provenance-allowlist` entry with a ticket in the same PR.
  5. Report the median and range, not single samples; state plainly when data is insufficient (docs/evidence/2026-07-29-ci-health-after-split.md:139-169 is the discipline template).
- **Test expectation:** none — evidence artifact, not code.
- **Verification:** `scripts/check_evidence_provenance.py` passes on the doc (real, existing SHA); the verdict and its per-run numbers are internally consistent with the recorded run/job IDs (Covers AE4).

---

## Verification Contract

- **Unit tests:** `cd packages/temper-placer && uv run pytest tests/placer/cp_sat/test_parallel_drc_helper.py -v --tb=short`
- **Trio tests, individually:** the three node IDs from U2/U3/U4, each run with `-v --tb=short` (plus `-s -rs` for the hybrid)
- **Slow-lane simulation:** `cd packages/temper-placer && uv run python ../../scripts/pytest_guard.py --min-tests 1 -- <zone node ID> <routing node ID> -v --tb=short -p no:cacheprovider --maxfail=10 -n auto --dist loadgroup` — guard prints PASS (Covers AE5)
- **Gates:** `uv run python scripts/import_linter_gate.py` (no new src modules, but the gate runs in CI); `actionlint` on the `.github/workflows/python-tests.yml` change; coverage gate unaffected — no new public `temper_placer` functions (helpers live in the test tree); `scripts/check_undeclared_imports.py` clean (stdlib-only helper)
- **Measurable threshold (the plan's optimization exit criterion):** slow-lane step-level span < 6 min across N=5 PR runs, with the pair recovering margin toward ~3.5 min (`max(211s, 102s)` plus overhead); nightly hybrid within its 30-min budget
- **Evidence gate:** `scripts/check_evidence_provenance.py` passes on the verdict doc

---

## Definition of Done

**Global:**

- All of U1-U6 landed in one PR series; no unit left partially merged.
- The slow lane's step-level span is under 6 min across N=5 PR runs (R6) and the guard passes genuinely (R5) — verified from job logs, not from the checks UI alone.
- No change to the measurement design (R2), lane placement (R4), or the nightly hybrid's node ID and flags (R10) — verified by diff.
- The verdict doc is in `docs/evidence/` with run/job IDs, persistent SHA, and board hashes, and the evidence-provenance gate passes (R7).
- No new `continue-on-error` added anywhere; the existing TODO'd flags are untouched.
- Cleanup criterion: any abandoned concurrency approaches from the implementation (alternate executors, dead helper variants) are removed from the diff — no dead-end code ships.

**Per-unit:**

- U1: helper tests green; helper is stdlib-only; no `mktemp` anywhere.
- U2: zone-pour test XFAILs as before, faster, no silent-skip path.
- U3: routing-DRC test passes/fails on the same baselines; `mktemp` gone.
- U4: hybrid test completes within budget with the same printed report shape.
- U5: slow lane logs `[pytest-guard] PASS`; no other lane's floor silently broken by the audit.
- U6: verdict doc written, provenance-valid, internally consistent with run IDs.
