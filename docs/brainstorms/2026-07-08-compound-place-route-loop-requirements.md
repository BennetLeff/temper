---
date: "2026-07-08"
topic: compound-place-route-loop
status: requirements
tier: deep-feature
---

# The Compound Place→Route Loop — All Gates, Unattended Convergence

## Summary

Extend the existing `PlaceRouteLoop` to consume all five territory gates (placement DRC, routing DRC + ERC, physics oracle, W4 quality linter). On any violation, emit a constraint and re-solve — the loop iterates until all gates are green or it surfaces the blocking constraint to the operator. Gate: `PlaceRouteLoop.run()` converges to all-green on the temper board, unattended, within a bounded number of rounds.

## Problem Frame

The existing `PlaceRouteLoop` (`placer/cp_sat/loop.py`) handles placement feedback only (DRC violations → SEPARATED constraint deltas → CP-SAT re-solve). It does not consume routing quality gates (W1 R1-R4: unconnected nets, DRC errors, ERC violations), physics gates (W3 R1-R4: loop inductance, thermal margin, creepage), or aesthetic gates (W4 R1-R5: octilinear %, via count, slop linter). Each workstream (W1-W4) produces a gate but leaves the feedback mechanism as "deferred to the compound loop." This workstream wires them all together.

## Requirements

### R1 — Extend PlaceRouteLoop to consume all gates

Add a gate registry to `PlaceRouteLoop`: a list of `Gate` objects, each with a `check(state) → list[Violation]` method and a `to_delta(violation) → ConstraintDelta` method. After each place→route round, run all registered gates. On any violation, emit the corresponding constraint delta and trigger a re-solve.

Gate types:
- `DrcGate` (placement DRC from golden-board decomposition)
- `RoutingGate` (unconnected nets, routing DRC, ERC from W1)
- `PhysicsGate` (loop inductance, thermal margin, creepage from W3)
- `QualityGate` (octilinear %, via count, slop linter from W4)

Gate: `PlaceRouteLoop.run()` iterates until `all_gates_green()` or `max_rounds` reached.

### R2 — Constraint delta vocabulary for each gate

Each gate maps its violation type to a `ConstraintDelta` that the placer or router can consume:
- **DRC violation** (clearance, short, mask bridge): `SeparatedConstraint(min_distance_mm = violated_mm + δ)` — existing pattern
- **Unconnected net:** `AnchoredConstraint(net, near_pin)` — force the net to be routed through a specific channel
- **Loop inductance > budget:** `LoopAreaConstraint(loop_name, max_area_mm2)` — force tighter component grouping
- **Creepage violation:** `SeparatedConstraint(net_a, net_b, min_distance_mm=6.0)` — same as existing cross-class SEPARATED
- **Via count > ceiling:** `ViaCostMultiplier(net, multiplier)` — increase via penalty for the offending net
- **Slop pattern:** `KeepoutConstraint(region)` — block the region where the slop occurred

Gate: every gate type has at least one `ConstraintDelta` mapping. The loop's existing `_solve_with_delta` handler dispatches the delta to CP-SAT re-solve.

### R3 — Bounded convergence

The loop must converge within a bounded number of rounds (max 10 per the existing `MAX_ROUNDS`). If `max_rounds` is reached without convergence, surface the blocking constraints to the operator via the UNSAT core mechanism.

Gate: on the temper board, the loop converges to all-green within ≤ 5 rounds. If it doesn't, the UNSAT core identifies which gate is over-constrained.

### R4 — Unattended execution

`temper optimize` with all gates registered must run to completion without operator intervention. The loop must handle infeasible deltas by escalating to the operator (existing `UnsatError` mechanism), not by silently skipping gates.

Gate: `temper optimize --all-gates temper.kicad_pcb` runs to completion and produces a routed `.kicad_pcb` that passes all gates.

## Key Decisions

- **Gate registry, not monolithic loop.** Adding each new gate type to a central `if/elif` chain would create a god-function. A registry of `Gate` objects with `check()` → `to_delta()` keeps the loop clean and each gate testable in isolation.
- **Constraint deltas follow the existing hybrid backtracking policy.** Safety-critical deltas (creepage, thermal) are hard — the operator must approve. Quality deltas (via count, slop) are soft — the loop tries them, skips on UNSAT.
- **The loop orchestrates; gates are pure functions.** A `Gate.check(state)` receives the current board state and returns violations. It does not mutate state. The loop handles the feedback logic.

## Scope Boundaries

- New constraint types (beyond the existing PCL vocabulary + delta extensions) are out of scope — reuse existing constraint types with delta parameters.
- Real-time convergence visualization is out of scope — the loop reports round-by-round status via logging.
- Multi-board optimization (running the loop on multiple boards in parallel) is out of scope.

## Dependencies

- **W0-W4.** All five workstreams must be complete for the compound loop to consume their gates.
- **Existing PlaceRouteLoop.** The loop's existing delta injection and UNSAT surfacing mechanisms are reused.

## Success Criteria

1. `PlaceRouteLoop.run(all_gates=True)` converges to all-green on the temper board within ≤ 5 rounds
2. Each gate type (DRC, routing, physics, quality) has a `check()` and `to_delta()` implementation
3. `temper optimize --all-gates` runs unattended and produces a routed `.kicad_pcb` passing all gates
4. On an intentionally broken board (e.g., too-small board for 6mm creepage), the UNSAT core names the blocking constraint
