"""Router V6: copper-pour eligibility, geometry and emission.

Which nets get a pour, with what margin and clearance, how isolated pads on
those nets are stitched into it, and how the resulting zones are written back
into a board file. Split out of _adapter_convert.py, which had grown past its
size cap (ticket temper-N7-cap5).

``_next_tstamp`` is imported inside ``_stitch_isolated_pads`` rather than at
module scope: _adapter_convert imports this module for ``_emit_zone_pours``,
so a module-level import back into it would be a cycle. Deferring it is the
same pattern used elsewhere in this package for exactly this reason.
"""

from typing import Any


def _zone_layers_for_net(net_name: str) -> list[str]:
    """Resolve the zone/pour layer(s) for a net from the netclass SSOT.
    Returns empty list for nets that don't get zone treatment."""
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS

    nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    if nc in ("GND", "Power", "GateDrive", "HighVoltage", "ACMains"):
        return ["F.Cu", "B.Cu"]
    return []


def _zone_params_for_net(net_name: str) -> tuple[float, float]:
    """Resolve per-netclass zone margin and clearance from DesignRules."""
    from temper_placer.core.design_rules import (
        TEMPER_NET_ASSIGNMENTS,
        TEMPER_NET_CLASSES,
    )

    nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    rules = TEMPER_NET_CLASSES.get(nc)
    if rules is not None:
        # Bounded by clearance -- the project's own authoritative safety
        # constant for ACMains/HighVoltage (SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
        # in design_rules.py). The previous trace_width * 10.0 heuristic
        # produced a 25-30mm zone-boundary expansion for those classes on a
        # ~100-150mm board -- an arbitrary multiple with no principled bound.
        # NOTE: investigation on 2026-07-21 found the oversized margin does
        # NOT explain the PR #263 shorting_items increase (0 of 85 shorting
        # violations on the production board involved a zone at all -- see
        # docs/plans or session notes for the measurement). This change is
        # kept on its own merits: bounding margin by clearance is principled,
        # trace_width * 10.0 was not.
        margin = rules.clearance
        clearance = rules.clearance
    else:
        margin = 0.3
        clearance = 0.3
    return margin, clearance


# U1: netclasses where clustering would fragment a continuous return/ground
# plane and undermine EMI/loop-area control for switching-power-supply nets.
_CONTINUITY_EXEMPT_CLASSES = frozenset({"GND", "ACMains", "HighVoltage"})


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

    from temper_placer.core.design_rules import (
        TEMPER_NET_ASSIGNMENTS,
    )

    for net_name, positions in pad_positions.items():
        nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
        if nc not in ("GND", "Power", "GateDrive", "HighVoltage", "ACMains"):
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


def _emit_zone_pours(
    pad_positions: dict[str, list[tuple[float, float]]],
    segments: list[str],
    net_name_to_number: dict[str, int],
    *,
    design_rules: Any = None,
    tstamp_counter: list[int] | None = None,
) -> None:
    """Emit filled-copper zone geometry for all zone-eligible nets.

    ``tstamp_counter``: see ``_stitch_isolated_pads`` -- threaded through
    so the isolated-pad stitch segments this function emits (via
    ``_stitch_isolated_pads``) continue the same deterministic tstamp
    sequence as the caller's other segments/vias.
    """
    from temper_placer.core.design_rules import (
        TEMPER_NET_ASSIGNMENTS,
        TEMPER_NET_CLASSES,
    )
    from temper_placer.router_v6.zone_emission import (
        ZoneDefinition,
        compute_zones_for_net,
        emit_zone_s_expr,
    )

    zone_netclasses: set[str] = set()
    for net_name in pad_positions:
        if _zone_layers_for_net(net_name):
            nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
            if nc:
                zone_netclasses.add(nc)

    effective_clearance: dict[str, float] = {}
    class_pairs = getattr(design_rules, "class_pairs", {}) or {}
    for nc in zone_netclasses:
        own_rules = TEMPER_NET_CLASSES.get(nc)
        own_clearance = own_rules.clearance if own_rules else 0.3
        eff = own_clearance
        for other_nc in zone_netclasses:
            if other_nc == nc:
                continue
            pair_key = tuple(sorted((nc, other_nc)))
            if pair_key in class_pairs:
                pair_clearance = class_pairs[pair_key].get("clearance", eff)
                eff = max(eff, pair_clearance)
            else:
                other_rules = TEMPER_NET_CLASSES.get(other_nc)
                other_clearance = other_rules.clearance if other_rules else 0.3
                eff = max(eff, max(own_clearance, other_clearance))
        effective_clearance[nc] = eff

    _MAX_DRU_PRIORITY = max(
        (r.dru_priority for r in TEMPER_NET_CLASSES.values()),
        default=90,
    )
    zone_priority: dict[str, int] = {}
    for nc in zone_netclasses:
        rules = TEMPER_NET_CLASSES.get(nc)
        dru_p = rules.dru_priority if rules else 0
        zone_priority[nc] = _MAX_DRU_PRIORITY - dru_p

    zone_points_by_net: dict[str, list[tuple[tuple[float, float], ...]]] = {}
    for net_name, positions in pad_positions.items():
        zone_layers = _zone_layers_for_net(net_name)
        if not zone_layers:
            continue
        net_num = net_name_to_number.get(net_name, 0)
        if net_num > 0 and positions:
            nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
            eff_clearance = effective_clearance.get(nc, 0.3)
            prio = zone_priority.get(nc, 0)
            exempt = nc in _CONTINUITY_EXEMPT_CLASSES

            for layer in zone_layers:
                try:
                    margin, _clearance = _zone_params_for_net(net_name)
                    zds = compute_zones_for_net(
                        net_name,
                        net_num,
                        positions,
                        layer=layer,
                        margin=margin,
                        cluster=not exempt,
                    )
                    for zd in zds:
                        zd = ZoneDefinition(
                            net_name=zd.net_name,
                            net_number=zd.net_number,
                            layer=zd.layer,
                            points=zd.points,
                            clearance=eff_clearance,
                            min_thickness=zd.min_thickness,
                            priority=prio,
                        )
                        segments.append(emit_zone_s_expr(zd))
                        zone_points_by_net.setdefault(net_name, []).append(zd.points)
                except ValueError:
                    pass

    _stitch_isolated_pads(
        pad_positions,
        segments,
        net_name_to_number,
        zone_points_by_net,
        tstamp_counter=tstamp_counter,
    )
