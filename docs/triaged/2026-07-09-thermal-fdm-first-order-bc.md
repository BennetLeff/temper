# Triaged Bug Report — Thermal FDM solver is 1st-order accurate (cell-centre Dirichlet BC)

**Status:** triaged, scoped as follow-up (not fixed in `feat/physics-verification-rigor`)
**Severity:** low (accuracy limitation, not a correctness violation)
**Found by:** plan unit U5, order-of-accuracy refinement ladder (R11) —
`packages/temper-placer/tests/physics/test_thermal_fdm_refinement.py`
**Component:** `packages/temper-placer/src/temper_placer/physics/thermal_fdm.py` (physics-U5)
**Classification (per AGENTS.md R22):** architectural / discretization change → documented and
scoped as a separate follow-up, **not inlined** into the verification branch.

---

## Symptom

The refinement ladder solves a smooth, continuous-conductivity analytic case (uniform-`k` 1-D bar,
Dirichlet top edge, `T(y) = T_top + Q/(2k)·(H² − y²)`) at grid spacings `h`, `h/2`, `h/4` and measures
RMS error against the analytic solution:

| Grid spacing | Grid size | RMS error | ratio |
|--------------|-----------|-----------|-------|
| h = 2.0 mm   | 10×10     | 1.9500    | —     |
| h/2 = 1.0 mm | 20×20     | 0.9875    | 1.97× |
| h/4 = 0.5 mm | 40×40     | 0.4969    | 1.99× |

Effective order **p ≈ 0.99 (first order)**. A genuinely 2nd-order scheme would show ~4× error
reduction per halving (p ≈ 2). The interior 5-point stencil *is* 2nd-order; the global order is
dragged to 1st.

## Root cause

The Dirichlet boundary condition is imposed at **cell centres**, not on the physical boundary. The
half-cell offset between the cell-centre where `T = T_ambient` is enforced and the true edge
introduces a uniform `O(h)` error term that dominates the RMS/∞ norm as the grid refines. This is a
BC-placement artefact, not a stencil bug — the same mechanism by which the harmonic-mean interface
treatment drops to 1st order at material discontinuities.

## Impact assessment

- **Cost-field use (routing/placement guidance):** negligible. The field is a *relative* spatial cost;
  a uniform `O(h)` offset does not change the argmin structure that A*/zone-penalties consume.
- **Validation-instrument use:** bounded and now *documented* — the refinement test asserts the true
  (1st-order) rate with a tolerance band, so the instrument is honest about the solver's accuracy
  rather than over-claiming 2nd order. K1 (closed-form absolute agreement) still passes within its
  tolerance.
- **No invariant is violated:** energy conservation (R7), monotonicity (R8), maximum principle (R9),
  and SPD (R10) all hold on the current scheme. This is an accuracy floor, not a soundness failure.

## Why it is not fixed here

Recovering 2nd order requires changing the boundary discretization (ghost-cell / boundary-aligned
Dirichlet, i.e. placing the fixed-temperature node on the edge and adjusting the adjacent stencil
rows). That changes **every** thermal field value globally, with blast radius across the physics
feature's own thermal tests (K1/K2/adjacent-superposition/wider-trace), the U4 invariant battery
tolerances, and the U3 scorer↔solver comparison baselines. Per AGENTS.md R22, a discretization change
of this shape is scoped as a separate follow-up rather than inlined into a verification-hardening PR.

## Recommended fix (follow-up scope)

1. Replace cell-centre Dirichlet with a boundary-aligned / ghost-cell Dirichlet at the heatsink edge
   so the fixed-temperature node sits on the physical boundary.
2. Re-run the U5 refinement ladder; expect p → ~2 (≈4× reduction per halving). Tighten the ladder's
   asserted order accordingly.
3. Re-baseline the affected physics-feature thermal tests and the U4 invariant tolerances; confirm
   U3's convective-boundary scorer still shows the expected high-Biot disagreement.
4. Land as its own `fix(physics): 2nd-order Dirichlet BC in thermal FDM` PR with the re-baselined
   goldens in the same commit (per the golden-fixture-ladder convention).

## References

- Test: `packages/temper-placer/tests/physics/test_thermal_fdm_refinement.py`
- Solver: `packages/temper-placer/src/temper_placer/physics/thermal_fdm.py`
- Methodology: `docs/physics-verification-methodology.md`
- Plan: `docs/plans/2026-07-09-001-feat-physics-verification-rigor-plan.md` (U5, R11)
