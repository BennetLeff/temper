---
title: SPICE Estimator Oracle - Plan
type: feat
date: 2026-08-02
topic: spice-estimator-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R10)
---

# SPICE Estimator Oracle - Plan

## Goal Capsule

**Objective:** Fast estimator outputs are periodically re-derived against a full reference solve on representative snapshots; estimator error bounds are measured, not assumed.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. The error metric and snapshot corpus shape are determined at implementation time from the measured data.

---

## Product Contract

### Summary

The SPICE validation pipeline feeds placement-derived parasitics into ngspice templates. The placement-derived parasitics come from a fast geometric estimator; its error against a full reference solve is currently unmeasured. This plan makes the estimator accountable: representative snapshot placements are periodically re-derived through both the fast estimator and the full reference, the error is measured, a bound is registered with provenance, and measured error beyond the bound fails the run.

### Problem Frame

This idea exists for the estimator-error-assumed incident class: a fast approximation feeds a safety-relevant check and nobody quantifies the approximation error. The `spice_pipeline.py` orchestration injects geometric loop-inductance estimates into the gate-drive, bootstrap, and DC-bus ngspice templates; the pipeline's own `validate_placement` path treats the estimate as ground truth. The portfolio's R3 independent-oracle rule says agreement must be measured against a reference that uses a different method, not assumed. This plan applies that rule to the SPICE estimator.

### Requirements

- R10. **SPICE estimator oracle differential** (Oracle / Physics / P2): fast estimator outputs are periodically re-derived against a full reference solve on representative snapshots — estimator error bounds are measured, not assumed. Seed: `packages/temper-placer/src/temper_placer/validation/spice_pipeline.py`.
  - **Success signal:** the measured error between the fast estimator and the full reference is registered for each loop class with provenance; a deliberately perturbed estimator (e.g. a 2x inductance multiplier) is caught by the differential in CI.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the seed and success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. The fast estimator is the geometric loop-inductance estimate (`estimate_loop_inductance` in `validation/spice.py`, backed by `spice_estimators.rs` in `temper-geometry`); the full reference is the ngspice template simulation consuming a reference extraction of the same placement. Rationale: the in-repo ngspice solve is the only full reference available; a dedicated field solver for loop inductance does not exist in the repo and is an assumption, not a given.
- KTD2. Representative snapshots are frozen into a corpus, one snapshot per loop class (gate drive, bootstrap, DC bus) across placement families that exercise geometric diversity. Rationale: "representative" needs a concrete, versioned definition or the periodic run cannot be reproduced.
- KTD3. The error metric is relative error on the estimator output that feeds the template parameter, plus the downstream effect on the simulation measurement. Rationale: a parameter error that does not move the measurement is benign; the bound must be on the quantity that matters.
- KTD4. Cadence is periodic (scheduled CI run), not per-solve. Rationale: full reference solves are expensive; the portfolio's idea text says "periodically", and the snapshot corpus makes the periodic run deterministic.

### Assumptions

- The full reference for loop inductance is the in-repo ngspice full template solve with reference-extracted parasitics; a 3-D field-solver reference is out of scope and would replace this reference later.
- "Periodically" means a scheduled CI job (nightly), not a per-solve or per-commit run.
- The estimator's known fallback defaults (50 nH, 100 nH, 200 nH when the estimate is below 1e-12) remain part of the measured surface and are included in the corpus.
- The noise floor for the ngspice reference on identical input is measured before any error bound is set (no assumed precision).

---

## Implementation Units

### U1. Representative snapshot corpus

**Goal:** Freeze a versioned corpus of representative placements, one per loop class, that the periodic re-derivation runs against.

**Requirements:** R10, KTD2.

**Dependencies:** none.

**Files:**
- `packages/temper-placer/src/temper_placer/validation/spice_pipeline.py` (corpus loading hook)
- `power_pcb_dataset/spice_snapshot_corpus/` (new corpus directory with frozen placements)
- `packages/temper-placer/tests/validation/test_spice_pipeline.py` (new tests)

**Approach:**
1. Select one snapshot per loop class (gate drive, bootstrap, DC bus) from real or representative placements, covering geometric diversity (trace length, loop area, component spacing).
2. Freeze each snapshot with its placement state, netlist, and board data so re-derivation is deterministic.
3. Add a loader that reads the corpus and drives the pipeline for both the estimator and the reference path.

**Patterns to follow:** the golden-fixture conventions in `tests/` fixtures; the corpus-board pattern in `power_pcb_dataset/corpus/`.

**Test scenarios:**
- The corpus loads and contains exactly one snapshot per loop class.
- Each frozen snapshot reproduces a deterministic estimator output on repeated runs.
- A snapshot with a missing file raises a clear error rather than silently skipping the class.

**Verification:** the corpus is versioned, loadable, and deterministic per snapshot.

### U2. Periodic re-derivation runner

**Goal:** Run the fast estimator and the full reference solve on every snapshot and record the per-class error.

**Requirements:** R10, KTD1, KTD4.

**Dependencies:** U1.

**Files:**
- `packages/temper-placer/src/temper_placer/validation/spice_pipeline.py` (re-derivation mode)
- `packages/temper-placer/src/temper_placer/validation/spice.py` (reference-path reuse)
- `scripts/rederive_spice_estimator_bounds.py` (new; requires a `scripts/manifest.yaml` entry)
- `packages/temper-placer/tests/validation/test_spice_pipeline.py` (new tests)

**Approach:**
1. For each snapshot, compute the fast estimator output and the full-reference value on the same placement.
2. Compute the relative error on the template parameter and the downstream measurement delta.
3. Emit a per-class, per-snapshot error record into the register.

**Patterns to follow:** the `NgspiceValidator.is_available()` preflight and skip pattern; the fail-closed `UNMEASURED` discipline for a missing ngspice binary.

**Test scenarios:**
- A snapshot with ngspice unavailable records `UNMEASURED` for that class instead of fabricating a bound.
- Re-derivation on identical input twice produces identical error records (determinism).
- A perturbed estimator input (2x multiplier injected at the call site) produces a measurably different error record.
- The runner covers all three loop classes in one invocation.

**Verification:** one invocation re-derives every snapshot and writes error records for every class or an explicit `UNMEASURED`.

### U3. Measured error bounds and register

**Goal:** Register per-class error bounds derived from the measured re-derivation runs, with provenance.

**Requirements:** R10, KTD3, KTD4.

**Dependencies:** U2.

**Files:**
- `power_pcb_dataset/spice_estimator_bounds.json` (new register)
- `scripts/check_spice_estimator_bounds.py` (new gate; requires a `scripts/manifest.yaml` entry)
- `packages/temper-placer/tests/validation/test_spice_pipeline.py` (register tests)

**Approach:**
1. Measure the error distribution per loop class over the corpus; set the bound as observed max plus headroom per the DRC-ceiling convention.
2. Store per-class bounds with provenance (commit, corpus identity, ngspice version, tool version) and an attribution note per class.
3. The gate reads the register; a measured error beyond the bound fails the scheduled run.

**Patterns to follow:** the provenance block and `_march` log convention of `power_pcb_dataset/drc_ceiling.json`.

**Test scenarios:**
- The register parses and every loop class carries a bound and provenance.
- A measured error below the bound passes the gate.
- A measured error above the bound fails the gate with the class and snapshot named.
- A register entry missing provenance fails validation.
- Re-measuring on unchanged input reproduces the registered bound within headroom.

**Verification:** per-class bounds are registered with provenance and enforced by the gate.

### U4. Fail-capable differential tests

**Goal:** Prove the differential bites on the bug classes the estimator exists to catch.

**Requirements:** R10, KTD1, KTD3.

**Dependencies:** U1, U2.

**Files:**
- `packages/temper-placer/tests/validation/test_spice_pipeline.py`
- `packages/temper-placer/tests/validation/test_spice_rust_differential.py`

**Approach:**
1. Add fail-capable scenarios per the R4 bug-class list: sign flip in the estimator, dropped term in the loop-area computation, and loosened bound on the parameter fallback.
2. Each scenario must push the measured error beyond the registered bound.
3. Keep the noise-floor measurement explicit: identical-input variance is recorded and the bound exceeds it.

**Patterns to follow:** the fail-capable conventions in `docs/physics-verification-methodology.md` section 4.

**Test scenarios:**
- Sign flip in the estimator's x-coordinate term is detected.
- Dropped perimeter term in the loop-inductance formula is detected.
- A loosened fallback default (50 nH → 100 nH) is detected on the snapshot that triggers the fallback.
- Identical-input noise floor is below the registered bound (no false failure on a healthy run).

**Verification:** each fail-capable scenario names its bug class and fails the differential as expected.

---

## Verification Contract

- Unit tests: `uv run pytest packages/temper-placer/tests/validation/ -q` from `packages/temper-placer/`.
- Rust differential tests: `uv run pytest packages/temper-placer/tests/validation/test_spice_rust_differential.py -q`.
- Import boundary gate: `uv run python scripts/import_linter_gate.py` at repo root.
- Coverage gate: run `uv run pytest tests/core/ -q --cov=temper_placer --cov-report=json --cov-config=../../pyproject.toml` from `packages/temper-placer/`, then `python scripts/check_coverage_gate.py`; new public functions need tests or an allowlist entry.
- Script manifest: new scripts require entries in `scripts/manifest.yaml`; refresh with `uv run python scripts/trace_invocations.py`.
- The scheduled re-derivation job must be green with a healthy ngspice binary; a perturbed estimator fails CI.

---

## Definition of Done

- A versioned snapshot corpus covers all three loop classes.
- The periodic re-derivation runner records per-class estimator error against the full reference.
- Per-class error bounds are registered with provenance and enforced by a gate.
- Fail-capable scenarios demonstrate the differential catches sign-flip, dropped-term, and loosened-bound mutations.
- Abandoned experimental code from bound measurement is removed before the branch is complete.

---

## Scope Boundaries

- **In scope:** estimator error measurement, snapshot corpus, registered bounds, periodic gating.
- **Out of scope:** changing the loop-inductance estimator's formula; adding a 3-D field-solver reference; changing the ngspice template set.

### Deferred to Follow-Up Work

- A 3-D field-solver reference for loop inductance to replace the in-repo ngspice reference.
- Extending the same differential pattern to the thermal scorer's estimator surfaces (overlaps the R9 plan's U3 gate).
- Promoting the periodic cadence to per-commit once full-reference cost is characterized.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin (R10).
- `packages/temper-placer/src/temper_placer/validation/spice_pipeline.py` — the seed pipeline to extend.
- `packages/temper-placer/src/temper_placer/validation/spice.py` — `estimate_loop_inductance`, template substitution, and the ngspice preflight pattern.
- `docs/physics-verification-methodology.md` — the independent-oracle rule (R3) and fail-capable rule (R4).
- `power_pcb_dataset/drc_ceiling.json` — the measured-bound-with-provenance convention.
