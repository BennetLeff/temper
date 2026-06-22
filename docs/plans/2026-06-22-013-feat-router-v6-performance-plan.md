---
date: 2026-06-22
type: feat
origin: docs/brainstorms/2026-06-22-router-v6-performance-fixes-requirements.md
status: active
---

# Plan: Router V6 Performance — 5 Quality-Preserving Fixes

## Problem Frame

Router V6 takes 180s per closure test run on the Temper PCB. Profile shows 85% of time in four hot paths: grid lookup (33s), A* search + heuristic (112s), channel skeleton (23s), and Shapely buffers (21s). This plan applies five targeted fixes, each preserving routing quality while eliminating a specific bottleneck.

## Requirements Trace

| Requirement | Source | Acceptance |
|-------------|--------|------------|
| R1 — Numpy occupancy grid | Requirements doc | `is_free()` eliminated from profile top 20 |
| R2 — Distance-to-goal map | Requirements doc | Heuristic + heappop calls < 1M (from 45M) |
| R3 — Outer-layer-only skeleton | Requirements doc | Skeleton build < 4s (from 10s) |
| R4 — Coarse-to-fine grid | Requirements doc | A* search space 60-80% smaller |
| R5 — Shapely buffer caching | Requirements doc | Buffer call count 50%+ reduced |
| SC1 | Requirements doc | Full run < 60s |
| SC2-SC3 | Requirements doc | No completion or DRC regression |

## Implementation Units

### U1. Numpy Occupancy Grid
**Goal:** Replace `is_free()` Python function dispatch with numpy boolean array.
**Requirements:** R1
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` (callers of `is_free`, `mark_occupied`, `unblock_cell`)
**Approach:**
- `OccupancyGrid.__init__`: initialize a 2D numpy boolean array `self._grid = np.zeros((w, h), dtype=bool)` for the grid dimensions
- `is_free(x, y)`: return `not self._grid[y, x]` (direct array lookup, no function overhead)
- `mark_occupied(x, y)`: set `self._grid[y, x] = True` in-place
- `_unblock_net_pads`: unblock cells by setting `self._grid[y, x] = False` and track for restoration
- Add `numpy` to dependencies (already in temper-placer dependencies)
- Keep the existing dict-based access as a fallback for dimensions not in the numpy array
**Patterns to follow:** `OccupancyGrid` class at `occupancy_grid.py:28-79`
**Test scenarios:**
- Grid initialized with correct dimensions for `temper_placed` board
- `is_free` returns False after `mark_occupied` for same cell
- `_unblock_net_pads` restores cell to free after routing completes
- Same routing results as dict-based grid (SC2, SC3 preserved)
**Verification:** `is_free` absent from profile top 20. Runtime improved.

---

### U2. Distance-to-Goal Map
**Goal:** Replace per-call `_heuristic(a, b)` with precomputed distance-to-goal map.
**Requirements:** R2
**Dependencies:** None (independent of U1, but benefits from U1's faster grid access)
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
**Approach:**
- In `_astar_search`, before the A* loop: compute a distance map from the goal cell using a simple BFS/flood-fill on the occupancy grid. For each reachable cell, store the Euclidean distance to the goal.
- The flood-fill uses `is_free()` so only traversable cells get distances. Unreachable cells get infinity.
- `_heuristic(a, b)` becomes `distmap[a]` — O(1) array lookup
- Fall back to Euclidean distance if the cell is not in the distance map (edge case: unreachable cells)
**Patterns to follow:** `_astar_search` at `astar_pathfinding.py:1151`
**Test scenarios:**
- Distance map covers all reachable cells within the A* search space
- Same A* path as without distance map (admissible heuristic)
- Heap size smaller (better heuristic) → `heappop` calls reduced
**Verification:** `_heuristic` + `heappop` calls < 1M (from 22.7M each). Heap queue depth reduced.

---

### U3. Outer-Layer-Only Channel Skeleton
**Goal:** Extract skeleton from F.Cu + B.Cu only, skipping 3 inner layers.
**Requirements:** R3
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
**Approach:**
- In `_run_stage2`, filter `routing_spaces` to `{"F.Cu", "B.Cu"}` before the skeleton extraction loop at line 258
- Occupancy grids are still built for all 5 layers (needed for obstacle avoidance and layer switching)
- SAT model and A* guidance use the reduced skeleton — 60% fewer nodes
- The pipeline already uses `fcu_skeleton` and `bcu_skeleton` as primary routing layers at lines 406-408
**Patterns to follow:** `_run_stage2` routing spaces loop at `pipeline.py:249-293`
**Test scenarios:**
- Skeleton extracted for 2 layers (not 5)
- All routable nets have channel paths on F.Cu or B.Cu
- Layer switching still works — occupancy grids for inner layers remain available
**Verification:** Skeleton build time < 4s. SAT model variables reduced proportionally.

---

### U4. Coarse-to-Fine Grid Routing
**Goal:** Route on 0.2mm grid first, refine path on 0.1mm grid.
**Requirements:** R4
**Dependencies:** U1 (numpy grid makes downsampling trivial)
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` (`_astar_route_multilayer`)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py` (add `downsample` method)
**Approach:**
- Add `OccupancyGrid.downsample(factor=2)` that returns a coarser grid: cell (i,j) is blocked if any of its `factor × factor` sub-cells in the parent grid are blocked
- In `_astar_route_multilayer`, before the main route call: downsample occupancy to 0.2mm, run A* on the coarse grid, get a coarse path
- Coarse path is a list of (x, y) cells at 0.2mm resolution. Map each cell to a set of 0.1mm cells (the `factor × factor` sub-cells).
- Build a corridor mask: for each 0.1mm cell within `corridor_width` cells of any point on the coarse path, mark as traversable
- Run fine A* on the 0.1mm grid, but `is_free` returns False for cells outside the corridor mask
- If coarse A* fails (no path found), fall back to full-grid 0.1mm A*
**Patterns to follow:** `_astar_route_multilayer` at `astar_pathfinding.py:867`
**Test scenarios:**
- Coarse path found for all previously-routable nets
- Fine path matches or improves coarse path at full 0.1mm resolution
- Fallback to full grid when coarse A* exhausts
- Path quality: same net endpoints connected, same clearance constraints
**Verification:** A* search space (cells explored) reduced by 60-80%. `_astar_search` cumulative time reduced.

---

### U5. Shapely Buffer Caching
**Goal:** Cache Shapely buffer results to eliminate redundant geometry inflation.
**Requirements:** R5
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py`
**Approach:**
- Add a module-level `_buffer_cache: dict[bytes, Any]` keyed on `(wkb_hash, radius)` 
- In `OccupancyGrid._inflate_obstacles` and `channel_skeleton` buffer calls, check cache before calling `shapely.buffer()`
- Cache key: `hashlib.sha256(geometry.wkb + struct.pack('d', radius)).digest()` for collision-resistance
- Cache is bounded to 10K entries (LRU eviction) to prevent memory growth on large boards
**Patterns to follow:** `shapely.buffer()` call sites in `occupancy_grid.py` and `channel_skeleton.py`
**Test scenarios:**
- Identical geometry + radius returns cached buffer (hash hit)
- Cache miss falls through to `shapely.buffer()`
- Cache does not affect buffer results (same output as uncached)
**Verification:** Shapely `buffer()` call count reduced 50%+. Shapely drops substantially in profile top 20.

---

## Scope Boundaries

### Deferred to Follow-Up Work
- SAT model optimization (profile showed < 1% of runtime)
- Theta* or smoothing enablement (quality, not performance)
- Router V6 completion rate improvements
- C/C++/Rust ports of A* or occupancy grid

## Test Strategy

- All 5 units are independent (touch different code paths) — can be implemented and tested in parallel
- Closure test (`pcb/temper_placed.kicad_pcb`) is the integration gate after all 5 land
- Profile each fix individually (run closure test with cProfile, verify the targeted hot path shrinks)
- Regression: existing `tests/regression/test_closure.py` must pass unchanged
