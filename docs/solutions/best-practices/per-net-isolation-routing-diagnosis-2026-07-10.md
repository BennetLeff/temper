---
title: Per-net isolation routing diagnosis separates router-side from placement-side failures
date: "2026-07-10"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "a board routes at less than 100% and the failure cause is unknown"
  - "deciding whether to fix the router or the placement — the split determines scope by an order of magnitude"
  - "a routing failure could be 'the router missed it' or 'no legal path exists under the constraints'"
tags:
  - routing
  - diagnosis
  - isolation-test
  - pcb
---

# Per-net isolation routing diagnosis separates router-side from placement-side failures

## Context

A board routed at 87.5% — 3 of 24 nets failed. The open question: "what's wrong with the router?" The answer determines whether the fix is a router improvement (algorithmic, bounded) or a placement rebuild (multi-gate feedback loop, much larger). Guessing wastes an order of magnitude of effort on the wrong branch.

## Guidance

For each unrouted net, route it **in isolation** — every other net and all constraints frozen, that single net attempted alone:

- **Legal path exists in isolation but fails in context** → *router-capability / congestion / ordering* failure. The fix is router-side (ordering heuristic, rip-up-reroute, negotiated-congestion). This is the bounded branch.
- **No legal path even in isolation** → *placement-topology* failure. The placement created an unroutable arrangement given the constraints. The fix is placement-side (re-place, routability feedback loop). This is the larger branch.

The isolation test converts the unanswerable "what's wrong with the router" into the measurable per-net "what blocks net X," and it runs before any fix work — measurement before plan.

## Why This Matters

The diagnosis split is decisive: a pure router-side fix is algorithmic (days); a placement feedback loop is architectural (weeks). The same failure rate — 3 of 24 nets — could mean either. The isolation test eliminates the entire architectural branch when zero nets fail the legal-path-exists test (as happened on the temper board: 3/3 routed in isolation → R3 off the table, R2 is the only work). This is the single cheapest measurement in the routing diagnosis workflow and the single most impactful scoping decision.

## When to Apply

- Any board that routes at less than 100%.
- Before committing to "improve the router" or "re-place" — the diagnosis determines which.
- Before `ce-plan` on routing work. The plan's scope is entirely determined by the isolation-test split; planning before measuring is planning on a guess.

## Examples

On the temper induction-cooker board (87.5% routed, 3 unrouted nets: SPI_MOSI, SPI_CLK, I_SENSE):

```python
# ISOLATION: route each net alone, all others removed from the board.
# Write a temp board with only the target net's connections, route it,
# and check whether the net routed.
for net_name in ['SPI_MOSI', 'SPI_CLK', 'I_SENSE']:
    isolated = _write_board_with_only(net_name, board_file)
    result = route_pcb(isolated_board, placements, seed=42)
    routed = net_name not in result.unrouted_nets
    print(f'{net_name}: {"ROUTED — legal path exists" if routed else "STILL UNROUTED"}')
```

Result: **3/3 routed in isolation** → legal paths exist → router-side failure. R3 (placement feedback loop) off the table. The remaining work is purely router-side: ordering, rip-up-reroute, or negotiated-congestion.

## Related

This is **step 1 of the routing-diagnosis ladder**: isolation → coexistence → escalate.
- `docs/solutions/best-practices/round-coexistence-cheaper-than-seed-stability-2026-07-10.md` — step 2 (within router-side: ordering vs contention)
- `docs/solutions/best-practices/seed-stability-doesnt-discriminate-ordering-contention-2026-07-10.md` — the anti-pattern that makes the step-2 check necessary
- `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` (U1 — the plan this diagnosis grounded)
- `docs/solutions/best-practices/termination-is-not-convergence-2026-07-09.md` (the same "measure, don't guess" discipline applied to loop behavior)
