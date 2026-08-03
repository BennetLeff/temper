---
title: Post-Solve Audit for All Constraints - Plan
type: feat
date: 2026-08-02
topic: post-solve-audit-all-constraints
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R24)
---

# Post-Solve Audit for All Constraints - Plan

## Goal Capsule

**Objective:** Extend the post-solve audit from physics-gated surfaces to every encoded constraint, so actual constraint values are recomputed post-solve and mismatches fail the run — closing the silent-constraint-drop seam class.

**Product authority:** temper-placer maintainer (single-maintainer project; this plan is pulled from the portfolio menu, not scheduled).

**Open blockers:** none.

---

## Product Contract

### Summary

The solver's output is trusted until the run ends. The post-solve audit recomputes each encoded constraint's actual value from the placement coordinates and compares it against what the solver claimed to enforce. Today the audit covers a subset of constraint types and silently passes on unregistered types. This plan makes the audit total: every encoded constraint type maps to a recomputation, unknown types fail closed, and mismatches fail the run at the solve boundary rather than surfacing later in tests.

### Problem Frame

The silent-constraint-drop seam class is a constraint that is present in the config, appears enforced, but resolves to nothing and drops without error — the solver reports OPTIMAL because it solved a nearly-unconstrained problem (`docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md`). The existing auditor closes part of that seam but has its own silent gaps: an unregistered constraint type returns a clean pass, and `PIN_TO_PIN` adjacency is skipped for lack of pin geometry.

### Requirements

- R24. The post-solve audit extends from physics-gated surfaces to every encoded constraint — actual values are recomputed post-solve and mismatches fail the run, closing the silent-constraint-drop seam class.
  - **Success signal:** for every constraint type the encoder can emit, the audit has exactly one recomputation; a constraint type with no recomputation, or a recomputed value that contradicts the solver's claimed enforcement, fails the run.

### Key Technical Decisions

- KTD1. **Fail closed on unregistered constraint types.** `PlacementAuditor._check` currently returns an empty pass list for any type not in its map; that becomes a hard failure naming the type. Rationale: a pass-on-unknown is the exact seam class this plan exists to close.
- KTD2. **One recomputation per encoded type.** The audit register maps every `ConstraintType` the encoder can emit to exactly one post-solve check; the register is enforced to be complete, so adding a new encoding without an audit entry is a compile/test-time failure. Rationale: totality is the requirement, not coverage that drifts.
- KTD3. **Recompute from placement geometry with the same primitives.** Checks recompute actual values from positions, rotations, and sizes using the `temper-geometry` primitives the encoder used (`_bbox`, `_chebyshev_gap`), per the R24 discipline in `docs/physics-verification-methodology.md`. Rationale: a different geometry path would audit a different model.

### Assumptions

- A1. The seed `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` exists with `PlacementAuditor` covering `SEPARATED`, `ENCLOSING`, `ADJACENT`, `ON_SIDE`, `ANCHORED`, `KEEPOUT`, `ALIGNED`, and `LOOP_AREA` — and with two known silent gaps: unknown types pass, and `PIN_TO_PIN` adjacency returns no violation.
- A2. Physics-gated surfaces already carry a post-solve audit somewhere in the placer stack (the physics gates and their domain checks); this plan extends the same recompute-and-compare pattern to the remaining encodings rather than inventing a second audit style.
- A3. The full encoded type surface is enumerable from the constraint handlers under `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/` plus `domain_clearance.py`, `netclass_constraints.py`, and `isolation_barrier.py`.
- A4. "Fails the run" means the audit verdict is wired into the solve pipeline so a mismatch aborts the placement result as a failure, not merely a test assertion.

---

## Implementation Units

### U1. Close the silent-skip gaps in the existing auditor

**Goal:** Make `PlacementAuditor` fail closed on unknown constraint types and stop silently passing `PIN_TO_PIN` adjacency.

**Requirements:** R24

**Dependencies:** none

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py`
- `packages/temper-placer/tests/placer/cp_sat/test_audit.py`

**Approach:** Change `_check` so a `ConstraintType` absent from `_CHECK_MAP` raises a named error identifying the type. For `PIN_TO_PIN` adjacency, either verify it against real pin geometry carried into the `Placement` model, or — when pin geometry is genuinely unavailable — emit an explicit `UNVERIFIED` audit record instead of a silent pass; an `UNVERIFIED` record fails the run unless the constraint carries a documented exemption.

**Patterns to follow:** The `AuditViolation`/`AuditReport` shape; the fail-closed verdict discipline of `validation/validation_gates.py`.

**Test scenarios:**
1. Fail path — an auditor fed a constraint type outside `_CHECK_MAP` raises, with the type named.
2. Fail path — a `PIN_TO_PIN` adjacency constraint audits to `UNVERIFIED` (no pin geometry), which counts as not-passing.
3. Happy path — the eight mapped types still audit to their existing pass/fail behavior with zero regressions in `test_audit.py`.
4. Edge case — a constraint referencing a component absent from the placement still reports a violation or a named `UNVERIFIED` marker, never a clean pass.

**Verification:** The existing `test_audit.py` suite passes unchanged for the mapped types, and the two new fail-path tests pass.

### U2. Extend the audit to every remaining encoded constraint family

**Goal:** Give every constraint type the encoder can emit a post-solve recomputation check.

**Requirements:** R24

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`
- `packages/temper-placer/tests/placer/cp_sat/test_audit.py`
- `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py`
- `packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py`

**Approach:** Enumerate the full encoded type surface from the constraint handlers and the three standalone encoding modules. For each type without a check, add a recomputation that reads the placement geometry and compares against the constraint's encoded requirement, reusing the existing per-module geometry helpers where they already compute the same quantity. Extend `_CHECK_MAP` (or its replacement register) so the map and the encoder's emitted types are proven equal by a completeness test.

**Patterns to follow:** The existing per-type check methods in `audit.py`; the Chebyshev-gap soundness framing in `handlers/separated.py`; the recompute-from-coordinates discipline of the physics gates.

**Test scenarios:**
1. Happy path — each newly covered type has a constraint satisfied by construction and audits to zero violations.
2. Fail path — each newly covered type has a constraint deliberately violated in the placement and audits to a violation naming the constraint and the actual value.
3. Completeness — a test asserts the audit register covers exactly the set of types the encoder can emit; a new type in the encoder without an audit entry fails this test.
4. Integration — a placement produced by a real solve audits clean across all types.
5. Edge case — a type whose geometry is not representable in the `Placement` model reports `UNVERIFIED`, never a clean pass.

**Verification:** The completeness test passes, the per-type fail-path tests demonstrate bite, and a real solve audits clean.

### U3. Wire the audit into the solve pipeline as a run-failing step

**Goal:** A post-solve mismatch aborts the run at the solve boundary instead of surfacing only in tests.

**Requirements:** R24

**Dependencies:** U2

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py` (or the pipeline entry that consumes solve results)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py`
- `packages/temper-placer/tests/placer/cp_sat/test_integration_temper.py`

**Approach:** Invoke the extended auditor on every feasible solve result at the same boundary where the result is accepted. A non-passing audit report converts the solve result to a failure verdict carrying the violations, following the existing fail-closed style of the pipeline's gate wiring. The audit runs on the same `Placement` geometry the pipeline builds, so no new serialization is introduced.

**Patterns to follow:** The gate-wiring pattern already used at the solve boundary (e.g., how `AcceptanceGate` converts a DRC disagreement into a run signal in `cp_sat/gate.py`).

**Test scenarios:**
1. Integration — a normal temper solve completes with the audit pass recorded in the result.
2. Fail path — a hand-forged solver result whose coordinates violate an encoded constraint is rejected by the pipeline with the audit violations attached.
3. Edge case — an `INFEASIBLE` or `MODEL_INVALID` solve skips the audit (no placement to audit) and is not mislabeled as an audit pass.
4. Edge case — the audit itself raising (U1 fail-closed) surfaces as a run failure naming the type, not a swallowed exception.

**Verification:** The integration suite passes on clean solves, and the forged-violation scenario fails the run with named violations.

### U4. Register and document the audit surface

**Goal:** Make the audit register and its exemptions a documented, reviewable contract.

**Requirements:** R24

**Dependencies:** U3

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` (register docstring)
- `docs/plans/2026-08-02-016-feat-post-solve-audit-all-constraints-plan.md` (this plan's register appendix section is not required; the register lives in code)
- `docs/solutions/` (new entry capturing the audit-surface contract) — path decided at implementation

**Approach:** Record in the audit module a table of every encoded type, its check method, and any documented `UNVERIFIED` exemption with a reason. Exemptions require an explicit note naming the missing geometry, mirroring the documented-NOTE convention from the silent-constraint-drop fix. The completeness test from U2 enforces that the table matches the encoder surface.

**Patterns to follow:** The documented-NOTE convention in `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` (genuinely-missing parts disabled with documented NOTEs, never guessed).

**Test scenarios:**
1. Happy path — the register table lists every encoded type with exactly one check or one documented exemption.
2. Fail path — a type with neither a check nor an exemption fails the register validation test.
3. Consistency — the register docstring and the completeness test agree; drift between them fails the test.

**Verification:** The register validation test passes, and the table is readable in the audit module docstring.

---

## Verification Contract

The extended auditor runs under the existing pytest configuration in `packages/temper-placer/` (`tests/placer/cp_sat/`). The completeness and register tests run in the normal suite, not a separate workflow. New public functions in `temper_placer/` must clear the coverage gate (`.coverage-allowlist`). No new `scripts/*.py` is introduced, so no `scripts/manifest.yaml` entry is required. The run-failing wiring is verified by the integration scenarios in U3.

---

## Definition of Done

- Unknown constraint types fail closed in the auditor (U1).
- Every encoded type has one recomputation or one documented `UNVERIFIED` exemption (U2, U4).
- A completeness test proves the audit register matches the encoder's emitted type set (U2).
- A post-solve mismatch fails the run at the solve boundary with named violations (U3).
- All new public functions have executed-line coverage.
- The `tests/placer/cp_sat/` suite passes, including the new fail-path and completeness scenarios.

---

## Scope Boundaries

**In scope:** auditor totality across every encoded constraint type; run-failing wiring; the register contract.

**Out of scope:** mutation-based validation of the audit itself (that is the portfolio's R32 constraint-mutation suite); extending the auditor to validate routing output; changing constraint encodings — the audit verifies what the encoder emits.

### Deferred to Follow-Up Work

- Adding pin geometry to the `Placement` model so `PIN_TO_PIN` adjacency audits for real instead of `UNVERIFIED`.
- The R32 constraint-mutation suite, which will use this audit as its kill oracle.
- Auditing constraint types added by future encoders beyond the current surface.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the portfolio origin (R24).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py` — the seed; existing `_CHECK_MAP` and per-type checks.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/` — the encoded constraint type surface.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`, `netclass_constraints.py`, `isolation_barrier.py` — standalone encodings requiring audit coverage.
- `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` — the incident class and the documented-NOTE convention.
- `docs/physics-verification-methodology.md` — the R24 soundness / BMC / post-solve-audit discipline this plan operationalizes.
