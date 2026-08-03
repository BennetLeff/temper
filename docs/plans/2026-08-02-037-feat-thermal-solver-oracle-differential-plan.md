---
title: Thermal Solver Oracle Differential - Plan
type: feat
date: 2026-08-02
topic: thermal-solver-oracle-differential
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R9)
---

# Thermal Solver Oracle Differential - Plan

## Goal Capsule

**Objective:** Every placement solve that runs the thermal scorer also runs an MFEM reference solve on a subsampled grid; the field comparison is recorded; drift beyond a measured bound fails the run.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. The divergence threshold is a measured value determined at implementation time, per the portfolio's deferred question for R9.

---

## Product Contract

### Summary

Every solve's thermal scorer output is compared against an MFEM reference solve on a subsampled grid. Drift beyond a measured bound fails the run. The comparison reuses the existing fail-closed MFEM corroboration pipeline; only the cadence (per-solve instead of per-placement) and the bound (measured instead of a fixed 5.0 C default) are new.

### Problem Frame

This idea exists for the model-divergence incident class: an abstract model produces a field that nothing re-checks against an independent model. The MFEM corroboration gate already closes part of that gap, but it runs once per placement and applies a hardcoded tolerance of 5.0 C. The incident record (courtyard 0-vs-43, the unsound encodings) shows that trust in an unmeasured bound is exactly the seam that fails. Per-solve comparison with a measured drift bound makes the thermal scorer's output continuously accountable to the external-FEM validity proxy.

### Requirements

- R9. **Thermal solver oracle differential** (Oracle / Physics / P2): every solve's thermal scorer output is compared against an MFEM reference solve on a subsampled grid — drift beyond a measured bound fails the run. Seed: `packages/temper-placer/src/temper_placer/validation/mfem_compare.py`.
  - **Success signal:** a solve whose thermal field drifts beyond the measured bound fails the run with a spatial attribution; a deliberately perturbed solver (conductivity or boundary-condition change) is caught by the differential in CI.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the seed and success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. Extend the existing `MFEMCorroborationGate` pipeline into the per-solve path instead of building a parallel instrument. Rationale: the pipeline (preflight → mesh → solve → project → compare) and its fail-closed `UNMEASURED` discipline already exist; a second instrument would drift from it.
- KTD2. The drift bound is measured, not assumed. Rationale: the hardcoded 5.0 C default is the exact unmeasured-threshold class the portfolio targets; the bound is derived from a baseline corpus using the DRC-ceiling convention (observed max plus headroom) and registered with provenance.
- KTD3. Comparison runs on a subsampled grid. Rationale: per-solve cadence makes full-grid MFEM comparison too expensive; subsampling equivalence is validated against full-grid comparison before adoption.
- KTD4. Fail mode is fail-closed. Rationale: an unavailable MFEM binary or failed solve returns `UNMEASURED`, never a silent `CLEAN`, matching the existing gate and the physics-verification methodology's fail-closed discipline.

### Assumptions

- The MFEM binary remains available in CI (the existing `mfem_corroboration` gate already requires it).
- "Every solve" means every placement solve that invokes the thermal scorer inside the solve loop, not every optimizer round.
- The subsampling ratio is an implementation-time choice bounded by an equivalence test against full-grid comparison.
- The measured bound follows the DRC-ceiling convention (observed max plus headroom, attributed per cause) until a better methodology is demonstrated.

---

## Implementation Units

### U1. Per-solve differential instrument

**Goal:** Run the MFEM reference solve and field comparison for every thermal-scoring solve, producing a recorded `ComparisonResult`.

**Requirements:** R9, KTD1, KTD4.

**Dependencies:** none.

**Files:**
- `packages/temper-placer/src/temper_placer/validation/mfem_gate.py` (extend the pipeline and the gate)
- `packages/temper-placer/src/temper_placer/validation/mfem_compare.py` (add subsampled comparison entry point)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_loop_core.py` (hook point where the thermal scorer output is produced per solve)
- `packages/temper-placer/tests/validation/test_mfem_compare.py` (new tests)
- `packages/temper-placer/tests/validation/test_mfem_gate.py` (new tests)

**Approach:**
1. Add a subsampled comparison entry point next to `compare_fields` that strided-selects FDM cells and compares only those against the projected MFEM field.
2. Extract the thermal scorer's per-solve FDM field at the solve-loop hook and route it through the existing `project_mfem_to_fdm` → `compare_fields` chain.
3. Wire the per-solve comparison into the solve loop so each thermal-scoring solve records a `ComparisonResult` instead of only the final placement.

**Patterns to follow:** the `MFEMCorroborationGate` pipeline (`validation/mfem_gate.py`), the `UNMEASURED` fail-closed pattern, the attribution logic in `mfem_compare.py::_attribute_disagreement`.

**Test scenarios:**
- Happy path: a solve with known-good thermal field produces a `ComparisonResult` with `exceeds_tolerance=False` and `max_delta_C` below the bound.
- Subsampled vs full-grid equivalence: on a fixed fixture field, the subsampled comparison agrees with full-grid comparison on the pass/fail decision.
- Edge case: `mfem_field` and FDM field shapes mismatch on a subsampled selection raises a clear `ValueError` rather than a silent partial comparison.
- Error path: MFEM binary missing or solve failure returns `UNMEASURED`, never `CLEAN`.
- Integration: a full solve through the loop emits one recorded comparison per thermal-scoring solve.

**Verification:** a solve run records a `ComparisonResult` per thermal-scoring solve; the fail-closed path returns `UNMEASURED` when the binary is absent.

### U2. Measured drift bound and register

**Goal:** Measure the observed drift between the thermal scorer and the MFEM reference over a baseline corpus and register the bound with provenance.

**Requirements:** R9, KTD2.

**Dependencies:** U1.

**Files:**
- `scripts/measure_thermal_drift_bound.py` (new; requires a `scripts/manifest.yaml` entry)
- `power_pcb_dataset/thermal_drift_bound.json` (new register)
- `packages/temper-placer/tests/validation/test_mfem_compare.py` (bound-registry tests)

**Approach:**
1. Run the differential over a corpus of representative solves and record the observed per-cell and per-device drift distribution.
2. Set the bound as observed max plus headroom, following the DRC-ceiling convention, and attribute any per-fixture delta to a cause.
3. Store the bound, the corpus identity, and provenance (commit, input hash, tool version) in the register, mirroring `power_pcb_dataset/drc_ceiling.json`'s structure.

**Patterns to follow:** the provenance and `_march` log convention of `power_pcb_dataset/drc_ceiling.json`; the `check_measurement_provenance.py` fail-closed style.

**Test scenarios:**
- The register parses and carries provenance fields for every entry.
- A bound read from the register is what the differential gate uses (no hardcoded fallback).
- Re-measuring with an unchanged corpus reproduces the registered bound within the documented headroom.
- A corpus change that would raise the bound requires an attributed cause in the register.

**Verification:** the register contains a measured bound with full provenance; the gate consumes the register value.

### U3. Per-solve differential gate

**Goal:** Fail the run when a per-solve comparison drifts beyond the measured bound.

**Requirements:** R9, KTD2, KTD4.

**Dependencies:** U1, U2.

**Files:**
- `packages/temper-placer/src/temper_placer/validation/mfem_gate.py` (bound-aware gate)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` (gate registration)
- `packages/temper-placer/tests/validation/test_mfem_gate.py` (new tests)

**Approach:**
1. Replace the fixed `tolerance_C` default with the measured bound loaded from the register.
2. Emit `VIOLATIONS` with the spatial attribution (near-heatsink edge, far-field, device footprint) when `exceeds_tolerance` is true.
3. Keep `UNMEASURED` for instrument absence and `CLEAN` only for a comparison that passed within the measured bound.

**Patterns to follow:** the existing `MFEMCorroborationGate.check` flow and `ViolationType.THERMAL` reporting.

**Test scenarios:**
- A synthetic field with drift above the measured bound yields `VIOLATIONS` with a non-empty attribution.
- A field within the bound yields `CLEAN`.
- A missing binary yields `UNMEASURED` even when the field would have passed.
- The gate reads the bound from the register; a tampered register value changes the gate's decision.
- Mutating the solver's conductivity constant by 10x is caught by the gate (fail-capable per the R4 bug classes).

**Verification:** the run fails on drift beyond the measured bound with attribution; fail-closed behavior is preserved.

### U4. Subsampling equivalence and fail-capable battery

**Goal:** Prove the subsampled comparison does not lose real signal and that the differential bites on plausible bug classes.

**Requirements:** R9, KTD3, KTD4.

**Dependencies:** U1.

**Files:**
- `packages/temper-placer/tests/validation/test_mfem_compare.py`
- `packages/temper-placer/tests/validation/test_mfem_gate.py`

**Approach:**
1. Add an equivalence test asserting the subsampled and full-grid comparisons make the same pass/fail decision across a drift sweep.
2. Add fail-capable tests per the R4 bug-class list: boundary-condition swap, conductivity-field sign flip, and source double-count must each push the comparison past the bound.
3. Assert the fail-closed paths (missing binary, malformed MFEM output) return `UNMEASURED`.

**Patterns to follow:** the fail-capable test conventions in `docs/physics-verification-methodology.md` section 4.

**Test scenarios:**
- Drift sweep: for fields at 0.5x, 1.0x, 1.5x, 2.0x the bound, subsampled and full-grid comparisons agree on pass/fail.
- BC swap (adiabatic ↔ convective on the heatsink edge) is detected.
- Conductivity-field sign flip is detected.
- Double-counted heat source is detected.
- Malformed MFEM output (empty temperature array) returns `UNMEASURED`.

**Verification:** the full battery passes and each fail-capable scenario documents the bug class it probes.

---

## Verification Contract

- Unit tests: `uv run pytest packages/temper-placer/tests/validation/ -q` from `packages/temper-placer/`.
- Import boundary gate: `uv run python scripts/import_linter_gate.py` at repo root.
- Coverage gate: run `uv run pytest tests/core/ -q --cov=temper_placer --cov-report=json --cov-config=../../pyproject.toml` from `packages/temper-placer/`, then `python scripts/check_coverage_gate.py`; new public functions need tests or an allowlist entry.
- Script manifest: `scripts/measure_thermal_drift_bound.py` requires an entry in `scripts/manifest.yaml`; refresh with `uv run python scripts/trace_invocations.py`.
- The per-solve differential gate runs in the placement solve path; a deliberate solver perturbation fails CI.

---

## Definition of Done

- Every thermal-scoring solve records a comparison against the MFEM reference on a subsampled grid.
- The drift bound is measured, provenance-carrying, and consumed by the gate; no hardcoded tolerance remains in the per-solve path.
- Drift beyond the bound fails the run with spatial attribution; instrument absence returns `UNMEASURED`.
- Fail-capable and equivalence batteries pass; the R4 bug classes are each represented by a scenario.
- Abandoned experimental code from bound-calibration runs is removed before the branch is complete.

---

## Scope Boundaries

- **In scope:** per-solve differential cadence, measured drift bound, subsampled comparison, fail-closed gating.
- **Out of scope:** changing the thermal solver's physics; re-specifying the MFEM mesh; hardware power-on measurement (deferred closing instrument per the methodology doc).

### Deferred to Follow-Up Work

- Closing the known gap in `mfem_compare.py` where `cell_size_mm` is accepted but ignored (physical-unit metrics).
- A field-solver reference for loop inductance that the R10 plan would reuse (see the R10 plan's assumptions).
- Moving the per-solve differential into the nightly battery at lower cadence once per-solve cost is characterized.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin (R9) and deferred-question record.
- `packages/temper-placer/src/temper_placer/validation/mfem_gate.py` — the fail-closed gate to extend.
- `packages/temper-placer/src/temper_placer/validation/mfem_compare.py` — comparison and attribution machinery.
- `docs/physics-verification-methodology.md` — the independent-oracle rule (R3), fail-capable rule (R4), and validity-proxy ladder that R9 instantiates.
- `power_pcb_dataset/drc_ceiling.json` — the measured-bound-with-provenance convention the drift bound mirrors.
- `docs/evidence/2026-07-30-domain-clearance-copper-aware-fix.md` — the model-divergence incident class this idea exists for.
