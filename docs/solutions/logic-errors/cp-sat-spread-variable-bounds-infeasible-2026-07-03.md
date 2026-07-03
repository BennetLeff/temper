---
title: "CP-SAT spread variable bounds derived from component sizes cause INFEASIBLE when board is larger"
date: 2026-07-03
category: logic-errors
module: placer/cp_sat/model
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "CP-SAT model reported INFEASIBLE when wirelength objective with spread variables was enabled"
  - "Spread variable bounds derived from `max(component_size) * 2` were too small for the actual board span (100x150mm, 1000x1500 grid units)"
root_cause: logic_error
resolution_type: code_fix
tags:
  - or-tools
  - cp-sat
  - spread-variables
  - bounds
  - infeasibility
  - over-constrained
---

# CP-SAT spread variable bounds derived from component sizes cause INFEASIBLE

## Problem

`add_soft_wirelength_objective()` created intermediate `IntVar` variables (for
Manhattan distance deltas and bounding-box spread) with upper-bound domains
derived from max component size × 2.  When the board is significantly larger
than the components (e.g., 100×150mm board with components averaging 20mm),
the speculative bounds were too tight, causing the solver to return INFEASIBLE
even though a valid placement existed.

## Symptoms

- The CP-SAT model returned INFEASIBLE for configurations verified feasible by
  the U0 feasibility spike (which used hardcoded board dimensions).
- Removing the objective line made the model solve instantly — the infeasibility
  was in the objective channel, not the hard constraint channel.
- The error manifested only when the wirelength objective was enabled;
  feasibility-only solves (no objective) completed successfully.

## What Didn't Work

The original implementation derived variable domains from component sizes:

```python
# Original: domains from component sizes — too small for most boards
board_w_units = max(ctx.x_size[r] for r in ctx.x_size) * 2  # e.g., 440 units
board_h_units = max(ctx.y_size[r] for r in ctx.y_size) * 2

for a, b in net_pairs:
    dx = model.NewIntVar(0, board_w_units, f"dx_{a}_{b}")
    dy = model.NewIntVar(0, board_h_units, f"dy_{a}_{b}")
```

On a 100×150mm board with 0.1mm grid resolution (1000×1500 units), and components
averaging 20mm (200 units), the bound `200 × 2 = 400` was a fraction of the
actual board span.  Components at opposite board ends would need Manhattan distance
variables exceeding 400 units — exceeding their declared domain caps, which the
solver treats as infeasibility.

## Solution

Accept board dimensions as parameters with a larger fallback:

```python
def add_soft_wirelength_objective(
    model: cp_model.CpModel,
    ctx: SolveContext,
    net_pairs: list[tuple[str, str]],
    board_w_units: int = 0,
    board_h_units: int = 0,
    spread_weight: float = 1.0,
) -> None:
    if board_w_units <= 0:
        board_w_units = max(ctx.x_size[r] for r in ctx.x_size) * 4
    if board_h_units <= 0:
        board_h_units = max(ctx.y_size[r] for r in ctx.y_size) * 4

    # IntVars now use board_w_units / board_h_units for domain bounds
    x_min = model.NewIntVar(0, board_w_units, "x_min")
    x_max = model.NewIntVar(0, board_w_units, "x_max")
    # ...
```

Callers that know the board dimensions pass `_to_units(board.width, scale)`
and `_to_units(board.height, scale)` so variable domains match the real solution
space.  The fallback is also bumped from `×2` to `×4` as a more generous safety
net for code paths that don't pass board dimensions.

Fixed in commit `ddd8232c`.

## Why This Works

In CP-SAT, every `IntVar` must have a finite domain `[0, max_value]`.  When the
solver explores a placement with components at opposite corners of the board,
the distance variable must accommodate that span.  If the domain cap is smaller
than the actual distance the solver needs to express, the solver cannot encode
the solution and declares INFEASIBLE.

By setting the domain bounds to match the actual board dimensions, the variable
domain is large enough to express any feasible placement.

## Prevention

1. **Pass board dimensions to objective functions.** The parameters
   `board_w_units`/`board_h_units` should be required when the model's space is
   board-scaled.  Callers already holding `board_w_mm`/`board_h_mm` should pass
   `_to_units(...)` at the call site.
2. **When a model is INFEASIBLE, check the objective channel first.**
   Feasibility-only solves vs. with-objective solves is the fastest diagnostic
   split.  If the model solves without an objective and fails with one, the
   objective channel contains the infeasibility.
3. **Set variable domains to the maximum physically meaningful value.** For PCB
   placement, that's the board diagonal in grid units.  Component sizes are wrong
   because placement is a board-spanning problem.
4. **Test feasibility-only as a baseline.** Before adding objectives, confirm
   the hard constraint model is satisfiable.

## Related

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` —
  constraint encoding correctness pattern
- `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py:add_soft_wirelength_objective`
- Commit `ddd8232c` — spread variable bounds fix
