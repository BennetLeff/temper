---
title: "CP-SAT feasibility-first placement solves in 0.1s; wirelength optimization drives the 60s budget"
date: 2026-07-03
category: architecture-patterns
module: placer/cp_sat
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "Designing CP-SAT models for PCB placement with ~30 components and 5+ hard constraint types"
  - "Choosing between a single combined solve (feasibility + objective) and a two-phase approach"
  - "Evaluating whether hard constraints natively expressed in CP-SAT are cheap enough to make feasibility-first the default strategy"
  - "When the wirelength objective dominates solver time and you want to unblock the pipeline with a feasible placement"
tags:
  - or-tools
  - cp-sat
  - feasibility-first
  - performance
  - pcb-placement
  - optimization-strategy
---

# CP-SAT feasibility-first placement solves in 0.1s; wirelength optimization drives the 60s budget

## Context

On a real PCB with 33 components and 5 hard constraint types (NoOverlap2D,
Chebyshev clearance, edge anchoring, pairwise proximity, region membership),
running CP-SAT **without an objective** (feasibility only) finds a valid
placement in **0.1 seconds**.  Adding a wirelength optimization objective
drives the solve time to **60 seconds** (hitting the timeout without proving
optimality).  The feasibility solve is **~600× faster** than the optimization solve.

This confirms the feasibility-first paradigm thesis: hard constraints are cheap
when expressed natively in CP-SAT's constraint programming primitives
(NoOverlap2D, `OnlyEnforceIf` disjunctive encoding, linear inequalities).  The
solver's propagation engine handles them efficiently.  The soft objective — a
sum of Manhattan distances plus a bounding-box spread term — transforms the
problem from constraint satisfaction (CSP → easy for CP-SAT) to constrained
optimization (COP → hard for CP-SAT).

## Guidance

**Produce a feasibility-only placement first (instant), then run a separate
follow-up optimization pass to improve wirelength without blocking the placement
pipeline.**

The two-stage approach:

```
Stage 1 — Feasibility (fast path):
  Solve with hard constraints only, NO objective
  Typ. 0.1s for N=33, 5 constraint types
  Output: valid placement suitable for routing

Stage 2 — Optimization (optional slow path):
  Warm-start from the Stage 1 placement
  Add wirelength objective, run with a soft timeout (e.g., 60s)
  Accept best-found solution when time expires
```

Implementation pattern:

```python
# Stage 1: Feasibility-first (near-instant)
feasible_model, ctx = build_cp_sat_model(components, board_w_mm, board_h_mm)
# Add hard constraints only ... no objective set
feasible_result = solve_cp_sat_model(feasible_model, ctx, timeout_s=30.0)

if feasible_result.status not in (OPTIMAL, FEASIBLE):
    return feasible_result  # UNSAT — report core extraction

# Stage 2: Warm-start optimization (time-bounded)
opt_model, opt_ctx = build_cp_sat_model(components, board_w_mm, board_h_mm)
# Add hard constraints AND objective
add_soft_wirelength_objective(opt_model, opt_ctx, net_pairs, ...)
opt_result = solve_cp_sat_model(opt_model, opt_ctx, timeout_s=60.0)

# Return best available result
final_positions = (
    opt_result.positions
    if opt_result.status in (OPTIMAL, FEASIBLE)
    else feasible_result.positions
)
```

## Why This Matters

- **Pipeline latency:** A placement pipeline that must produce output within
  seconds (interactive design tool, CI feedback loop) cannot afford a 60s
  optimization solve on every invocation.  The feasibility-first path gives a
  valid placement in 0.1s.  Optimization becomes a background refinement.
- **Diagnostic clarity:** When a solve fails, the feasibility/optimization split
  immediately tells you whether the problem is over-constrained (Stage 1 fails)
  or just hard to optimize (Stage 1 passes, Stage 2 times out).  This avoids
  the "is it infeasible or just slow?" ambiguity.
- **Robustness:** The optimization pass producing only FEASIBLE (not OPTIMAL)
  is OK — per the plan, "first feasible solution is the target."  The
  objective is a tiebreaker, not a hard requirement.

## When to Apply

Apply the feasibility-first paradigm when:
- The primary requirement is **valid placement** (all hard constraints met) —
  optimization is a secondary concern.
- Hard constraints are **natively expressible** in CP-SAT primitives
  (NoOverlap2D, interval variables, linear inequalities, `OnlyEnforceIf`).
- The objective function involves **sums of non-local terms** (wirelength,
  spread) that drive search complexity.
- The constraints are **dense enough** that feasibility is non-trivial (N≥10
  components, ≥3 constraint types).
- Your pipeline must produce output within **interactive time** (sub-second)
  but can accept best-effort optimization.

Do NOT apply when:
- The model is trivially feasible (e.g., a single component).
- The objective is also expressible as a hard constraint.
- The optimization quality must be **provably optimal**.

## Examples

### Comparison from temper board validation

| Test | Status | Time | Outcome |
|---|---|---|---|
| Feasibility-only (no objective) | OPTIMAL | **0.1s** | 33/33 components placed |
| With wirelength objective | FEASIBLE | **60.0s** (timeout) | Objective=2425, optimality not proven |

Constraint audit: 652/652 checks passed — no violations across all 5 constraint types.

### Feasibility-only solve with constraint audit

```python
model, ctx = build_cp_sat_model(components, board_w_mm=100, board_h_mm=150)
add_chebyshev_clearance(model, ctx, hv_lv_pairs, clearance_mm=8.5)
add_edge_anchoring(model, ctx, ["J_AC", "J_COIL"], max_dist_mm=5, edge="left")
add_proximity(model, ctx, [("Q1", "Q2", 10.0)])
add_region_membership(model, ctx, ["Q1", "Q2", "D1", "C_DC"],
                      region_x_min_mm=0, region_x_max_mm=50,
                      region_y_min_mm=0, region_y_max_mm=80, margin_mm=2)

result = solve_cp_sat_model(model, ctx, timeout_s=30)  # 0.1s
audit = audit_placement(result.positions, components, constraints)
assert audit.passed, f"Failed audit: {audit.violations}"
```

## Related

- `docs/solutions/architecture-patterns/alternating-projections-constraint-feasibility-optimization-init-2026-07-01.md` —
  C-CAP was the previous feasibility-first attempt (v2); CP-SAT is v3
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` —
  constraint solver audit pattern applied here
- `docs/solutions/best-practices/bmc-induction-ladder-constraint-verification-2026-07-01.md` —
  verification infrastructure for constraint encodings
- `docs/reports/2026-07-03-cp-sat-feasibility-first-placer-implementation-report.md` —
  full implementation report with parity gate status
