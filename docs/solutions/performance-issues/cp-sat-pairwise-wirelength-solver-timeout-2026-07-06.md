---
module: temper_placer
date: "2026-07-06"
problem_type: performance_issue
component: placer
severity: medium
symptoms:
  - "CP-SAT solver timed out at 30s with 33 components and full pair-wise wirelength objective"
  - "Same model without objective solved in <0.1s"
  - "Each component pair adds 4 IntVars + 3 constraints, scaling at O(n²)"
root_cause: logic_error
resolution_type: code_fix
tags:
  - cp-sat
  - wirelength
  - performance
  - quadratic-complexity
  - objective-function
  - phase-strategy
  - solver-timeout
---

# O(n²) Wirelength Objective Degrades CP-SAT Performance at Scale

## Problem

The `solve_placement` function constructed a full pair-wise wirelength objective with `AbsEquality` constraints for all N×(N-1)/2 component pairs. At 33 components, this produced 528 pairs, each adding 4 `IntVar`s + 3 constraints, for ~2100 extra variables. The solver timed out at 30s. Without the objective, CP-SAT found a valid placement in <0.1s.

## Symptoms

- Solver timed out (returned UNKNOWN) at all timeout values: 1s, 5s, 15s, 30s
- Model without objective: OPTIMAL in <0.1s for the same 33 components
- Root cause confirmed by removing the `Minimize(sum(...))` call: solver instantly found a feasible placement

## Why This Matters

33 components × 528 pairs = ~2100 extra `IntVar`s. Each variable participates in constraints that must propagate through the solver's conflict analysis. In CP-SAT, variable count is a primary cost driver — 2100 additional variables make the model unsolvable even though the underlying placement problem is straightforward.

## Solution

**Phase 1 (feasibility):** Skip the wirelength objective entirely. CP-SAT finds a valid placement from `set_bounds` + `AddNoOverlap2D` in <0.1s. The solver's native search is sufficient for feasible non-overlapping placement.

**Phase 2 (polish):** If wirelength optimization is needed after feasibility, use a bounded pair count and a longer timeout. Each pair costs 4 `IntVar`s + 3 constraints — budget pair count against solver capacity.

```python
# Phase 1 — feasibility only
# OPTIMAL in <0.1s for 33 components
model = CpSatModel(units_per_mm=100)
for comp in components:
    model.add_component(comp.ref, 0, 0, w, h)
model.set_bounds(0, 0, board_w, board_h)
model.add_no_overlap_2d(refs)
# No Minimize call
solver.Solve(model.model_ref)
```

## When to Apply

- Component count exceeds ~10 (50+ pairs, each pair = 4 vars + 3 constraints)
- Phase 1 where any valid placement is sufficient
- When solver times out on models that should be trivially satisfiable — check if the objective is bloating variable count

## Prevention

- Cap pair count in `Minimize` objective (e.g., top 50 net-critical pairs, not all 528)
- Use `add_objective_term(var, weight)` for sparse objectives instead of `Minimize(sum(...))`
- Benchmark solver performance with and without objective before committing to a phase strategy

## See Also

- `docs/solutions/performance-issues/sat-model-too-large-for-splr-selective-construction-2026-06-28.md` — same model-size/timeout pattern, different solver
- `docs/solutions/architecture-patterns/cp-sat-constraint-encoder-greenfield-hard-ceiling-2026-07-05.md` — wirelength in objective is a known forbidden pattern
