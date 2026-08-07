"""Pinned Python oracle for the zone/pour emission geometry migration.

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
``ZoneDefinition``, ``emit_zone_s_expr`` below are a **verbatim** ``git show``
extraction from commit ``a920657f2d4fa2f56b24d71f3ae558dd244dc0fc``
(``origin/main``, 2026-08-06) of
``temper_placer/router_v6/zone_emission.py``.

``_chamfer_path_points`` and ``_stitch_isolated_pads`` below are a
**verbatim** ``git show`` extraction from the same commit of
``temper_placer/router_v6/_zone_pour_stitch.py``.

Nothing has been cleaned up, refactored, or fixed *by this file*.
``test_zone_pour_geometry_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

Why these four functions, and not the whole file
--------------------------------------------------
``_zone_layers_for_net`` and ``_zone_params_for_net`` are netclass-SSOT
lookups (``TEMPER_NET_ASSIGNMENTS``/``TEMPER_NET_CLASSES`` from
``core/design_rules.py``) -- data-driven business logic, not geometry, and
out of scope for this migration.  ``_stitch_isolated_pads`` still calls the
*live* (unmigrated) ``_zone_layers_for_net`` below, exactly as production
does -- only its point-in-polygon/nearest-neighbour geometry moves to Rust.

``_cluster_positions`` (scipy Ward-linkage hierarchical clustering) and
``_convex_hull_from_positions``'s ``shapely.buffer(margin, join_style=2)``
step (GEOS mitre-join polygon offsetting) are NOT migrated -- see the
JUSTIFIED-KEEP note in ``packages/temper-geometry/VERIFICATION.md`` ("Zone
Pour Emission Geometry" section) for the measured evidence.  They stay on
``compute_zones_for_net``/``compute_zone_for_net`` in the live
``zone_emission.py``, unpinned here because they are not being replaced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Module-level import so the pinned ``_stitch_isolated_pads`` body below can
# reference ``_zone_layers_for_net`` as a bare name (Python resolves free
# names in a function body against the *enclosing module's* globals at call
# time) WITHOUT adding an import line inside the pinned body itself, which
# would break the verbatim-copy proof
# (``test_oracle_is_verbatim_copy``). ``_zone_layers_for_net`` is not
# migrated -- this is the same live function production calls.
from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net  # noqa: F401

# ---------------------------------------------------------------------------
# From zone_emission.py @ a920657f2d4fa2f56b24d71f3ae558dd244dc0fc
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneDefinition:
    net_name: str
    net_number: int
    layer: str
    points: tuple[tuple[float, float], ...]
    clearance: float = 0.3
    min_thickness: float = 0.25
    priority: int = 0


def emit_zone_s_expr(zone: ZoneDefinition) -> str:
    """Render a ZoneDefinition as a KiCad ``(zone ...)`` s-expression."""
    poly = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in zone.points)
    return (
        f'  (zone (net {zone.net_number}) (net_name "{zone.net_name}")'
        f' (layer "{zone.layer}")'
        f" (hatch full 0.5)"
        f" (priority {zone.priority})"
        f" (connect_pads yes (clearance {zone.clearance:.4f}))"
        f" (min_thickness {zone.min_thickness:.4f})"
        f" (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))"
        f" (polygon (pts {poly})))"
    )


# ---------------------------------------------------------------------------
# From _zone_pour_stitch.py @ a920657f2d4fa2f56b24d71f3ae558dd244dc0fc
# ---------------------------------------------------------------------------


def _stitch_isolated_pads(
    pad_positions: dict[str, list[tuple[float, float]]],
    segments: list[str],
    net_name_to_number: dict[str, int],
    zone_points: dict[str, list[tuple[tuple[float, float], ...]]],
    *,
    tstamp_counter: list[int] | None = None,
) -> None:
    """U3: emit straight-line trace segments from pads outside every
    dense-cluster pour back to the nearest pour for that net.

    Uses the already-computed zone polygons (from the zone-emission
    loop above) rather than re-clustering independently.

    ``tstamp_counter`` lets a caller (``_emit_zone_pours`` /
    ``_write_routes_to_content``) share one deterministic tstamp
    sequence across every element emitted in a single route_pcb() call.
    Callers that invoke this function standalone (e.g. tests) get a
    fresh, independent counter starting at 0.
    """
    from temper_placer.router_v6._adapter_convert import _next_tstamp

    if tstamp_counter is None:
        tstamp_counter = [0]

    from shapely.geometry import Point as ShapelyPoint
    from shapely.geometry import Polygon

    for net_name, positions in pad_positions.items():
        # Zone-eligibility check delegates to _zone_layers_for_net() rather
        # than repeating its own copy of the netclass list -- this file
        # previously carried three independent hardcoded copies of "which
        # netclasses get zone treatment" (this function,
        # _zone_layers_for_net(), and _emit_zone_pours()'s own loop), which
        # is exactly the duplicate-hand-maintained-list drift shape fixed
        # in _zone_layers_for_net() itself on 2026-07-28 -- see
        # docs/evidence/2026-07-28-zone-layer-classification-fix.md. A net
        # with no zone_layers never gets a zone_points entry below anyway
        # (the `if not zps: continue` guard), so this was always
        # semantically redundant with _zone_layers_for_net(), just not
        # mechanically tied to it.
        if not _zone_layers_for_net(net_name):
            continue
        net_num = net_name_to_number.get(net_name, 0)
        if net_num <= 0 or len(positions) <= 1:
            continue

        zps = zone_points.get(net_name)
        if not zps:
            continue

        pour_polys: list[Polygon] = []
        for pts in zps:
            if len(pts) >= 3:
                pour_polys.append(Polygon(pts))

        if not pour_polys:
            continue

        outside: list[tuple[float, float]] = []
        for x, y in positions:
            pt = ShapelyPoint(x, y)
            if not any(poly.contains(pt) or poly.touches(pt) for poly in pour_polys):
                outside.append((x, y))

        if not outside:
            continue

        from scipy.spatial import cKDTree

        all_verts: list[tuple[float, float]] = []
        for poly in pour_polys:
            for x, y in poly.exterior.coords:
                all_verts.append((float(x), float(y)))
        if not all_verts:
            continue

        tree = cKDTree(all_verts)
        trace_layer = (
            _zone_layers_for_net(net_name)[0] if _zone_layers_for_net(net_name) else "F.Cu"
        )

        for px, py in outside:
            _dist, idx = tree.query((px, py))
            nearest_x, nearest_y = all_verts[idx]

            segments.append(
                f"  (segment (start {px:.4f} {py:.4f})"
                f" (end {nearest_x:.4f} {nearest_y:.4f})"
                f' (width {0.2:.4f}) (layer "{trace_layer}")'
                f" (net {net_num})"
                f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )


def _chamfer_path_points(
    path_points: list[tuple[float, float, str]],
    chamfer_offset: float = 0.1,
) -> list[tuple[float, float, str]]:
    """Chamfer 90-degree orthogonal turns to reduce grid-staircasing DRC violations.

    The A* router operates on a 0.1 mm grid, producing paths whose turns
    are sharp 90-degree corners.  When two adjacent traces follow similar
    grid paths, the clearance between their edges at these corners can
    dip below the DRC minimum.  This function replaces each orthogonal
    turn with a 45-degree diagonal chamfer, shortening both the incoming
    and outgoing segments by *chamfer_offset*.

    Layer transitions (vias) are never chamfered.  Start and end points
    are preserved unchanged.  Segments shorter than ``2 * chamfer_offset``
    on either side of a turn skip chamfering.
    """
    if len(path_points) <= 2:
        return list(path_points)

    result: list[tuple[float, float, str]] = [path_points[0]]

    for i in range(1, len(path_points) - 1):
        prev = path_points[i - 1]
        curr = path_points[i]
        nxt = path_points[i + 1]

        if prev[2] != curr[2] or curr[2] != nxt[2]:
            result.append(curr)
            continue

        lyr = curr[2]
        dx1 = curr[0] - prev[0]
        dy1 = curr[1] - prev[1]
        dx2 = nxt[0] - curr[0]
        dy2 = nxt[1] - curr[1]

        h1 = abs(dy1) < 1e-12 and abs(dx1) > 1e-12
        v1 = abs(dx1) < 1e-12 and abs(dy1) > 1e-12
        h2 = abs(dy2) < 1e-12 and abs(dx2) > 1e-12
        v2 = abs(dx2) < 1e-12 and abs(dy2) > 1e-12

        is_orthogonal = (h1 and v2) or (v1 and h2)
        if not is_orthogonal:
            result.append(curr)
            continue

        seg1_len = math.sqrt(dx1 * dx1 + dy1 * dy1)
        seg2_len = math.sqrt(dx2 * dx2 + dy2 * dy2)
        if seg1_len < 2.0 * chamfer_offset or seg2_len < 2.0 * chamfer_offset:
            result.append(curr)
            continue

        ux1 = dx1 / seg1_len
        uy1 = dy1 / seg1_len
        ux2 = dx2 / seg2_len
        uy2 = dy2 / seg2_len

        before = (curr[0] - ux1 * chamfer_offset, curr[1] - uy1 * chamfer_offset, lyr)
        after = (curr[0] + ux2 * chamfer_offset, curr[1] + uy2 * chamfer_offset, lyr)

        result.append(before)
        result.append(after)

    result.append(path_points[-1])
    return result
