---
title: "feat: Decompose RouterV6 Stage 2 Channel Analysis into 8 Micro-Stages"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-22-decompose-stage2-channel-analysis-requirements.md
---

# feat: Decompose RouterV6 Stage 2 Channel Analysis into 8 Micro-Stages

## Summary

Extract `RouterV6Pipeline._run_stage2` (`router_v6/pipeline.py:241-326`), an 85-line monolith calling 8 sequential sub-step functions, into 8 independent `Stage` subclasses conforming to the DeterministicPipeline's `Stage(ABC)` protocol (`run(state: BoardState) -> BoardState`). A `Stage2Orchestrator` chains the micro-stages in dependency order and a backward-compatibility adapter assembles `Stage2Output` from the final `BoardState` so `_run_stage3` and `_run_stage4` operate unchanged. Each micro-stage is backed by golden fixture parity tests on 4 canonical boards, property-based tests (hypothesis, >=100 examples), a per-stage DRC gate, and a >=90% per-module line-coverage gate. This makes the 0.5% completion rate independently debuggable at each sub-step boundary.

---

## Problem Frame

Router V6 Stage 2 (channel analysis) feeds Stage 3 (SAT solver) and Stage 4 (A* router). If channel analysis produces a wrong occupancy grid or misidentifies bottlenecks, everything downstream fails — but there is no way to isolate which of the 8 sub-steps is at fault. Each sub-step already has its own module (`obstacle_map.py`, `occupancy_grid.py`, etc.) and low-level tests, but no per-sub-step integration tests, golden fixtures, incremental DRC gates, or parity assertions against the monolith.

The DeterministicPipeline already defines a clean Stage protocol: `Stage.run(state: BoardState) -> BoardState` with immutable frozen-dataclass state. Channel analysis sub-steps inherit no such protocol — they take disparate arguments and return loose dataclasses assembled by `_run_stage2`.

---

## Scope Boundaries

### In scope

- R1–R9 from the origin requirements document: BoardState extension, 8 micro-stage classes, Stage2Orchestrator + adapter, golden fixtures, PBT suites, DRC gates, coverage gates per module, monolith parity tests, extraction order enforcement.
- 8 implementation units (one per sub-step), plus the Stage2Orchestrator and parity tests.
- Construction of the `generate_stage2_goldens.py` fixture-generation script and `test_stage2_golden_parity.py` / `test_stage2_monolith_parity.py` parity tests.
- A `StageDRCFailure` error type and 8 `_validate(state) -> list[StageDRCFailure]` standalone validator functions, auto-discovered via a `@register_validator(name)` decorator.

### Deferred

- Extracting Stage 3 (SAT solver) or Stage 4 (A* router). These are downstream consumers; they continue to receive `Stage2Output` unchanged.
- Parameterizing the Stage DAG for runtime reordering. The 8 micro-stages are chained in a fixed order.
- Implementing the unified Stage protocol for the full codebase (ideation #3). BoardState gains channel-analysis fields; `PipelineOrchestrator` and `DeterministicPipeline` are not refactored.
- Cross-stage DRC gates. R6 validates invariants within a single stage only.
- Improving channel analysis algorithms. The micro-stages delegate to existing module-level functions unchanged.

### Out of scope

- Changing the Stage 3 or Stage 4 interfaces. `_run_stage3` and `_run_stage4` continue to consume `Stage2Output`.
- Performance optimization beyond the <5% overhead bound. The extraction adds one function call per micro-stage + one `dataclasses.replace` per stage — negligible vs. SAT/A* wall time.

---

## Key Technical Decisions

**K1. BoardState extension via frozen dataclass field addition (not subclass).** `BoardState` (`deterministic/state.py:16-39`) is a frozen dataclass where every existing field uses `= None` or `= field(default_factory=...)`. Adding 8 new `Optional[...] = None` fields does not break existing consumers. A `ChannelAnalysisState(BoardState)` subclass would force the orchestrator to downcast — field addition is simpler and introduces zero cast risk.

**K2. Eight direct Stage subclasses, no mixin.** The requirements R1 described a `ChannelAnalysisStage(Stage)` mixin, but each micro-stage's `run()` shape is identical (read from BoardState, call existing function, write to BoardState). A mixin adds a layer of indirection with no deduplication benefit. The resolved decision: 8 direct `Stage` subclasses each in their existing module file.

**K3. Extraction order: forward (obstacle -> ... -> bottleneck).** The dependency DAG is:

```
ObstacleMap ──┬──> RoutingSpace ──┬──> ChannelSkeleton ──> ChannelWidths ──┐
              │                   │                                         ├──> LayerCapacity ──┐
              │                   └──> OccupancyGrid ───────────────────────┘                    ├──> BottleneckAnalysis
              │                                                                                  │
              └──> (board, netlist) ──> RoutingDemand ───────────────────────────────────────────┘
```

Extracting data producers first means each extraction can be verified by running real upstream stages (not mocks) against monolith intermediate state. Extracting bottleneck first would require mocking all 7 upstream stages.

**K4. Stage2Orchestrator chains micro-stages + backward-compat adapter.** `Stage2Orchestrator` runs the 8 micro-stages in dependency order, threading `BoardState` through. `_run_stage2` is refactored to instantiate the orchestrator, run it, then assemble `Stage2Output` from the final `BoardState`. Stage 3 accesses only `skeletons` + `channel_widths`; Stage 4 accesses `skeletons`, `occupancy_grids`, `routing_spaces`. The adapter only needs those 4 fields populated on `Stage2Output`.

**K5. Golden fixture format: JSON with custom encoders.** Occupancy grids (numpy arrays) serialize via `.tolist()`; channel skeletons (NetworkX graphs) via `node_link_data`. JSON is human-diffable in CI. A `--regenerate` flag on the generation script gates intentional algorithm changes.

**K6. Per-stage DRC validators: standalone functions with decorator registration.** `validate_obstacle_map(state: BoardState) -> list[StageDRCFailure]` with `@register_validator("ObstacleMap")` auto-discovery. Standalone functions are more testable and composable than stage methods; the decorator pattern is already established in the codebase (entry_points groups in `pyproject.toml`).

**K7. Coverage gate: per-module `pytest-cov` with `--cov-fail-under=90`.** Each module is measured independently (e.g., `--cov=temper_placer.router_v6.obstacle_map --cov-fail-under=90`). No aggregation trick that hides an untested module behind a well-tested neighbor.

**K8. Performance regression bound: <5% wall-clock overhead on canonical boards vs monolith.** The extraction adds one function call per micro-stage + one `dataclasses.replace` per stage. This is <1ms total vs. seconds of SAT/A* wall time. A benchmark in `test_stage2_monolith_parity.py` asserts this bound.

---

## Implementation Units

### U0. BoardState Extension and StageDRCFailure Infrastructure

**What:** Add 8 channel-analysis fields to `BoardState` (`deterministic/state.py`). Define `StageDRCFailure` error type and `@register_validator` decorator in a new `router_v6/stage_validators.py`.

**Deliverables:**
- `BoardState` gains: `obstacle_maps: Optional[dict[str, MultiPolygon]] = None`, `routing_spaces: Optional[dict[str, RoutingSpace]] = None`, `channel_skeletons: Optional[dict[str, ChannelSkeleton]] = None`, `channel_widths: Optional[dict[str, ChannelWidths]] = None`, `occupancy_grids: Optional[dict[str, OccupancyGrid]] = None`, `layer_capacities: Optional[dict[str, LayerCapacity]] = None`, `routing_demand: Optional[RoutingDemand] = None`, `bottleneck_analysis: Optional[BottleneckAnalysis] = None`
- New file `router_v6/stage_validators.py` with `StageDRCFailure(field: str, value: Any, reason: str)` dataclass and `VALIDATOR_REGISTRY: dict[str, Callable]` + `@register_validator(name)` decorator
- Unit test `tests/router_v6/test_stage_validators.py` asserting registry discovery

**Dependencies:** `deterministic/state.py`, `deterministic/stages/base.py`

**Validation:** Existing DeterministicPipeline tests pass with new optional-None fields. `dataclasses.replace(state, obstacle_maps=...)` produces a valid BoardState.

---

### U1. ObstacleMapStage

**What:** Extract `build_obstacle_map(pcb, escape_vias) -> dict[str, MultiPolygon]` into a `Stage` subclass.

**Stage class:** `ObstacleMapStage` in `router_v6/obstacle_map.py`
- `name = "ObstacleMap"`
- `run(state)`: reads `state.board` (contains `pcb`), `state.vias` (escape vias); calls `build_obstacle_map(...)`; returns `replace(state, obstacle_maps=...)`

**Validators** (via `@register_validator("ObstacleMap")`):
- No obstacles on layers not declared in the stackup
- All declared copper layers have an obstacle entry (even if empty)
- Obstacle count >= pad count for through-hole components

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/obstacle_maps.json`

**PBT:** For any set of pads with known positions, the obstacle map covers every pad center point on the pad's declared layer. Pad centers never fall within free space.

**Coverage target:** `temper_placer.router_v6.obstacle_map` >= 90% line coverage

**Extraction order:** 1st (no upstream channel-analysis dependency)

---

### U2. RoutingSpaceStage

**What:** Extract `compute_routing_space(pcb, escape_vias) -> dict[str, RoutingSpace]` into a `Stage` subclass.

**Stage class:** `RoutingSpaceStage` in `router_v6/routing_space.py`
- `name = "RoutingSpace"`
- `run(state)`: reads `state.board`, `state.vias`, `state.obstacle_maps`; calls `compute_routing_space(...)`; returns `replace(state, routing_spaces=...)`

**Validators:**
- Routing area >= 0 for all layers
- Routing space polygons are disjoint within a layer
- Available area subset of board boundary

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/routing_spaces.json`

**PBT:** Routing area + obstacle area equals total area within 1% tolerance. No routing space polygon extends outside board boundary.

**Coverage target:** `temper_placer.router_v6.routing_space` >= 90%

**Extraction order:** 2nd (depends on obstacle_maps)

---

### U3. ChannelSkeletonStage

**What:** Extract `extract_channel_skeleton(routing_space, ...) -> ChannelSkeleton` (per-layer loop from `_run_stage2:257-264`) into a `Stage` subclass.

**Stage class:** `ChannelSkeletonStage` in `router_v6/channel_skeleton.py`
- `name = "ChannelSkeleton"`
- `run(state)`: reads `state.board`, `state.routing_spaces`; iterates outer layers (F.Cu, B.Cu); calls `extract_channel_skeleton(...)`; returns `replace(state, channel_skeletons=...)`

**Validators:**
- Skeleton node count > 0 for any layer with routing area > 0
- Edge endpoints within the layer's routing space bounding box

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/channel_skeletons.json`

**PBT:** For a connected routing space, the skeleton must have at least one node and every edge must lie within the routing space. Skeleton graph must be acyclic (no cycles that would create ambiguous routing channels).

**Coverage target:** `temper_placer.router_v6.channel_skeleton` >= 90%

**Extraction order:** 3rd (depends on routing_spaces)

---

### U4. ChannelWidthsStage

**What:** Extract `compute_channel_widths(routing_space, skeleton) -> ChannelWidths` (per-layer loop from `_run_stage2:269-275`) into a `Stage` subclass.

**Stage class:** `ChannelWidthsStage` in `router_v6/channel_widths.py`
- `name = "ChannelWidths"`
- `run(state)`: reads `state.routing_spaces`, `state.channel_skeletons`; iterates layers; calls `compute_channel_widths(...)`; returns `replace(state, channel_widths=...)`

**Validators:**
- All width values finite and non-negative
- Widths defined for every skeleton edge

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/channel_widths.json`

**PBT:** Every channel width measurement >= minimum allowed by design rules and <= maximum spatial extent of routing space on that layer.

**Coverage target:** `temper_placer.router_v6.channel_widths` >= 90%

**Extraction order:** 4th (depends on routing_spaces + channel_skeletons)

---

### U5. OccupancyGridStage

**What:** Extract `build_occupancy_grid(routing_space, inflation_mm) -> OccupancyGrid` (per-layer loop from `_run_stage2:286-289`) into a `Stage` subclass.

**Stage class:** `OccupancyGridStage` in `router_v6/occupancy_grid.py`
- `name = "OccupancyGrid"`
- `run(state)`: reads `state.routing_spaces`, `state.board` (for design_rules); computes `base_inflation`; calls `build_occupancy_grid(...)`; returns `replace(state, occupancy_grids=...)`

**Validators:**
- Grid dimensions are positive integers
- `cell_size <= min_channel_width` from design rules (grid resolves channels)
- Blocked-cell count >= pad count on that layer

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/occupancy_grids.json`

**PBT:** Pad centers marked as blocked (not free). Free-cell count <= routing space area / cell_area^2.

**Coverage target:** `temper_placer.router_v6.occupancy_grid` >= 90%

**Extraction order:** 5th (depends on routing_spaces + design_rules)

---

### U6. LayerCapacityStage

**What:** Extract `calculate_layer_capacity(grid, widths, ...) -> LayerCapacity` (per-layer loop from `_run_stage2:294-302`) into a `Stage` subclass.

**Stage class:** `LayerCapacityStage` in `router_v6/layer_capacity.py`
- `name = "LayerCapacity"`
- `run(state)`: reads `state.occupancy_grids`, `state.channel_widths`, `state.board` (for design_rules); calls `calculate_layer_capacity(...)` with 1.5x trace width margin; returns `replace(state, layer_capacities=...)`

**Validators:**
- `estimated_traces >= 0`
- `free_cells <= total_cells`
- All capacity values finite

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/layer_capacities.json`

**PBT:** Estimated trace count <= (free_cells * cell_size^2) / (trace_width + clearance)^2. Bottleneck severity monotonic with capacity-to-demand ratio.

**Coverage target:** `temper_placer.router_v6.layer_capacity` >= 90%

**Extraction order:** 6th (depends on occupancy_grids + channel_widths)

---

### U7. RoutingDemandStage

**What:** Extract `estimate_routing_demand(pcb) -> RoutingDemand` into a `Stage` subclass.

**Stage class:** `RoutingDemandStage` in `router_v6/routing_demand.py`
- `name = "RoutingDemand"`
- `run(state)`: reads `state.board` (for `pcb.nets` and `pcb.components`, equivalent to ParsedPCB); calls `estimate_routing_demand(...)`; returns `replace(state, routing_demand=...)`

**Validators:**
- `signal_nets + power_nets <= total_nets`
- All counts non-negative integers

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/routing_demand.json`

**PBT:** Total demand across all layers equals total routable net count. Demand for power nets is 0.

**Coverage target:** `temper_placer.router_v6.routing_demand` >= 90%

**Extraction order:** 7th (depends on board + netlist; no channel-analysis dependency, but needs BoardState populated)

**Note:** BoardState currently has a `board: Optional["Board"]` field typed as `temper_placer.core.board.Board`, not `ParsedPCB`. The routing demand stage needs `ParsedPCB` (nets, components). The stage adapts via `pcb = state.board` — this works because `deterministic/state.py`'s `Board` is a compatible concept, or we add a temp workaround: the orchestrator passes `ParsedPCB` through `state.board` by wrapping/coercing. Resolution: during U0 BoardState extension, verify that the DeterministicPipeline's `Board` type is compatible, or accept a `# type: ignore` bridge annotated with a ticket for future protocol unification.

---

### U8. BottleneckAnalysisStage

**What:** Extract `identify_bottlenecks(layer_capacities, demand) -> BottleneckAnalysis` into a `Stage` subclass.

**Stage class:** `BottleneckAnalysisStage` in `router_v6/bottleneck_analysis.py`
- `name = "BottleneckAnalysis"`
- `run(state)`: reads `state.layer_capacities`, `state.routing_demand`; calls `identify_bottlenecks(...)`; returns `replace(state, bottleneck_analysis=...)`

**Validators:**
- No bottleneck has severity NONE with utilization > 0
- Bottleneck count <= layer count

**Golden fixture:** `tests/fixtures/stage2_goldens/{board}/bottleneck_analysis.json`

**PBT:** If all layer capacities are infinite, no bottlenecks reported. If a layer has zero free cells, reported with CRITICAL severity.

**Coverage target:** `temper_placer.router_v6.bottleneck_analysis` >= 90%

**Extraction order:** 8th (depends on layer_capacities + routing_demand; highest downstream impact, extracted last because all others are its dependencies)

---

### U9. Stage2Orchestrator and Monolith Adapter

**What:** Build the `Stage2Orchestrator` that chains U1–U8 in dependency order, and refactor `_run_stage2` to use it.

**Deliverables:**
- `Stage2Orchestrator` class in a new `router_v6/stage2_orchestrator.py`:
  ```python
  class Stage2Orchestrator:
      _stages: list[Stage]
      def run(self, pcb: ParsedPCB, escape_vias: list[EscapeVia],
              initial_state: BoardState) -> BoardState: ...
  ```
  Chains: ObstacleMap -> RoutingSpace -> ChannelSkeleton -> ChannelWidths -> OccupancyGrid -> LayerCapacity -> RoutingDemand -> BottleneckAnalysis
  Each stage calls `state = stage.run(state)`; DRC validators run after each stage via `VALIDATOR_REGISTRY`.

- Refactored `_run_stage2` (`pipeline.py:241-328`):
  1. Construct initial `BoardState` from `pcb` and `escape_vias`
  2. Run `Stage2Orchestrator.run(pcb, escape_vias, initial_state)`
  3. Assemble `Stage2Output` from final `BoardState` fields
  4. Preserve verbose-logging lines (gated on `self.verbose`)

- Backward-compatibility adapter: `Stage2Output` assembly reads exactly the 8 fields from BoardState. Stage 3 accesses only `skeletons` + `channel_widths`; Stage 4 accesses `skeletons`, `occupancy_grids`, `routing_spaces` — all present.

**Performance regression test:** `test_stage2_monolith_parity.py` benchmarks wall-clock time of old `_run_stage2` vs `Stage2Orchestrator` on all 4 canonical boards, asserts <5% overhead.

---

### U10. Golden Fixture Generation Script and Parity Tests

**What:** Script to generate committed JSON fixtures, and two parity test files.

**Deliverables:**
- `tests/router_v6/generate_stage2_goldens.py`:
  - Runs `Stage2Orchestrator` on each of the 4 canonical boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra)
  - Captures per-sub-step output as JSON under `tests/fixtures/stage2_goldens/{board_name}/{stage_name}.json`
  - Runs each micro-stage individually (feeding intermediate BoardState) so each fixture isolates one sub-step
  - `--regenerate` flag for intentional algorithm changes
  - Custom JSON encoders: numpy `ndarray` -> `.tolist()`, NetworkX graph -> `node_link_data`, Shapely `MultiPolygon` -> WKT

- `tests/router_v6/test_stage2_golden_parity.py`:
  - Loads each fixture and asserts the corresponding micro-stage produces identical output
  - Tolerances: coordinate equality to 1e-6, exact integer equality for cell counts
  - Runs in CI only on commits touching channel analysis modules (path-filtered)

- `tests/router_v6/test_stage2_monolith_parity.py`:
  - Runs full `_run_stage2` monolith and `Stage2Orchestrator` on each canonical board
  - Asserts `Stage2Output` field-by-field equality
  - Per-stage parity: `test_obstacle_map_parity` compares only `obstacle_maps`, etc.
  - Performance regression: asserts <5% wall-clock overhead
  - Runs in CI on every push

---

### U11. PBT Suites (One per Micro-Stage)

**What:** Hypothesis-based property test suites as specified in R5a–R5h.

**Deliverables (8 test files):**
- `tests/router_v6/test_obstacle_map_pbt.py`
- `tests/router_v6/test_routing_space_pbt.py`
- `tests/router_v6/test_channel_skeleton_pbt.py`
- `tests/router_v6/test_channel_widths_pbt.py`
- `tests/router_v6/test_occupancy_grid_pbt.py`
- `tests/router_v6/test_layer_capacity_pbt.py`
- `tests/router_v6/test_routing_demand_pbt.py`
- `tests/router_v6/test_bottleneck_analysis_pbt.py`

Each suite:
- Runs >=100 random examples per strategy (`@settings(max_examples=100)`)
- Registered in CI with 30-second timeout
- Uses `@composite` strategies for geometric inputs where needed
- Catches a deliberately introduced invariant violation during development

---

### U12. Per-Module Coverage Gate

**What:** CI gate ensuring each channel analysis module achieves >=90% line coverage independently.

**Deliverable:** CI configuration addition (pytest invocation per module):
```bash
pytest tests/router_v6/test_obstacle_map.py tests/router_v6/test_obstacle_map_pbt.py \
  --cov=temper_placer.router_v6.obstacle_map --cov-fail-under=90
```
Repeated for each of the 8 modules. Enforced on every push touching any channel analysis module.

**Note:** `pytest-cov>=4.1.0` and `hypothesis>=6.0.0` are already in `pyproject.toml` test dependencies (confirmed).

---

## Extraction Order and Gating

| Step | Unit | Depends On | Gate to Pass Before Next |
|------|------|-----------|--------------------------|
| 0 | U0 (BoardState + validators) | — | Existing DeterministicPipeline tests pass |
| 1 | U1 (ObstacleMap) | U0 | Coverage >= 90%, golden parity, DRC gate |
| 2 | U2 (RoutingSpace) | U1 | U1 passes + U2 coverage >= 90%, PBT, DRC |
| 3 | U3 (ChannelSkeleton) | U2 | U3 coverage >= 90%, golden parity, PBT, DRC |
| 4 | U4 (ChannelWidths) | U2, U3 | U4 coverage >= 90%, golden parity, PBT, DRC |
| 5 | U5 (OccupancyGrid) | U2 | U5 coverage >= 90%, golden parity, PBT, DRC |
| 6 | U6 (LayerCapacity) | U4, U5 | U6 coverage >= 90%, golden parity, PBT, DRC |
| 7 | U7 (RoutingDemand) | U0 | U7 coverage >= 90%, golden parity, PBT, DRC |
| 8 | U8 (BottleneckAnalysis) | U6, U7 | U8 coverage >= 90%, golden parity, PBT, DRC |
| 9 | U9 (Orchestrator) | U1–U8 | U10 monolith parity passes on all 4 boards |
| 10 | U10 (Golden fixtures + parity) | U9 | All golden diffs = 0; monolith parity = pass |
| 11 | U11 (PBT suites) | U1–U8 | All 8 PBT suites >=100 examples and pass |
| 12 | U12 (Coverage gates) | U11 | All 8 modules >=90% in CI |

Steps 1–8 may be implemented in parallel passes within dependency constraints (e.g., U7 can be extracted independently of U2–U6 since it depends only on board/netlist).

---

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — `Stage(ABC)` with `name` and `run(state) -> BoardState` (protocol extended)
- `packages/temper-placer/src/temper_placer/deterministic/state.py` — `BoardState` frozen dataclass (8 new fields added)
- `packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py` — `build_obstacle_map` (wrapped, not rewritten)
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py` — `compute_routing_space`, `RoutingSpace`
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py` — `extract_channel_skeleton`, `ChannelSkeleton`
- `packages/temper-placer/src/temper_placer/router_v6/channel_widths.py` — `compute_channel_widths`, `ChannelWidths`
- `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py` — `build_occupancy_grid`, `OccupancyGrid`
- `packages/temper-placer/src/temper_placer/router_v6/layer_capacity.py` — `calculate_layer_capacity`, `LayerCapacity`
- `packages/temper-placer/src/temper_placer/router_v6/routing_demand.py` — `estimate_routing_demand`, `RoutingDemand`
- `packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py` — `identify_bottlenecks`, `BottleneckAnalysis`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `_run_stage2`, `Stage2Output`, `RouterV6Pipeline` (refactored `_run_stage2` only)
- `packages/temper-placer/src/temper_placer/router_v6/test_boards.py` — `TEST_BOARDS` with 4 canonical boards
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py` — `ParsedPCB` (used by RoutingDemandStage)
- `packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py` — `EscapeVia` (used by ObstacleMapStage, RoutingSpaceStage)
- Existing test files: `tests/router_v6/test_obstacle_map.py`, `test_routing_space.py`, `test_channel_skeleton.py`, `test_channel_widths.py`, `test_occupancy_grid.py`, `test_layer_capacity.py`, `test_routing_demand.py`, `test_bottleneck_analysis.py`

---

## Assumptions

1. **BoardState fields can be extended without breaking the DeterministicPipeline.** BoardState is a frozen dataclass with `Optional[...] = None` defaults — adding 8 new optional fields does not change existing consumers because they default to `None`. Verified: `state.py:19-39` — all fields use `= None` or `= field(default_factory=...)`.

2. **The 4 canonical test boards are representative.** Piantor_Right (digital, 2L, 33 nets), LibreSolar_BMS (power, 4L, 200 nets), RP2040_DesignGuide (mixed, 4L, 120 nets), BitAxe_Ultra (mixed, 2L, 80 nets) span digital, power, and mixed-signal domains. If golden fixtures match on all 4, the extraction is correct.

3. **Existing module-level functions are pure enough to wrap.** They read arguments, compute, return dataclasses — no global state mutation, disk I/O, or external service dependencies. Verified by reading function signatures: all return new objects.

4. **The `_run_stage2` ordering (obstacle -> routing space -> skeleton -> widths -> occupancy -> capacity -> demand -> bottleneck) is the correct dependency DAG.** Verified: bottleneck reads `layer_capacities` + `routing_demand` (both computed earlier). Occupancy grid reads `routing_spaces` (computed earlier). The micro-stage DAG mirrors this order.

5. **`hypothesis` and `pytest-cov` are available.** Confirmed: `pyproject.toml` test deps include `hypothesis>=6.0.0`, `pytest-cov>=4.1.0`, `pytest>=7.4.0`.

6. **Serialization to JSON is feasible.** Occupancy grids (numpy ndarray) serialize via `.tolist()`. Channel skeletons (NetworkX Graph) serialize via `node_link_data`. Shapely `MultiPolygon` serializes via WKT. Custom JSON encoder handles all three.

7. **`_run_stage3` and `_run_stage4` field access is bounded.** Verified: Stage 3 accesses `stage2.skeletons` (line 337) + `stage2.channel_widths` (line 339). Stage 4 accesses `stage2.skeletons` (lines 409, 414–416), `stage2.occupancy_grids` (lines 447–453, 528), `stage2.routing_spaces` (line 501). The backward-compatibility adapter only needs to populate these 4 fields from BoardState; the other 4 fields (`obstacle_maps`, `layer_capacities`, `routing_demand`, `bottleneck_analysis`) are present in `Stage2Output` but not consumed downstream.

8. **Parity test runs in <60 seconds in CI.** Parsing and obstacle map building may take seconds per board, but SAT/A* downstream stages are not invoked. The parity test runs only `_run_stage2` monolith + `Stage2Orchestrator`.

---

## Open Questions

### Resolved (decisions incorporated above)

- **[K1]** BoardState extension via field addition, not subclass.
- **[K2]** 8 direct Stage subclasses, no mixin.
- **[K3]** Forward extraction order (obstacle -> bottleneck).
- **[K5]** JSON with custom encoders for golden fixtures.
- **[K6]** Standalone validator functions with decorator registration.
- **[K4/K8]** BoardState field mapping confirmed: Stage 3 needs `skeletons` + `channel_widths`; Stage 4 needs `skeletons` + `occupancy_grids` + `routing_spaces`.

### Unresolved (for implementation phase)

- **[U7][Technical]** `RoutingDemandStage` needs `ParsedPCB` (nets, components), but `BoardState.board` is typed as `Optional["Board"]` (the DeterministicPipeline's `Board` from `temper_placer.core.board`, not `ParsedPCB`). Resolution during U0: verify whether `Board` is compatible with `ParsedPCB` or bridge with explicit cast + ticket annotation.

- **[U10][Needs research]** Are the 4 canonical boards' `.kicad_pcb` fixture files present at `tests/fixtures/external/.cache/`? The `test_boards.py` defines `PIANTOR_PATH` etc. — confirm `exists()` returns True before writing the golden generation script.

- **[U11][Needs research]** What `hypothesis` strategies produce valid geometric inputs for each sub-step? Obstacle maps need pad geometry strategies; occupancy grids need routing space strategies. Each PBT module may need custom `@composite` strategies. The `shapely` hypothesis plugin (`hypothesis-shapely`) may provide ready-made strategies.

- **[U12][Process]** Exact `pytest-cov` invocation for per-module coverage gate. Confirm `--cov=temper_placer.router_v6.obstacle_map --cov-fail-under=90` works with the existing `[tool.pytest.ini_options]` in `pyproject.toml`.

- **[U1][Scope]** `build_obstacle_map` is already called inside `compute_routing_space` (line 80 of `routing_space.py`). This means `ObstacleMapStage` and `RoutingSpaceStage` both call the same function — the orchestrator must either pass pre-computed obstacle maps to `compute_routing_space` (avoid double computation) or accept the minor redundancy. Resolution during U2: check if `compute_routing_space` accepts pre-computed obstacle maps as an optional parameter. If not, add one (light refactor) or accept double computation (the obstacle map is cheap — <100ms).

---

## Success Criteria

- **SC1.** `Stage2Orchestrator` produces `Stage2Output` identical to the monolith's `_run_stage2` on all 4 canonical test boards (U10 monolith parity test passes)
- **SC2.** Each of the 8 micro-stage modules reaches >=90% line coverage (U12 coverage gates pass in CI)
- **SC3.** The golden fixture test (U10) diffs exactly 0 on all 4 boards when no algorithm changes are made
- **SC4.** The per-stage DRC gate (R6) catches a deliberately introduced invariant violation (e.g., a pad center marked as free in occupancy grid) with a named `StageDRCFailure`
- **SC5.** The PBT suite (U11) runs >=100 examples per stage and catches a deliberately introduced geometric invariant violation
- **SC6.** The closure test produces identical `router_completion_pct` and `drc_errors` before and after the decomposition
- **SC7.** Existing tests in `tests/router_v6/test_*.py` for the 8 channel analysis modules continue to pass
- **SC8.** Performance regression <= 5% wall-clock overhead vs monolith on canonical boards

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BoardState field addition breaks DeterministicPipeline consumers | Low | High | All existing fields use `= None` defaults; deterministic pipeline tests run as gate before any micro-stage lands |
| `RoutingDemandStage` Board/BoardState type mismatch | Medium | Medium | Resolved during U0 with explicit bridge; if impossible, defer U7 to a follow-up and keep `estimate_routing_demand` called directly in orchestrator |
| Can't run parity test on all 4 boards (missing .kicad_pcb fixtures) | Medium | Medium | Fall back to whatever subset is available; document which boards are tested |
| `hypothesis` strategies for geometric inputs are too slow or flaky | Low | Medium | Timeouts (30s per suite) catch this; flaky strategies can be swapped for seeded RNG strategies |
| Double computation in RoutingSpaceStage (obstacle maps built twice) | Low | Low | Either pass pre-computed maps or accept <100ms redundancy |
| Per-module coverage gate reveals existing gaps in test coverage | High | Low | This is the point — gaps are filled as part of each U1–U8 implementation |
| Monolith parity breaks due to float tolerance differences | Medium | Medium | JSON golden fixtures use 1e-6 tolerance for geometric fields; parity test at same precision |
| Existing `_run_stage2` verbose logging lost in extraction | Low | Low | Orchestrator preserves verbose flag; each stage can accept an optional `verbose: bool` parameter |

---

## Implementation Notes

### Code conventions
- Stage subclasses follow the DeterministicPipeline pattern: `name` property, `run(state: BoardState) -> BoardState` method.
- All module-level functions (`build_obstacle_map`, `compute_routing_space`, etc.) remain unchanged and callable directly.
- DRC validators are standalone functions decorated with `@register_validator("StageName")`, not methods.
- Golden fixtures use JSON with custom encoder (numpy `.tolist()`, networkx `node_link_data`, shapely WKT).
- PBT suites use `hypothesis` with `@settings(max_examples=100, deadline=30000)`.

### File listing
```
packages/temper-placer/src/temper_placer/
  deterministic/
    state.py                          # +8 fields (MODIFY)
  router_v6/
    stage_validators.py               # NEW: StageDRCFailure + @register_validator
    stage2_orchestrator.py            # NEW: Stage2Orchestrator
    obstacle_map.py                   # +ObstacleMapStage class (MODIFY)
    routing_space.py                  # +RoutingSpaceStage class (MODIFY)
    channel_skeleton.py               # +ChannelSkeletonStage class (MODIFY)
    channel_widths.py                 # +ChannelWidthsStage class (MODIFY)
    occupancy_grid.py                 # +OccupancyGridStage class (MODIFY)
    layer_capacity.py                 # +LayerCapacityStage class (MODIFY)
    routing_demand.py                 # +RoutingDemandStage class (MODIFY)
    bottleneck_analysis.py            # +BottleneckAnalysisStage class (MODIFY)
    pipeline.py                       # _run_stage2 refactored (MODIFY)

packages/temper-placer/tests/
  fixtures/stage2_goldens/
    {board_name}/
      obstacle_maps.json              # NEW: golden fixture
      routing_spaces.json             # NEW
      channel_skeletons.json          # NEW
      channel_widths.json             # NEW
      occupancy_grids.json            # NEW
      layer_capacities.json           # NEW
      routing_demand.json             # NEW
      bottleneck_analysis.json        # NEW
  router_v6/
    test_stage_validators.py          # NEW
    test_stage2_golden_parity.py      # NEW
    test_stage2_monolith_parity.py    # NEW
    generate_stage2_goldens.py        # NEW
    test_obstacle_map_pbt.py          # NEW
    test_routing_space_pbt.py         # NEW
    test_channel_skeleton_pbt.py      # NEW
    test_channel_widths_pbt.py        # NEW
    test_occupancy_grid_pbt.py        # NEW
    test_layer_capacity_pbt.py        # NEW
    test_routing_demand_pbt.py        # NEW
    test_bottleneck_analysis_pbt.py   # NEW
```
