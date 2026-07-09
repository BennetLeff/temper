---
title: Endpoint-only bounding is unsound without a monotonicity proof
date: "2026-07-09"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "A feasibility/safety gate evaluates only the extremes of a parameter range and treats them as bounds on the whole interval"
  - "Gate can report CLEAN while an interior parameter value violates the ceiling"
  - "No continuous model of the swept parameter exists — only two labelled endpoints"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags:
  - bounding
  - monotonicity
  - soundness
  - gate
  - interval
---

# Endpoint-only bounding is unsound without a monotonicity proof

## Problem
The operating-point gate (`physics/operating_point.py`) bounded the coupled-load operating point by evaluating only the two coupling extremes (`k=0`, `k=1`) and treating them as bounds on the whole `[0,1]` range. Evaluating endpoints bounds the interior **only if the function is monotone** over the interval — otherwise an interior extremum can breach a ceiling while both endpoints pass, and the gate reports CLEAN on an unsafe design.

## Symptoms
- Gate computed `di/dt` and power at `k=0` and `k=1` only; `_ExtremePoint.coupling` was a label (0.0/1.0), not a sampled range.
- No `L_eff(k)` interpolation existed, so there was no interior to check.
- A non-monotone operating point with an interior violation would pass the gate.

## What Didn't Work
- Assuming "extremes bound the interior" without stating *why*. For this circuit it happens to be true, but the code encoded the conclusion without the premise — so any future change that made a term non-monotone would silently make the gate unsound.

## Solution
Make the continuous model explicit and either prove monotonicity or sample the interior:

```python
# define the continuous coupling model the gate was missing
L_eff(k) = L_coil * (1 - k) + L_leakage * k        # k in [0, 1]
# di/dt(k) = V_bus / L_eff(k) is monotone in k (1/x, L_eff linear & one-signed);
# power / T_j are coupling-independent  => endpoints PROVABLY bound the interior.
```

Document the proof, and add an interior-sampling safeguard (fixed grid, e.g. 11 points) that asserts no sampled interior value beats the endpoint worst-case — so if a future model becomes non-monotone the gate degrades to sampling instead of silently trusting the extremes. Keep it fail-closed (VIOLATIONS/UNMEASURED, never a silent CLEAN).

## Why This Works
Endpoint evaluation is a valid bound **iff** the quantity is monotone on the interval. Proving `L_eff(k)` linear and `di/dt = V_bus/L_eff` monotone makes the endpoints a sound bound; the interior sampler is a cheap guard against the monotonicity assumption breaking later. A property test then asserts `sampled_interior_worst_case ≤ reported_worst_case` across generated profiles.

## Prevention
- Any gate that bounds a swept quantity by its extremes must **state and test** the monotonicity that makes that sound, or sample/interval-bound the interior.
- This is the runtime cousin of the CP-SAT physics-constraint discipline (AGENTS.md R24): a bound that gates on a physics quantity needs a soundness argument, not just endpoint evaluation.

## Related Issues
- `docs/plans/2026-07-09-001-feat-physics-verification-rigor-plan.md` (U2, R5)
- AGENTS.md — "Future CP-SAT Physics Constraint Discipline (R24)"
