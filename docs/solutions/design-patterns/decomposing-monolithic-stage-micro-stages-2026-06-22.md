---
title: "Decomposing Monolithic Stage Methods into Individually Testable Micro-Stages"
date: 2026-06-22
category: design-patterns
module: temper_placer
problem_type: design_pattern
component: development_workflow
severity: high
applies_when:
  - A pipeline stage method exceeds 50 lines with 4+ sequential sub-steps
  - Sub-steps already have well-typed intermediate dataclasses but share no architectural boundary
  - Debugging a downstream failure requires bisecting which sub-step introduced a wrong value
  - The codebase defines a Stage protocol (ABC) but the method bypasses it with loose function calls
  - You want per-sub-step golden fixtures, property-based tests, DRC gates, and coverage targets
tags:
  - decomposition
  - micro-stages
  - stage-protocol
  - golden-fixtures
  - property-based-testing
  - coverage-gate
  - monolith-parity
  - strangler-fig
  - router-v6
  - sprint-U9
---

# Decomposing Monolithic Stage Methods into Individually Testable Micro-Stages

## Context

`RouterV6Pipeline._run_stage2` was an 85-line monolith method in
`pipeline.py:241-326` that performed 8 sequential channel-analysis sub-steps:
build obstacle maps, compute routing spaces, extract channel skeletons, compute
channel widths, build occupancy grids, calculate layer capacities, estimate
routing demand, and identify bottlenecks. Each sub-step already had its own
module (`obstacle_map.py`, `occupancy_grid.py`, etc.) with well-typed
intermediate dataclasses — the logical separation existed, but no architectural
boundary enforced it.

The downstream stages (SAT solver in Stage 3, A* router in Stage 4) consumed the
assembled output. If channel analysis produced a wrong occupancy grid or
misidentified bottlenecks, everything downstream failed — but there was no way to
isolate which of the 8 sub-steps was at fault. Each sub-step had low-level unit
tests, but no per-sub-step integration tests, golden fixtures, incremental DRC
gates, or parity assertions against the monolith.

The project's `DeterministicPipeline` already defined a clean `Stage` protocol:
`Stage.run(state: BoardState) -> BoardState` with immutable frozen-dataclass
state. But `_run_stage2` bypassed this protocol with its own orchestration
calling loose functions with disparate arguments.

## Guidance

### The micro-stage extraction pattern

1. **Extend the shared state container.** Add nullable fields for every
   sub-step's output to `BoardState` (e.g., `obstacle_maps`, `routing_spaces`,
   `channel_skeletons`, etc.). Each field defaults to `None`. This is the
   contract: each micro-stage reads its upstream fields and writes its own.

2. **Extract each sub-step as a `Stage` subclass.** Each micro-stage becomes a
   class with a single `run(state) -> state` method. It reads `state` fields
   written by upstream stages, delegates to the existing module-level function,
   and writes its result back via `dataclasses.replace`. Each class is a
   separate file (or at least a separate test target).

3. **Forward extraction order (data producers first).** Start with the sub-step
   that has no upstream dependencies within the batch (here, `ObstacleMap`),
   then work forward through the dependency chain. This lets each extraction be
   verified against real pipeline state at the moment it's integrated, not
   against mocks. A stage already in the chain can supply inputs for validation
   of the next stage being extracted.

4. **Orchestrator chains them in dependency order.** Create an
   `Stage2Orchestrator` class whose `run()` iterates the 8 micro-stages in
   sequence, calling `stage.run(state)` on each and running per-stage DRC
   validators after each. The orchestrator replaces the monolith's loop body.

5. **Backward-compat adapter preserves existing callers.** The monolith method
   `_run_stage2` is replaced with a thin adapter that (a) instantiates the
   orchestrator, (b) calls `orchestrator.run(pcb, escape_vias)`, and (c)
   assembles `Stage2Output` from the final `BoardState`. Callers of
   `_run_stage2` (including `_run_stage3` and `_run_stage4`) are unchanged.
   This is the strangler-fig transition: the old interface lives while the new
   implementation is validated.

6. **Golden fixture parity tests.** A fixture-generation script
   (`generate_stage2_goldens.py`) runs the orchestrator on each canonical board
   and captures per-sub-step output as JSON. The parity test
   (`test_stage2_golden_parity.py`) loads committed fixtures and asserts each
   micro-stage produces output consistent with the golden data. Fixtures should
   be small (<100 KB) or regenerated on-demand; 14 MB of original golden JSON
   was removed from the repo.

7. **Monolith parity tests.** A `test_stage2_monolith_parity.py` directly
   compares the old monolith function against the orchestrator, field by field
   (obstacle maps, routing spaces, skeletons, channel widths, occupancy grids,
   layer capacities, routing demand, bottleneck analysis). This catches any
   semantic drift during extraction.

8. **Property-based tests per sub-step.** Each micro-stage gets a Hypothesis
   (`max_examples=100`) suite (`test_*_pbt.py`) testing invariants:
   `signal_nets + power_nets <= total_nets`, `routable_nets <= total_nets`,
   occupancy grid cells are non-negative, channel skeleton graphs are connected,
   etc. These complement the golden fixtures by verifying mathematical
   invariants that hold regardless of board geometry.

9. **Per-module coverage gate.** Each extracted module carries a
   `--cov-fail-under=90` coverage requirement measured independently (e.g.,
   `--cov=temper_placer.router_v6.obstacle_map --cov-fail-under=90`). No
   aggregation trick that hides an untested module behind a well-tested
   neighbor.

10. **Per-stage DRC gate.** Each micro-stage has a standalone validator function
    auto-discovered via a `@register_validator(name)` decorator. The
    orchestrator calls `run_validators(stage.name, state)` after each stage and
    collects `StageDRCFailure` results. This catches cross-stage data corruption
    at the earliest possible point.

11. **Performance regression bound.** A slow-test marker
    (`@pytest.mark.slow`) gates a <5% wall-clock overhead assertion comparing
    the monolith against the orchestrator (2 warm-up + 2 measured runs). The
    extraction adds one function call per micro-stage plus one
    `dataclasses.replace` per stage — negligible vs. downstream SAT/A* wall
    time.

### Dependency-visibility rule

After decomposition, downstream stages that consume `Stage2Output` should only
depend on the fields they actually need. This was discovered during extraction:
`_run_stage3` accesses only `skeletons` + `channel_widths`; `_run_stage4`
accesses `skeletons` + `occupancy_grids` + `routing_spaces`. The adapter
assembles all 8 fields into `Stage2Output`, but the micro-stage design makes the
actual dataflow visible — each `run()` method can declare exactly which
upstream fields it reads.

## Why This Matters

**Before decomposition**, the 85-line monolith was a black box. If occupancy
grid cells were wrong, there was no way to know whether the obstacle map,
routing space, or the occupancy grid builder itself was at fault. Debugging
meant reading the monolith's source and mentally bisecting.

**After decomposition**, each sub-step is independently testable:
- **Golden fixtures** verify per-board, per-layer, per-sub-step output matches
  known-good values (32/32 tests).
- **Property-based tests** verify mathematical invariants regardless of board
  geometry (28/28 tests, Hypothesis, `max_examples=100`).
- **DRC gates** catch data corruption at the earliest point — after each
  micro-stage, not at the pipeline endpoint.
- **Coverage gates** prevent untested code from merging silently, and because
  each module is measured independently, a 100%-covered obstacle map can't
  paper over a 40%-covered bottleneck analysis.
- **Performance bound** guarantees the architectural improvement doesn't regress
  runtime.

The architectural boundary also makes the dataflow explicit. Before, you had to
read the monolith to know that routing demand depends on the PCB netlist, not on
any prior sub-step. After, you read `RoutingDemandStage.run()` and see exactly
which `BoardState` fields it consumes and produces.

## When to Apply

Apply this pattern when:

- A pipeline stage method has 4+ sequential sub-steps that can be independently
  verified.
- Sub-steps already have their own modules and well-typed intermediate
  dataclasses — the logical separation exists but not the architectural
  boundary.
- The codebase defines a Stage protocol (ABC with `run(state) -> state`) that
  the method can conform to.
- Downstream consumers fail in ways that require bisecting which sub-step
  introduced a wrong value.
- You have 4+ canonical test boards for golden fixture generation.

Do NOT apply when:

- Sub-steps are tightly coupled with shared mutable state that can't be
  extracted into a state container.
- The extraction overhead (>2 additional function calls per sub-step) matters in
  a hot inner loop (not the case for channel analysis — SAT/A* dominate wall
  time).
- The monolith is <3 sub-steps or <25 lines — the cost of 8 new module files
  and test suites may exceed the value.
- Sub-steps don't have stable intermediate outputs (e.g., they use generators or
  streaming) that can be materialized into `BoardState` fields.

### Decision Flow

```
Monolith method with N sequential sub-steps identified
    │
    ├─ N >= 4 and well-typed intermediate dataclasses exist? ── No ──→ Not a micro-stage candidate
    │
    ├─ A Stage protocol (ABC) exists in the codebase? ── No ──→ Define the protocol first,
    │                                                           then apply decomposition
    │
    ├─ Downstream consumers can remain on old interface? ── No ──→ Plan migration path for
    │                                                             callers before extracting
    │
    ├─ Canonical test boards available for golden fixtures? ── No ──→ Skip golden fixtures;
    │                                                              rely on PBT + monolith parity
    │
    └─ Yes → Extract forward, add PBT + coverage + DRC per module, strangler-fig the monolith
```

## Examples

### Before: Monolith `_run_stage2` (85 lines)

```python
# router_v6/pipeline.py:241-326 (before extraction)
def _run_stage2(self, pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> Stage2Output:
    if self.verbose:
        print("Stage 2: Channel analysis...")

    profiling = self.profiler

    # 2.1: Obstacle maps
    with profiling.stage("2.1-Obstacle"):
        obstacle_maps = build_obstacle_map(pcb, escape_vias)

    # 2.2: Routing spaces
    with profiling.stage("2.2-RoutingSpace"):
        routing_spaces = compute_routing_space(
            pcb, escape_vias, obstacle_maps=obstacle_maps
        )

    # 2.3: Channel skeletons (outer layers only)
    with profiling.stage("2.3-Skeleton"):
        outer_layers = {k: v for k, v in routing_spaces.items()
                        if k in ("F.Cu", "B.Cu")}
        skeletons: dict[str, ChannelSkeleton] = {}
        for layer_name, routing_space in outer_layers.items():
            skeletons[layer_name] = extract_channel_skeleton(
                routing_space, pcb=pcb
            )

    # 2.4: Channel widths
    with profiling.stage("2.4-Widths"):
        channel_widths: dict[str, ChannelWidths] = {}
        for layer_name, skeleton in skeletons.items():
            channel_widths[layer_name] = compute_channel_widths(
                routing_spaces[layer_name], skeleton
            )

    # 2.5: Occupancy grids
    with profiling.stage("2.5-Occupancy"):
        base_inflation = (
            pcb.design_rules.default_trace_width_mm / 2.0
        ) + pcb.design_rules.default_clearance_mm
        occupancy_grids: dict[str, OccupancyGrid] = {}
        for layer_name, routing_space in routing_spaces.items():
            occupancy_grids[layer_name] = build_occupancy_grid(
                routing_space, inflation_mm=base_inflation
            )

    # 2.6: Layer capacities
    with profiling.stage("2.6-Capacity"):
        layer_capacities: dict[str, LayerCapacity] = {}
        for layer_name in occupancy_grids.keys():
            cw = channel_widths.get(layer_name)
            if cw is not None:
                layer_capacities[layer_name] = calculate_layer_capacity(
                    occupancy_grids[layer_name], cw,
                    pcb.design_rules.default_trace_width_mm * 1.5,
                    pcb.design_rules.default_clearance_mm,
                )

    # 2.7: Routing demand
    with profiling.stage("2.7-Demand"):
        routing_demand = estimate_routing_demand(pcb)

    # 2.8: Bottleneck analysis
    with profiling.stage("2.8-Bottleneck"):
        bottleneck_analysis = identify_bottlenecks(
            layer_capacities, routing_demand
        )

    # Assemble result
    result = Stage2Output(
        obstacle_maps=obstacle_maps,
        routing_spaces=routing_spaces,
        skeletons=skeletons,
        channel_widths=channel_widths,
        occupancy_grids=occupancy_grids,
        layer_capacities=layer_capacities,
        routing_demand=routing_demand,
        bottleneck_analysis=bottleneck_analysis,
    )
    return result
```

### After: 8 micro-stage classes + orchestrator

**Micro-stage example** (`obstacle_map.py`):

```python
# router_v6/obstacle_map.py (Stage 2.1)
class ObstacleMapStage(Stage):
    """Build obstacle maps for all copper layers from pads, vias, keepouts."""

    name = "obstacle_map"

    def run(self, state: BoardState) -> BoardState:
        pcb = state._parsed_pcb
        escape_vias = list(state._escape_vias) if state._escape_vias else []
        maps = build_obstacle_map(pcb, escape_vias)
        return replace(state, obstacle_maps=maps)
```

**Micro-stage example** (`routing_space.py`):

```python
# router_v6/routing_space.py (Stage 2.2)
class RoutingSpaceStage(Stage):
    """Compute available routing area by subtracting obstacles from board area."""

    name = "routing_space"

    def run(self, state: BoardState) -> BoardState:
        pcb = state._parsed_pcb
        escape_vias = list(state._escape_vias) if state._escape_vias else []
        obstacle_maps = state.obstacle_maps
        routing = compute_routing_space(pcb, escape_vias, obstacle_maps=obstacle_maps)
        return replace(state, routing_spaces=routing)
```

*(Remaining 6 micro-stages follow the same pattern: `ChannelSkeletonStage`,
`ChannelWidthsStage`, `OccupancyGridStage`, `LayerCapacityStage`,
`RoutingDemandStage`, `BottleneckAnalysisStage`.)*

**Orchestrator** (`stage2_orchestrator.py`):

```python
# router_v6/stage2_orchestrator.py
class Stage2Orchestrator:
    """Chains the 8 channel-analysis micro-stages in dependency order."""

    _stages: list[Stage]

    def __init__(self, verbose: bool = False):
        self._stages = [
            ObstacleMapStage(),
            RoutingSpaceStage(),
            ChannelSkeletonStage(),
            ChannelWidthsStage(),
            OccupancyGridStage(),
            LayerCapacityStage(),
            RoutingDemandStage(),
            BottleneckAnalysisStage(),
        ]
        self.verbose = verbose

    def run(
        self,
        pcb: ParsedPCB,
        escape_vias: list[EscapeVia],
        initial_state: BoardState | None = None,
    ) -> BoardState:
        state = initial_state or BoardState()
        state = replace(state, _parsed_pcb=pcb, _escape_vias=tuple(escape_vias))

        for stage in self._stages:
            state = stage.run(state)
            drc_failures = run_validators(stage.name, state)
            if drc_failures and self.verbose:
                for f in drc_failures:
                    print(f"    DRC WARNING: {f}")

        return state

    @staticmethod
    def assemble_stage2_output(state: BoardState) -> Stage2Output:
        return Stage2Output(
            obstacle_maps=state.obstacle_maps,
            routing_spaces=state.routing_spaces,
            skeletons=state.channel_skeletons,
            channel_widths=state.channel_widths,
            occupancy_grids=state.occupancy_grids,
            layer_capacities=state.layer_capacities,
            routing_demand=state.routing_demand,
            bottleneck_analysis=state.bottleneck_analysis,
        )
```

**Strangler-fig adapter** (`pipeline.py`, after):

```python
# router_v6/pipeline.py (after extraction)
def _run_stage2(self, pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> Stage2Output:
    """Run Stage 2: Channel Analysis (delegated to Stage2Orchestrator)."""
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator

    orchestrator = Stage2Orchestrator(verbose=self.verbose)
    state = orchestrator.run(pcb, escape_vias)
    return Stage2Orchestrator.assemble_stage2_output(state)
```

### Golden fixture parity test

```python
# tests/router_v6/test_stage2_golden_parity.py
@pytest.mark.parametrize("board_name", AVAILABLE_BOARDS)
def test_routing_demand_parity(board_name: str):
    """Assert routing_demand matches committed golden fixture."""
    state = _get_board_state(board_name)
    fixture = _load_fixture(board_name, "routing_demand")
    if fixture is None:
        pytest.skip("No golden fixture")

    assert state.routing_demand.total_nets == fixture["total_nets"]
    assert state.routing_demand.routable_nets == fixture["routable_nets"]
    assert state.routing_demand.total_pins == fixture["total_pins"]
```

### Monolith parity test

```python
# tests/router_v6/test_stage2_monolith_parity.py
def test_full_output_parity(self):
    """Asserts field-by-field equality of all Stage 2 outputs."""
    monolith_output = _run_monolith(self.pcb, self.escape_vias)

    assert monolith_output["routing_demand"].total_nets == \
        self.state.routing_demand.total_nets
    assert set(monolith_output["occupancy_grids"].keys()) == \
        set(self.state.occupancy_grids.keys())

    for layer_name in monolith_output["occupancy_grids"]:
        m_grid = monolith_output["occupancy_grids"][layer_name]
        o_grid = self.state.occupancy_grids[layer_name]
        assert np.array_equal(m_grid.grid, o_grid.grid), \
            f"Grid mismatch on {layer_name}"
```

### Property-based test

```python
# tests/router_v6/test_routing_demand_pbt.py
@given(
    total=st.integers(min_value=0, max_value=1000),
    signal=st.integers(min_value=0, max_value=1000),
    power=st.integers(min_value=0, max_value=500),
    diff=st.integers(min_value=0, max_value=100),
    pins=st.integers(min_value=0, max_value=5000),
)
@settings(max_examples=100, deadline=30000)
def test_routing_demand_invariant_classification(total, signal, power, diff, pins):
    """signal_nets + power_nets + diff_pair_nets <= total_nets."""
    rd = RoutingDemand(
        total_nets=total,
        routable_nets=min(total, signal + power + diff),
        total_pins=pins,
        signal_nets=min(signal, total),
        power_nets=min(power, total - min(signal, total)),
        diff_pair_nets=min(diff, total - min(signal, total) - min(power, total - min(signal, total))),
        avg_pins_per_net=pins / max(1, total),
        max_pins_per_net=min(pins, 100),
    )
    assert rd.signal_nets + rd.power_nets + rd.diff_pair_nets <= rd.total_nets
    assert rd.total_nets >= 0
    assert rd.routable_nets >= 0
    assert rd.total_pins >= 0
    assert rd.signal_nets >= 0
    assert rd.power_nets >= 0
```

### Performance regression guard

```python
# tests/router_v6/test_stage2_monolith_parity.py
@pytest.mark.slow
def test_performance_regression(self):
    """Asserts <5% wall-clock overhead (2 warm-up + 2 measured runs)."""
    orch = Stage2Orchestrator(verbose=False)

    # Warm-up
    _run_monolith(self.pcb, self.escape_vias)
    orch.run(self.pcb, self.escape_vias)

    # Benchmark
    t0 = time.perf_counter()
    _run_monolith(self.pcb, self.escape_vias)
    mono_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    orch.run(self.pcb, self.escape_vias)
    orch_time = time.perf_counter() - t0

    overhead_pct = ((orch_time - mono_time) / mono_time) * 100 \
        if mono_time > 0 else 0
    assert overhead_pct < 5.0, (
        f"Performance regression: {overhead_pct:.1f}% overhead"
    )
```

## Caveats

### Golden fixture size

The initial golden fixture generation produced 14 MB of JSON across 4 boards x
8 sub-steps. This was removed from the repo. Committed fixtures should be small
(<100 KB per file) or regenerated on-demand by the test suite. The
`generate_stage2_goldens.py` script is checked in as a fixture-rebuilding tool;
the test skips cleanly when fixtures are absent.

### Dependency ordering is critical

The 8 micro-stages must run in dependency order: `ObstacleMap` → `RoutingSpace`
→ `ChannelSkeleton` → `ChannelWidths` → `OccupancyGrid` → `LayerCapacity` →
`RoutingDemand` → `BottleneckAnalysis`. The orchestrator enforces this, but if
someone rearranges the list, intermediate results will be `None` and stages will
fail at runtime. A static dependency graph with topological sort would be a
natural next step.

### BoardState field naming

The `BoardState` container carries all 8 intermediate results. This works for a
64-stage pipeline but naming collisions become more likely as more stages are
extracted. A per-stage sub-container (e.g., `state.channel_analysis.obstacle_maps`)
is worth considering if the number of extracted stages grows beyond ~12.

### Not all monoliths decompose this cleanly

This extraction worked because each sub-step already had (a) its own module,
(b) well-typed intermediate dataclasses, and (c) low-level unit tests. A monolith
that interleaves allocation, computation, and side effects would need more
refactoring before the micro-stage pattern applies. See the "When to Apply"
decision flow above.

## Related

- `packages/temper-placer/src/temper_placer/router_v6/stage2_orchestrator.py` — Stage2Orchestrator implementation
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:50-73` — Stage2Output dataclass
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:365-386` — strangler-fig adapter (post-extraction `_run_stage2`)
- `packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py` — ObstacleMapStage (2.1)
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py` — RoutingSpaceStage (2.2)
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py` — ChannelSkeletonStage (2.3)
- `packages/temper-placer/src/temper_placer/router_v6/channel_widths.py` — ChannelWidthsStage (2.4)
- `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py` — OccupancyGridStage (2.5)
- `packages/temper-placer/src/temper_placer/router_v6/layer_capacity.py` — LayerCapacityStage (2.6)
- `packages/temper-placer/src/temper_placer/router_v6/routing_demand.py` — RoutingDemandStage (2.7)
- `packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py` — BottleneckAnalysisStage (2.8)
- `packages/temper-placer/tests/router_v6/test_stage2_golden_parity.py` — golden fixture parity tests
- `packages/temper-placer/tests/router_v6/test_stage2_monolith_parity.py` — monolith parity + performance regression tests
- `packages/temper-placer/tests/router_v6/generate_stage2_goldens.py` — fixture generation script
- `packages/temper-placer/tests/router_v6/test_*_pbt.py` — 8 property-based test suites (one per sub-step)
- `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py` — per-stage DRC validator registry
- `docs/plans/2026-06-22-012-feat-decompose-stage2-plan.md` — origin plan
- `docs/brainstorms/2026-06-22-decompose-stage2-channel-analysis-requirements.md` — origin requirements
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — sibling pattern (per-stage DRC gates)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling pattern (baseline + monotonic shrink)
