---
date: 2026-06-22
topic: router-v6-performance-fixes
focus: Five quality-preserving runtime improvements targeting profiled hot paths
origin: docs/ideation/2026-06-22-router-v6-performance-bottleneck-ideation.md
status: active
actors: closure test, CI system
---

# Requirements: Router V6 Performance — 5 Quality-Preserving Fixes

## Problem Frame

Router V6 takes 180 seconds to route the Temper PCB (`temper_placed.kicad_pcb`, 23 nets). A cProfile sample across a full run identified four hot paths consuming 85% of runtime:

| Hot path | Function | Time | Calls | % |
|----------|----------|------|-------|---|
| Grid lookup | `is_free()` | 33s | 180M | 18% |
| A* heuristic | `_heuristic()` + `heappop` + `_astar_search` | 112s | 22.7M each | 63% |
| Channel skeleton | `extract_channel_skeleton` + `compute_channel_widths` | 23s | 5 layers | 13% |
| Geometry buffers | Shapely `buffer()` | 21s | 3.6M | 12% |

All five fixes preserve routing quality — they accelerate the same algorithm, same resolution, same paths. No routes should change. Completion rate and DRC count must not regress.

## Actors

- **A1. Closure test** — runs `ClosureTest(pcb_path).run()` end-to-end; the acceptance gate
- **A2. CI system** — runs `ci_closure_test.py`; must complete in under the CI timeout budget

## Requirements

### R1. Numpy Occupancy Grid
Status: required

Replace the per-cell `is_free(x_cell, y_cell)` Python function dispatch with a numpy boolean array lookup. The `OccupancyGrid` class (`occupancy_grid.py:28-49`) stores per-cell occupancy as a dict or nested list. Migrate to a 2D numpy boolean array where `grid[y, x]` returns occupancy status in O(1) without Python function call overhead.

- The grid resolution (0.1mm default at `occupancy_grid.py:367`) must not change
- All callers that read occupancy must route through the same array interface — no mixed dict + array access
- `_mark_route_blocked` (writes) and `_unblock_net_pads` (temporary unblocking) must update the numpy array in-place

**Success criterion:** `is_free()` calls eliminated from the profile top-20 entirely. 180M Python function calls removed.

### R2. Pre-Computed Distance-to-Goal Map
Status: required

The A* heuristic `_heuristic(a, b)` at `astar_pathfinding.py:1213` computes Euclidean distance between two grid cells. Called 22.7M times per full run. Since the goal cell is fixed for a single A* invocation (routing one segment of one net), pre-compute the distance from every grid cell to the goal once at the start of the A* search.

- Use Dijkstra or a simple flood-fill from the goal cell to populate a 2D float array
- The A* heuristic reads from the precomputed array: `distmap[y, x]`
- Accept ~5% approximation if needed for memory — the heuristic only needs to be admissible, not exact
- The map is recomputed per A* invocation (per waypoint segment) since the goal changes

**Success criterion:** `_heuristic` and `heappop` reduced from 45M cumulative calls to < 1M. Heap size proportional to search frontier, which shrinks with a better heuristic.

### R3. Outer-Layer-Only Channel Skeleton
Status: required

The channel skeleton is extracted for all 5 layers (`pipeline.py:268`, `channel_skeleton.py:42`), producing ~13K nodes and ~16K edges across 5 layers. The pipeline already prefers F.Cu and B.Cu for routing (`pipeline.py:406-408`). Restrict skeleton extraction to F.Cu and B.Cu only — the two outer signal layers.

- Inner layers (In1.Cu, In2.Cu, In3.Cu) are used for power/ground planes and contribute minimal routing value for signal nets that can route on outer layers
- Layer switching via THT pads still works — the skeleton for the target layer is available when a net switches
- The occupancy grid for inner layers must still be built (for obstacle avoidance) — just the skeleton graph skips them

**Success criterion:** Channel skeleton build time reduced from 10s to ~4s. SAT model variable count reduced proportionally (60% fewer channel nodes = 60% fewer variables).

### R4. Coarse-to-Fine Grid Routing
Status: required

Run A* pathfinding in two passes: a coarse pass on a 2× coarser grid (0.2mm cells), then a fine pass on the standard 0.1mm grid constrained to a corridor around the coarse path.

- Coarse grid: downsample the 0.1mm occupancy grid by a factor of 2 in each dimension. A cell is blocked if any of its 4 sub-cells are occupied.
- Coarse A* finds an approximate path at 0.2mm resolution
- Fine A* re-runs on the 0.1mm grid but only explores cells within a corridor (e.g., 5 cells on each side of the coarse path)
- The final path is at full 0.1mm resolution — identical to the current single-pass result
- If the coarse path fails (A* exhausted), fall back to full-grid 0.1mm A* as today

**Success criterion:** A* search space reduced by 60-80%. 144 `_astar_search` calls produce paths of identical quality to single-pass 0.1mm.

### R5. Shapely Buffer Caching
Status: required

Shapely `buffer()` calls at 3.6M total compute obstacle inflation for the occupancy grid, pad unblocking, and layer-connection generation. Many inflate the same geometry at the same radius. Add a per-stage cache keyed on `(geometry_hash, buffer_radius)`.

- Cache lives per pipeline stage (built during stage 2, reused during stage 4 where the same obstructions are inflated)
- `geometry_hash` uses `shapely.to_wkb()` or `geometry.wkb_hex` for fast hashing
- Cache size is bounded: the channel skeleton has ~13K nodes, each inflated at most 2-3 radii
- No quality impact — same buffers, computed fewer times

**Success criterion:** Shapely `buffer()` call count reduced by 50%+. Shapely disappears from or drops substantially in the profile top 20.

## Success Criteria

- **SC1.** Full closure test completes in < 60 seconds (target, from 180s baseline)
- **SC2.** Router completion rate must not decrease (0.5% baseline on `temper_placed`)
- **SC3.** DRC error count must not increase (16 errors, 52 warnings baseline)
- **SC4.** All 5 fixes independently measurable — each fix has a specific profile metric that confirms the improvement

## Scope Boundaries

### Deferred for later
- Changing the routing algorithm itself (same A*, same grid, same path)
- SAT model optimization (profile showed it's < 1% of runtime)
- Theta* or smoothing enablement (quality improvements, not performance — profile showed these make routing slower, not faster)
- Router V6 completion rate improvements (separate concern from runtime)

### Outside this product's identity
- Replacing the occupancy grid with a quadtree, R-tree, or voxel representation
- Porting A* to C/C++/Rust (Python-only scope)
- Changing the grid resolution itself (0.1mm is the design choice for routing quality)

## Dependencies

- `occupancy_grid.py:28-79` — `OccupancyGrid` class, `is_free()`, and all mutation methods
- `astar_pathfinding.py:1151-1300` — `_astar_search`, `_heuristic`
- `astar_pathfinding.py:780-865` — `_astar_route_multilayer` (uses the grid for routing)
- `pipeline.py:249-293` — Stage 2 channel skeleton extraction loop
- `channel_skeleton.py:42` — `extract_channel_skeleton`

## Assumptions

1. The 0.1mm grid resolution is fixed — coarsening is only for the initial A* pass, not for the final path
2. The numpy boolean array for `is_free()` maintains the same interface signature so existing callers need minimal changes
3. Skeleton extraction for F.Cu + B.Cu already covers all routable nets — verified by `pipeline.py:406-408` preferring these layers
4. Buffer caching hit rate is high enough (>50%) to justify the cache infrastructure — verified by observing repeated inflation radii in the profile
