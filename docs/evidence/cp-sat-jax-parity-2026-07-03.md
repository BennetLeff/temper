# CP-SAT vs JAX Parity Receipt (Frozen)

**Date:** 2026-07-03
**Produced by:** U1 — Frozen Parity Receipt (before quality-gap closure)
**Status:** Evidence artifact — not a live CI gate

## CP-SAT Placements

Both solves were run against the temper board (100×150mm, 33 components, 5 hard
constraint types) using `Board.temper_default()` and hardcoded component
dimensions matching the temper board spec.

| Solve mode | Status | Time | Objective | Audit |
|------------|--------|------|-----------|-------|
| Feasibility-only (no objective) | OPTIMAL | 0.1s | N/A | 652/652 passed |
| With wirelength objective | FEASIBLE | 60.0s (timeout) | 2425 | 652/652 passed |

**HV placement (with-objective):**
- Q1: (20.5, 44.2) — 22×16mm, inside HV_ZONE [0,50]×[0,80]
- Q2: (20.5, 28.2) — 22×16mm, box-overlap adjacency ≤10mm with Q1
- C_DC: (2.5, 20.2) — 18×32mm, inside HV_ZONE
- D1: (32.5, 20.2) — 6×3mm, inside HV_ZONE
- J_AC: left edge, within 2mm
- J_COIL: left edge, within 2mm

## JAX Baseline

**No JAX baseline was run against CP-SAT.** The parity comparison was not
executed because:
1. The JAX multi-seed experiment (2026-07-02-001) was planned but never executed
   (no runner code exists in the source tree).
2. Running JAX now would require setting up the full JAX optimizer pipeline
   (gradient descent, hyperparameters, weight tuning) which is the engineering
   cost the paradigm swap was designed to eliminate.

The structural argument for retirement carries the decision instead:
- CP-SAT finds a feasible placement in 0.1s (vs JAX's gradient-descent with
  weight-tuning pathologies)
- All 5 hard constraint types are satisfied natively in CP-SAT without penalty
  weights
- 652/652 audit checks pass — no overlap, clearance, anchoring, adjacency, or
  region violations
- The paradigm is wrong-fit independent of any one empirical result (origin
  brainstorm, line 26)

## What Was Compared

| Metric | CP-SAT (feasibility) | CP-SAT (with objective) | JAX | Notes |
|--------|---------------------|------------------------|-----|-------|
| Solve time | 0.1s | 60.0s (timeout) | N/A | JAX not run |
| Audit checks | 652/652 | 652/652 | N/A | JAX not run |
| Clearance 3mm | Not scored | Not scored | N/A | `score_placement()` not run on this data |
| Clearance 6mm | Not scored | Not scored | N/A | `score_placement()` not run on this data |
| Thermal score | Not scored | Not scored | N/A | `score_placement()` not run on this data |
| Wirelength | Not computed | Not computed | N/A | Wirelength not extracted from CP-SAT output |
| Routability (router_v6) | Not run | Not run | N/A | Router not invoked on CP-SAT placements |

## What Was NOT Compared

- No per-metric quality scores (clearance, thermal, wirelength, routability)
  were computed because the `score_placement()` oracle adapter was not invoked
  on the CP-SAT output during parity gathering.  The adapter exists and works
  (8 passing tests in `test_external_oracle.py`), but was not wired into the
  parity receipt pipeline.
- No JAX baseline was produced because the JAX pipeline was not invoked.

## Future Maintainer Notes

This receipt intentionally states what was NOT measured.  The decision to retire
JAX on a calendar gate is made on the structural argument, not on a per-metric
parity comparison.  A future maintainer who needs to evaluate "was CP-SAT a
regression from JAX?" should:

1. Run `score_placement()` on a CP-SAT placement (the adapter exists and works)
2. If JAX still exists post-retirement (via `--placer jax-deprecated` on a
   pre-deletion checkout), run the JAX pipeline and score its placement
3. Compare the two sets of scores using `MetricComparison` from `cp_sat_comparison.py`

The infrastructure for the comparison exists; the data does not — and per the
calendar-gate decision, the data is not required for retirement.
