---
type: feat
origin: docs/brainstorms/2026-06-23-min-cut-bottleneck-requirements.md
status: completed
date: 2026-06-23
---

# Plan: Min-Cut Bottleneck Detection for Routing Failures

## Problem Frame

The closure test reports `routing_completion_pct = 0.5%` and emits one line per stuck net, giving the board designer no actionable signal. The current `NetRoutingReport.failure_point` and `BlockingObstacle` entries are derived from the A* search, not from a global routing-capacity model, so they point at a cell, not a cause. Per-failed-net max-flow min-cut on a capacitated grid graph (built from the existing `ClearanceGrid` and `NetClassRules`) identifies the exact bottleneck geometry — the two HV components whose pads straddle the s-t partition, the current gap, and the required creepage — turning "10 nets failed" into "Q1 at (22.2, 15.0) and D1 at (30.5, 25.0) create 4mm gap that needs 6mm."

## Implementation Units

### U1. `BottleneckGeometry` Dataclass + Capacity Model Foundation

**Goal:** Establish the data contract and capacity function that downstream units consume.

**Requirements:** R0, R2, R4

**Files:**
- packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py (read for `BottleneckAnalysis` upstream signal only; not modified)
- packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py (new — module created here, populated further in U2)
- packages/temper-placer/src/temper_placer/router_v6/diagnostics.py
- packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py (read for `_get_clearance_for_net`; not modified)

**Approach:**
- R0: Note the rename boundary. Keep `router_v6/bottleneck_analysis.py` exporting the existing `BottleneckAnalysis` (capacity/demand rollup). Create `router_v6/bottleneck_geometry.py` for the new geometry payload (U1 establishes the module; U2 adds the higher-level graph construction and `analyze_bottleneck` on top). No file move needed since the new module has a distinct name.
- R2: In `diagnostics.py`, add a frozen `@dataclass(frozen=True) BottleneckGeometry` with the nine fields from the brainstorm (`component_pair`, `pair_kind`, `positions_mm`, `current_gap_mm`, `required_gap_mm`, `cut_size`, `cut_cells`, `message`, `bottleneck_status`). Add a `Literal` import and the `pair_kind` enum. Add `bottleneck: BottleneckGeometry | None = None` field to `NetRoutingReport`. Update `NetRoutingReport.to_dict()` to serialize the new field as a nested dict; when `None`, emit `"bottleneck": null` for forward compatibility.
- R4: Add `_compute_cell_capacity(cell: tuple[int,int,int], layer: int, grid: ClearanceGrid, net_class_rules: NetClassRules) -> int` to `bottleneck_geometry.py`. Capacity starts at 4, subtracts 1 per existing trace through the cell, subtracts 1 per adjacent creepage exclusion from any higher-safety-category pad. Clamp to `[0, 4]`. Hard-blocked cells are excluded from the graph (return value irrelevant — caller omits the node). Reuse `_get_clearance_for_net` from `clearance_grid.py:626-673` for the creepage lookup.

**Test scenarios:**
- `test_capacity_cell_baseline`: input cell with no traces and no nearby HV pads → expected capacity 4.
- `test_capacity_cell_creepage_excluded`: input cell 3mm from a category-HIGH pad on a category-LOW net → expected capacity 3.
- `test_capacity_cell_saturated`: input cell with 4 existing traces → expected capacity 0; net `is_hard_blocked == True` for caller.
- `test_diagnostics_to_dict_bottleneck_present`: build `NetRoutingReport` with `bottleneck=BottleneckGeometry(...)` → `to_dict()["bottleneck"]` is a dict with all 9 keys; existing fields byte-identical to pre-change output.
- `test_diagnostics_to_dict_bottleneck_absent`: build `NetRoutingReport` with `bottleneck=None` → `to_dict()["bottleneck"] is None`; all other fields unchanged.

**Verification:** `uv run pytest packages/temper-placer/tests/router_v6/test_diagnostics.py -k "bottleneck or capacity"`; `uv run python scripts/import_linter_gate.py`; visual diff of a sample `to_dict()` output to confirm backward compat.

### U2. `analyze_bottleneck` Module — Min-Cut Computation

**Goal:** Implement the offline min-cut analysis that turns a `ClearanceGrid` plus a failing net into a `BottleneckGeometry`.

**Requirements:** R1, K1, K3, K4, K5, K6

**Files:**
- packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py (module created in U1; add higher-level functions here)
- packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py (read)
- packages/temper-placer/src/temper_placer/core/community.py (read for `partition_netlist_min_cut` pattern)

**Approach:**
- On top of the existing `bottleneck_geometry.py` module (created in U1, which already exports `BottleneckGeometry` and `_compute_cell_capacity`), add:
  - `_build_capacitated_graph(grid, source_cells, sink_cells, net_class_rules, board_state) -> nx.DiGraph`
  - `_partition_to_components(partition, board_state) -> tuple[ComponentRef|Point, ComponentRef|Point]`
  - `_format_message(component_pair, positions_mm, current_gap_mm, required_gap_mm, pair_kind) -> str`
  - `analyze_bottleneck(grid, net, state, report) -> BottleneckGeometry | None` (public entry point)
- `_build_capacitated_graph`: nodes = `(layer, row, col)` triples with capacity > 0 and not hard-blocked; edges = 4-neighbor adjacencies on the same layer, weighted by `min(src_capacity, dst_capacity)`; use `netx.DiGraph.add_node` / `add_edge` with `capacity` attr. Exclude cells per R4's multi-net-class rule (different-net pad, hard obstacle, higher-safety-category creepage halo).
- `analyze_bottleneck` short-circuits and returns `None` when `report.failure_reason` is set and not in `{CHANNEL_CAPACITY, CLEARANCE, None}`.
- `analyze_bottleneck` calls `networkx.minimum_cut(graph, source, sink, capacity="capacity", flow_func=nx.algorithms.flow.edmonds_karp)` and unpacks `(cut_value, (reachable, non_reachable))`.
- `_partition_to_components` intersects `reachable` and `non_reachable` with the `pad_centers` index from `board_state.netlist`; classifies the pair as `component_component` / `component_edge` / `component_keepout` based on which side(s) hit non-component geometry (board bbox or keepout polygons).
- `shapely.shortest_line` computes `current_gap_mm` between the two positions; `required_gap_mm` comes from `net_class_rules.required_creepage_mm` for the higher-safety category on the cut.
- `_format_message` produces the three message forms from R2 per `pair_kind`.
- Define module-level `BOTTLENECK_TIMEOUT_S: float = 0.5` (seconds) and wrap the body in a `time.monotonic()` budget of that size (R6); on exceedance, return `BottleneckGeometry(..., bottleneck_status="aborted_timeout", cut_size=0, cut_cells=[])` and log DEBUG.

**Test scenarios:**
- `test_bottleneck_3x3_synthetic`: input 3×3 grid with center cell capacity=1, all others=4; source=top-left, sink=bottom-right → expected `cut_size == 1`, `cut_cells` contains the center cell, `current_gap_mm < required_gap_mm` (SC6).
- `test_bottleneck_skips_non_capacity_failure`: input report with `failure_reason=TOPOLOGY` → expected return `None`, no networkx call (assert via mock).
- `test_bottleneck_timeout_aborts`: input large grid exceeding `BOTTLENECK_TIMEOUT_S` → expected return has `bottleneck_status="aborted_timeout"`, `cut_size=0`.
- `test_bottleneck_build_failure_returns_aborted`: input grid where `_build_capacitated_graph` raises (force via fixture) → expected return has `bottleneck_status="aborted_build_failure"`, caller doesn't see exception.
- `test_bottleneck_pair_kind_component_keepout`: input source on a component pad, sink in a keepout polygon → expected `pair_kind == "component_keepout"`, message references keepout.
- `test_bottleneck_deterministic_seed`: rerun `analyze_bottleneck` 3× on identical inputs at fixed seed → expected `BottleneckGeometry` deeply equal (SC3).

**Verification:** `uv run pytest packages/temper-placer/tests/router_v6/test_bottleneck_geometry.py -v`; new tests cover SC3, SC6; existing `test_bottleneck_analysis.py` continues to pass.

### U3. Wire `analyze_bottleneck` into `SequentialRoutingStage`

**Goal:** Invoke min-cut analysis for every failed/blocked/partial net after the main routing loop completes; never let it crash the routing pass.

**Requirements:** R3

**Files:**
- packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py
- packages/temper-placer/src/temper_placer/router_v6/diagnostics.py (read for `NetRoutingReport.status` enum, `FailureReason`)

**Approach:**
- The exact wire point in `sequential_routing.py` is the `return replace(state, routes=frozenset(all_traces), vias=frozenset(all_vias))` at the end of `SequentialRoutingStage.run()` (line 1955). The two preceding loops — the main per-net A* loop `for net_idx, net_name in enumerate(net_order):` (lines 1101-1704) and the PHASE 2 retry loop (lines 1711-1953) — both commit their results to the local `all_traces` / `all_vias` lists, so by the time we reach the `return`, every net's per-pass outcome is final. The bottleneck analysis is invoked immediately before the `return`, iterating over failed/blocked/partial reports (there is no existing `state.routing_reports` accumulator; U3 introduces per-net report tracking and the post-mortem invocation in one pass).
- For each, call `analyze_bottleneck(state.grid, net_def, state, report)`. Wrap in a broad `try/except Exception` that logs at DEBUG with the net name and exception type, leaves `bottleneck = None`, and continues the iteration. The routing pass's existing pass/fail result is the source of truth — min-cut is post-mortem only.
- On non-`None` return, mutate the report in place: `report.bottleneck = result`.
- Emit `logger.warning("routing_bottleneck: %s", result.message)` so the closure test's WARNING capture surfaces the message in its JSON output.

**Test scenarios:**
- `test_sequential_routing_attaches_bottleneck`: input 2-net board where net 2 is forced to fail (sink pad inside net 1's creepage zone) → expected `report.bottleneck` is non-`None` after routing, `message` matches the "X at (a, b) and Y at (c, d) create E mm gap that needs R mm" format.
- `test_sequential_routing_bottleneck_isolated_from_exception`: input where `analyze_bottleneck` raises (mocked to throw) → expected routing pass still reports its original status, `report.bottleneck is None`, warning logged.
- `test_sequential_routing_skips_successful_nets`: input board where all nets route → expected `analyze_bottleneck` is never called (assert via mock call count).
- `test_sequential_routing_does_not_run_in_jit`: wrap the per-net post-loop body of `SequentialRoutingStage.run()` (the `analyze_bottleneck` invocation that U3 inserts immediately before the `return` at line 1955) in `jax.make_jaxpr` with concrete `grid` / `state` / `report` inputs, then assert the produced jaxpr does **not** contain any operation derived from `analyze_bottleneck` (i.e., the call is treated as an opaque Python call, not traced). This is a behavioral check — even if a future contributor wraps the routing stage in `jax.jit`, the bottleneck analysis remains a Python-level post-mortem and cannot be silently traced into the jaxpr. Addresses Open Question [Affects R6].

**Verification:** `uv run pytest packages/temper-placer/tests/router_v6/test_sequential_routing.py -k bottleneck`; `uv run pytest packages/temper-placer/tests/router_v6/` full suite to confirm no regression in other tests; manual closure-test run on a synthetic 2-net board to confirm the warning appears in the JSON.

### U4. Closure Test Integration + New Test + Performance Gate

**Goal:** Surface `BottleneckGeometry` in the closure test output and prove the success criteria end-to-end.

**Requirements:** R5, R6, SC1, SC2, SC3, SC4, SC5

**Files:**
- packages/temper-placer/src/temper_placer/regression/closure_test.py (verify the existing `to_dict()` consumer path; no code change needed if it already serializes nested dataclasses)
- packages/temper-placer/src/temper_placer/regression/reporter.py (verify the "Routing failures" section reads `bottleneck.message` when present)
- packages/temper-placer/tests/regression/test_routing_bottleneck_reporting.py (new)
- packages/temper-placer/tests/router_v6/test_closure_bottleneck_perf.py (new)

**Approach:**
- Audit `closure_test.py` and `reporter.py` for the path that ingests `NetRoutingReport.to_dict()` and surfaces routing-failure messages. Confirm (or add minimal code) so that the "Routing failures" section uses `report["bottleneck"]["message"]` when present, falling back to the existing summary when absent. This is the SC1/SC2 surface.
- New test `test_routing_bottleneck_reporting.py`: build a 2-net board fixture where the second net is forced to fail (sink pad inside net 1's creepage zone). Run the closure test pipeline end-to-end at a fixed seed. Assert: (a) the resulting JSON contains a `bottleneck` key on the failed net; (b) `component_pair` is non-null and names two specific components; (c) `current_gap_mm < required_gap_mm`; (d) the human-readable `message` contains the expected "create Xmm gap that needs Ymm" wording. Rerun 3× and assert byte-identical output (SC3).
- New test `test_closure_bottleneck_perf.py`: run the closure test on the Temper PCB and assert wall-clock ≤ 210s (SC4: 180s baseline + 30s budget for U2's per-failed-net work).
- Add a regression test asserting that for any `NetRoutingReport` with `bottleneck = None`, the `to_dict()` output for all other fields is byte-identical to the pre-change snapshot (SC5). Use a `pytest-regressions` snapshot or a hand-rolled golden fixture.

**Test scenarios:**
- `test_routing_bottleneck_reporting.py::test_two_net_creepage_failure_yields_bottleneck`: input 2-net forced-failure board at seed=42 → expected JSON has `bottleneck.message` non-null, `component_pair` names both pads, `current_gap_mm < required_gap_mm`.
- `test_routing_bottleneck_reporting.py::test_deterministic_across_reruns`: same fixture, seed=42, run 3× → expected all three JSON outputs byte-identical (SC3).
- `test_routing_bottleneck_reporting.py::test_message_format_matches_ideation`: assert `bottleneck.message` matches `r"^.+ at \([\d.]+, [\d.]+\) and .+ at \([\d.]+, [\d.]+\) create [\d.]+mm gap that needs [\d.]+mm$"` (SC2 template).
- `test_closure_bottleneck_perf.py::test_temper_pcb_within_budget`: full closure test on Temper PCB → expected `elapsed_s <= 210` (SC4).
- `test_closure_bottleneck_perf.py::test_large_node_count_falls_back`: input board > 200×200mm at 0.5mm → expected analysis either completes within `BOTTLENECK_TIMEOUT_S` (defined in `router_v6/bottleneck_geometry.py`) or sets `bottleneck_status="aborted_timeout"`, never raises (addresses Open Question [Deferred to Planning: max node count]).
- `test_net_routing_report_snapshot_no_bottleneck`: input `NetRoutingReport` with `bottleneck = None` → expected `to_dict()` matches the pre-change golden file exactly (SC5).

**Verification:** `uv run pytest packages/temper-placer/tests/regression/test_routing_bottleneck_reporting.py`; `uv run pytest packages/temper-placer/tests/regression/test_closure_bottleneck_perf.py`; run the closure test against the Temper PCB and inspect the "Routing failures" section of the JSON for `bottleneck.message` strings; compare `to_dict()` snapshot diffs across the full `tests/router_v6/` suite to confirm SC5 (no byte-level regression for existing fields).

## Risks & Dependencies

- **Performance risk (R6):** `networkx.minimum_cut` is pure Python and runs outside JAX's JIT (intentional per Open Question [Affects R6]). For boards with > 200×200mm at 0.5mm resolution (160K cells), the connected component can exceed Edmonds-Karp's practical range. Mitigated by the `BOTTLENECK_TIMEOUT_S` per-net budget (default 0.5s, defined in `router_v6/bottleneck_geometry.py`) and a `bottleneck_status="aborted_timeout"` path; deferred to follow-up is a sampled-subgraph fallback for very large boards. **Closure-test budget math:** the 210s perf budget in U4 assumes at most ~60 failed nets at the 0.5s timeout each (60 × 0.5s = 30s, well under the 30s allocated for bottleneck work on top of the 180s baseline). If a future corpus has more than 60 failed nets, the `test_temper_pcb_within_budget` test should not assert SC4 wall-clock and should instead verify only the per-net timeout behavior via `test_large_node_count_falls_back`.
- **Determinism risk (SC3):** `networkx` is deterministic for fixed inputs, but the grid cell iteration order in `_build_capacitated_graph` must be stable across Python versions. Iterate cells in `sorted()` order; pin `networkx` major version in `pyproject.toml` if drift appears.
- **Backward-compat risk (SC5):** `NetRoutingReport.to_dict()` is consumed by the closure test, regression fixtures, and downstream tooling. The new `bottleneck` field is additive, but a typo in serialization (e.g., wrong key name) breaks every existing fixture. Mitigated by U1's golden-snapshot test asserting byte-identical output when `bottleneck is None`.
- **Stale `bottleneck_analysis.py` collision risk (R0):** the existing `router_v6/bottleneck_analysis.py` defines a class also named `BottleneckAnalysis`. The new module is named `bottleneck_geometry.py` and its payload is `BottleneckGeometry`. No collision, but the names are similar — import linter will catch any accidental circular import. Verify with `scripts/import_linter_gate.py`.
- **Wire-point ambiguity (R3, Open Question):** the wire point in `sequential_routing.py` is now pinned: the post-mortem `analyze_bottleneck` invocation is inserted immediately before the `return replace(state, routes=frozenset(all_traces), vias=frozenset(all_vias))` at line 1955, after both the main per-net A* loop (lines 1101-1704) and the PHASE 2 retry loop (lines 1711-1953) have committed their results. U3 also introduces the per-net report accumulator that this iteration consumes.
- **Closure test fixture scope (R5, Open Question):** the existing corpus (Piantor, LibreSolar, RP2040, BitAxe) may or may not include a board with a single net failing due to creepage. If none does, U4's new test ships its own hand-crafted 2-net fixture; no corpus change required.

## Scope Boundaries

### Deferred to Follow-Up Work

- **Re-placement feedback loop.** The ideation doc's #1-#5 ideas (ghost-pad injection, channel-aware scoring) are upstream mitigations. A future initiative may consume `BottleneckGeometry` to drive automatic re-placement retries. This plan only emits the diagnostic.
- **Multi-net / board-wide min-cut.** Computing a single min-cut spanning all failing nets (the "global congestion" view) is more expensive and less actionable than per-net analysis. Deferred per brainstorm §"Deferred for later."
- **Cut visualization.** Plotting the cut on the existing `export_visualization` PNG is debugging-only and not required for actionable diagnostics.
- **Consolidating `BlockingObstacle` with `BottleneckGeometry`.** The two fields are complementary (local A* signal vs. global capacity signal). Both retained.
- **Sampled-subgraph fallback for > 200×200mm boards.** Empirically gated; current Temper PCB is well under the threshold. Add only if a future board triggers the timeout.
- **Firmware / C-side impact.** None. This work is Python/JAX only.

### Out of Scope

- Modifying the A* router, `ClearanceGrid`, or any other per-cell blocking logic. The capacitated graph is built alongside, not in place of, the existing structures.
- Adding new `FailureReason` enum values. `CHANNEL_CAPACITY` and `CLEARANCE` already exist; this work produces a richer payload for those categories only.
- Changing the closure test's pass/fail criteria. The test still passes when routing completes; `bottleneck` is informational.
- Touching any KiCad, DRC, or manufacturing-reporting code paths.
