---
title: Solve-Gap Oracle & Certificate - Plan
type: feat
date: 2026-08-02
topic: optimality-gap-certificate
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R14, R25)
---

# Solve-Gap Oracle & Certificate - Plan

## Goal Capsule

**Objective:** Compute a relaxation-based lower bound on the objective per solve, and report and register the solver gap per solve against expected-gap bounds per problem class — so a gap beyond a measured threshold flags weak search (separating a "valid" placement from a "good" one) and a worsening gap beyond bound fails, distinguishing tuning drift from real regressions.

**Product authority:** temper-placer maintainer (single-maintainer project; this plan is pulled from the portfolio menu, not scheduled).

**Open blockers:** none. The expected-gap bounds per problem class are a measured-at-pull-time quantity (origin Outstanding Questions convention); this plan measures them on the corpus boards as its own unit.

---

## Product Contract

### Summary

Every CP-SAT solve already records an objective value. It does not record the solver's own lower bound on that objective, so a feasible-but-weak placement is indistinguishable from a well-optimized one. This plan surfaces the relaxation bound (`BestObjectiveBound`) into the solve result, computes a relative gap, and feeds that one gap to two consumers: the oracle, which classifies weak search against a measured per-class threshold (R14), and the certificate, which registers every solve's gap against a provenance-attributed per-class bound and fails a worsening gap (R25). The oracle distinguishes "the solver found a placement" from "the solver searched well"; the certificate makes the expectation explicit and registered so the same signal is classified by its class bound instead of by whoever happens to read the log.

First-run honesty: on large boards the CP-SAT relaxation bound can be loose — the observed max gap may approach 100% until a regression occurs. The gap check is a regression detector, not a first-run quality gate; per-class bounds must be pinned from the observed gap distribution on accepted solves, not from the first measurement alone.

### Problem Frame

A solve that returns `FEASIBLE` proves constraint satisfaction, not search quality. When the abstract model diverges from reality or the encoding weakens, the solver still returns a placement — the metric is self-scored and the weakness is invisible. A solver that returns a worse gap is also ambiguous: it may be a real regression in placement quality, a tuning drift in solver parameters, or noise. A lower bound on the objective is the missing yardstick: a small gap means the returned objective is provably near the best possible under the model, a large gap means the search stopped early or the encoding is weak. The certificate makes that expectation explicit and registered, so the same signal is classified by its class bound instead of by whoever happens to read the log.

### Requirements

- R14. A relaxation-based lower bound on the objective is computed per solve — a gap beyond a measured threshold flags weak search, separating "valid" from "good".
  - **Success signal:** every solve result carries a bound and a gap; a gap beyond the measured threshold for its problem class fails the run with the bound and incumbent reported. Because on large boards CP-SAT bounds can be loose, the observed max gap may approach 100% until a regression occurs — the separating-valid-from-good framing applies once per-class thresholds are pinned from the observed gap distribution on accepted solves, not from the first run.
- R25. Solver gap is reported and registered per solve with expected-gap bounds per problem class — a worsening gap beyond bound fails, distinguishing tuning drift from real regressions.
  - **Success signal:** each solve writes a certificate (gap, class, bound, verdict); a gap above its class bound fails the run; the bounds file records every prior bound move with an attributed cause.

### Key Technical Decisions

- KTD1. **Use the CP-SAT solver's own relaxation bound.** OR-Tools exposes the best objective bound of its LP/CP relaxation via `BestObjectiveBound()`; that bound is the relaxation-based lower bound this idea names. Rationale: it is a genuine lower bound on the minimized objective and requires no new relaxation machinery.
- KTD2. **Report the relative gap, not the absolute.** Gap is `(objective − bound) / objective`, so the threshold generalizes across problem classes of different objective scale; one bound computation feeds both the oracle classification and the certificate, with no duplicated machinery. Rationale: absolute gaps on the temper board's integer grid units are not comparable to a minimal synthetic board's.
- KTD3. **Bounds are measured per problem class from the observed gap distribution on accepted solves — not pinned from the first measurement alone.** The oracle is a regression detector: its value is in flagging a gap that *worsens* past a class's expected range. A single first-run sample has no distribution to anchor to, so the measurement unit samples each class and pins the bound above the observed max with headroom. Rationale: an unmeasured threshold is either vacuously loose or brittle; the origin defers thresholds to pull time.
- KTD4. **Adopt the `drc_ceiling.json` provenance-and-march pattern for the bounds registry.** The registry carries a content-hash provenance block and a `_march`-style log attributing every bound change to a cause, validated by a dedicated enforcement script (mirroring `scripts/check_drc_ceiling_approval.py` and `scripts/check_measurement_provenance.py`) rather than only by the test suite. Rationale: this is the repo's existing, enforced convention for "expected bounds that move only with attribution"; a new format would lose the enforcement discipline.
- KTD5. **A bound rise requires an attributed cause and a measured sample.** A class bound moves only for measured noise or a deliberate, attributed change — never to absorb an unexplained regression. Rationale: mirrors the DRC-ceiling rule that a rise must not silently ratchet past a regression.

### Assumptions

- A1. No seed is named in the origin for either R-ID. The solve-result surface is `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py` (`CpSolverSolution`) and `_encoder_solve.py` (`CpSatPlacementResult`), which record `objective_value` but no bound today.
- A2. The installed OR-Tools version exposes `BestObjectiveBound()` on the solver after `Solve()`, and on `OPTIMAL` status the bound equals the objective, giving a gap of zero.
- A3. The objective is a minimization over the registered `_objective_terms` (the model's `Minimize` call in `model.solve`); the bound is only meaningful for that single objective.
- A4. Problem classes are the corpus boards (`power_pcb_dataset/corpus/` manifest entries) plus the existing synthetic small-instance classes used by the CP-SAT test suite.
- A5. The certificate is a flat per-solve record (class, gap, bound, verdict, git hash, timestamp), written by the pipeline at the same boundary where the solve result is accepted.
- A6. "Tuning drift" is detected as a shift in a class's observed gap distribution across runs with an unchanged bound; the certificate record is what makes that shift visible, not a separate telemetry system.

---

## Implementation Units

**Unit provenance (merge map 015 → 017):** U1–U4 keep the surviving plan's (017) numbering. Absorbed plan 015's U1 (bound and gap in the solve result) is the identical dataclass capture step and is merged into U1; 015's U2 (lower-bound oracle evaluator) is carried as U5; 015's U3 (measured per-class thresholds) is merged into U3's measurement unit — one capture, one registry, one measurement, two consumers.

### U1. Gap field on the solve result

**Goal:** Record the relaxation bound and relative gap on every CP-SAT solve result so downstream consumers can read them without re-solving.

**Requirements:** R14, R25

**Dependencies:** none

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`
- `packages/temper-placer/tests/placer/cp_sat/test_model.py`
- `packages/temper-placer/tests/placer/cp_sat/test_encoder.py`

**Approach:** Extend the two solve-result dataclasses (`CpSolverSolution`, `CpSatPlacementResult`) with `best_bound` and `relative_gap` fields. Read `BestObjectiveBound()` at the same point `ObjectiveValue()` is read (KTD1). Compute the relative gap per KTD2; guard the division so a zero objective yields a defined value (gap of zero). On non-finite or missing bound, record a sentinel that downstream units treat as `UNMEASURED`. This unit is the shared capture step both origin requirements describe; if the capture has already landed by the time this plan executes, this unit becomes a verification-only pass confirming the fields exist and are populated.

**Patterns to follow:** The existing result-dataclass shape in `model.py` (`CpSolverSolution`) and `_encoder_solve.py` (`CpSatPlacementResult`); the `SolveStatus` enum for status handling; the sentinel discipline for unmeasured quantities.

**Test scenarios:**
1. Happy path — a feasible solve records a finite, non-negative `relative_gap` with `best_bound <= objective_value`.
2. Optimality — a trivially small instance solved to `OPTIMAL` records a gap of zero (bound equals objective).
3. Edge case — a solve with a zero objective records a defined gap of zero, not a division error.
4. Edge case — an `INFEASIBLE` or `MODEL_INVALID` solve records no bound and a sentinel that downstream code reads as `UNMEASURED`.
5. Regression — existing consumers of `objective_value` keep working unchanged (field additions only).

**Verification:** The unit tests above pass, and a real corpus solve reports a finite bound and gap.

### U2. Certificate writer and registry file

**Goal:** Write one certificate per solve and maintain the per-class expected-gap bounds registry with provenance.

**Requirements:** R25

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/validation/gap_certificate.py` (new)
- `power_pcb_dataset/solver_gap_bounds.json` (new)
- `packages/temper-placer/tests/validation/test_gap_certificate.py` (new)

**Approach:** Build a certificate writer that takes a solve result and its problem class, resolves the class bound from the registry, and writes a flat record. The registry file holds per-class bounds with a provenance block (git hash, tool version, dirty flag, sample count) and a `_march`-style log of every bound move with its attributed cause, following the `drc_ceiling.json` shape (KTD4). Unmeasured classes resolve to `UNMEASURED`, never a silent bound of zero.

**Patterns to follow:** `power_pcb_dataset/drc_ceiling.json` provenance and `_march` structure; the fail-closed `UNMEASURED` discipline from `docs/physics-verification-methodology.md` §5.

**Test scenarios:**
1. Happy path — a solve within its class bound writes a certificate with verdict `PASS`.
2. Fail path — a solve above its class bound writes a certificate with verdict `FAIL` and the gap, bound, and class recorded.
3. Edge case — a class absent from the registry resolves to `UNMEASURED` and the certificate is not a pass.
4. Round-trip — the registry parses, and a bound move without an attributed cause entry fails registry validation.
5. Provenance — every registry entry carries a git hash and sample count.

**Verification:** The certificate writer's verdict matrix is covered, and the registry validation rejects an unattributed bound move.

### U3. Expected-gap measurement per class

**Goal:** Measure and pin the initial expected-gap bounds per problem class from the observed gap distribution on accepted solves, with provenance.

**Requirements:** R14, R25

**Dependencies:** U2

**Files:**
- `power_pcb_dataset/solver_gap_bounds.json`
- `packages/temper-placer/tests/validation/test_gap_certificate.py`
- `packages/temper-placer/tests/validation/test_optimality_oracle.py`

**Approach:** Run each corpus class and synthetic class under the standard timeout, record the observed gap **range** per class from the distribution of accepted solves — not from the first measurement alone (KTD3) — and pin each bound above the observed max with headroom, documenting the sample count and the reasoning per class in the `_march` log — the same discipline the DRC-ceiling convention documents in AGENTS.md. A class whose solves are all `OPTIMAL` pins a zero bound. On large boards a loose relaxation may put the observed max near 100%; that is recorded as the class's honest starting distribution, not hidden — the bound only bites when the gap worsens past it.

**Patterns to follow:** The `_march` log's "observed max + headroom" reasoning style for the one nondeterministic category in `power_pcb_dataset/drc_ceiling.json`; the sample-count discipline documented in AGENTS.md for DRC ceiling re-measurement.

**Test scenarios:**
1. Happy path — each class records a finite observed gap range and pins a bound above the observed max with a documented sample count.
2. Edge case — a class whose solves are all `OPTIMAL` pins a zero bound.
3. Fail path — a deliberately degraded solve (timeout too short to reach optimality) exceeds the pinned bound and the check verdict is `WEAK_SEARCH`/`FAIL`.
4. Attribution — the initial `_march` entry records why each bound was chosen, and every entry carries a git hash, sample count, and tool version.

**Verification:** The pinned bounds parse, every class resolves, and the degraded-solve scenario demonstrates the check bites.

### U4. Standing certificate gate in CI

**Goal:** Make the certificate check and the registry validation standing gates so a worsening gap beyond bound — or an unattributed bound move — fails every run, not just ad-hoc runs.

**Requirements:** R25

**Dependencies:** U3

**Files:**
- `packages/temper-placer/src/temper_placer/validation/gap_certificate.py`
- `packages/temper-placer/tests/validation/test_gap_certificate.py`
- `scripts/check_solver_gap_bounds.py` (new)
- `scripts/tests/test_check_solver_gap_bounds.py` (new)
- `.github/workflows/python-tests.yml`

**Approach:** Invoke the certificate check on the corpus solves already exercised by the CI validation suite, extending the existing `checks` job in `.github/workflows/python-tests.yml` rather than adding a parallel workflow. The check fails when any exercised solve's gap exceeds its class bound, and reports the certificate lines. Registry validation gets a dedicated enforcement script, `scripts/check_solver_gap_bounds.py`, mirroring the `drc_ceiling.json` convention's `scripts/check_drc_ceiling_approval.py` and `scripts/check_measurement_provenance.py`: it validates the registry's content-hash provenance and rejects a bound move without an attributed `_march` cause, invoked as its own step in the same CI job so the registry is enforced even when the solve suites do not run.

**Patterns to follow:** The repo convention of extending existing gates over new parallel scripts (AGENTS.md); the `checks` job structure in `.github/workflows/python-tests.yml`; the standalone enforcement-step style of the DRC-ceiling approval and measurement-provenance gates.

**Test scenarios:**
1. Integration — a clean corpus solve run passes the certificate check with certificates written.
2. Fail path — a run with a degraded solve fails the check and the failure names the class, gap, and bound.
3. Fail path — a registry bound move without an attributed `_march` cause fails `scripts/check_solver_gap_bounds.py`.
4. Regression — existing CI behavior is unchanged when all gaps are within bounds.

**Verification:** The CI checks job passes on clean runs, the degraded-run scenario demonstrates the gate bites, and the enforcement script rejects an unattributed bound move outside the test suite.

### U5. Lower-bound oracle evaluator

**Goal:** Classify a solve as "good", "valid", or "weak search" from its gap, with a fail-closed verdict. (Absorbed from 015 U2.)

**Requirements:** R14

**Dependencies:** U1, U3

**Files:**
- `packages/temper-placer/src/temper_placer/validation/optimality_oracle.py` (new)
- `packages/temper-placer/tests/validation/test_optimality_oracle.py` (new)

**Approach:** Build an evaluator that takes a solve result plus the problem class's measured threshold (from U3's registry) and returns a verdict: `GOOD` when the gap is at or below threshold, `WEAK_SEARCH` when above, and `UNMEASURED` when no threshold or no bound exists. The verdict is a data object with the bound, incumbent, gap, and threshold recorded, following the `GateResult` shape in `validation/validation_gates.py`. `WEAK_SEARCH` is the run-failing verdict; `UNMEASURED` never passes silently.

**Patterns to follow:** The fail-closed verdict style of `validation/validation_gates.py` and the `UNMEASURED` discipline in `docs/physics-verification-methodology.md` §5.

**Test scenarios:**
1. Happy path — a gap below threshold yields `GOOD`.
2. Fail path — a gap above threshold yields `WEAK_SEARCH` with the exact bound and incumbent in the verdict.
3. Edge case — a missing threshold yields `UNMEASURED`, which is not a pass.
4. Edge case — a missing bound (sentinel from U1) yields `UNMEASURED` regardless of threshold.
5. Boundary — a gap exactly at threshold yields `GOOD` (inclusive bound).

**Verification:** The evaluator's verdict matrix is covered by the scenarios above, including the two fail-closed cases.

---

## Verification Contract

The certificate gate and the registry enforcement script run inside the existing `checks` job of `.github/workflows/python-tests.yml`, so no new workflow file is introduced. The oracle evaluator and certificate suites run under the standard pytest configuration in `packages/temper-placer/`. Registry validation runs both as a unit test (U2 test scenario 4) and as a dedicated enforcement script, `scripts/check_solver_gap_bounds.py`, invoked as its own CI step (U4) — the `drc_ceiling.json` convention has dedicated enforcement scripts rather than relying on the test suite alone, and this registry mirrors that so validation never depends on the solve suites running. The new script requires a `scripts/manifest.yaml` entry per the AGENTS.md script-manifest convention. New public functions in `temper_placer/` must clear the coverage gate (`.coverage-allowlist`). The corpus measurement runs on demand with the same sample discipline as DRC ceiling re-measurement. Per the portfolio recommendation, every new CI gate remains advisory while branch protection on `main` is disabled.

---

## Definition of Done

- Every solve result carries `best_bound` and `relative_gap` (U1).
- Each solve writes a certificate with class, gap, bound, and verdict (U2).
- Per-class expected-gap bounds are measured from the observed gap distribution, pinned, and attributed in `power_pcb_dataset/solver_gap_bounds.json` (U3).
- The certificate check runs in CI and fails on a gap beyond its class bound (U4).
- The registry enforcement script runs in CI and rejects an unattributed bound move (U4).
- A deliberately weak solve fails the oracle, and a deliberately degraded solve fails the certificate (U3 test scenario 3, U5 test scenario 2).
- All new public functions have executed-line coverage.
- The validation test suite passes under the standard pytest run.

---

## Scope Boundaries

**In scope:** bound and gap capture on the existing solve path; the oracle verdict; the certificate record; the per-class bounds registry with provenance; the CI certificate gate and the registry enforcement script.

**Out of scope:** changing solver parameters to improve the gap — the oracle and certificate only measure and fail; building an independent relaxation (LP dual, Lagrangian) — the CP-SAT bound is the relaxation this idea names; a telemetry backend beyond the flat certificate file — the flat record is the registered artifact this idea names.

### Deferred to Follow-Up Work

- Cross-class bound inference for problem classes never yet solved.
- Gap thresholds for problem classes beyond the corpus and synthetic test classes.
- Exposing bound and gap through the CLI placement result output.
- A dashboard or aggregated view of certificate history (the flat records accumulate; aggregation is a follow-up).
- Automatic detection of tuning drift from the certificate history without a CI run (the certificate makes it visible; classification is follow-up).

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the portfolio origin (R14, R25; Outstanding Questions threshold convention).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py` — solve path and `CpSolverSolution`; where `ObjectiveValue()` is read today.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py` — the second solve path (`CpSatPlacementResult`).
- `packages/temper-placer/src/temper_placer/validation/validation_gates.py` — `GateResult` verdict shape and fail-closed discipline.
- `docs/physics-verification-methodology.md` — independent-oracle rule (§3) and `UNMEASURED` fail-closed discipline (§5).
- `power_pcb_dataset/drc_ceiling.json` — the provenance-and-attribution pattern the threshold file mirrors.
- `scripts/check_drc_ceiling_approval.py`, `scripts/check_measurement_provenance.py` — the enforcement-script pattern the registry validation mirrors.
- `.github/workflows/python-tests.yml` — the `checks` job the certificate gate and enforcement script extend.
