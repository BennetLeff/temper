---
title: "feat: Deploy Strangler to RouterV6 Stage 4 (A* Pathfinding) into 5 Micro-Stages"
type: feat
status: active
date: 2026-06-23
origin: prior session — pipeline strangler decomposition continuation
---

# feat: Deploy Strangler to RouterV6 Stage 4 (A* Pathfinding)

## Summary

Complete the strangler-fig decomposition of `RouterV6Pipeline._run_stage4` (`router_v6/pipeline.py:444-683`), centered on the 1795-line `router_v6/astar_pathfinding.py` monolith. Partial extraction has already started (`astar_core.py` with search algorithms, `astar_grid.py` with grid helpers) but the monolith still carries duplicate copies of all extracted code. This plan deduplicates the existing extraction AND extracts the remaining unique code (orchestration, net ordering, result aggregation) into 5 `Stage` subclasses, wired via a `Stage4Orchestrator` with per-stage DRC gates, golden fixture parity, PBT suites, and coverage gates. The pattern matches Stage 2 (8 micro-stages) and Stage 3 (5 micro-stages) decomposition.

---

## Problem Frame

Stage 4 (A* geometric realization) is the last monolithic stage in the RouterV6 pipeline. Its `_run_stage4` handler in `pipeline.py` is a 240-line sequential call chain — setup channel mapping, run A* pathfinding (the 1795-line monolith), smooth paths, place vias, assign widths, compile results. When a net fails to route, attribution is opaque: the failure could be a malformed channel mapping (Stage 3), an over-constrained occupancy grid (Stage 4.1), an incorrect net ordering heuristic (Stage 4.2), or the A* search itself (Stage 4.3). Without per-micro-stage isolation, there are no incremental DRC fences and no way to tell which sub-step introduced the problem.

The `astar_pathfinding.py` monolith contains:
- **6 unique functions** not yet extracted: `run_astar_pathfinding()` (306 lines), `_astar_route_with_ripup()`, `_astar_route_multilayer()`, `_astar_route()`, `_compute_net_order()`, plus `PathfindingResult` and `RoutingFailureReport` dataclasses
- **Duplicate code** already extracted to `astar_core.py` (`RoutePath`, `RouteNode3D`, `RoutePath3D`, A*/Theta*/3D search algorithms) and `astar_grid.py` (grid helpers, pad access)
- **2 stubs** (`astar_diagnostics.py`, `astar_lanes.py`) that were never implemented — not addressed by this plan

All infrastructure from Stage 2/3 decomposition (Stage protocol, golden format, CI gates, DRC fence, `BoardState` extension pattern, orchestrator/adapter pattern) is built, tested, and proven across 13 micro-stages.

---

## Scope Boundaries

### In scope

- Complete deduplication of `astar_core.py` and `astar_grid.py` — wire monolith to delegate, eliminate copied functions
- Extract remaining unique functions into 5 `Stage` subclasses
- `Stage4Orchestrator` chaining 6 micro-stages (grid prep → net ordering → route → result aggregate, plus the 2 deduplicated-as-micro-stage wrappers)
- Backward-compatibility adapter assembling `PathfindingResult` from final `BoardState`
- Per-stage DRC validators via `@register_validator` decorator
- Golden fixtures (4 canonical boards × 4 new micro-stages = 16 JSON fixtures)
- Golden parity test + monolith parity test
- PBT suites (hypothesis, >=100 examples per micro-stage)
- Per-module coverage gate >=90%
- `generate_stage4_goldens.py` fixture generation script

### Deferred

- Implementing `astar_diagnostics.py` and `astar_lanes.py` stubs — the stubs remain 1-line placeholders
- Stage 4 smoothing, via placement, trace width assignment, length matching — these are separate sub-steps in `_run_stage4` outside the A* core
- Cross-stage DRC gates — DRC validates invariants within a single stage only
- Parametric A* search (varying heuristics, tie-breaking strategies)

### Out of scope

- Changing the Stage 4 interface — `_run_stage5` continues to consume `Stage4Output` (the existing `PathfindingResult`)
- Performance optimization beyond the <5% overhead bound
- Changing search algorithm behavior (A*, Theta*, Lazy Theta* work identically before and after)
- Adding new routing capabilities or heuristics

---

## Stage 4 Sub-Step DAG

The monolithic `_run_stage4` decomposes into 5 sequential sub-steps forming a linear DAG:

```
GridPrep ──> NetPrep ──> Route ──> ResultAggregate
```

Additionally, 2 existing extracted modules are wrapped as Stage subclasses for consistency:

```
AstarCoreStage: delegates to astar_core.py search algorithms
AstarGridStage: delegates to astar_grid.py grid helpers
```

| Step | Pipeline Lines | Module | Description |
|------|---------------|--------|-------------|
| 4.0 | 452-460 | `astar_pathfinding.py` (extracted) | Build per-layer occupancy grids from routing space |
| 4.1 | 470-478 | `astar_pathfinding.py` (extracted) | Extract pad centers, THT locations, classify nets, compute routing order |
| 4.2 | 484-496 | `astar_pathfinding.py` (extracted) | Route nets with A*/Theta*/Lazy Theta* and ripup/reroute |
| 4.3 | 500-510 | `astar_pathfinding.py` (extracted) | Compile `PathfindingResult` from per-net success/failure data |

Note: The actual A*/Theta*/3D search algorithms live in the already-extracted `astar_core.py` module and are called by the route micro-stage. Grid helpers (pad extraction, THT locations, marking/unmarking) live in the already-extracted `astar_grid.py` module and are called by the net prep and route micro-stages.

---

## Key Technical Decisions

**K1. BoardState extension via frozen dataclass field addition (not subclass).** Same pattern as Stage 2 and Stage 3. `BoardState` gains 3 new `Optional[...] = None` fields for Stage 4 intermediate state. Non-breaking for existing consumers.

**K2. Single-pass deduplication + extraction.** Rather than wire the monolith to delegate incrementally, the deduplication happens during extraction: each extracted function is removed from `astar_pathfinding.py` and imported from its destination module. After all units complete, the monolith contains only forward-looking imports and the entry-point function — a true strangler facade.

**K3. Extraction order: forward (grid → prep → route → aggregate).** The DAG is linear. Extracting data producers first means each extraction can be verified by running real upstream micro-stages against monolith intermediate state.

**K4. Stage4Orchestrator chains micro-stages + backward-compat adapter.** Same pattern as `Stage2Orchestrator` and `Stage3Orchestrator`. `_run_stage4` is refactored to instantiate the orchestrator, run it, then assemble `Stage4Output` (the existing `PathfindingResult`) from the final `BoardState`. Downstream `_run_stage5` operates unchanged.

**K5. Golden fixture format: JSON with custom encoders.** Same format as Stage 2/3 golden fixtures. Custom JSON encoders handle numpy arrays, shapely geometries, and networkx graphs. `--regenerate` flag gates intentional algorithm changes.

**K6. Per-stage DRC validators: standalone functions with existing `@register_validator` decorator.** New validators register under `"GridPrep"`, `"NetPrep"`, `"Route"`, `"ResultAggregate"`.

**K7. Coverage gate: per-module `pytest-cov` with `--cov-fail-under=90`.** Measured independently for each new micro-stage module. Existing coverage for `astar_core.py` and `astar_grid.py` is preserved.

**K8. Performance regression bound: <5% wall-clock overhead on canonical boards vs monolith.** The extraction adds one function call per micro-stage + one `dataclasses.replace` per stage. Stage 4 wall time is dominated by A* search (seconds-engine minutes), not orchestration overhead.

---

## Implementation Units

### U1. BoardState Extension + Existing Module Cleanup

**Goal:** Add 3 Stage 4 fields to `BoardState`. Register 4 validator names. Remove duplicate copies of already-extracted functions from the monolith, replacing them with imports from `astar_core.py` and `astar_grid.py`.

**Requirements:** Stage 4 fields on BoardState (R1). Deduplicated monolith (R2).

**Files:**
- `packages/temper-placer/src/temper_placer/deterministic/state.py` — add 3 Optional fields
- `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py` — register 4 stage names
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — remove duplicate functions, replace with imports
- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` — verify no missing exports
- `packages/temper-placer/src/temper_placer/router_v6/astar_grid.py` — verify no missing exports

**Approach:**
- Add to `BoardState`: `parsed_grids: Optional[dict[str, Any]] = None`, `net_route_order: Optional[list[str]] = None`, `per_net_results: Optional[dict[str, Any]] = None`
- In `astar_pathfinding.py`, replace all functions that have duplicates in `astar_core.py`/`astar_grid.py` with `from temper_placer.router_v6.astar_core import ...` and `from temper_placer.router_v6.astar_grid import ...`
- Verify no circular imports (the modules are leaf-level with no cross-dependencies)
- Register `"GridPrep"`, `"NetPrep"`, `"Route"`, `"ResultAggregate"` in `stage_validators.py`

**Patterns to follow:** U0/U1 in Stage 3 plan (`deterministic/state.py` field additions, `stage_validators.py` registrations).

**Test scenarios:**
- Existing `BoardState` construction tests pass with 3 new `None` fields
- `dataclasses.replace(state, parsed_grids={...})` produces a valid `BoardState`
- All existing A* tests pass after deduplication (imports resolve correctly)
- `astar_core.py` and `astar_grid.py` maintain >=90% coverage

**Verification:** `pytest packages/temper-placer/tests/router_v6/test_astar_pathfinding.py` passes. `git diff --stat` shows monolith line count reduced.

---

### U2. GridPrepStage

**Goal:** Extract the per-layer occupancy grid construction (`_run_stage4` lines 452-460) into a `Stage` subclass. This builds the `F.Cu` and `B.Cu` occupancy grids from `Stage2Output.routing_spaces`, inflating traces by trace_width/2 + clearance.

**Requirements:** GridPrep micro-stage (R3).

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — extract grid-building logic, leave facade import
- `packages/temper-placer/src/temper_placer/router_v6/grid_prep_stage.py` — new file

**Stage class:** `GridPrepStage`
- `name = "GridPrep"`
- `run(state)`: reads `state._parsed_pcb` for design_rules, `state._parsed_pcb.routing_spaces` (from Stage 2); calls existing occupancy grid construction with inflation; returns `replace(state, parsed_grids=...)`

**Validators** (via `@register_validator("GridPrep")`):
- Grids exist for `F.Cu` and `B.Cu`
- Grid dimensions match routing space dimensions
- Inflation radius > 0 (trace_width/2 + clearance > 0)

**Golden fixture:** `tests/fixtures/stage4_goldens/{board}/parsed_grids.json`

**PBT:** For any routing space, occupancy grid dimensions match. Grid cells outside routing space are blocked. Cell size matches design_rules grid resolution.

**Coverage target:** `temper_placer.router_v6.grid_prep_stage` >= 90% line coverage

**Extraction order:** 1st (no upstream Stage 4 dependency; reads Stage 2/3 fields)

---

### U3. NetPrepStage

**Goal:** Extract pad center extraction, THT location building, net classification, and routing order computation (`_run_stage4` lines 470-478 and `_compute_net_order`) into a `Stage` subclass.

**Requirements:** NetPrep micro-stage (R4).

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — extract `_compute_net_order`, pad extraction, THT location building
- `packages/temper-placer/src/temper_placer/router_v6/net_prep_stage.py` — new file

**Stage class:** `NetPrepStage`
- `name = "NetPrep"`
- `run(state)`: reads `state._parsed_pcb`, `state.parsed_grids` (from U2); calls existing pad extraction functions (from `astar_grid.py`), calls `_compute_net_order()`; returns `replace(state, net_route_order=..., pad_data=...)`

**Validators** (via `@register_validator("NetPrep")`):
- Every net in `net_route_order` exists in the PCB
- Pad data extracted for every net with at least one terminal
- THT locations identified for all through-hole components
- Net ordering is deterministic (same input → same order)

**Golden fixture:** `tests/fixtures/stage4_goldens/{board}/net_order.json`

**PBT:** Net ordering respects priority (power nets first). Identical nets produce identical ordering across runs of the same board. Every net has at least one pad center when it has terminals.

**Coverage target:** `temper_placer.router_v6.net_prep_stage` >= 90% line coverage

**Extraction order:** 2nd (depends on parsed_grids)

---

### U4. RouteStage

**Goal:** Extract the core A*/Theta*/Lazy Theta* routing loop with ripup/reroute (`_astar_route_with_ripup`, `_astar_route_multilayer`, `_astar_route`, and the main routing loop from `run_astar_pathfinding`) into a `Stage` subclass. This is the largest extraction — the actual net-by-net A* pathfinding.

**Requirements:** Route micro-stage (R5).

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — extract `_astar_route_with_ripup`, `_astar_route_multilayer`, `_astar_route`, routing loop
- `packages/temper-placer/src/temper_placer/router_v6/route_stage.py` — new file

**Stage class:** `RouteStage`
- `name = "Route"`
- `run(state)`: reads `state._parsed_pcb`, `state.net_route_order`, `state.parsed_grids`, `state.pad_data` (from U3); iterates nets in route order, for each net: calls A*/Theta*/Lazy Theta* search, tracks path, on failure records blockers and tries ripup; stores per-net results; returns `replace(state, per_net_results=..., route_failures=...)`

**Validators** (via `@register_validator("Route")`):
- Routed paths respect occupancy grid (no collisions with existing routes or obstacles)
- Path endpoints match pad center positions
- No path exceeds board boundaries
- Failed nets have at least one reason recorded (failure report)
- `per_net_results` count == `net_route_order` count

**Golden fixture:** `tests/fixtures/stage4_goldens/{board}/routed_paths.json`

**PBT:** For any net with a clear straight-line path, A* finds a route. For any board, total routed nets + failed nets == total routable nets. Ripup never loops infinitely (bounded by `max_ripup_depth`). Path length monotonically decreases with higher iteration limits.

**Coverage target:** `temper_placer.router_v6.route_stage` >= 90% line coverage

**Extraction order:** 3rd (depends on net_route_order and parsed_grids)

---

### U5. ResultAggregateStage

**Goal:** Extract `PathfindingResult` assembly (currently the return value construction at the end of `run_astar_pathfinding`) into a `Stage` subclass. Compiles per-net results into `PathfindingResult` with success/failure counts, failure reports, per-path latency tracking.

**Requirements:** ResultAggregate micro-stage (R6). Backward-compatible `PathfindingResult` output (R7).

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — extract `PathfindingResult`, `RoutingFailureReport` dataclasses; extract result assembly logic
- `packages/temper-placer/src/temper_placer/router_v6/result_aggregate_stage.py` — new file

**Stage class:** `ResultAggregateStage`
- `name = "ResultAggregate"`
- `run(state)`: reads `state.per_net_results`, `state.route_failures`, `state._parsed_pcb`; counts successes/failures, compiles failure reports, computes completion rate; returns `replace(state, pathfinding_result=PathfindingResult(...))`

**Validators** (via `@register_validator("ResultAggregate")`):
- `success_count + failure_count == total_routable_nets`
- `completion_rate == success_count / total_nets` (when total_nets > 0)
- All failure reports reference nets that failed to route
- `PathfindingResult.routed_paths` only contains success entries

**Golden fixture:** `tests/fixtures/stage4_goldens/{board}/pathfinding_result.json`

**PBT:** Empty net list produces success_count=0, failure_count=0, completion_rate=0. For any set of per-net results, sum of success+failure equals total. `per_path_latency_ms` values are non-negative.

**Coverage target:** `temper_placer.router_v6.result_aggregate_stage` >= 90% line coverage

**Extraction order:** 4th (depends on per_net_results)

---

### U6. Stage4Orchestrator + Pipeline Adapter

**Goal:** Create `Stage4Orchestrator` chaining the 5 micro-stages (U2-U5) in dependency order. Refactor `_run_stage4` to use the orchestrator and assemble `PathfindingResult` from the final `BoardState`. `Stage4Output = PathfindingResult` — no new output type.

**Requirements:** Orchestrator chaining (R8). Pipeline integration (R9). Backward compatibility (R10).

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/stage4_orchestrator.py` — new file
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — refactor `_run_stage4`

**Stage4Orchestrator:**
```python
class Stage4Orchestrator:
    _stages: list[Stage]
    _stage4_fence: DRCFence  # per-stage DRC verification

    def __init__(self, verbose: bool = False, profiler=None, fence=None):
        self._stages = [
            GridPrepStage(),
            NetPrepStage(),
            RouteStage(),
            ResultAggregateStage(),
        ]

    def run(self, state: BoardState) -> BoardState:
        for stage in self._stages:
            state = stage.run(state)
            drc_failures = run_validators(stage.name, state)
            if self._stage4_fence:
                self._stage4_fence.check(stage.name, drc_failures)
        return state

    @staticmethod
    def assemble_pathfinding_result(state: BoardState) -> PathfindingResult:
        return state.pathfinding_result
```

**Pipeline integration** (`_run_stage4`):
```python
def _run_stage4(self, pcb, stage3, channel_mapping) -> Stage4Output:
    state = BoardState(...)  # seed with upstream fields
    state = replace(state, _parsed_pcb=pcb, channel_mapping=channel_mapping)
    orchestrator = Stage4Orchestrator(verbose=self.verbose, profiler=self.profiler, fence=self.fence)
    state = orchestrator.run(state)
    return orchestrator.assemble_pathfinding_result(state)
```

**Patterns to follow:** `Stage2Orchestrator` in `router_v6/stage2_orchestrator.py`, `Stage3Orchestrator` pattern in `router_v6/topology_solver.py`.

**Test scenarios:**
- Orchestrator with all stages produces same output as monolith `run_astar_pathfinding` on 4 canonical boards
- Orchestrator with only GridPrepStage produces partial state
- Per-stage DRC failures cause appropriate fence action
- Profiler instrumentation wraps each stage execution

**Verification:** Existing `test_astar_pathfinding.py` tests pass with orchestrator. All pipeline integration tests pass.

**Extraction order:** 5th (depends on U2-U5 completion)

---

### U7. Golden Fixtures + Parity Tests

**Goal:** Generate golden fixtures for each of the 4 new micro-stages (U2-U5) on 4 canonical boards. Create `generate_stage4_goldens.py`, `test_stage4_golden_parity.py`, and `test_stage4_monolith_parity.py`.

**Requirements:** Golden fixture parity (R11). Monolith parity (R12).

**Files:**
- `tests/fixtures/stage4_goldens/` — 4 board dirs × 4 micro-stage fixtures = 16 JSON files
- `packages/temper-placer/tests/router_v6/generate_stage4_goldens.py` — new file
- `packages/temper-placer/tests/router_v6/test_stage4_golden_parity.py` — new file
- `packages/temper-placer/tests/router_v6/test_stage4_monolith_parity.py` — new file

**Patterns to follow:** `generate_stage2_goldens.py`, `test_stage2_golden_parity.py`, `test_stage2_monolith_parity.py`.

**Test scenarios:**
- `test_stage4_monolith_parity`: Run old `run_astar_pathfinding` vs orchestrated stages — `PathfindingResult` fields match exactly. Same boards, same inputs.
- `test_stage4_golden_parity`: Run orchestrated stages, compare each micro-stage output against committed fixture. `--regenerate` updates fixtures when algorithm changes are intentional.
- Both tests on all 4 canonical boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra)
- Performance regression check: orchestrator <5% wall-clock overhead vs monolith

**Verification:** `python tests/router_v6/generate_stage4_goldens.py` produces deterministic fixtures. `pytest tests/router_v6/test_stage4_golden_parity.py` passes. `pytest tests/router_v6/test_stage4_monolith_parity.py` passes.

**Extraction order:** 6th (depends on U6)

---

### U8. PBT Suites + DRC Gates + Coverage Gates

**Goal:** Add hypothesis-based property-based tests for each micro-stage (U2-U5). Wire DRC validators into orchestrator. Set per-module coverage gates.

**Requirements:** PBT coverage (R13). DRC gates (R14). Coverage gates (R15).

**Files:**
- `packages/temper-placer/tests/router_v6/test_grid_prep_pbt.py` — new file
- `packages/temper-placer/tests/router_v6/test_net_prep_pbt.py` — new file
- `packages/temper-placer/tests/router_v6/test_route_pbt.py` — new file
- `packages/temper-placer/tests/router_v6/test_result_aggregate_pbt.py` — new file
- `packages/temper-placer/pyproject.toml` — add coverage gates for new modules

**Patterns to follow:** PBT suites from Stage 2 (`test_channel_skeleton_pbt.py`, `test_obstacle_map_pbt.py`, etc.), each with `@settings(max_examples=100, deadline=30000)`.

**PBT scenarios (per micro-stage):**
- **GridPrep:** For any routing space with obstacles, grid cells covering obstacles are blocked. Grid dimensions match routing space dimensions. Cell size is consistent across layers.
- **NetPrep:** Net ordering is invariant across runs on same board. Power nets (GND, VCC, PGND) sort before signal nets. Every net with N pins has N pad centers.
- **Route:** For any net with Manhattan-distance-connected pads, A* finds a route (no unavoidable obstacles). Ripup depth limit prevents infinite loop. Path endpoints match pad positions within tolerance.
- **ResultAggregate:** Success+failure == total nets. Completion rate is 0-1. Latency values are non-negative. Failure reports reference only net names that failed.

**Coverage targets:**
- `temper_placer.router_v6.grid_prep_stage` >= 90%
- `temper_placer.router_v6.net_prep_stage` >= 90%
- `temper_placer.router_v6.route_stage` >= 90%
- `temper_placer.router_v6.result_aggregate_stage` >= 90%

**Verification:** `pytest tests/router_v6/test_*_pbt.py --hypothesis-profile=ci` passes. Coverage gates report >=90%.

**Extraction order:** 7th (depends on U2-U5 for module existence)

---

## Dependencies

| Path | Role |
|------|------|
| `packages/temper-placer/src/temper_placer/deterministic/state.py` | `BoardState` dataclass — add 3 fields (U1) |
| `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` | `Stage(ABC)` protocol — micro-stages implement this |
| `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py` | `@register_validator`, `StageDRCFailure`, `VALIDATOR_REGISTRY` |
| `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` | The monolith — deduplicate (U1), then strip to facade |
| `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` | Already-extracted search algorithms — wire imports (U1) |
| `packages/temper-placer/src/temper_placer/router_v6/astar_grid.py` | Already-extracted grid helpers — wire imports (U1) |
| `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` | `_run_stage4` — use orchestrator (U6) |
| `packages/temper-placer/src/temper_placer/router_v6/test_boards.py` | 4 canonical boards for fixtures |
| `packages/temper-placer/src/temper_placer/pipeline/state.py` | Pipeline-level `BoardState` (re-exports from deterministic/state.py) |
| `packages/temper-placer/src/temper_placer/profiling/__init__.py` | `PipelineProfiler` for orchestrator instrumentation |

## Assumptions

1. `BoardState` frozen dataclass extension with Optional fields is non-breaking (proven by Stage 2/3).
2. Occupancy grid construction logic (`_run_stage4` lines 452-460) is self-contained with no hidden side effects.
3. Net ordering via `_compute_net_order` does not mutate global state.
4. `PathfindingResult` dataclass can be moved from `astar_pathfinding.py` to `result_aggregate_stage.py` without breaking 18+ downstream importers (all 18 test files reference `PathfindingResult` from `astar_pathfinding` — a re-export alias manages compatibility).
5. The 4 canonical test boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) provide representative coverage.
6. Per-stage DRC validators have no false positives on valid intermediate `BoardState`.
7. A* pathfinding is deterministic with identical inputs (same PCB, same channel mapping, same random seed) — proven by existing test behavior.
8. The <5% performance overhead bound is achievable (proven by Stage 2/3).
9. `astar_diagnostics.py` and `astar_lanes.py` stubs remain 1-line files — no functional change.

## Open Questions

- `astar_diagnostics.py` was planned for rip-up metrics export. Should it be deleted instead of left as a 1-line stub? **Deferred to implementation**: if no code references it, delete it; otherwise leave the stub.
- The 18+ downstream test files importing `PathfindingResult` from `astar_pathfinding` will need import updates. A re-export in the monolith's `__init__.py` or a compatibility alias can bridge. **Deferred to implementation**: the exact mechanism depends on how `run_astar_pathfinding` is exposed.

## Success Criteria

- **SC1:** `astar_pathfinding.py` reduced from 1795 lines to <500 lines (facade with imports + entry point)
- **SC2:** 5 new `Stage` subclasses exist and pass their individual test suites
- **SC3:** `Stage4Orchestrator` produces identical `PathfindingResult` to monolith on all 4 canonical boards
- **SC4:** Monolith parity test passes (orchestrator output == monolith output)
- **SC5:** Golden fixture parity test passes (micro-stage output matches committed fixtures)
- **SC6:** PBT suites pass with >=100 examples each
- **SC7:** Per-module coverage >=90% for all new micro-stage modules
- **SC8:** Pipeline integration tests pass (end-to-end routing via `RouterV6Pipeline`)

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Deduplication breaks existing A* tests | Medium | High | Run `test_astar_pathfinding.py` after each function removal — fail fast, revert the single removal |
| Orchestrator introduces >5% overhead | Low | Medium | Profile wall-clock time on LibreSolar_BMS (200 nets, 4L) — if >5%, investigate `dataclasses.replace` cost |
| Golden fixture tests flake on non-deterministic routing | Low | High | Verify A* determinism: same board + same seed → same output. If non-deterministic, use equality-with-tolerance |
| PBT suites take too long to run (100 examples × 4 stages = 400 tests) | Medium | Low | Set `deadline=None` for Route PBT (seconds per example); keep `deadline=30000` for faster stages |
| 18 downstream test files break from dataclass relocation | High | High | Re-export `PathfindingResult` from `astar_pathfinding.__init__` during transition; update imports over time |

## Implementation Notes

**Execution order:** U1 → U2 → U3 → U4 → U5 → U6 → U7 → U8

Each unit depends on previous. U1 (BoardState + dedup) must complete first because all micro-stages depend on the clean module structure. U7 (fixtures) needs the orchestrator from U6. U8 (PBT + gates) needs the micro-stage modules from U2-U5.

**Monolith line count trajectory:**
- Start: 1795 lines (all duplicate + unique)
- After U1 (dedup): ~500 lines (facade + entry point + unique functions)
- After U2-U5 (extractions): ~100 lines (facade with imports)
- After U6 (orchestrator adapter): `run_astar_pathfinding` delegates to orchestrator, monolith becomes true facade

**Import compatibility:** All existing consumers importing from `temper_placer.router_v6.astar_pathfinding` continue to work throughout the transition via re-exports. The monolith becomes a pure compatibility facade.

**Stage comparison:**

| Dimension | Stage 2 (Channel Analysis) | Stage 3 (SAT) | Stage 4 (A*) |
|-----------|---------------------------|---------------|--------------|
| Micro-stages | 8 | 5 | 5 |
| Monolith lines | ~85 (in pipeline.py) | ~55 (in pipeline.py) | 1795 (astar_pathfinding.py) |
| Pre-extracted modules | No | No | Yes (astar_core.py, astar_grid.py) |
| Golden fixtures | 32 (8×4) | 20 (5×4) | 16 (4×4) |
| PBT suites | 8 | 5 | 4 |
| DRC validators | 8 | 5 | 4 |
| Coverage modules | 8 | 5 | 4 |
