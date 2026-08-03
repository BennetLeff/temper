---
title: "Pattern: Post-Solve Audit Totality Register (every encoded constraint recomputed, unregistered types fail closed)"
date: 2026-08-02
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: cp_sat
severity: high
applies_when:
  - "A solver reports OPTIMAL/FEASIBLE but the placement is only as good as the constraints that were actually encoded"
  - "New constraint encodings can be added without any requirement to also add a post-solve verification"
  - "An audit exists but silently passes on constraint types it does not know about, or skips constraints whose geometry it cannot represent"
  - "The audit recomputes constraint values through a different geometry path than the encoder used, so a units/primitive bug passes both sides"
symptoms:
  - "PlacementAuditor._check returned [] for any constraint type absent from its map — an unregistered type was a clean pass, not a failure"
  - "PIN_TO_PIN adjacency was skipped for lack of pin geometry with a bare return [], indistinguishable from a verified pass"
  - "A check that could not resolve a referenced component silently continued, so a constraint referencing a dropped part passed vacuously"
  - "The audit was not wired into the solve pipeline at all — a mismatch could only surface in tests"
root_cause: missing_validation
resolution_type: code_addition
tags:
  - r24
  - post-solve-audit
  - fail-closed
  - constraint-encoding
  - silent-failure
  - register-contract
  - unverified-exemption
---

# Post-Solve Audit Totality Register

## Problem

The post-solve audit (`PlacementAuditor` in
`packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py`) is the
R24 item-3 gate: after a solve it recomputes each encoded constraint's
actual value from the placement coordinates and compares it against what
the solver claimed to enforce, so the solver's bookkeeping is never
trusted. But the audit itself had the same silent-gap disease it exists to
catch:

1. **Unregistered constraint types passed.** `_check` did
   `_CHECK_MAP.get(c.constraint_type)` and returned `[]` (a clean pass)
   when the type was absent — the exact "looks applied but isn't" seam
   class from
   `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md`.
2. **PIN_TO_PIN adjacency was skipped.** `_check_adjacent` returned `[]`
   for `DistanceMetric.PIN_TO_PIN` because the `Placement` model carries no
   per-pin geometry — indistinguishable from a verified pass.
3. **Absent refs were silently skipped.** Every per-type check had
   `if ref not in placement.positions_mm: continue` (or returned `[]`), so
   a constraint referencing a component dropped from the placement passed
   vacuously.
4. **Not wired into the run.** The auditor ran only through the orphaned
   `AcceptanceGate` (zero production callers); a mismatch could only fail
   a test, never the placement run.

## Solution

Plan `docs/plans/2026-08-02-016-feat-post-solve-audit-all-constraints-plan.md`
(totality for the audit), implemented in `audit.py`:

1. **Fail closed on unregistered types (KTD1).** `_check` raises
   `UnregisteredConstraintTypeError` naming the type instead of returning
   `[]`. A pass-on-unknown is a hard failure.
2. **UNVERIFIED records with a documented-exemption registry.** A
   constraint whose geometry is not representable in the `Placement` model
   (PIN_TO_PIN adjacency, absent refs) audits to an `UNVERIFIED` record.
   An `UNVERIFIED` record **fails the run** unless its
   `(ConstraintType, discriminator)` key carries a documented exemption in
   `PlacementAuditor._EXEMPTIONS`. The one current exemption — PIN_TO_PIN —
   is pre-registered with a documented NOTE, so real solves never strand;
   the corpus has no PIN_TO_PIN today, so the exemption path is latent but
   built and tested.
3. **One recomputation per encoded type (KTD2).** `_CHECK_MAP` maps every
   encoder-emittable `ConstraintType` to exactly one check method.
   `validate_audit_register()` enforces totality as a test-time contract:
   any `ConstraintType` member or handler-registered type without a check,
   or any mapped method that does not exist, raises. The completeness tests
   in `tests/placer/cp_sat/test_audit.py` prove the register equals the
   encoder surface (`HANDLER_REGISTRY`), and the register docstring table
   is drift-checked against the code.
4. **Standalone encodings covered.** `domain_clearance.py`,
   `netclass_constraints.py` and the courtyard generator all emit
   `SeparatedConstraint` objects (covered by `_check_separated`); the
   isolation barrier's HV/SELV one-sided bounds are recomputed post-solve
   by `audit_isolation_barrier`, with the isolator pad-cluster straddle
   recorded as a documented UNVERIFIED exemption (per-pad geometry is not
   carried in the `Placement` model).
5. **Run-failing wiring at the solve boundary (U3).** `solve_placement`
   audits every feasible result over the full encoded surface (originals +
   auto-generated netclass + courtyard, via the new
   `build_encoded_constraint_surface`); a non-passing report converts the
   result to `status="audit_failed"` with the violations attached, and the
   place-route loop and CLI treat that status as a failure. INFEASIBLE /
   MODEL_INVALID solves skip the audit (no placement to audit) and are
   never mislabeled as an audit pass. A fail-closed raise from the audit
   itself surfaces as `audit_failed` naming the type, not a swallowed
   exception.

## Why This Works

Totality is the requirement, not coverage that drifts. Because the
register is proven equal to the encoder surface by a test, adding a new
encoding without an audit entry is a test-time failure; because unknown
types raise, a constraint the audit does not know about can never be a
clean pass; because UNVERIFIED fails unless exempt, a constraint whose
geometry the model cannot represent is either documented (visible in the
report) or fatal — never silently green.

## Prevention

- **Any future constraint encoding must land with an audit entry in
  `_CHECK_MAP` or a documented exemption in `_EXEMPTIONS`** — the
  completeness test enforces this; do not bypass it by extending the
  allowlist.
- **UNVERIFIED is a first-class audit state.** It is neither a violation
  nor a pass: with an exemption it is visible-but-not-failing; without one
  it fails the run. Never add a silent `return []` / `continue` path to a
  check.
- **Recompute with the encoder's own primitives.** Checks use the same
  `_bbox` / `_chebyshev_gap` geometry the handlers encoded against (KTD3),
  so a different geometry path cannot audit a different model.

## Related Issues

- `docs/plans/2026-08-02-016-feat-post-solve-audit-all-constraints-plan.md` — the plan this entry implements.
- `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` — the incident class and the documented-NOTE convention.
- `docs/solutions/test-failures/integration-temper-hardcoded-components-drifted-from-pcl-fixture.md` — the false-positive PIN_TO_PIN incident this audit's UNVERIFIED path guards against.
- `docs/physics-verification-methodology.md` — the R24 discipline (soundness proof / BMC / post-solve audit) this pattern operationalizes.
