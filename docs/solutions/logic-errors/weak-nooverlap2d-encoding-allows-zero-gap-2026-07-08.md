---
title: Weak NoOverlap2D encoding allows zero-gap touching — Chebyshev disjunction is the correct SEPARATED encoding
date: "2026-07-08"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "CP-SAT reports OPTIMAL but physical DRC shows component pads shorting"
  - "Pairwise Euclidean gaps as low as 0mm despite a 0.4mm SEPARATED constraint"
  - "Constraint enforcement appears to work for large margins (6mm) but fails for small margins (0.3mm)"
root_cause: "One-axis interval inflation under-enforces pairwise clearance — AddNoOverlap2D with inflation on one component's intervals only requires disjointness on ONE axis, not both. The Chebyshev disjunction is chosen over symmetric two-axis inflation because it enables per-pair UNSAT assumption literals (R3 requirement)."
resolution_type: code_fix
tags: ["cp-sat", "separated", "nooverlap2d", "chebyshev", "encoding", "soundness-proof", "induction"]
---

# Weak NoOverlap2D encoding allows zero-gap touching — Chebyshev disjunction is the correct SEPARATED encoding

## Problem

The netclass-aware clearance SSOT enforced SEPARATED constraints at 6mm (cross-class), 0.4mm (courtyard τ), and 0.3mm (netclass Power↔GND). The solver reported OPTIMAL, indicating all constraints were satisfied. But kicad-cli DRC showed 12 shorting items, 15 solder mask bridges — components were physically touching.

The gap between C_MCU_3 and C_CT_FILT was 0.135mm despite a 0.3mm netclass constraint. The gap between J_AC_IN and D1 was 0.000mm despite a 0.4mm courtyard constraint.

## Symptoms

- CP-SAT solver status: OPTIMAL (claiming all constraints satisfied)
- Physical gap between C_MCU_3↔C_CT_FILT: 0.135mm (expected ≥0.3mm)
- Physical gap between J_AC_IN↔D1: 0.000mm (expected ≥0.4mm)
- 12 shorting_items, 15 solder_mask_bridge in kicad-cli DRC
- 6mm cross-class constraints happened to work (HV/LV zones on opposite sides of board)

## What Didn't Work

**Investigating `mm_to_units` rounding.** The unit conversion was correct — `mm_to_units(0.3) = 30`, `mm_to_units(6.0) = 600`. No rounding error.

**Investigating constraint deduplication.** All 528 pairs had at least one SEPARATED constraint (276 netclass + 338 courtyard). No uncovered pairs.

**Investigating the model wrapper.** Constraints were correctly added to the same CpModel instance used for solving. No model-copying issue.

**Suspicion confirmed: validate with raw OR-Tools.** A minimal test with 2 components and the raw OR-Tools API confirmed the encoding itself was correct — the constraint enforcement failed only through the wrapper path. But deeper investigation revealed the wrapper was fine; the issue was subtler.

## Root Cause

**The `_encode_separated` handler inflated ONE component's intervals and checked `AddNoOverlap2D(inflated_A, normal_B)`.** `AddNoOverlap2D` correctly enforces non-overlap, and symmetric two-axis inflation would also correctly enforce clearance ≥ margin — cheaper than 6 Booleans × 528 pairs. The real reason to prefer the Chebyshev disjunction is per-pair UNSAT assumption literals: `AddNoOverlap2D` (global constraint) cannot carry `OnlyEnforceIf` enforcement literals, so it cannot surface which specific pair caused infeasibility. The disjunction encodes the same pairwise separation as axis-level `AddNoOverlap2D` variants but with per-pair enforceable Booleans, satisfying R3's per-pair UNSAT surfacing requirement.

With one-axis inflation, `AddNoOverlap2D(inflated_A, normal_B)` only requires disjointness on ONE axis. If A is above B (y disjoint), they can touch horizontally (x overlap), producing a 0 gap on the unconstrained axis.

```python
# OLD ENCODING (weak):
# Inflate component A's intervals, leave B's normal
x_start_a = model.new_int_var(..., va.x_start - margin, ...)
x_end_a = model.new_int_var(..., va.x_end + margin, ...)
model.model_ref.AddNoOverlap2D([inflated_A_x, B_x], [inflated_A_y, B_y])
```

`AddNoOverlap2D` requires that the 2D rectangles don't overlap — meaning EITHER their x-intervals are disjoint OR their y-intervals are disjoint. If A is above B (y disjoint), they can touch horizontally (x overlap). The inflation widens A's interval, but only on one side (A), and only affects one axis.

For the 6mm cross-class constraints, this happened to work because HV components were on the left side of the board and LV components on the right — the solver naturally separated them horizontally. For small same-class components with τ = 0.3mm or 0.4mm, the solver found vertical separation and left horizontal gaps at 0.

## Solution

Replace `AddNoOverlap2D` + inflation with a proper pairwise **Chebyshev disjunction** using 6 Boolean variables per pair:

```python
# NEW ENCODING (correct):
margin = model.mm_to_units(constraint.min_distance_mm)

# Direction Booleans
left  = model.new_bool_var(...)
right = model.new_bool_var(...)
below = model.new_bool_var(...)
above = model.new_bool_var(...)

model.model_ref.Add(va.x_end + margin <= vb.x_start).OnlyEnforceIf(left)
model.model_ref.Add(vb.x_end + margin <= va.x_start).OnlyEnforceIf(right)
model.model_ref.Add(va.y_end + margin <= vb.y_start).OnlyEnforceIf(below)
model.model_ref.Add(vb.y_end + margin <= va.y_start).OnlyEnforceIf(above)

# Axis Booleans: x_ok ⇔ left ∨ right, y_ok ⇔ below ∨ above
x_ok = model.new_bool_var(...)
y_ok = model.new_bool_var(...)
model.model_ref.AddBoolOr([x_ok.Not(), left, right])
model.model_ref.AddBoolOr([y_ok.Not(), below, above])

# Final disjunction: at least one axis has the gap
model.model_ref.AddBoolOr([x_ok, y_ok])
```

## Why This Works

**Soundness theorem.** At SAT, `x_ok ∨ y_ok` is true. If `x_ok` is true, then `left ∨ right` is true — one of the directional x-booleans holds, and the corresponding linear bound is enforced. The same holds for y. In all cases, the Chebyshev (L∞) gap between the two components' bounding boxes is ≥ margin. Since d₂ = √(gx² + gy²) ≥ max(gx, gy) = d∞, the Euclidean gap is also ≥ margin.

**Induction.** Base: n ≤ 1 — no pairs, constraint vacuously satisfied. Step: assume all pairs in {1..k} satisfy the constraint. Adding component k+1 adds pairwise constraints (i, k+1) for i ≤ k. Each is an independent set of linear bounds on existing variables — previously satisfied constraints are unaffected. By induction, at SAT all pairs satisfy the Chebyshev gap ≥ margin. ∎

## Prevention

1. **Property-based test for soundness.** P1 in `test_geometry_constraints_pbt.py` verifies that for Hypothesis-generated placements, the Euclidean gap between ALL pairs' **bounds boxes** is ≥ τ. This catches encoding bugs in the constraint handler. However, P1 does NOT verify that bounds enclose pads — if `component.bounds ⊉ pads`, the constraint can be perfectly satisfied on bounds while DRC still sees shorts at the pad level. That gap needs a separate invariant test (bounds ⊇ pads on every component) plus the golden-board DRC gate.

2. **Golden-board DRC gate.** `test_regression_drc.py` runs kicad-cli DRC on the placed temper board and asserts specific violation counts. This catches both encoding bugs AND bounds-vs-pads gaps because it measures the territory, not the model. P1 measures the map — both are needed.

3. **Binary-search margin test.** A deterministic test: two components with τ separation → solver SAT → verify Chebyshev gap ≥ τ. For τ = 0.1, 0.3, 0.4, 6.0. Each τ value catches under-enforcement at different scales.

## Related

- `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py:92` — `_encode_separated` (fixed)
- `packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py` — P1 soundness test
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — golden-board DRC gate
- `docs/reports/2026-07-08-netclass-clearance-ssot-full-report.md` — full workstream report
