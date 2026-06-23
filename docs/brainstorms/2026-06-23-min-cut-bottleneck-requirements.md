---
date: 2026-06-23
topic: min-cut-bottleneck-detection
focus: Replace "10 nets stuck" with "Q1@22.2,15.0 and D1@30.5,25.0 create 4mm gap that needs 6mm" by computing max-flow min-cut on a capacitated grid graph
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (#6)
status: active
actors: Router V6 developer, closure test, board designer
---

# Requirements: Min-Cut Bottleneck Detection for Routing Failures

## Problem Frame

The closure test reports `routing_completion_pct = 0.5%` and emits a single line per stuck net. The board designer cannot act on "10 nets failed" — they need to know which two HV components are too close, by how many mm, and the exact gap geometry causing the failure. Today's `NetRoutingReport` (`router_v6/diagnostics.py:85-162`) carries a `failure_point: tuple[float, float]` and a list of `BlockingObstacle` entries, but neither is computed from a global routing-capacity model: obstacles are local to the A* search, not derived from the board's residual graph. The result is a diagnosis that points at a cell, not a cause.

Max-flow min-cut (Ford-Fulkerson, Edmonds-Karp) gives an exact answer to "what's the smallest set of edges whose removal disconnects source from sink?" Translating the answer: the s-t min-cut partition of the capacitated routing graph identifies the exact bottleneck geometry — the HV component at one end of the cut, the LV cluster at the other, and the minimum required creepage. This is the same technique used in VLSI global routing (e.g., the TimberWolf congestion map, the FastRoute rip-up-and-reroute feedback loop).

## Actors

- **A1. Board designer** — opens the closure test report, sees a specific component-pair bottleneck with mm-scale geometry, and knows exactly which component to move or which zone to widen
- **A2. Router V6 developer** — implements the new module, wires its output into `NetRoutingReport`, and verifies the closure test parses the new fields without regression
- **A3. Closure test** — produces JSON diagnostics consumable by `docs/ideation/2026-06-23-...md` follow-up initiatives (placement-routing feedback loop)

## Key Decisions

- **K1. Capacitated graph derived from existing `ClearanceGrid`.** Edge capacity = max(0, free_capacity − (pads + traces + creepage_exclusion)). The grid already encodes per-cell blocking (`clearance_grid.py:113-150`); the new module consumes the same grid plus the `NetClassRules` lookup to weight capacity drops near HV pads. No second grid is built; we read the existing one and assign capacities to a directed graph.
- **K2. Per-failed-net min-cut, not board-wide.** Compute s-t min-cut only for nets where `NetRoutingReport.status` ∈ {`FAILED`, `BLOCKED`, `PARTIAL`}. For partial nets, treat the unrouted endpoint as sink. Board-wide min-cut is O(V·E) per net pair and offers no actionable signal because it does not identify which net.
- **K3. Translate the cut into component references, not raw cells.** After computing the source-side and sink-side vertex sets from the min-cut partition, intersect each set with the `pad_centers` index (component_ref → pad position). The bottleneck is the pair of components (or component and edge) whose pads lie on opposite sides of the cut and whose perpendicular distance through the cut < `required_creepage_mm` from `NetClassRules`.
- **K4. New `BottleneckGeometry` dataclass on `NetRoutingReport`.** Extend `diagnostics.py` with a frozen `BottleneckGeometry` dataclass carrying `component_pair: tuple[str | tuple[float, float], str | tuple[float, float]]` (each side is a component ref or an `(x, y)` point for board edges / keepout regions), `pair_kind: Literal['component_component', 'component_edge', 'component_keepout']` to discriminate the three cases K3 anticipates, `positions_mm: tuple[tuple[float, float], tuple[float, float]]`, `current_gap_mm: float`, `required_gap_mm: float`, `cut_size: int`, `cut_cells: list[tuple[int, int, int]]`, and `bottleneck_status: str`. The existing `failure_point` and `blocking_obstacles` remain for backward compatibility; the new field is additive.
- **K5. Use `networkx.minimum_cut` (Edmonds-Karp) and `shapely.shortest_line` for geometry.** Both are already in `pyproject.toml` (`networkx>=3.0`, `shapely>=2.1.2`). No new dependencies. The existing `partition_netlist_min_cut` (`core/community.py:83-124`) shows the codebase pattern for `networkx`-based partitioning.
- **K6. Compute offline, not in the routing hot path.** The min-cut is a post-mortem diagnostic: run after `SequentialRoutingStage` fails, not during the per-net A* loop. The closure test budget absorbs the additional cost; the per-net routing budget does not.

## Requirements

### R0. Rename / Relocate
Status: required

The existing `router_v6/bottleneck_analysis.py` defines `BottleneckAnalysis` (capacity/demand rollup). Move the new geometry dataclass and `analyze_bottleneck` function to `router_v6/bottleneck_geometry.py` and import the existing `BottleneckAnalysis` as the upstream signal. This keeps the existing capacity/demand `BottleneckAnalysis` and the new geometry payload `BottleneckGeometry` from sharing a filename.

### R1. New Module: `temper_placer/router_v6/bottleneck_geometry.py`
Status: required

Implement a single module that:
- Takes a `ClearanceGrid` (from `state.grid`), the failing net's pin positions, the `NetClassRules` registry, and the full `BoardState.netlist` (for component_ref → pad mapping)
- Builds a directed capacitated graph: one node per `(layer, row, col)` triple that is not hard-blocked, one edge per 4-neighbor adjacency weighted by residual capacity (cell capacity − existing usage − creepage exclusion)
- Runs `networkx.minimum_cut` from source pin cell to sink pin cell, returning the partition and the cut-edge list
- Translates the partition to a `BottleneckGeometry` per K3

The module exports a single function `analyze_bottleneck(grid, net, state, report: NetRoutingReport) -> BottleneckGeometry | None`. If `report.failure_reason` is set and not in {`FailureReason.CHANNEL_CAPACITY`, `FailureReason.CLEARANCE`, `None`} (e.g., `TOPOLOGY`, `AREA_ESTIMATE_EXCEEDED`), return `None` without invoking networkx.

### R2. `BottleneckGeometry` Dataclass
Status: required

In `router_v6/diagnostics.py`, add:

```python
@dataclass(frozen=True)
class BottleneckGeometry:
    component_pair: tuple[str | tuple[float, float], str | tuple[float, float]]
    pair_kind: Literal['component_component', 'component_edge', 'component_keepout']
    positions_mm: tuple[tuple[float, float], tuple[float, float]]
    current_gap_mm: float                # measured perpendicular distance
    required_gap_mm: float               # from NetClassRules safety clearance
    cut_size: int                        # raw min-cut value in capacity units
    cut_cells: list[tuple[int, int, int]]  # grid cells on the cut edge
    message: str                         # human-readable: "Q1 at (22.2, 15.0) and D1 at (30.5, 25.0) create 4mm gap that needs 6mm"; the formatter selects wording by pair_kind
    bottleneck_status: str               # 'ok' | 'aborted_timeout' | 'aborted_build_failure' | 'not_capacity_limited'
```

The `message` formatter handles three forms, selected by `pair_kind`:
- `component_component`: `"{a} at (x1, y1) and {b} at (x2, y2) create {gap}mm gap that needs {req}mm"` (e.g., Q1 and D1)
- `component_edge`: `"{a} at (x1, y1) and board edge at (x2, y2) create {gap}mm gap that needs {req}mm"` (e.g., Q1 to board edge)
- `component_keepout`: `"{a} at (x1, y1) and keepout region at (x2, y2) create {gap}mm gap that needs {req}mm"` (e.g., Q1 to mounting hole)

Add `bottleneck: BottleneckGeometry | None = None` to `NetRoutingReport`. Update `to_dict()` to serialize it. Backward compatible: existing `to_dict()` consumers see the new key but old fields unchanged.

### R3. Wire into `SequentialRoutingStage`
Status: required

After the main routing loop in `sequential_routing.py`, for every net in `net_order` whose `NetRoutingReport.status` ∈ {`FAILED`, `BLOCKED`, `PARTIAL`}:

- Call `analyze_bottleneck(state.grid, net_def, state)`
- Attach the returned `BottleneckGeometry` to the net's `NetRoutingReport`
- Log the `message` field at WARNING level (closure test already captures warnings into its JSON output)

The new call must not raise; on any exception (graph build failure, `networkx` timeout, missing component ref) it must log a debug message and leave `bottleneck = None`. The routing pass itself remains the source of truth for pass/fail.

### R4. Capacity Model: How Edge Weights Are Computed
Status: required

Define `_compute_cell_capacity(cell, layer, grid, net_class_rules) -> int`:
- Start with `max_capacity = 4` (max concurrent traces per cell, accounting for the 4 cardinal neighbors)
- Subtract 1 for each existing trace passing through the cell on this layer
- Subtract 1 for each adjacent creepage exclusion (HV pad within `required_creepage_mm` of the cell center)
- Clamp to `[0, 4]`
- If a cell is hard-blocked (obstacle or different-net pad), it gets no node in the graph

The creepage exclusion lookup reuses the per-net-class clearance computation already in `clearance_grid.py:626-673` (`_get_clearance_for_net`). The new module imports this and applies it to HV-net cells.

**Multi-net-class rule (resolves Open Question [Affects R4]).** A cell is excluded from the graph (no node) if any of:
1. it is a pad of a different net,
2. it is a hard obstacle, or
3. it lies within `required_creepage_mm` of a pad whose `safety_category` is higher than the source/sink net's category.

For the 33% completion wall, source/sink are treated as LV; HV pad cells and their creepage halo are excluded.

### R5. Closure Test Output Integration
Status: required

The closure test at `packages/temper-placer/src/temper_placer/regression/closure_test.py` already ingests `NetRoutingReport.to_dict()`. After R2 lands, the closure test JSON gains `bottleneck` keys on failed nets. The `BottleneckGeometry.message` field is the human-readable summary surfaced in the test report's "Routing failures" section.

Add a new test `test_routing_bottleneck_reporting.py` that runs the closure test on a 2-net board where the second net is forced to fail (by moving its destination pad into the first net's creepage zone), and asserts the report contains a `BottleneckGeometry` with non-null `component_pair` and `current_gap_mm < required_gap_mm`.

### R6. Performance Budget
Status: required

The min-cut analysis adds post-routing work. Budget per failed net: ≤ 500ms on a 100×100mm board at 0.5mm grid resolution (20,000 cells). Total budget across all failed nets: ≤ 30s, well under the 180s closure test target. The `networkx.minimum_cut` call dominates; for the test grid, the source-sink connected component has ≤ 10,000 nodes, well within Edmonds-Karp's practical range.

If a net's analysis exceeds 500ms, the analysis is aborted and `bottleneck = None` is set with a debug log. The closure test must not regress from timeout pressure.

## Scope Boundaries

### Deferred for later

- **Real-time feedback to placement.** The ideation doc's #1-#5 initiatives (ghost-pad injection, channel-aware scoring, etc.) are upstream mitigations. The min-cut diagnostic surfaces the failure cause for human/automated re-placement; it does not itself trigger a placement retry. A future initiative may consume `BottleneckGeometry` to drive a re-placement loop.
- **Multi-net min-cut.** Computing a single min-cut that spans multiple failing nets (the "global congestion" view) is more expensive and less actionable than per-net analysis. Deferred.
- **Visualization of the cut.** Plotting the cut on the existing `export_visualization` PNG is a nice-to-have for debugging but not required for the closure test to report actionable diagnostics.
- **Replacing `BlockingObstacle` with `BottleneckGeometry`.** The existing field is local to the A* search; the new field is global. Both have value. Consolidation deferred.

### Outside this product's identity

- **Changing the A* router.** The router's per-cell blocking logic is unchanged. The capacitated graph is built alongside, not in place of, the existing `ClearanceGrid`.
- **Adding new failure categories.** `FailureReason.CHANNEL_CAPACITY` already exists (`diagnostics.py:27`); this work produces a richer payload for that category but does not add new enum values.
- **Modifying the closure test pass/fail logic.** The test still passes when routing completes; the new `bottleneck` field is informational.

## Success Criteria

- **SC1.** On the canonical Temper PCB closure test, ≥ 90% of nets with `status=FAILED` include a non-null `BottleneckGeometry` whose `message` names two specific components and reports `current_gap_mm < required_gap_mm`. The remaining ≤ 10% are nets whose analysis was aborted per R3 / R6 (graph-build failure or 500ms budget exceeded); these still appear in the JSON with `bottleneck: null` and a `bottleneck_status` enum (`ok` | `aborted_timeout` | `aborted_build_failure` | `not_capacity_limited`).
- **SC2.** The example message from the ideation doc — "Q1 at (22.2, 15.0) and D1 at (30.5, 25.0) create a 4mm gap that needs 6mm" — appears verbatim or with component-specific substitution in the closure test output for the Temper PCB
- **SC3.** A 2-net reproduction board (R5) produces a deterministic `BottleneckGeometry` with identical output across 3 reruns at the same seed
- **SC4.** The closure test completes in ≤ 210s on the Temper PCB (current: 180s, +30s budget for R6)
- **SC5.** All existing tests in `tests/router_v6/` and `tests/regression/test_closure.py` continue to pass; `to_dict()` output for the existing fields is byte-identical for nets where `bottleneck = None`
- **SC6.** A new test asserts that for a 3×3 grid with one interior cell reduced to capacity 1 (all neighbors at capacity 4), the min-cut between opposite corners equals 1, and the bottleneck cell is correctly identified as the unique cell on the cut whose capacity equals 1.

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` — `ClearanceGrid` (consumed; not modified), `_get_clearance_for_net` (reused for creepage computation)
- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` — wire point for post-routing analysis call
- `packages/temper-placer/src/temper_placer/router_v6/diagnostics.py` — extend `NetRoutingReport` with new optional field
- `packages/temper-placer/src/temper_placer/routing/analysis.py` — read for the existing "Severe routing bottleneck detected" pattern at line 86; new module replaces this with precise geometry
- `packages/temper-placer/src/temper_placer/core/community.py` — reference pattern for `networkx`-based partitioning (`partition_netlist_min_cut:83-124`)
- `pyproject.toml` — `networkx>=3.0`, `shapely>=2.1.2` already declared
- `NetClassRules.safety_category` (from ideation doc past-learning #4) — SSOT for HV/LV classification feeding creepage lookups
- `NetRoutingReport` consumers (closure test, regressions) — additive change; no consumer refactor required

## Assumptions

1. **The board's `ClearanceGrid` is the only source of routing capacity truth.** The capacity model in R4 reads from the same grid the A* router uses; it does not build a parallel structure. Verified: the grid exposes `is_available` (`clearance_grid.py:179-201`) and per-cell net-id lookups sufficient for residual-capacity computation.
2. **`networkx.minimum_cut` on a 20,000-node graph completes in < 500ms.** Not verified in this project context; `networkx` documentation indicates Edmonds-Karp runs in O(V·E²) which for V=10K and E=40K is well under 1s. Will be confirmed in the new test (R5 / SC6).
3. **The board designer needs component-pair output, not raw cells.** A 4mm gap is actionable; "cells (44, 30), (44, 31), (45, 30), (45, 31) saturated" is not. The component-pair translation (K3) is the value-add. Verified against the ideation doc's example message format.
4. **A failed net's source-sink cells are recoverable post-routing.** After `SequentialRoutingStage` runs, the pin positions are still in `state.netlist` and the grid is still in `state.grid`. The min-cut module reads both, not intermediate A* state.
5. **The `BottleneckGeometry.message` field's format ("X at (a, b) and Y at (c, d) create E mm gap that needs R mm") is the right granularity.** Verified against the ideation doc's stated goal. The `component_pair` and `positions_mm` fields give downstream consumers structured access to the same data.

## Open Questions

### Resolve Before Planning

- **[Affects R1][Technical]** What cell size should the capacitated graph use? `clearance_grid.py:582` defaults to 0.5mm; the existing A* uses this. Building a finer graph (0.25mm) improves min-cut precision but doubles node count. Recommendation: reuse the existing grid's 0.5mm resolution for parity with the routing model.
- **[Affects R3][Technical]** Where in `SequentialRoutingStage` is the right wire point? The failure detection happens inside the `for net_idx, net_name in enumerate(net_order)` loop (`sequential_routing.py:1101+`). The min-cut analysis should run after the loop completes, iterating over `state.routing_reports` (or wherever failed nets are accumulated). Resolve during planning by reading the full loop body and existing report-aggregation pattern.

### Deferred to Planning

- **[Affects R1][Technical]** Is there a max node count above which `networkx.minimum_cut` should fall back to a sampled subgraph? For boards much larger than the Temper PCB (e.g., 200×200mm at 0.5mm = 160,000 cells), the algorithm may take seconds. Determine threshold empirically in SC6's test and add a fallback if needed.
- **[Affects R5][Process]** What is the minimal 2-net reproduction board for SC3? The closure test corpus includes 4 boards (Piantor, LibreSolar, RP2040, BitAxe); a 5th hand-crafted board may be needed. Determine during planning whether existing fixtures can be modified or a new fixture must be generated.
- **[Affects R6][Needs research]** How do `networkx` and `shapely` perform under JAX's tracing/compilation model? The codebase uses JAX extensively; `networkx` is pure Python and may not be JIT-compatible. Resolve by calling `analyze_bottleneck` outside any `jax.jit` boundary (it already runs in Python per R6's offline timing).
