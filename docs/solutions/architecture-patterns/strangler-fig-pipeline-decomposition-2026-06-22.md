---
title: "Pattern: Strangler Fig Pipeline Decomposition"
date: 2026-06-22
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - Multiple overlapping pipeline systems exist with incompatible interfaces
  - A monolithic pipeline needs decomposition into testable, verifiable stages
  - Internal components must be reused without modification during migration
  - Stage boundaries lack explicit contracts, causing silent state corruption
tags:
  - strangler-fig
  - pipeline-decomposition
  - adapter-pattern
  - stage-protocol
  - immutability
  - closure-test
  - contract-boundaries
  - sprint-N5-N6
---

# Pattern: Strangler Fig Pipeline Decomposition

## Context

The Temper induction cooker's PCB design automation pipeline grew organically into
three overlapping systems with incompatible interfaces: `PipelineOrchestrator`
(an 8-phase monolith), `RouterV6Pipeline` (5-stage), and `DeterministicPipeline`
(26 stages). Each had its own lifecycle, state representation, and error
handling. They could not compose — `RouterV6Pipeline` consumed raw tuples,
`PipelineOrchestrator` used mutable dicts, and `DeterministicPipeline` used
frozen dataclasses. Adding a feature meant choosing one pipeline and living with
its limitations, or worse, wiring output from one into another via ad-hoc
conversion scripts.

The solution applied the **strangler fig pattern**: identify seams between
stages → build facade adapters around existing components without modifying
internals → verify parity with a closure test → replace incrementally with
protocol-conforming stages.

## Guidance

### Phase 1: Identify seams and build adapter facades

The first step is to wrap existing pipeline components behind a unified interface
**without modifying their internals**. This is the core of strangler fig — the
old system continues to function while the new system grows around it.

```python
# Before: RouterV6Pipeline exposes raw functions with incompatible signatures
def route_pcb_v6(board: dict, config: dict) -> dict:
    ...  # ~3400 lines of routing logic

# After: Adapter wraps the existing function behind the Stage protocol
class RoutePcbAdapter(Stage[BoardState, RouteResult]):
    """Facade: wraps RouterV6Pipeline's route_pcb_v6 without modifying it."""

    def execute(self, state: BoardState) -> RouteResult:
        board_dict = board_state_to_dict(state)
        config_dict = build_router_config(state)
        raw_result = route_pcb_v6(board_dict, config_dict)
        return RouteResult.from_dict(raw_result)
```

The adapter pattern applied across all three pipeline systems:

| Pipeline System | Adapter | Wraps |
|---|---|---|
| `PipelineOrchestrator` (8-phase) | `benders_placement()` | `BendersPlacer.place()` — 8 monolithic phases behind a single Stage |
| `RouterV6Pipeline` (5-stage) | `route_pcb()` | `route_pcb_v6()` — routing engine unchanged |
| `DeterministicPipeline` (26-stage) | Stage protocol native | Already decomposed — provided the target pattern |

### Phase 2: Unified Stage protocol

Three pipeline systems with incompatible interfaces required a **unified Stage
protocol** before decomposition could compose them:

```python
from typing import Protocol, TypeVar, Generic

T_in = TypeVar("T_in", contravariant=True)
T_out = TypeVar("T_out", covariant=True)

class Stage(Protocol[T_in, T_out]):
    """A single pipeline stage: takes input, produces output, must not mutate
    its input (BoardState is frozen — immutability is enforced by the type)."""

    name: str
    input_type: type
    output_type: type

    def execute(self, state: T_in) -> T_out: ...

    def can_execute(self, state: T_in) -> bool: ...
```

Every adapter and new stage conforms to this protocol. The `can_execute` method
provides a pre-flight check that replaces ad-hoc `isinstance` guards and missing-
key `try/except` chains in the old systems.

### Phase 3: Immutable BoardState as the shared data contract

`DeterministicPipeline` already used a frozen `BoardState` dataclass. This
became the canonical data model generalized across the unified pipeline:

```python
@dataclass(frozen=True)
class BoardState:
    """Immutable snapshot of the board at a pipeline stage boundary.
    Never mutated. Stages that need to 'modify' return a new BoardState
    (typically via dataclasses.replace)."""
    components: tuple[Component, ...]
    nets: tuple[Net, ...]
    layers: tuple[Layer, ...]
    placement: Placement | None
    routes: tuple[Route, ...]
    drc_results: tuple[DRCViolation, ...]
    metadata: PipelineMetadata
```

Immutability is the contract enforcement mechanism. Because `BoardState` is
frozen, a stage cannot silently modify state that a downstream stage will read —
it must return a new `BoardState`, making the transformation explicit and
testable in isolation.

### Phase 4: Stage boundary contracts prevent silent overwrites

The canonical failure that drove contract boundaries: `PowerPlaneStage` silently
overwrote `LayerAssignmentStage`'s layer assignments for high-current nets.
`LayerAssignmentStage` assigned `Net["VIN"]` to layer 2 (inner). `PowerPlaneStage`
re-assigned it to layer 4 because its heuristic only considered copper weight,
ignoring the prior stage's cost-model decision.

The fix: every stage declares its output fields and must not touch fields owned
by another stage:

```python
@dataclass(frozen=True)
class StageContract:
    """Declares which BoardState fields a stage reads and which it writes."""
    name: str
    reads: frozenset[str]
    writes: frozenset[str]

# Contract enforcement at composition time
def compose_stages(stages: list[Stage]) -> Pipeline:
    for i, s1 in enumerate(stages):
        for s2 in stages[i + 1:]:
            overlap = s1.contract.writes & s2.contract.writes
            if overlap:
                raise ContractViolation(
                    f"{s1.name} and {s2.name} both write to {overlap} — "
                    f"this is the PowerPlaneStage problem: silent overwrite"
                )
    return Pipeline(stages)
```

### Phase 5: Closure test as the integration gate

A **closure test** (parse → place → route → DRC) served as the parity gate,
verifying that adapted components produce real, drc-passing results:

```python
def test_closure_parse_place_route_drc():
    """Integration gate: the adapted pipeline must produce a DRC-clean board
    from a real KiCad netlist."""
    board = parse_board(TEST_NETLIST_PATH)
    state = BoardState(
        components=tuple(board.components),
        nets=tuple(board.nets),
        layers=DEFAULT_4LAYER_STACKUP,
        placement=None,
        routes=(),
        drc_results=(),
        metadata=PipelineMetadata(source="closure_test"),
    )

    pipeline = Pipeline([
        benders_placement(),
        route_pcb(),
        run_drc(),
    ])

    result = pipeline.run(state)
    assert len(result.drc_results) == 0, (
        f"Closure failed: {len(result.drc_results)} DRC violations\n"
        f"First 5: {result.drc_results[:5]}"
    )
```

This test runs in CI and gates every PR against the pipeline. If an adapter
change breaks end-to-end correctness, the closure test catches it before code
review.

## Why This Matters

Before strangler fig decomposition, adding a feature to the PCB pipeline meant
choosing one of three incompatible systems, each with its own state management
and error handling. A bug in `PowerPlaneStage`'s layer assignment could not be
caught by existing tests because `PowerPlaneStage` was buried inside
`PipelineOrchestrator` phase 4 — there was no way to test it in isolation.

After decomposition:
- **Every stage is testable in isolation.** `test_power_plane_stage.py` feeds a
  known `BoardState` and asserts the exact output — no need to run the full
  pipeline.
- **Stage boundaries have explicit contracts.** A stage that writes to
  `board_state.layers` when its contract says it only writes to `power_planes` is
  caught at composition time, not 2000 lines later when routing produces garbage.
- **Immutability prevents side channels.** Without frozen `BoardState`, a stage
  could stash data in mutable state that a downstream stage silently consumes.
  The adapter pattern caught one instance where `RouterV6Pipeline` was mutating
  a shared `config` dict that `PipelineOrchestrator` later read — the adapter
  deep-copied it, preventing the cross-contamination.
- **Three pipelines became one.** `PipelineOrchestrator`, `RouterV6Pipeline`, and
  `DeterministicPipeline` are now composed stages behind adapters. New work
  targets the unified `Stage` protocol; old internals are replaced
  incrementally.

## When to Apply

Apply this pattern when:
- Two or more pipeline/processing systems exist with incompatible interfaces and
  overlapping functionality.
- You need to decompose a monolithic pipeline into testable stages without a
  rewrite (the internal components work; the composition is the problem).
- Stage boundaries are implicit or nonexistent, and silent state corruption
  (the PowerPlaneStage problem) has occurred or is likely.
- You have a working end-to-end test (like the closure test) that can serve as
  the parity gate during incremental migration.

Do NOT apply when:
- There is a single, well-structured pipeline already using immutable state and
  explicit stage contracts — you already have this pattern.
- The internal components are themselves broken and need rewriting before
  wrapping — write the replacement stage directly.
- The pipeline is simple enough (≤3 stages with clear boundaries) that
  decomposition adds more ceremony than value.

### Decision Flow

```
Multiple overlapping pipeline systems exist
    │
    ├─ Do internal components work? ── No ──→ Fix components first
    │
    ├─ Can you write a closure test? ── No ──→ Write one (it is the parity gate)
    │
    ├─ Is there a natural immutable data model? ── No ──→ Freeze the best
    │                                                      existing model
    │
    └─ Yes → Build adapters → Unify protocol → Enforce contracts
                                                  → Replace incrementally
```

## Examples

### Before: Three incompatible pipeline systems

```python
# PipelineOrchestrator — mutable dicts, 8 phases, no stage isolation
class PipelineOrchestrator:
    def run(self, input_data: dict) -> dict:
        state = {"components": [], "nets": [], ...}  # mutable, any phase can mutate any key
        state = self.phase1_load(state)
        state = self.phase2_assign_layers(state)
        state = self.phase3_place(state)
        state = self.phase4_power_planes(state)  # silently overwrites phase2's layer assignments
        state = self.phase5_route(state)
        state = self.phase6_optimize(state)
        state = self.phase7_drc(state)
        state = self.phase8_export(state)
        return state

# RouterV6Pipeline — raw function, returns dict, no protocol
result = route_pcb_v6(board_dict, config_dict)

# DeterministicPipeline — frozen dataclasses but isolated from the other two
result = DeterministicPipeline().run(board_state)
```

### After: Unified pipeline with adapters and contracts

```python
# All stages conform to the Stage protocol
pipeline = Pipeline(
    stages=[
        benders_placement(),       # Adapter wrapping PipelineOrchestrator phases 1-3 + BendersPlacer
        assign_layers(),           # New native Stage — extracted from PipelineOrchestrator phase 2
        route_power_planes(),      # New native Stage — extracted from phase 4, now with contract
        route_pcb(),               # Adapter wrapping RouterV6Pipeline
        run_drc(),                 # Native Stage
    ],
    contracts_enabled=True,
)

result = pipeline.run(board_state)

# Contract violation caught at composition time:
# ContractViolation: assign_layers and route_power_planes both write to
# frozenset({'layers'}) — route_power_planes must only write to 'power_planes'
```

### Stage isolation: testing PowerPlaneStage independently

```python
def test_power_plane_stage_preserves_layer_assignments():
    """PowerPlaneStage must not overwrite layer assignments from upstream."""
    state = BoardState(
        nets=(Net("VIN", assigned_layer="In2.Cu"),),
        layers=DEFAULT_4LAYER_STACKUP,
        ...
    )
    stage = route_power_planes()
    result = stage.execute(state)

    # The net's assigned layer must not change — power planes add copper,
    # they don't reassign layers.
    vin_net = next(n for n in result.nets if n.name == "VIN")
    assert vin_net.assigned_layer == "In2.Cu", (
        f"PowerPlaneStage overwrote layer to {vin_net.assigned_layer}"
    )
```

### Adapter: wrapping RouterV6Pipeline without touching internals

```python
@dataclass(frozen=True)
class RoutePcbAdapter:
    """Strangler fig adapter: wraps route_pcb_v6 without modifying it."""
    name: str = "route_pcb"
    contract: StageContract = StageContract(
        name="route_pcb",
        reads=frozenset({"components", "nets", "layers", "placement"}),
        writes=frozenset({"routes"}),
    )

    def execute(self, state: BoardState) -> BoardState:
        # Convert BoardState to the dict format route_pcb_v6 expects
        board_dict = {
            "components": [c.to_dict() for c in state.components],
            "nets": [n.to_dict() for n in state.nets],
            "layers": [l.to_dict() for l in state.layers],
            "placement": state.placement.to_dict() if state.placement else {},
        }
        # Deep copy the config to prevent mutation leaking back
        config = deepcopy(build_router_config(state))
        # Call the original, unmodified routing engine
        raw_result = route_pcb_v6(board_dict, config)
        # Convert back and return a new BoardState (immutable)
        return dataclasses.replace(
            state,
            routes=tuple(Route.from_dict(r) for r in raw_result["routes"]),
        )
```

## Related

- `packages/temper-placer/src/temper_placer/pipeline/` — Unified pipeline with Stage protocol and contract enforcement
- `packages/temper-placer/src/temper_placer/pipeline/adapters/` — Strangler fig adapters wrapping PipelineOrchestrator and RouterV6Pipeline
- `packages/temper-placer/src/temper_placer/core/board_state.py` — Frozen BoardState dataclass (canonical data model)
- `packages/temper-placer/src/temper_placer/pipeline/contract.py` — StageContract and compose_stages contract enforcement
- `packages/temper-placer/tests/pipeline/test_closure.py` — Closure test (parse → place → route → DRC)
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — Frozen-model immutability precedent (NetClassRules)
- `docs/solutions/workflow-issues/parallel-worktree-sprint-pipeline.md` — Parallel worktree isolation pattern
- `docs/plans/2026-06-22-005-feat-duplicate-script-consolidation-plan.md` — N5 consolidation (pipeline scripts before adapter extraction)
