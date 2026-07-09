---
date: "2026-07-08"
topic: gate-contract
status: requirements
tier: standard-feature
---

# Gate Contract — Shared Specification for W1–W5

## Summary

Every gate in the place→route loop (W1 routing gate, W2 stackup gate, W3 physics gate, W4 quality gate, W5 compound loop) conforms to this contract. A gate is a pure, testable checker with a fail-closed measurement discipline: it must distinguish "measured, clean" from "couldn't measure."

This document is the single authoritative definition of `Gate`, `GateResult`, `GateStatus`, and `Violation`. W1–W4 define their gates against this contract. W5 implements the registry and loop orchestration.

---

## Gate Interface

```python
class Gate:
    stage: GateStage          # PLACEMENT or ROUTING
    name: str                 # human-readable gate name for diagnostics

    def check(self, state: BoardState) -> GateResult:
        """Inspect the current board state and return a three-state result."""
        ...

    def to_delta(self, violation: Violation) -> ConstraintDelta | None:
        """Map a violation to a constraint delta that the loop can inject.
        Returns None if this violation type has no corrective delta
        (e.g., an intra-component clearance that placement cannot fix).
        """
        ...
```

## GateResult — Three-state measurement discipline

```python
@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    violations: tuple[Violation, ...] = ()
    error_message: str = ""       # only populated for UNMEASURED
```

**Why three-state, not a bare list.** An empty `violations` list means two different things: "measured, clean" and "couldn't measure." This is the `run_drc` false-zero bug elevated to an architectural invariant. A gate whose tool crashes (kicad-cli exit 3, board didn't load, oracle exception) returns `UNMEASURED`, not `[]`. The loop must see an unmeasured gate as blocking — never as passing.

## GateStatus Enum

| Value | Meaning | Loop behavior |
|-------|---------|---------------|
| `CLEAN` | Measurement completed, zero violations. | Gate is green — no deltas emitted. |
| `VIOLATIONS` | Measurement completed, violations found. | Emit `to_delta(v)` for each violation. |
| `UNMEASURED` | Measurement could not be performed. | Gate is red — convergence blocked. Loop surfaces the `error_message` and retries or exits. |

A gate returning `UNMEASURED` is never treated as `CLEAN`. `all_gates_green()` requires every gate's `status == CLEAN`.

## GateStage Enum

| Value | When checked |
|-------|-------------|
| `PLACEMENT` | After CP-SAT solve, before routing. |
| `ROUTING` | After routing completes. |

DrcGate runs at `PLACEMENT`. All other gates (RoutingGate, PhysicsGate, QualityGate) run at `ROUTING`. This avoids re-routing on placement-only violations.

## Violation Dataclass

```python
@dataclass(frozen=True)
class Violation:
    type: ViolationType         # enum: CLEARANCE, UNROUTED, LOOP_INDUCTANCE,
                                #       THERMAL, CREEPAGE, VIA_COUNT, SLOP
    components: tuple[str, ...] # component refs involved
    nets: tuple[str, ...]       # net names involved
    severity: float             # violated value (mm, mm², count, ratio)
    threshold: float            # the limit that was exceeded
    description: str            # human-readable explanation
    context: dict               # gate-specific parameters
                                # (required_mm, max_area_mm2, location, etc.)
```

## BoardState

A snapshot of the current pipeline state — placement + routing + netlist + board geometry. All gates receive the same `BoardState` instance and must not mutate it.

```python
@dataclass(frozen=True)
class BoardState:
    placement: CpSatPlacementResult  # component positions + rotations
    routing: RoutingResult           # routed tracks, vias, completion rate
    netlist: Netlist                 # component netlist
    board: Board                     # board geometry (zones, stackup)
    design_rules: DesignRules        # netclass clearance/trace-width rules
    routed_pcb_path: Path | None     # path to the routed .kicad_pcb file
```

## Gate Examples

### DrcGate (placement DRC)

```python
class DrcGate(Gate):
    stage = GateStage.PLACEMENT
    name = "placement_drc"

    def check(self, state: BoardState) -> GateResult:
        # Run kicad-cli pcb drc on the placed PCB
        result = subprocess.run(["kicad-cli", "pcb", "drc", ...])
        if result.returncode != 0:
            return GateResult(GateStatus.UNMEASURED,
                              error_message=f"kicad-cli exit {result.returncode}: {result.stderr}")
        violations = _parse_drc_json(output_path)
        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
        return GateResult(GateStatus.CLEAN)

    def to_delta(self, v: Violation) -> ConstraintDelta:
        return ConstraintDelta(
            constraint=SeparatedConstraint(a=v.components[0], b=v.components[1],
                                           min_distance_mm=v.severity + 0.1),
            reason=f"DRC {v.type} at {v.severity}mm",
        )
```

### PhysicsGate (routing physics)

```python
class PhysicsGate(Gate):
    stage = GateStage.ROUTING
    name = "physics"

    def check(self, state: BoardState) -> GateResult:
        try:
            loop_area = _compute_commutation_loop_area(state.routing)
        except Exception as e:
            return GateResult(GateStatus.UNMEASURED,
                              error_message=f"loop area computation failed: {e}")
        vs = []
        if loop_area > 2000:
            vs.append(Violation(type=ViolationType.LOOP_INDUCTANCE,
                                components=("Q1", "Q2", "C_BUS1", "C_BUS2"),
                                severity=loop_area, threshold=2000,
                                description=f"Commutation loop area {loop_area}mm² > 2000mm²"))
        if vs:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(vs))
        return GateResult(GateStatus.CLEAN)
```

## Integration with PlaceRouteLoop (W5)

The W5 compound loop owns the gate registry and orchestration:

```python
class PlaceRouteLoop:
    gates: list[Gate] = []

    def all_gates_green(self, state: BoardState) -> bool:
        results = {g.name: g.check(state) for g in self.gates}
        for name, result in results.items():
            if result.status == GateStatus.UNMEASURED:
                self._surface(f"Gate {name} UNMEASURED: {result.error_message}")
            elif result.status == GateStatus.VIOLATIONS:
                for v in result.violations:
                    delta = g.to_delta(v)
                    if delta:
                        self._inject_delta(delta)
        return all(r.status == GateStatus.CLEAN for r in results.values())
```

## Succession of Older Docs

This contract supersedes the gate-adjacent sections of:
- `docs/brainstorms/2026-07-05-place-route-loop-feedback-requirements.md` — the feedback loop is now subsumed by the Gate registry
- `docs/brainstorms/2026-06-21-scripted-routing-requirements.md` — routing quality gates replace scripted routing checks
- `docs/brainstorms/2026-06-22-placement-routing-pipeline-gap-requirements.md` — the pipeline gap is closed by W1's routing gate
- `docs/brainstorms/2026-06-28-remove-dijkstra-channel-routing-requirements.md` — channel routing is replaced by the A* pathfinder + W4 quality gates

These docs remain in the repository as historical context but are marked superseded by this contract and the W1–W5 workstreams.
