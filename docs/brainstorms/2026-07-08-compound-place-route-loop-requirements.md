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

Add a gate registry to `PlaceRouteLoop`: a list of `Gate` objects, each with a `check(state) → GateResult` method. `GateResult` is a three-state type (see `docs/brainstorms/2026-07-08-gate-contract.md`):

```
GateResult{status: CLEAN | VIOLATIONS | UNMEASURED, violations: list[Violation]}
```

- `CLEAN` — measurement completed, zero violations. The gate is green.
- `VIOLATIONS` — measurement completed, violations found. Emit `to_delta()` per violation.
- `UNMEASURED` — measurement could not be performed (tool crashed, board didn't load, oracle errored, kicad-cli exited nonzero). The gate is red — convergence is blocked until the gate can measure.

**Why three-state.** An empty violations list means two different things: "measured, clean" and "couldn't measure." This is the `run_drc` false-zero bug elevated to an architectural invariant: a gate whose tool crashes returns `UNMEASURED`, not `[]`. `all_gates_green()` returns `True` when every gate's `status == CLEAN` — an unmeasured gate can never pass.

`Violation` is a dataclass with:
- `type` (enum: `CLEARANCE`, `UNROUTED`, `LOOP_INDUCTANCE`, `THERMAL`, `CREEPAGE`, `VIA_COUNT`, `SLOP`)
- `components` (`list[str]`)
- `nets` (`list[str]`)
- `severity` (`float`)
- `context` (`dict` for gate-specific parameters like `required_mm`, `max_area_mm2`, `location`)

`state` is a `BoardState` wrapping the current placement (`CpSatPlacementResult`) + routing (`RoutingResult`) + netlist.

Gate types:
- `DrcGate` (placement DRC from golden-board decomposition)
- `RoutingGate` (unconnected nets, routing DRC, ERC from W1)
- `PhysicsGate` (loop inductance, thermal margin, creepage from W3)
- `QualityGate` (octilinear %, via count, slop linter from W4)

Each `Gate` declares a `stage`: `PLACEMENT` (checked after CP-SAT solve, before routing) or `ROUTING` (checked after routing). `DrcGate` runs at `PLACEMENT`; all others run at `ROUTING`. This avoids re-routing on placement-only violations.

**Integration with existing code.** The `Gate` registry wraps the existing `FeedbackClassifier`. `DrcGate` and `RoutingGate` compose the existing feedback classes (congestion, DRC, unrouted-pin). `PhysicsGate` and `QualityGate` are additive. The loop calls `Gate.check()` after each round, replacing the direct `classify()` call.

`all_gates_green()` returns `True` when every registered `Gate`'s `check(state)` returns `status == CLEAN`. Equivalent to: `all(gate.check(state).status == GateStatus.CLEAN for gate in self.gates)`. A gate returning `UNMEASURED` prevents convergence until the measurement can be performed successfully.

Gate: `PlaceRouteLoop.run()` iterates until `all_gates_green()` or `max_rounds` reached.

### R2 — Constraint delta vocabulary for each gate

Each gate maps its violation type to a `ConstraintDelta` that the placer or router can consume:
- **DRC violation** (clearance, short, mask bridge): `SeparatedConstraint(min_distance_mm = violated_mm + δ)` — existing pattern
- **Unconnected net:** `AnchoredConstraint(component=comp_ref, region=vicinity_of_pin)` — bias the offending component toward the pin so the net can route (matches the existing `feedback.py:334-340` implementation)
- **Loop inductance > budget:** `LoopAreaConstraint(loop_name, max_area_mm2)` — force tighter component grouping
- **Creepage violation:** `SeparatedConstraint(net_a, net_b, min_distance_mm=6.0)` — same as existing cross-class SEPARATED
- **Thermal margin not met:** `SeparatedConstraint(a=hot_component, b=thermal_sensitive_component, min_distance_mm=violated_margin + δ)` — increase separation between the hot component and any component whose thermal budget is violated
- **Via count > ceiling:** `KeepoutConstraint(region)` — place a keepout zone on the congested via region to force re-routing
- **Slop pattern:** `KeepoutConstraint(region)` — block the region where the slop occurred, where `region` = bounding box of the offending trace segments, expanded by 2× `track_width` on each side

`LoopAreaConstraint` tightens by 5% per round: `max_area_mm2 = measured × 0.95`. It is treated as SOFT — if UNSAT, it surfaces rather than blocks convergence.

Gate: every gate type has at least one `ConstraintDelta` mapping. The loop's existing `_solve_with_delta` handler dispatches the delta to CP-SAT re-solve.

### R3 — Bounded convergence

The loop must converge within a bounded number of rounds (max 10 per the existing `MAX_ROUNDS`). If `max_rounds` is reached without convergence, surface the blocking constraints to the operator via the UNSAT core mechanism.

Gate: on the temper board, the loop converges to all-green within ≤ 5 rounds. If it doesn't, the UNSAT core identifies which gate is over-constrained.

### R4 — Unattended execution

`temper optimize` with all gates registered must run to completion without operator intervention. The loop must handle infeasible deltas by escalating to the operator (existing `UnsatError` mechanism), not by silently skipping gates. Unattended mode auto-accepts hard deltas (no operator prompt).

Gate: `temper optimize --all-gates temper.kicad_pcb` runs to completion and produces a routed `.kicad_pcb` that passes all gates.

## Key Decisions

- **Gate registry, not monolithic loop.** Adding each new gate type to a central `if/elif` chain would create a god-function. A registry of `Gate` objects with `check()` → `to_delta()` keeps the loop clean and each gate testable in isolation.
- **`check()` and `to_delta()` are split.** `Gate.check(state) → list[Violation]` is pure and testable in isolation. A separate `DeltaMapper.map(violation) → ConstraintDelta` is shared across gates and tested once.
- **Constraint deltas follow the existing hybrid backtracking policy.** Safety-critical deltas (creepage, thermal) are hard-constraint deltas — the solver must satisfy them without skipping. If a hard delta produces UNSAT, the loop surfaces it (via `UnsatError`) but continues trying the next delta. In attended mode, the operator approves relaxation. In unattended mode, the loop exits with the UNSAT core surfaced in the result. Quality deltas (via count, slop) are soft — the loop tries them, skips on UNSAT.
- **The loop orchestrates; gates are pure functions.** A `Gate.check(state)` receives the current board state and returns violations. It does not mutate state. The loop handles the feedback logic.

## Scope Boundaries

- New PCL constraint types are out of scope. Via-count feedback reuses `KeepoutConstraint`. Thermal margin reuses `SeparatedConstraint`. All delta types map to existing PCL types.
- ERC violations are limited to routing-induced issues (pins left floating because a trace couldn't route). These map to `AnchoredConstraint` as above. Schematic-level ERC violations are detected pre-loop and fail-fast before convergence.
- Real-time convergence visualization is out of scope — the loop reports round-by-round status via logging.
- Multi-board optimization (running the loop on multiple boards in parallel) is out of scope.

## Dependencies

- **W0-W4.** All five workstreams must be complete for the compound loop to consume their gates.
- **Existing PlaceRouteLoop.** The loop's existing delta injection and UNSAT surfacing mechanisms are reused.

## Success Criteria

1. `PlaceRouteLoop.run(all_gates=True)` converges to all-green on the temper board within ≤ 5 rounds
   - **SC1a:** With `DrcGate` + `RoutingGate` only (no `PhysicsGate`/`QualityGate`), converges to all-green within ≤ 5 rounds on the temper board.
   - **SC1b:** Full gate convergence verified after W3/W4 integration.
2. Each gate type (DRC, routing, physics, quality) has a `check()` and `to_delta()` implementation
3. `temper optimize --all-gates` runs unattended and produces a routed `.kicad_pcb` passing all gates
4. On an intentionally broken board (e.g., too-small board for 6mm creepage), the UNSAT core names the blocking constraint
