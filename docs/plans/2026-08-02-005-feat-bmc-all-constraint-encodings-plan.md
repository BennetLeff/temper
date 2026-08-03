---
title: BMC-Exhaustive All Constraint Encodings - Plan
type: feat
date: 2026-08-02
topic: bmc-all-constraint-encodings
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R21)
---

# BMC-Exhaustive All Constraint Encodings - Plan

## Goal Capsule

**Objective:** The BMC-exhaustive pattern extends from physics-gated constraints to every CP-SAT encoding; small-N exhaustive verification against a truthful oracle is the default, not the exception.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none, but the named seed is currently red (see Assumptions): `scripts/bmc_adoption_gate.py` fails on the current tree because the ESL/BMC evaluator modules and the `test_bmc_*.py` files were removed. Restoring the gate to green is the plan's first unit.

---

## Product Contract

### Summary

Every CP-SAT constraint encoding — the router-V6 topology family and the placer PCL handler family — gets small-N exhaustive verification against a truthful oracle. The existing `bmc_adoption_gate.py` AST-scan pattern is restored to green and extended to cover both families, so a new encoding without exhaustive verification fails CI by default.

### Problem Frame

This idea exists for the unsound-encoding incident class: an encoding is accepted on the strength of a review, then a `weak-nooverlap2d` or `atmostk` or `endpoint-bounding` failure shows the review missed the semantics. BMC-exhaustive verification replaces review trust with a proof over all inputs up to a bounded size. The pattern already exists as policy for physics-gated constraints (the R24 discipline's second item); this plan makes it the default for every encoding.

### Requirements

- R21. **BMC-exhaustive validation for all encodings** (Formal / Physics / P2): the BMC pattern extends from physics-gated constraints to every CP-SAT encoding — small-N exhaustive verification against a truthful oracle is the default, not the exception. Seed: `scripts/bmc_adoption_gate.py`.
  - **Success signal:** a new CP-SAT encoding without an exhaustive small-N verification test fails CI; the adoption gate is green for every registered encoding across both constraint families.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the seed and success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. The truthful oracle is per family: for router-V6 topology constraints, a small-N exhaustive evaluator over the surviving `esl()` declarations; for the placer PCL encoders, the post-solve `PlacementAuditor` plus the `temper-geometry` Rust geometry. Rationale: each family already has a trusted ground-truth surface; reusing it avoids inventing a third oracle.
- KTD2. The gate is one script covering both families, extending `bmc_adoption_gate.py` rather than a parallel script. Rationale: the repo convention prefers extending existing gates; one gate with two scan targets keeps the coverage contract in one place.
- KTD3. The small-N bound is exhaustive over coarse-grid placements for 2–3 components including rotations, matching the existing property-strategy files. Rationale: that bound is already the established BMC size in this repo (A* on 8×8 grids, router-V6 2^N with N ≤ 10).
- KTD4. Restoring the router-V6 side to green is a precondition, not a side quest. Rationale: a red adoption gate enforces nothing; the extension is only meaningful once the existing gate passes on the current tree.

### Assumptions

- **Seed discrepancy (verified):** `scripts/bmc_adoption_gate.py` exists and runs, but exits 3 on the current tree. The evaluator modules (`esl.py`, `bmc.py`) and the `test_bmc_*.py` files were deleted in commit `772776115` (refactor: delete 15 dead modules + 20 orphaned test files); the `esl()` methods survive on the constraint classes (`CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`; `ChannelSeparationConstraint` lacks them). The gate's `test_bmc_*.py` glob in `tests/router_v6/` therefore finds nothing. The plan assumes the router-V6 exhaustive machinery must be re-established from the surviving `esl()` declarations; if the constraint family itself is slated for removal by the Wave 4 Rust migration, the re-establishment is scoped to a minimal evaluator rather than a full rebuild.
- The PCL handler family (8 encoders in `placer/cp_sat/handlers/`) is in scope for exhaustive verification; the router-V6 topology family is restored to its documented baseline.
- BMC-exhaustive means enumerating all inputs up to the bound and asserting agreement with the oracle — no sampling at that bound.

---

## Implementation Units

### U1. Restore router-V6 exhaustive ground truth

**Goal:** Re-establish a small-N exhaustive evaluator for the router-V6 constraint declarations and restore the adoption gate to green.

**Requirements:** R21, KTD1, KTD4.

**Dependencies:** none.

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` (surviving `esl()` declarations; read-only unless a declaration is wrong)
- `packages/temper-placer/tests/router_v6/test_bmc_encoding.py` (new exhaustive tests)
- `scripts/bmc_adoption_gate.py` (fix the stale test glob if needed)

**Approach:**
1. Implement a small-N exhaustive evaluator that interprets each constraint's `esl()` declaration over all 2^N primary assignments for N ≤ 10.
2. Add exhaustive tests asserting the evaluator agrees with the declared semantics on every assignment.
3. Restore the gate's test-reference glob to the actual test files and confirm exit 0.

**Patterns to follow:** the documented BMC shape in `docs/physics-verification-methodology.md` section 2 (exhaustive base, no sampling); the deleted `bmc.py` behavior described in `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`.

**Test scenarios:**
- For `CapacityConstraint` with N ≤ 10, every assignment the evaluator marks satisfiable matches the `esl()` semantics (no false pass).
- For `DiffPairConstraint` and `LayerConstraint`, the same exhaustive agreement holds.
- `ChannelSeparationConstraint` either gains `esl()` coverage or is explicitly registered as out of scope with a note in the gate.
- The gate exits 0 with every surviving constraint carrying an exhaustive test reference.

**Verification:** `uv run python scripts/bmc_adoption_gate.py` exits 0 on the current tree.

### U2. Exhaustive verification for the PCL encoders

**Goal:** Give every placer PCL encoder a small-N exhaustive test against the auditor oracle.

**Requirements:** R21, KTD1, KTD3.

**Dependencies:** U1.

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/` (8 encoders; read-only unless a defect is found)
- `packages/temper-placer/tests/pcl/test_bmc_encodings.py` (new exhaustive tests)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` (oracle entry point)

**Approach:**
1. For each handler, enumerate all placements of 2–3 components on a coarse grid (including the 4 rotations) and assert the encoded constraint and the auditor agree.
2. Where the encoder and auditor disagree, classify the direction (encoder looser than auditor is a defect; auditor weaker is an audit gap) before fixing.
3. Reuse the existing property-strategy files for the grid and rotation space.

**Patterns to follow:** `tests/placer/cp_sat/test_geometry_constraints_pbt.py` for grid/rotation strategy reuse; `tests/placer/cp_sat/test_audit.py` for the auditor as ground truth.

**Test scenarios:**
- `SEPARATED` encoding agrees with the auditor on every coarse-grid placement (the Chebyshev disjunction case).
- `ENCLOSING`, `KEEPOUT`, `ALIGNED`, `ON_SIDE`, `ANCHORED`, `ADJACENT`, and `LOOP_AREA` each have exhaustive agreement on their parameterized fixtures.
- A known auditor gap (e.g. the `PIN_TO_PIN` skip in `_check_adjacent`) is documented in the test rather than silently excluded.
- A deliberately loosened encoder bound (margin halved) is caught by the exhaustive test.

**Verification:** every handler has an exhaustive small-N test; the suite is green on the current tree.

### U3. Extend the adoption gate to both families

**Goal:** One gate enforces exhaustive coverage for router-V6 and PCL encodings.

**Requirements:** R21, KTD2, KTD3.

**Dependencies:** U1, U2.

**Files:**
- `scripts/bmc_adoption_gate.py` (extend the scan to `placer/cp_sat/handlers/`)
- `scripts/manifest.yaml` (entry already present; refresh invocation graph)
- `packages/temper-placer/tests/pcl/test_bmc_encodings.py` (gate-referenced tests)

**Approach:**
1. Add a second scan target to the gate: enumerate registered PCL handlers and require an exhaustive test reference per handler.
2. Keep the existing router-V6 checks; the gate reports per family with a single exit code.
3. Wire the extended gate into CI alongside the current invocation.

**Patterns to follow:** the existing `bmc_adoption_gate.py` scan-and-report structure; the import-linter gate exit-code conventions.

**Test scenarios:**
- A new PCL handler without an exhaustive test reference fails the gate with the handler named.
- Removing a handler's test reference fails the gate.
- A new router-V6 constraint class without `esl()` and exhaustive coverage fails the gate.
- The gate exits 0 with both families fully covered.

**Verification:** the extended gate is green on the current tree and red on a synthetic unregistered encoding in either family.

### U4. PBT middle layer and documentation

**Goal:** Statistically validate encodings above the exhaustive bound and document the BMC-default convention.

**Requirements:** R21, KTD3.

**Dependencies:** U3.

**Files:**
- `packages/temper-placer/tests/pcl/test_bmc_encodings_pbt.py` (new property tests)
- `docs/physics-verification-methodology.md` (extend section 2 to the PCL family)
- `docs/solutions/best-practices/bmc-induction-ladder-constraint-verification-2026-07-01.md` (link the extension)

**Approach:**
1. Add Hypothesis property tests above the exhaustive bound for the encodings that support it, marked with the repo's PBT marker.
2. Document the exhaustive-bound default in the methodology doc so new encodings start from BMC, not from example tests.
3. Record the seed-discrepancy resolution (restored evaluator, re-pointed glob) in the doc trail.

**Patterns to follow:** the `@pytest.mark.l3_pbt` marking convention in the methodology doc; the property-strategy reuse in `tests/placer/cp_sat/_strategies.py`.

**Test scenarios:**
- Property tests on 4+ component placements find no encoder/auditor disagreement on sampled inputs.
- A seeded adversarial placement (tightly packed, mixed rotations) is included in the sampled space.
- The methodology doc cites the gate and the exhaustive default for both families.

**Verification:** the PBT layer runs in CI and the docs reflect the BMC-default convention.

---

## Verification Contract

- Gate: `uv run python scripts/bmc_adoption_gate.py` at repo root; must exit 0.
- Unit tests: `uv run pytest packages/temper-placer/tests/pcl/ packages/temper-placer/tests/router_v6/ -q` from `packages/temper-placer/`.
- Import boundary gate: `uv run python scripts/import_linter_gate.py`.
- Coverage gate: new public functions in `temper_placer` need tests or an allowlist entry (run per the standard `--cov` invocation from `packages/temper-placer/`).
- Script manifest: `scripts/trace_invocations.py` refresh after gate edits.

---

## Definition of Done

- The adoption gate exits 0 with exhaustive coverage for both the router-V6 and PCL families.
- Every PCL handler has a small-N exhaustive test against the auditor oracle.
- The gate fails on any new encoding without exhaustive verification in either family.
- The PBT middle layer runs above the exhaustive bound where supported.
- Abandoned experimental evaluator code is removed before the branch is complete.

---

## Scope Boundaries

- **In scope:** restoring the router-V6 ground truth, exhaustive PCL encoder verification, gate extension, PBT middle layer.
- **Out of scope:** re-architecting the router-V6 constraint family ahead of the Wave 4 Rust migration; writing new soundness proofs (the R20 plan owns that); post-solve audit changes (the portfolio's R24).

### Deferred to Follow-Up Work

- Full ESL-style semantic declarations for `ChannelSeparationConstraint` and any future topology constraints.
- Inductive (k-induction) proofs beyond the bounded base for encodings where the exhaustive bound is too small to be convincing.
- Decision on whether the router-V6 family survives the Wave 4 migration; the minimal-evaluator scope in U1 keeps re-establishment cheap either way.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — origin (R21).
- `scripts/bmc_adoption_gate.py` — the seed gate; verified to fail (exit 3) on the current tree.
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` — surviving `esl()` declarations.
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — the incident class and the deleted ESL/BMC machinery's documented shape.
- `docs/physics-verification-methodology.md` — the BMC-exhaustive → k-induction → PBT ladder (section 2).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` — the PCL-family truthful oracle.
- `packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py` — grid/rotation strategy reuse for the exhaustive bound.
