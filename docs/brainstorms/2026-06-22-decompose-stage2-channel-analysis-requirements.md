---
date: 2026-06-22
topic: decompose-stage2-channel-analysis
focus: Split RouterV6 Stage 2's 8-sub-step monolith into individually testable micro-stages conforming to the unified Stage protocol
origin: docs/ideation/2026-06-22-pipeline-strangler-decomposition-ideation.md (#5)
status: active
actors: Router V6 developer, CI system, closure test pipeline
---

# Requirements: Decompose RouterV6 Stage 2 Channel Analysis

## Problem Frame

Router V6's completion rate is 0.5%. Stage 2 (channel analysis) feeds into Stage 3 (SAT solver) and Stage 4 (A* router). If channel analysis produces a wrong occupancy grid or misidentifies bottlenecks, everything downstream fails — but there is no way to isolate which of the 8 sub-steps is at fault. Today `_run_stage2` (`pipeline.py:241-326`) is an 85-line monolith method that calls 8 sequential functions and returns a composite `Stage2Output` dataclass. Each sub-step already has its own module file (`obstacle_map.py`, `occupancy_grid.py`, etc.) and its own low-level tests — but no per-sub-step integration tests, golden fixtures on canonical boards, incremental DRC gates, or parity assertions against the monolith.

The TDD per-concern pattern (past learning #5) proved this approach works: 5 test files each targeting one isolation concern achieved 96.7% clearance pass rate. The DeterministicPipeline already defines a clean Stage protocol: `Stage.run(state: BoardState) → BoardState` with immutable frozen-dataclass state. Channel analysis sub-steps inherit no such protocol — they take disparate arguments and return loose dataclasses assembled by `_run_stage2`.

## Actors

- **A1. Router V6 developer** — changes channel analysis logic (e.g., a new channel skeleton algorithm), runs per-sub-step tests and parity tests to confirm correctness before integration
- **A2. CI system** — runs the per-stage test suite, golden fixture diffs, DRC gate, and coverage gate on every push that touches any channel analysis module
- **A3. Closure test** — the project's end-to-end validation loop (parse → place → route → DRC); after extraction, closure test results can be compared before/after decomposition to confirm behavioral preservation

## Key Decisions

- **K1. Extraction into independent Stages conforming to the DeterministicPipeline Stage protocol.** Each of the 8 sub-steps becomes a `Stage` subclass with `run(state: BoardState) → BoardState`. The monolith's `_run_stage2` becomes a Stage2Orchestrator that chains the 8 micro-stages in order. The unified Stage protocol from ideation #3 is applied here first because Stage 2 has the cleanest pre-existing seam pattern (well-typed intermediate dataclasses, already-separate modules).
- **K2. Extraction order by downstream impact.** Extract bottleneck identification first (it flags the severity that SAT/A* consume), then occupancy grid (A* reads it directly), then channel widths, skeleton, routing space, obstacle maps, layer capacity, and routing demand. The first extraction is the hardest because it requires defining the BoardState fields the micro-stage reads and writes; subsequent extractions inherit that pattern.
- **K3. Golden fixtures on canonical test boards.** Each micro-stage's output on the 4-board corpus (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) is captured as a committed JSON/pickle fixture. Parity tests assert the extracted micro-stage produces identical output to the monolith's corresponding sub-step call. Fixtures are regenerated when the sub-step algorithm intentionally changes (via a `--regenerate-fixtures` flag in the test).
- **K4. Per-stage DRC gate.** Each micro-stage's `BoardState` output is validated against a stage-specific invariant that does not require downstream context. For example, the occupancy grid stage asserts no free cell overlaps a pad center; the obstacle map stage asserts no obstacles on non-existent layers. These are run as CI gates on every push.
- **K5. Coverage target per extracted module.** Each micro-stage reaches ≥90% line coverage before the next micro-stage is extracted. The coverage gate is module-scoped (e.g., `temper_placer.router_v6.channel_widths` at ≥90%). This prevents extraction from compounding untested code.

## Requirements

### R1. Unified Stage Protocol for Channel Analysis

Status: required

Define a `ChannelAnalysisStage(Stage)` subclass or mixin that extends the DeterministicPipeline's `Stage(ABC)` with channel-analysis-specific BoardState fields:

- `BoardState` gains fields for: `obstacle_maps`, `routing_spaces`, `channel_skeletons`, `channel_widths`, `occupancy_grids`, `layer_capacities`, `routing_demand`, `bottleneck_analysis`
- Each field is typed as a frozen/immutable container (e.g., `Mapping[str, ...]` stored as `frozenset` or `tuple[tuple[str, ...], ...]` where the type system requires it)
- The existing `Stage2Output` dataclass is deprecated in favor of reading these fields from `BoardState`; `_run_stage2` is refactored to populate BoardState and assemble `Stage2Output` from it for backward compatibility with Stages 3 and 4

Design rationale: Extend the existing DeterministicPipeline BoardState rather than invent a parallel protocol. The deterministic pipeline's Stage pattern is the cleanest architecture in the codebase; adopting it here unifies a path that future extractions (Stage 3, Stage 1) can follow.

### R2. Eight Micro-Stage Classes

Status: required

Implement the following `Stage` subclasses, each in its existing module file:

| # | Stage class | Module | Input fields | Output fields |
|---|-------------|--------|-------------|---------------|
| 1 | `ObstacleMapStage` | `obstacle_map.py` | `board`, `escape_vias` | `obstacle_maps` |
| 2 | `RoutingSpaceStage` | `routing_space.py` | `board`, `escape_vias`, `obstacle_maps` | `routing_spaces` |
| 3 | `ChannelSkeletonStage` | `channel_skeleton.py` | `routing_spaces` | `channel_skeletons` |
| 4 | `ChannelWidthsStage` | `channel_widths.py` | `routing_spaces`, `channel_skeletons` | `channel_widths` |
| 5 | `OccupancyGridStage` | `occupancy_grid.py` | `routing_spaces`, `design_rules` | `occupancy_grids` |
| 6 | `LayerCapacityStage` | `layer_capacity.py` | `occupancy_grids`, `channel_widths`, `design_rules` | `layer_capacities` |
| 7 | `RoutingDemandStage` | `routing_demand.py` | `board`, `netlist` | `routing_demand` |
| 8 | `BottleneckAnalysisStage` | `bottleneck_analysis.py` | `layer_capacities`, `routing_demand` | `bottleneck_analysis` |

Each micro-stage:
- Implements `name` (e.g., `"ObstacleMap"`) and `run(state: BoardState) -> BoardState`
- Delegates to the existing module-level function (e.g., `ObstacleMapStage.run()` calls `build_obstacle_map(pcb, escape_vias)` under the hood)
- Does not import from other micro-stages except those listed as input fields (DAG edge enforcement)
- Raises a typed error (not a generic `RuntimeError`) if its input fields are unpopulated

### R3. Stage2Orchestrator and Monolith Adapter

Status: required

- **R3a.** `Stage2Orchestrator` chains the 8 micro-stages in dependency order, invoking `run(state)` and threading `BoardState` through. Returns the final `BoardState`.
- **R3b.** `_run_stage2` is refactored to instantiate and run `Stage2Orchestrator`, then assemble `Stage2Output` from the final `BoardState` fields for backward compatibility with Stages 3 and 4. Stage 3 (`_run_stage3`) and Stage 4 (`_run_stage4`) do not change.
- **R3c.** The existing module-level functions (`build_obstacle_map`, `compute_routing_space`, etc.) remain unchanged and callable directly for cases where a full `BoardState` is undesirable (e.g., interactive debugging, single-step benchmarking). The Stage classes are wrappers around these functions, not replacements.

### R4. Golden Fixtures on Canonical Test Boards

Status: required

- **R4a.** A `generate_stage2_goldens.py` script runs `Stage2Orchestrator` on each of the 4 canonical test boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) and captures per-sub-step output as committed JSON fixtures under `packages/temper-placer/tests/fixtures/stage2_goldens/{board_name}/{stage_name}.json`. The script runs each micro-stage individually (feeding it the intermediate BoardState) so each fixture isolates one sub-step.
- **R4b.** A test `test_stage2_golden_parity.py` loads each fixture and asserts that running the corresponding micro-stage on the same board produces identical output. Tolerances are defined per output type (e.g., coordinate equality to 1e-6 for geometric fields, exact integer equality for cell counts).
- **R4c.** The golden fixture tests run in CI only on commits that touch channel analysis modules (`obstacle_map.py`, `routing_space.py`, `channel_skeleton.py`, `channel_widths.py`, `occupancy_grid.py`, `layer_capacity.py`, `routing_demand.py`, `bottleneck_analysis.py`, `pipeline.py`). Regenerating fixtures is a manual step (`python generate_stage2_goldens.py --regenerate`) performed after an intentional algorithm change.

### R5. Property-Based Tests per Micro-Stage

Status: required

Implement a PBT suite per micro-stage using `hypothesis`:

- **R5a. Obstacle map PBT:** For any set of pads with known positions, the obstacle map must cover every pad center point on the pad's declared layer. Pad centers must never fall within free space.
- **R5b. Routing space PBT:** The routing area + obstacle area must equal total area within 1% tolerance. No routing space polygon may extend outside the board boundary.
- **R5c. Channel skeleton PBT:** For a connected routing space, the skeleton must have at least one node and every edge must lie within the routing space. The skeleton graph must be acyclic (tree or tree-like) — no cycles that would create ambiguous routing channels.
- **R5d. Channel width PBT:** Every channel width measurement must be ≥ the minimum width allowed by design rules and ≤ the maximum spatial extent of the routing space on that layer.
- **R5e. Occupancy grid PBT:** Pad centers must be marked as blocked, not free. The grid's free-cell count must be ≤ the routing space area divided by cell area squared.
- **R5f. Layer capacity PBT:** Estimated trace count must be ≤ (free cells × cell size²) / (trace width + clearance)². Bottleneck severity must be monotonic with capacity-to-demand ratio.
- **R5g. Routing demand PBT:** Total demand across all layers must equal the total routable net count. Demand for power nets must be 0 (power nets go on planes, not channels).
- **R5h. Bottleneck PBT:** If all layer capacities are infinite, no bottlenecks are reported. If a layer has zero free cells, it must be reported with CRITICAL severity.

Each PBT suite runs at least 100 random examples per strategy and is registered in CI with a 30-second timeout.

### R6. Per-Stage DRC Gate

Status: required

Each micro-stage's `run()` method includes a post-condition validation step (`_validate(state: BoardState)`) that asserts stage-specific invariants. If any invariant fails, the stage raises a `StageDRCFailure` with the violating field and value. The validators are:

- **ObstacleMap:** No obstacles on layers not declared in the stackup. All declared copper layers have an obstacle entry (even if empty). Obstacle count ≥ pad count for through-hole components.
- **RoutingSpace:** Routing area ≥ 0 for all layers. Routing space polygons are disjoint within a layer. Available area ⊆ board boundary.
- **ChannelSkeleton:** Skeleton node count > 0 for any layer with routing area > 0. Edge endpoints are within the layer's routing space bounding box.
- **ChannelWidths:** All width values are finite and non-negative. Widths are defined for every skeleton edge.
- **OccupancyGrid:** Grid dimensions are positive integers. cell_size ≤ min_channel_width from design rules (so the grid resolves channels). Blocked-cell count ≥ pad count on that layer.
- **LayerCapacity:** estimated_traces ≥ 0. free_cells ≤ total_cells. Capacity values are finite.
- **RoutingDemand:** signal_nets + power_nets ≤ total_nets. All counts are non-negative integers.
- **BottleneckAnalysis:** No bottleneck has severity NONE with utilization > 0. Bottleneck count ≤ layer count.

### R7. Coverage Target per Extracted Module

Status: required

- **R7a.** Each of the 8 channel analysis modules is registered in a coverage gate at `>= 90%` line coverage. The gate is enforced in CI on every push that touches any channel analysis module.
- **R7b.** The coverage report is scoped per module (e.g., `temper_placer.router_v6.obstacle_map`), not per pipeline. A module below threshold fails CI with a `coverage: <module> at X% < 90%` message.
- **R7c.** Coverage measurement uses `pytest-cov` with `--cov=temper_placer.router_v6.{module}` per-module flags. No aggregation trick that hides an untested module behind a well-tested neighbor.

### R8. Parity Test: Micro-Stage vs Monolith Sub-Step

Status: required

- **R8a.** `test_stage2_monolith_parity.py` runs the full `_run_stage2` monolith on each of the 4 canonical boards, then runs `Stage2Orchestrator` on the same board, and asserts that the resulting `Stage2Output` fields are identical to the monolith's. This is the integration safety net: it proves the extraction did not change behavior.
- **R8b.** The parity test is also runnable at the individual micro-stage level: `test_stage2_monolith_parity.py::test_obstacle_map_parity` compares only `Stage2Output.obstacle_maps`, etc. This allows fast re-verification when only one micro-stage's implementation changes.
- **R8c.** Parity test runs in CI on every push. It is the single gate that prevents silent drift between the extracted stages and the monolith.

### R9. Extraction Order Enforcement

Status: required

Extraction order is gated by the DAG: a micro-stage cannot be extracted and landed on `main` until all its input dependencies are extracted and passing R7 (coverage ≥ 90%). The extraction order is:

1. **ObstacleMapStage** — no upstream channel-analysis dependency
2. **RoutingSpaceStage** — depends on obstacle_maps
3. **ChannelSkeletonStage** — depends on routing_spaces
4. **ChannelWidthsStage** — depends on routing_spaces + channel_skeletons
5. **OccupancyGridStage** — depends on routing_spaces + design_rules
6. **LayerCapacityStage** — depends on occupancy_grids + channel_widths
7. **RoutingDemandStage** — depends on board + netlist (no channel-analysis dependency, but needs BoardState.netlist populated)
8. **BottleneckAnalysisStage** — depends on layer_capacities + routing_demand (highest downstream impact, extracted last because it depends on all others)

This is the reverse of the seed idea's suggested order (bottleneck→...→obstacle). Rationale: extracting the data producers first means each extraction can be verified by running the real upstream stages (not mocks) and comparing to the monolith's intermediate state at that point. Extracting bottleneck first would require mocking all 7 upstream stages — the extracted stage would be verified against synthetic data, not real pipeline state. The parity test at each extraction step compares the partially-extracted pipeline output to the monolith at the corresponding sub-step boundary, which is only possible when upstream stages are real.

## Scope Boundaries

### Deferred for later

- **Extracting Stage 3 (SAT solver) or Stage 4 (A* router).** These are downstream consumers of Stage 2 output. Decomposing Stage 2 first makes their own extraction easier (they receive a well-understood `BoardState`), but this initiative does not touch them beyond the backward-compatibility adapter in R3b.
- **Parameterizing the Stage DAG for runtime reordering.** The 8 micro-stages are chained in a fixed order. A configurable DAG executor (ideation #4) is a separate initiative.
- **Implementing the unified Stage protocol for the full codebase.** This initiative extends BoardState with channel-analysis fields; it does not refactor `PipelineOrchestrator` or `DeterministicPipeline` to use a common protocol. That unification is ideation #3.
- **Cross-stage DRC gates (e.g., "does the occupancy grid reflect obstacle map changes?").** R6 validates invariants within a single stage's output. Cross-stage invariants require a DAG with multi-stage context (ideation #6).

### Outside this product's identity

- **Improving channel analysis algorithms.** The micro-stages delegate to the existing module-level functions unchanged. This initiative changes the structure (how stages are composed and verified), not the algorithms (what the stages compute).
- **Changing the Stage 3 or Stage 4 interfaces.** `_run_stage3` and `_run_stage4` continue to consume `Stage2Output` — the orchestrator assembles it from `BoardState`.
- **Performance optimization.** The extraction adds a thin wrapper overhead (one function call per micro-stage, one `dataclasses.replace` per stage). This is negligible compared to SAT/A* wall time.

## Success Criteria

- **SC1.** `Stage2Orchestrator` produces `Stage2Output` identical to the monolith's `_run_stage2` on all 4 canonical test boards (R8 parity test passes)
- **SC2.** Each of the 8 micro-stage modules reaches ≥90% line coverage (R7 gate passes in CI)
- **SC3.** The golden fixture test (R4) diffs exactly 0 on all 4 boards when no algorithm changes are made
- **SC4.** The per-stage DRC gate (R6) catches a deliberately introduced invariant violation (e.g., a pad center marked as free in occupancy grid) with a named `StageDRCFailure`
- **SC5.** The PBT suite (R5) runs ≥100 examples per stage and catches a deliberately introduced geometric invariant violation
- **SC6.** The closure test (A3) produces identical `router_completion_pct` and `drc_errors` before and after the decomposition
- **SC7.** Existing tests in `tests/router_v6/test_*.py` for the 8 channel analysis modules continue to pass

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — `Stage(ABC)` with `name` and `run(state) → BoardState` (the protocol we extend)
- `packages/temper-placer/src/temper_placer/deterministic/state.py` — `BoardState` frozen dataclass (we add channel-analysis fields to it)
- `packages/temper-placer/src/temper_placer/router_v6/{obstacle_map, routing_space, channel_skeleton, channel_widths, occupancy_grid, layer_capacity, routing_demand, bottleneck_analysis}.py` — existing module-level functions (we wrap, not rewrite)
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `_run_stage2`, `Stage2Output`, `RouterV6Pipeline` (we refactor `_run_stage2`, leave other stages unchanged)
- `packages/temper-placer/src/temper_placer/router_v6/test_boards.py` — `TEST_BOARDS` with 4 canonical boards (golden fixture generation reads from here)
- `packages/temper-placer/tests/router_v6/test_{obstacle_map, routing_space, channel_skeleton, channel_widths, occupancy_grid, layer_capacity, routing_demand, bottleneck_analysis}.py` — existing per-module tests (must continue to pass, may be extended with Stage.run() integration tests)

## Assumptions

1. **BoardState fields can be extended without breaking the DeterministicPipeline.** BoardState is a frozen dataclass with `Optional[...] = None` defaults — adding 8 new optional fields does not change existing consumers because they default to `None`. Verified by reading `state.py`: all fields use `= None` or `= field(default_factory=...)`.
2. **The 4 canonical test boards are representative of the routing challenges that exercise all 8 sub-steps.** Piantor_Right (digital, 2L, 33 nets), LibreSolar_BMS (power, 4L, 200 nets), RP2040_DesignGuide (digital, 4L), and BitAxe_Ultra (mixed, 4L) span digital, power, and mixed-signal domains. Assumption: if golden fixtures match on all 4, the extraction is correct.
3. **The existing module-level functions are pure enough to be wrapped as Stage.run() without side effects.** They read their arguments, compute, and return dataclasses — they do not mutate global state, write to disk, or depend on external services. Verified by reading `obstacle_map.py:23`, `occupancy_grid.py`, etc. — all return new objects.
4. **The `_run_stage2` ordering in pipeline.py (obstacle → routing space → skeleton → widths → occupancy → capacity → demand → bottleneck) is the correct dependency DAG.** The bottleneck step reads `layer_capacities` and `routing_demand` — both computed earlier. Occupancy grid reads `routing_spaces` and `design_rules` — both available earlier. The micro-stage DAG mirrors this order.
5. **`hypothesis` is already a test dependency or can be added.** Not verified — during planning, confirm `hypothesis` is in `pyproject.toml [project.optional-dependencies] test` or add it.
6. **Serializing occupancy grids and channel skeletons to JSON is feasible.** Occupancy grids are integer arrays (np.ndarray), channel skeletons are NetworkX graphs. JSON fixtures may require custom encoders (e.g., networkx → edge list, ndarray → nested list). During planning, pick the serialization format (JSON with custom encoders, or pickle for binary-accurate comparison).

## Open Questions

### Resolve Before Planning

- **[Affects R1][Technical]** Should `BoardState` channel-analysis fields live directly on the DeterministicPipeline's `BoardState`, or should we define a `ChannelAnalysisState(BoardState)` subclass with the 8 fields? Subclass avoids touching `deterministic/state.py` but means the orchestrator must downcast.
- **[Affects R4][Technical]** What is the exact serialization format for golden fixtures? JSON with custom encoders (human-diffable but requires encoder maintenance) vs pickle (byte-accurate but opaque and Python-version-dependent). Recommendation: JSON with numpy `.tolist()` and networkx `node_link_data` for skeletons — diffable in CI.
- **[Affects R6][Design]** Should per-stage DRC validators be methods on the Stage class, or standalone functions registered against the stage name? Standalone functions are more testable and composable; methods are simpler to discover. Recommendation: standalone `validate_obstacle_map(state: BoardState) -> list[StageDRCFailure]` with a `@register_validator("ObstacleMap")` decorator for auto-discovery.
- **[Affects R3][Technical]** Does `_run_stage3` and `_run_stage4` access `Stage2Output` fields beyond what the BoardState adapter provides? If yes, the adapter must expose those fields. Verify by reading `_run_stage3:328-349+` and `_run_stage4` usage.

### Deferred to Planning

- **[Affects R4][Needs research]** Are the 4 canonical boards' `.kicad_pcb` fixture files all present under `tests/fixtures/external/.cache/`? The `test_boards.py` defines `PIANTOR_PATH` etc. — confirm `exists()` returns True for all 4 before writing the golden generation script.
- **[Affects R5][Needs research]** What `hypothesis` strategies generate valid geometric inputs for each sub-step? Obstacle maps need strategies that produce valid pad geometries; occupancy grids need strategies that produce valid routing spaces. Each PBT module may need custom `@composite` strategies.
- **[Affects R7][Process]** What is the exact `pytest-cov` invocation for a per-module coverage gate? Determine whether `--cov=temper_placer.router_v6.obstacle_map --cov-fail-under=90` works with the existing test runner, or if a custom `coverage` config section is needed.
- **[Affects R8][Technical]** Can the parity test run in a reasonable time for CI? Running `_run_stage2` monolith + `Stage2Orchestrator` on 4 boards may be slow (SAT/A* downstream stages are not invoked, but parsing and obstacle map building may take seconds per board). Target: parity test completes in < 60 seconds in CI.
