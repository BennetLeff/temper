---
title: Termination is not convergence — don't let a round-budget masquerade as a fixed point
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - "verifying an iterative or fixed-point loop (place-route feedback, relaxation, retry loops)"
  - "a loop has a max-iteration / round budget as its termination backstop"
  - "a success/convergence verdict is derived from a loop that stopped running"
tags:
  - fixed-point
  - convergence
  - termination
  - loop
  - verification
---

# Termination is not convergence — don't let a round-budget masquerade as a fixed point

## Context
The W5 place→field→route→field fixed-point loop has a round budget (`FIELD_CONVERGENCE_ROUND_LIMIT`) as its termination backstop. A verification requirement was phrased as "the loop terminates," and the success metric read "termination is proven." But a round budget makes **any** finite loop terminate — it says nothing about whether the loop reached a fixed point.

## Guidance
Split the property into two distinct claims and test them separately:

- **Halting (R15a):** the loop always stops — trivially guaranteed by the round budget or a ranking function. True of every finite loop; **never report this as "convergence."**
- **Convergence (R15b):** *when the loop reports success* (all stability counters ≥ threshold), the final state is within ε of a fixed point, or oscillation amplitude is bounded.

A run that exits on the round budget while the field is still drifting must be classified as **budget-exhaustion, not convergence**. The test for a monotonically-drifting input should assert `exit_reason == ROUND_LIMIT` (not SUCCESS).

## Why This Matters
Conflating the two gives false confidence: "the loop terminated" reads as "the layout settled," when it may have been chopped off mid-drift or mid-oscillation at the budget. Downstream consumers then trust a non-converged layout. The distinction is exactly the kind of green-signal-measuring-the-wrong-thing this project keeps getting bitten by.

## When to Apply
- Any iterative solver, relaxation, or feedback loop with a max-iteration cap.
- Any place where a "converged/success" flag is derived from a loop that stopped.
- Retry/backoff loops where "gave up after N" must not be reported as "succeeded."

## Examples
```
# Wrong: one property, conflated
assert loop.run(...).terminated          # true for ANY finite loop — proves nothing about the field

# Right: two properties
assert loop.run(drifting_field).exit_reason == ROUND_LIMIT     # R15a: halts, but NOT converged
r = loop.run(settling_field)
assert r.success and field_delta(r.last_rounds) < EPS          # R15b: convergence ⇒ near-fixed-point
```

Also useful: verify the counter logic with stateful property testing (Hypothesis `RuleBasedStateMachine`) driving random per-round outcomes — assert stability counters stay independent and `success ⟺ all counters ≥ threshold`.

## Related
- `docs/plans/2026-07-09-001-feat-physics-verification-rigor-plan.md` (U7, R15/R16)
- `docs/solutions/architecture-patterns/place-route-loop-feedback-constraint-deltas-2026-07-05.md`
