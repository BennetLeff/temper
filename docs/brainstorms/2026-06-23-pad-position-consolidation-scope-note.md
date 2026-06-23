---
date: 2026-06-23
topic: pad-position-consolidation-scope-note
status: scope-note (expand when sequenced after doc 1)
---

# Pad-Position Extraction (Doc 2 of 4) — Scope Note

## Place in sequence

Doc 2 of 4. Ships after **Doc 1 (Layer Names)** because layer canonicalization may be touched by pad-position code. Ships before **Doc 3 (Net Classification)** because pad-position is more local (no public API change) and is a real bug fix (40+ inlined copies of `pin.absolute_position` / `comp_pos + pin.position` — two divergent implementations that disagree for rotated components).

## Audit findings (from /ce-code-simplify consolidation audit)

**40+ inlined copies of pad-position extraction** across the codebase:
- `routing/maze_router.py:1653, 1832, 3020, 3294, 4926`
- `routing/pdn_router.py:139, 149, 185, 488-489`
- `routing/c_space_pipeline.py:155, 454`
- `routing/layer_assignment.py:338`
- `routing/escape_router.py:99-100`
- `routing/unified_router.py:631-632, 773, 786`
- `routing/net_ordering.py:213-214, 260-261`
- `routing/congestion.py:336-337`
- `deterministic/stages/fine_pitch_escape.py:135-136, 212-213`
- `deterministic/stages/clearance_grid.py:705`
- `deterministic/stages/setup.py:169`
- `deterministic/stages/sequential_routing.py:435, 523, 635, 1192, 1802`
- `deterministic/stages/drc_sweep.py:196`
- `deterministic/stages/via_validation.py:204`
- `placement/audit.py:55-61`
- `validation/metrics.py:395`
- `io/dsn_exporter.py:73, 227-228, 342-343`
- `router_v6/astar_grid.py:52-101` (`_extract_pad_centers_per_net` — canonical)
- `router_v6/channel_mapping.py:332`
- `router_v6/obstacle_map.py:63`
- `router_v6/escape_drc_validator.py:153`
- `router_v6/escape_via_generator.py:82, 94, 190`
- `router_v6/constraint_model.py:327`
- `router_v6/channel_skeleton.py:135`
- `router_v6/pad_escape_classification.py:75, 131`
- `core/routing_validator.py:123`

**Two divergent implementations** that disagree for rotated components:
- `pin.absolute_position(comp_pos, angle, side)` — uses Pin's rotation/side knowledge
- `comp_pos + pin.position` — treats pin as fixed offset, doesn't rotate

## Key decisions to make during expansion

- **Canonical home:** new `core/pin_geometry.py` (3 helpers: `pin_world_position(pin, comp) -> tuple[float, float]`, `pin_world_radius(pin) -> float`, `pin_world_layer(pin) -> str | int`) or add to existing `core/net_types.py`.
- **API surface:** helpers accept `Pin, Component` (the existing types) and return primitives (tuples/floats). No new types.
- **Migration strategy:** big-bang (matching doc 1's choice). The two divergent implementations are a real bug — the moment-of-truth is at the call sites, not in a deprecation window.
- **Whether to keep both APIs (`absolute_position` and `position + comp_pos`):** likely consolidate to one. The `absolute_position` form is the correct one (uses rotation); the `comp_pos + pin.position` form is the bug.

## Open questions for expansion

- Does `core/net_types.py` already have a `Pin` type, or is it defined in `core/board.py`? Where do the 40+ inlined calls actually import `Pin` from?
- Are there any tests that pin down the exact return values of `pin.absolute_position` for rotated components? If so, the bug surface is testable.
- `router_v6/astar_grid.py:_extract_pad_centers_per_net` returns `(x, y, radius, layer)` tuples — a richer return than `pin_world_position`. Is the helper API `pin_world_position` enough, or do we need a `pin_world_extents` that returns all 4?
