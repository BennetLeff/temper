---
title: MMS proves solver correctness — converge to the right answer, not just the right rate
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "verifying a numerical solver that already has an order-of-accuracy convergence check"
  - "the refinement ladder proves 2nd-order convergence but you need to know to *what*"
  - "closed-form analytic solutions are too narrow (single geometry, uniform k) to catch stencil/BC bugs in 2-D"
tags:
  - mms
  - method-of-manufactured-solutions
  - solver-verification
  - correctness
  - finite-difference
  - thermal
---

# MMS proves solver correctness — converge to the right answer, not just the right rate

## Context
The thermal FDM solver had two correctness checks: a closed-form 1D bar (K1, a single uniform-k geometry) and a refinement ladder that asserted 2nd-order convergence. The ladder proves you converge at the *right rate*; the 1D bar proves you're close to the right answer *on one case*. Neither proves you converge to the *right answer everywhere*. A solver with a sign error in the 2D stencil or a BC mis-handling still converges at 2nd order — just to the wrong solution.

## Guidance
Use Method of Manufactured Solutions (MMS):
1. **Pick any smooth analytic T*(x,y).** For uniform k use `T* = sin(πx/Lx)·sin(πy/Ly) + T_amb`; for spatially-varying k choose a smooth `k(x,y)` and a compatible T*. Ensure the manufactured T* satisfies the solver's BCs (Dirichlet on the heatsink edge, adiabatic elsewhere).
2. **Derive Q*(x,y) = −∇·(k∇T*) analytically** using symbolic differentiation (sympy, or hand-derive a few). This is the source that would *exactly* produce T*.
3. **Feed Q* to the solver** at grid spacings h, h/2, h/4; measure the error ‖T_h − T*‖ in both L2 and L∞ norms; assert 2nd-order convergence to the *true* T* — not just the right rate.

MMS works for arbitrary geometry, spatially-varying k, and mixed BCs — anywhere the PDE is analytically differentiable. It is the gold standard for solver verification, requires no reference solver, and catches the gap between "right order" and "right answer."

## Why This Matters
The refinement ladder proves order; MMS proves correctness. A 1D bar checks one column; MMS checks every cell. For the thermal FDM, the existing tests would pass a solver that converged at 2nd order to the wrong harmonic-mean interface conductivity or a misoriented Dirichlet — MMS catches exactly those bugs. Smooth varying-k MMS additionally exercises the harmonic-mean interface treatment across genuinely heterogeneous conductivity, which the uniform-k 1D bar cannot.

## When to Apply
- Any numerical PDE solver where closed-form solutions are limited.
- When a convergence-order ladder exists — MMS is the complementary instrument that proves *what* it converges to.
- After a discretization/BC change (e.g., cell-centre → boundary-aligned Dirichlet) — MMS is the definitive check that it's still correct.

## Examples
On the thermal FDM with 2nd-order boundary-aligned Dirichlet:
- **Uniform k:** L2 error 3.09e-2 → 7.70e-3 → 1.93e-3 (rate 2.002). L∞: 6.12e-2 → 1.54e-2 → 3.85e-3 (rate 1.998).
- **Smooth spatially-varying k:** L2 rate 2.005, L∞ rate 2.001. The harmonic-mean interface treatment stays 2nd-order for continuous conductivity — no order reduction.

## Related
- `docs/solutions/logic-errors/thermal-fdm-cell-centre-dirichlet-first-order-2026-07-09.md` (the 1st-order BC the refinement ladder caught)
- `docs/physics-verification-methodology.md` (four-layer verification pattern — MMS is the correctness rung of the three-target ladder)
