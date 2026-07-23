---
title: "Via-aware layer transitions — restoring the SSOT completion chain with a fallback-tier 3D A*"
date: 2026-07-20
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "SSOT layer assignments exist but the completion gate neutralizes them"
  - "A hardcoded layer write (F.Cu) is accidentally load-bearing"
  - "Adding multi-layer routing capability where single-layer routing had 100% completion"
  - "A branch's via outputs are hardcoded (always same layer pair, never emitted)"
  - "Before widening routing-layer divergence — validate connectivity end-to-end first"
tags:
  - via-aware-routing
  - 3d-astar
  - fallback-tier
  - ssot-layer-assignment
  - completion-gate
  - kicad-drc
  - anti-false-zero
  - router-v6
---

# Via-Aware Layer Transitions — Restoring the SSOT Completion Chain with a Fallback-Tier 3D A*

## Context

The W2 U2 work (SSOT layer assignments from `netclass_rules.yaml`) was wired but
non-functional since its introduction. Two independent mechanisms neutralised it:
(1) `_assign_layer()` returned the SSOT layer only when `ssot == heuristic` — a
no-op gate that made every explicit assignment match the name-pattern heuristic
it was meant to override; and (2) `_write_routes_to_content()` hardcoded
`(layer "F.Cu")` on every segment regardless of the computed `path_layer`. PR #220's
completion regression (commit `903dfaef`) proved the hardcoded F.Cu write was
accidentally load-bearing: re-landing the real `path_layer` write without real
via insertion caused 8 unconnected items because nets assigned to B.Cu had no
conductive path to their F.Cu pads.

The router had an existing 3D via-aware A* search (`_astar_search_3d`, authored
2026-01-12, tested, but never called from production dispatch) and a via-placement
module (`via_placement.py`) whose `RoutePath3D` branch hardcoded `from_layer="F.Cu"`
/ `to_layer="B.Cu"` for every via. Nothing wrote `(via ...)` s-expressions into
KiCad output.

The pre-fix production board had 149 `unconnected_items` after routing, with
`GateDrive` and other power nets forced onto F.Cu despite having explicit B.Cu
SSOT assignments.

## Guidance

Restore the chain in order: validate the 3D search at production scale, wire it
as a fallback tier, fix hardcoded layer-spans, apply per-netclass sizing, emit
real via output, re-land the segment-layer write, then — only then — relax the
completion gate. Verify each step with `kicad-cli pcb drc` before proceeding.

### U1: Production-scale wall-time spike proves 3D A* viable

Before committing to the 3D search as a fallback tier, run it against real
production-scale grids (95 nets, 149 components) and measure wall time,
via-legality correctness, and graceful degradation on congested regions. The
branching factor increase from 8 (2D) to 9 (2-layer 3D) is modest, but
measurement replaces argument:

```python
# test_astar_3d_production_scale_spike.py
result = _route_segment_3d(
    start_world, goal_world, "F.Cu", "B.Cu",
    grids, via_cost=10.0, via_diameter=0.6, clearance=0.2,
    net_id=42, max_iter=200_000,
)
```

Key finding: short (waypoint-scale) calls complete in tens to low hundreds of
iterations (<1ms). Unbounded worst-case degenerate segments can reach 66s —
mitigated by `max_iter=200_000` at the fallback call site (U2).

### U2: Wire `_route_segment_3d` as fallback tier in `_astar_route_multilayer`

After the existing primary-grid and THT-gated alternate-grid attempts both fail,
invoke the 3D search as a last resort. This is additive — segments that succeed
on the primary grid never reach this branch:

`astar_pathfinding.py:_astar_route_multilayer` (lines ~1086-1124):
```python
# U2: via-aware fallback tier. Both the primary-grid attempt and the
# THT-gated alternate-grid retry have failed for this segment.
grids_3d: dict[str, OccupancyGrid] = {primary_grid.layer_name: primary_grid}
if alternate_grid is not None:
    grids_3d[alternate_grid.layer_name] = alternate_grid

fallback_layer = primary_grid.layer_name
net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
result_3d = _route_segment_3d(
    start_world, goal_world, fallback_layer, fallback_layer,
    grids_3d, via_cost=10.0,
    via_diameter=net_rules.via_diameter_mm if net_rules else 0.6,
    clearance=net_rules.clearance_mm if net_rules else 0.2,
    net_id=net_id,
    max_iter=segment_3d_fallback_max_iter,
)

if result_3d is not None:
    world_path_3d, via_positions_3d = result_3d
    via_positions.extend(via_positions_3d)
    detailed_segments.extend(world_path_3d[1:])
    continue
```

The 3D search's `move_cost=via_cost` (default 10x) discourages excessive
transitions. Its `mark_via_blocked()` call after path reconstruction blocks via
positions on all spanned layers for subsequent nets (requires `net_id > 0`).

### U3: Fix hardcoded via layer-span (derive from segment layers)

`via_placement.py:_place_vias_for_path` hardcoded `from_layer="F.Cu"` /
`to_layer="B.Cu"` for every via. Fix: match each `via_positions` entry to
the segment that contains it, then read the layers of that segment and the
following segment:

`via_placement.py:_place_vias_for_path` (lines ~113-137):
```python
if hasattr(route_path, "via_positions") and hasattr(route_path, "segments"):
    segs = route_path.segments
    for vx, vy in route_path.via_positions:
        vi = None
        for i, (sx, sy, _) in enumerate(segs):
            if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
                vi = i
                break
        if vi is not None and vi + 1 < len(segs):
            from_layer = segs[vi][2]
            to_layer = segs[vi + 1][2]
        else:
            from_layer = "F.Cu"
            to_layer = "B.Cu"
        vias.append(Via(
            position=(vx, vy),
            from_layer=from_layer,
            to_layer=to_layer,
            diameter=via_diameter, drill=via_drill,
            net_name=net_name,
        ))
```

The legacy `RoutePath` branch (lines 118-139) was already correct — do not
conflate the two branches. On a 2-layer board, F.Cu/B.Cu still matches the
old behavior; the fix is observable with a synthetic 4-layer test fixture.

### U4: Per-netclass via sizing

Thread per-netclass `via_diameter`/`via_drill` from `netclass_rules.yaml`
through both the 3D search's legality check and the `Via` construction.
Replaces `_astar_search_3d`'s hardcoded `via_diameter=0.6, clearance=0.2`
defaults and `via_placement.py`'s board-wide `default_via_diameter_mm`:

```python
# In _astar_route_multilayer's U2 fallback call site (astar_pathfinding.py:1108-1113)
net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
result_3d = _route_segment_3d(
    ..., via_diameter=net_rules.via_diameter_mm if net_rules else 0.6,
    clearance=net_rules.clearance_mm if net_rules else 0.2, ...
)
```

For example, HV nets get 1.2mm/0.6mm, FinePitch gets 0.4mm/0.2mm.

### U5: Emit real `(via ...)` s-expression output

Loop over `compiled_route.vias` in `_write_routes_to_content` and emit one
`(via (at x y) (size d) (drill dr) (layers "X" "Y") (net n) ...)` per `Via`:

`adapter.py:_write_routes_to_content` (lines ~714-721):
```python
for via in getattr(compiled_route, "vias", []):
    vx, vy = via.position
    segments.append(
        f'  (via (at {vx:.4f} {vy:.4f}) (size {via.diameter:.4f})'
        f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
        f' (net {net_num}) (tstamp "{uuid.uuid4()}"))'
    )
```

### U6: Re-land the segment-layer write (previously reverted in 903dfaef)

Replace hardcoded `(layer "F.Cu")` with the already-computed `path_layer` in
the segment s-expression:

`adapter.py:_write_routes_to_content` (line ~631):
```python
# Before: f' (width {width:.4f}) (layer "F.Cu") (net {net_num})'
# After:
f' (width {width:.4f}) (layer "{path_layer}") (net {net_num})'
```

Sequence strictly after U1-U5: output must not diverge from `main` until via
insertion can connect paths on different layers to their F.Cu pads. Run
`kicad-cli pcb drc` before and after; `unconnected_items` must never regress.

### U7: Relax the SSOT completion-preserving gate

Remove the `ssot == heuristic` no-op condition from `_assign_layer`. This is the
one-line change that makes the entire chain functional:

`channel_mapping.py:_assign_layer` (lines ~144-150):
```python
# Before (PR #220 guard):
# if ssot is not None and ssot == heuristic:
#     return ssot

# After (U7):
ssot = _ssot_layer_for_net(net_name, layer_constraints)
if ssot is not None:
    return ssot
```

Now `GateDrive` (explicit netclass, SSOT layer B.Cu) routes on B.Cu with
real via transitions at its pads. Default/unassigned nets retain the heuristic.

Corpus result: 100% completion preserved. Routed violation count 329 (down
from U6.1's 331: eight fewer genuine shorts after explicit GateDrive/power
layer divergence).

### U8: KiCad DRC measurement — unconnected_items 149→0

Run `kicad-cli pcb drc` on the production board before and after U7. The
baseline 149 physical unconnected items reduced to 0 after the full chain
(U1-U7) landed. This is not just a connectivity claim from the router's internal
completion signal — it is verified against KiCad's DRC engine.

## Why This Matters

- **The SSOT gate was a no-op since PR #220.** Every explicit netclass layer
  assignment produced the same result as the heuristic because `ssot == heuristic`
  was always true for the gate to pass. The W2 U2 investment (SSOT layer
  assignment pipeline) was dead code for its entire production lifetime.

- **U7 made U1-U6 functional.** Without U7, the fallback-tier 3D search, real
  via output, per-netclass sizing, and segment-layer write were all working but
  unreachable — the gate never let a net diverge from its heuristic layer.

- **149 production-board unconnected items eliminated.** The pre-fix production
  board had unconnected pads because power nets assigned to B.Cu had no
  conductive path to F.Cu SMD pads. Via-aware transitions provide that path.

- **The accidental load-bearing hardcode is gone.** The F.Cu segment-layer write
  (`903dfaef` revert) was a PR #220 emergency fix. The U6 re-land with U1-U5
  backing is the proper, permanent solution.

## When to Apply

- When adding multi-layer routing capability to a previously single-layer router
  that achieved 100% completion
- When SSOT layer assignments exist in the pipeline but the completion gate
  neutralizes them (suspect this when a netclass-aware assignment always
  produces the same result as the name-pattern heuristic)
- When a hardcoded layer write (`F.Cu`) in the writer module is the only thing
  keeping DRC from finding unconnected items — the hardcode is load-bearing
  and must not be removed until via insertion is proven
- When sequencing a multi-unit refactor where one unit's change would regress
  connectivity without another unit's infrastructure — always build the
  safety net (vias) before removing the floor (hardcoded layer)
- When adding any output divergence from a known-good baseline — run
  `kicad-cli pcb drc` before and after and gate the merge on the delta

## Key Code Artifacts

| Unit | File | Change |
|------|------|--------|
| U7 | `channel_mapping.py:_assign_layer` | Removed `and ssot == heuristic` from SSOT gate |
| U3 | `via_placement.py:_place_vias_for_path` | Derive `from_layer`/`to_layer` from segment layers, not hardcoded pair |
| U6 | `adapter.py:_write_routes_to_content` | `path_layer` replaces hardcoded `"F.Cu"` in segment s-expression |
| U5 | `adapter.py:_write_routes_to_content` | `(via ...)` s-expression emission from `compiled_route.vias` |
| U2 | `astar_pathfinding.py:_astar_route_multilayer` | Third fallback tier: `_route_segment_3d` on `grids_3d` after primary+alternate fail |
| U4 | `astar_pathfinding.py:_astar_route_multilayer` | Per-netclass `via_diameter`/`clearance` threaded to `_route_segment_3d` |
| U1 | `astar_core.py:_astar_search_3d` | `max_iter` safety valve (200K default), production-scale validation harness |

## Related

- `docs/plans/2026-07-18-003-feat-via-aware-layer-transitions-plan.md` — the plan that sequenced these eight units
- `docs/brainstorms/2026-07-18-via-aware-layer-transitions-requirements.md` — origin brainstorm (R1-R7)
- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md` — PR #220 completion-regression excavation that motivated this chain
- `docs/plans/2026-07-18-002-feat-board-routing-completion-plan.md` — U7 audit that first surfaced the two-mechanism question
- `docs/brainstorms/2026-07-08-single-layer-route-requirements.md` — single-layer-first sequencing decision (six months before the 3D search)
- Commits: `903dfaef` (F.Cu revert), `112df593` (SSOT gate), `081e9cf8` (U2 fallback tier), `cd1c90a6` (U3 layer-span fix), `3bf897e8` (U4 netclass sizing), `5a90a212` (U5 via emission), `2e670584` (U6 segment-layer re-land), `15a80701` (U7 gate relaxation), `c48b0fe0` (U8 measurement chain)
