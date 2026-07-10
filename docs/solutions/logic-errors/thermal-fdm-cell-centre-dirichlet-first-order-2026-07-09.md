---
title: Thermal FDM was 1st-order accurate — cell-centre Dirichlet BC instead of boundary-aligned
date: "2026-07-09"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "Order-of-accuracy refinement ladder shows error halving (~2x per grid halving), not quartering (~4x)"
  - "Effective convergence order p ~ 0.99 (first order) on a smooth continuous-conductivity case where the 5-point stencil should be second order"
  - "Closed-form (K1) absolute error stuck around 0.5 C and only barely under a 2% tolerance"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags:
  - fdm
  - finite-difference
  - boundary-conditions
  - order-of-accuracy
  - thermal
  - dirichlet
---

# Thermal FDM was 1st-order accurate — cell-centre Dirichlet BC instead of boundary-aligned

## Problem
The thermal FDM solver (`physics/thermal_fdm.py`) converged at **first order** on a smooth problem where its 5-point stencil should be second order. The interior discretisation was fine; the boundary treatment silently capped the global accuracy.

## Symptoms
- Refinement ladder (`tests/physics/test_thermal_fdm_refinement.py`): RMS error 1.95 → 0.99 → 0.50 across h, h/2, h/4 — ratio ~2x, effective order p ≈ 0.99.
- A genuinely 2nd-order scheme gives ~4x reduction per halving (p ≈ 2).
- K1 closed-form error ~0.5 C — passing the 2% bar only barely, masking the accuracy loss.

## What Didn't Work
- Trusting the single-point K1 closed-form check: it passed within tolerance and hid the order deficiency. A point check confirms "close enough on this grid," not the convergence *rate*. The defect was invisible until a refinement ladder measured order across multiple grid spacings.

## Solution
The heatsink Dirichlet condition was imposed at the **cell centre** (a row of fixed cells: `A[idx,idx]=1.0; b[idx]=ambient`), which sits half a cell *inside* the physical edge — a uniform `O(h)` offset. Move it to the boundary **face**: boundary-adjacent cells become active, and the face toward the heatsink contributes a Dirichlet term at distance `cs/2`:

```python
# was: fixed identity row at the heatsink edge (cell-centre Dirichlet)
#   A[idx, idx] = 1.0; b[idx] = ambient_C; continue
# now: boundary-aligned Dirichlet FACE term (distance cs/2 -> factor 2)
coeff = 2.0 * k_c / dx2
diag += coeff
b[idx] += coeff * config.ambient_C
```

After the fix: error ratio **4.00x per halving, p = 2.00**; K1 error 0.5 C → **0.003 C** (~1000x). As a bonus, removing the identity rows makes the full system matrix symmetric positive-definite / M-matrix (previously only the interior block was).

## Why This Works
A cell-centred grid places unknowns at cell centres; the physical Dirichlet boundary is at the outer face, `cs/2` beyond the outermost centre. Enforcing the fixed value at the centre solves a slightly different problem (boundary shifted inward by `cs/2`), injecting an `O(h)` error that dominates the RMS/∞ norm and drags global order to 1. Placing the condition on the face (conductance `2k/cs² ` reflecting the half-cell distance) matches the true BC, restoring the interior stencil's 2nd order.

## Prevention
- **Verify convergence *order* with a refinement ladder, not just a single-grid point check.** Solve a smooth analytic case at h, h/2, h/4 and assert error quarters per halving.
- Use a **continuous-conductivity** analytic case for the order check — the harmonic-mean interface treatment legitimately drops to 1st order at material (copper/FR4) discontinuities, so a discontinuous board would fail a 2nd-order expectation for a correct stencil.
- When imposing Dirichlet on a cell-centred grid, decide explicitly whether the value lives at the centre or the face; for boundary-aligned physics use the `2k/dx²` half-cell face term.

## Related Issues
- `docs/triaged/2026-07-09-thermal-fdm-first-order-bc.md` (triaged report that scoped this fix)
- `docs/plans/2026-07-09-001-feat-physics-verification-rigor-plan.md` (U5, R11)
