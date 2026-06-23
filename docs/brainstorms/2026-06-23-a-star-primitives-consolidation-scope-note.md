---
date: 2026-06-23
topic: a-star-primitives-consolidation-scope-note
status: scope-note (expand when sequenced after docs 1-3)
---

# A* Primitives Consolidation (Doc 4 of 4) — Scope Note

## Place in sequence

Doc 4 of 4. Ships after the other 3 because A* primitives (`octile_distance`, 8-direction moves, bounds check, cell↔world conversion, polyline length) are used by A* search code that may also be touched by docs 2 and 3. Doc 4 is internal (no public API change), lowest blast radius, builds on whatever the earlier docs settled. Total sequence: layer names → pad-position → net classification → A* primitives.

## Audit findings (from /ce-code-simplify consolidation audit)

**Octile distance `max(d,…) + 0.414*min(d,…)`** duplicated in 6+ files:
- `routing/astar/python_astar.py:37, 136, 212, 317` (uses `OCTILE_DIAG = math.sqrt(2) - 1`)
- `router_v6/astar_core.py:146` (literal `0.414`)
- `deterministic/stages/multilayer_astar.py:59, 197, 312, 518` (literal `0.414`)
- `deterministic/stages/astar.py:46, 140` (literal `0.414`)
- `deterministic/stages/bidirectional_astar.py:294` (literal `0.414`)
- `routing/astar/astar_core.pyx:208-213` (Cython inline)

**Octile diagonal cost `1.414` (sqrt(2))** in 4+ files:
- `router_v6/astar_core.py:128, 565`
- `deterministic/stages/astar.py:175-178`
- `deterministic/stages/bidirectional_astar.py:236`
- `deterministic/stages/multilayer_astar.py:428-431`
- `routing/astar/python_astar.py:39-44` (uses `math.sqrt(2)`)

**8-direction neighbor table** duplicated in 5+ files:
- `routing/astar/python_astar.py:40-45` (uses `_SAME_LAYER_DELTAS` module constant)
- `routing/astar/astar_core.pyx:399-402` (C array)
- `router_v6/astar_core.py:113, 314, 425-433, 562` (inlined 4 times)
- `deterministic/stages/astar.py:170-179` (candidates list)
- `deterministic/stages/multilayer_astar.py:423-432` (same_layer_moves)
- `deterministic/stages/bidirectional_astar.py:204-237` (nested loop)
- `routing/neighbors/generator.py:17-67` (`get_cardinal_neighbors` — 4-direction only)

**Bounds check `0 <= r < rows and 0 <= c < cols`** inlined 15+ times across 12 files:
- `routing/astar/python_astar.py:225-227`
- `deterministic/stages/astar.py:148-156`
- `deterministic/stages/multilayer_astar.py:327-330`
- `deterministic/stages/bidirectional_astar.py:280-283`
- `deterministic/stages/clearance_grid.py:186`
- `router_v6/astar_pathfinding.py:601-602`
- `router_v6/astar_grid.py:237`
- `router_v6/astar_core.py:179, 316, 436, 634, 636`
- `router_v6/grid_update.py:76`
- `router_v6/occupancy_grid.py:58, 65, 319`
- `routing/geometry_fields/sdf_builder.py:146, 169`
- `routing/exact_geometry/path_simplifier.py:219`
- `routing/diff_pair_router.py:711-718`
- `deterministic/stages/sequential_routing.py:619, 659`
- `routing/grid/converter.py:132, 144, 155`

**`_state_to_mm` cell-center conversion** in 8+ inlined copies:
- `routing/astar/python_astar.py:300`
- `deterministic/stages/multilayer_astar.py:478`
- `deterministic/stages/astar.py:159, 190, 247` (3 inlined copies)
- `deterministic/stages/bidirectional_astar.py:217, 221, 249, 275` (4 inlined copies)
- `routing/astar/astar_core.pyx:482-489, 502-509`

**`level_order` dict mapping `CongestionLevel` → int** duplicated 3 times verbatim:
- `routing/adaptive_congestion.py:298-303`
- `deterministic/stages/multilayer_astar.py:160-165`
- `routing/astar/python_astar.py:46-51` (named `_CONGESTION_ORDER`)

**Polyline Euclidean length sum** in 3+ files:
- `router_v6/astar_pathfinding.py:491-494, 559-562`
- `router_v6/channel_mapping.py:451-473` (`_calculate_path_length`)
- `router_v6/occupancy_grid.py:167, 197, 241, 288, 309` (5 inlined copies)

**World↔grid conversion** — 3 different APIs:
- `core/units.mm_to_cell` (no origin)
- `router_v6/occupancy_grid.world_to_grid` (origin-aware)
- `routing/grid/converter.GridConverter.world_to_grid` (origin + clamp + round/floor variants)

**Pad-inflation radius `width/2 + clearance`** in 7+ files with 3 semantic variants:
- Plain: `w/2 + c`
- +cell/2: discretization safety
- +0.05: extra safety

## Key decisions to make during expansion

- **Canonical home:** extend the existing `routing/heuristics.py` (which already exists as a registry). It has `manhattan_heuristic` and `euclidean_heuristic` — add `octile_distance`, `same_layer_deltas`, `in_bounds`, `state_to_mm`, `polyline_length`.
- **`CongestionLevel.order` property** on the enum in `routing/iteration_budget.py` (cleaner than the level_order dict).
- **`core/units.mm_to_cell` footgun** (doesn't subtract origin) — fix or deprecate.
- **API surface:** free functions in `routing/heuristics.py`, not a class. Matches the existing pattern.
- **Migration strategy:** big-bang (matching doc 1's choice). Internal refactor, lowest blast radius of the 4.

## Open questions for expansion

- Should the `OCTILE_DIAG = math.sqrt(2) - 1` constant live in `routing/heuristics.py` or in a new `routing/octile.py`? (Same for `_SAME_LAYER_DELTAS`.)
- The Cython file `routing/astar/astar_core.pyx` has its own octile formula `(dx+dy) + (1.414213562 - 2.0) * min_dist` — algebraically equivalent but different. Should the Cython `cdef inline` reference the Python constant via a header, or stay self-contained?
- The `deterministic/stages/astar.py:170-179` 8-direction order is `(up, right, down, left, ul, ur, dl, dr)` while the others use `(up, right, down, left, ul, ur, dl, dr)` — actually the same order, but tie-breaking depends on iteration order in some A* implementations. Is the order observable in any test?
- `routing/heuristics.py:114` `heuristic()` closure captures a `dist_map` array; A* methods don't. Are these the same abstraction? Should the closure pattern be unified with the method pattern?
