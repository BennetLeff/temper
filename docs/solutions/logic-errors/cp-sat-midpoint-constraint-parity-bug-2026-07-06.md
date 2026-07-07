---
module: temper_placer
date: "2026-07-06"
problem_type: logic_error
component: placer
severity: high
symptoms:
  - "CP-SAT solver returned INFEASIBLE in <100ms when adding AddElement rotation to >7 components"
  - "Same model without rotation solved to OPTIMAL in <0.1s"
  - "Even-sized components (1000, 948 units) → OPTIMAL; odd-sized components (1100, 949 units) → INFEASIBLE"
root_cause: logic_error
resolution_type: code_fix
tags:
  - cp-sat
  - rotation
  - constraint-modeling
  - parity
  - solver-infeasible
  - mm-to-units
  - add-element
---

# CP-SAT Midpoint Constraint Parity: x_size Must Be Even

## Problem

Adding `AddElement` rotation to the CP-SAT placement model made it INFEASIBLE at >7 components. The solver returned INFEASIBLE in <100ms even with a 30-second timeout.

## Symptoms

- Solver returned INFEASIBLE in <100ms at 30s timeout with rotation enabled
- Failure threshold: infeasible at >7 components, feasible at ≤7 (threshold was coincidental — parity contradiction propagated later in larger models)
- Even-sized components always OPTIMAL; odd-sized always INFEASIBLE

## What Didn't Work

- Increasing solver timeout to 30s — still INFEASIBLE, confirming a constraint contradiction not search difficulty
- Separate index variables with equality constraint (`rot_x == rot_y`) — same result
- Replacing `AddElement` with `OnlyEnforceIf` per rotation — same result (the bug is in the constraint math, not OR-Tools)

## Solution

Changed `mm_to_units` in `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py:93-94` to round to the nearest even integer:

```python
# Before
def mm_to_units(self, mm: float) -> int:
    return int(round(mm * self.units_per_mm))

# After
def mm_to_units(self, mm: float) -> int:
    raw = int(round(mm * self.units_per_mm))
    return raw - (raw % 2) if raw % 2 else raw
```

## Why This Works

The CP-SAT model's midpoint and size constraints form a parity lock:

- `x_start + x_end == 2 * x_center` (midpoint constraint)
- `x_start + x_size == x_end` (size constraint)

Substituting: `2 * x_start + x_size == 2 * x_center`. Since `2 * x_center` is always even, `2 * x_start + x_size` must be even. `2 * x_start` is always even, so **x_size itself must be even**. With odd `x_size = 949` from `mm_to_units(9.49 * 100)`, the left side is odd while the right side is even — a contradiction that makes the entire model unsatisfiable.

For ≤7 components, solver search found an assignment before the parity contradiction propagated fully. For ≥8, the contradiction became unavoidable.

## Prevention

- Invariant test verifying all `mm_to_units` outputs are even
- Code comment near midpoint constraints documenting the parity requirement
- Consider using `x_center = x_start + x_end` (twice the actual center) to avoid parity entirely — allows half-unit centers for odd-sized components

## See Also

- `docs/solutions/architecture-patterns/cp-sat-constraint-encoder-greenfield-hard-ceiling-2026-07-05.md` — same encoder surface
- `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md` — rotation representation bugs produce silent failures
