"""Zone/pour emission and isolated-pad stitching for the router_v6 adapter.

Extracted from ``_adapter_convert.py`` (LOC cap paydown, ticket
temper-N7-cap5): ``_zone_layers_for_net``, ``_zone_params_for_net``,
``_CONTINUITY_EXEMPT_CLASSES``, ``_stitch_isolated_pads``,
``_emit_zone_pours``, and ``_chamfer_path_points`` all concern the same
seam -- deciding which nets get copper-pour treatment and shaping the
geometry that treatment emits -- distinct from ``_adapter_convert.py``'s
remaining ``route_pcb``/``_apply_placements_to_pcb``/
``_write_routes_to_content`` entry points. ``_adapter_convert.py``
re-imports every name here so existing import sites (``adapter.py``'s
``__all__`` re-exports, ``tests/router_v6/test_adapter.py``'s direct
``from temper_placer.router_v6._adapter_convert import ...``) are
unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

import temper_geometry as _tg

logger = logging.getLogger(__name__)

# U1: netclasses where clustering would fragment a continuous return/ground
# plane and undermine EMI/loop-area control for switching-power-supply nets.
# NOTE 2026-07-28: "GND" is currently dormant here -- _zone_layers_for_net()
# now drives zone eligibility from routing_strategy=="plane_required", which
# GND does not declare (only ACMains/HighVoltage do), so a GND net never
# reaches this membership check today (the zone-emission loop above skips
# it before this constant is consulted). Left in place rather than removed:
# it is not wrong, only unreachable under the current netclass SSOT, and
# would immediately reactivate if GND's routing_strategy is ever set to
# "plane_required" (e.g. per the pour audit's inner-layer-return-plane
# recommendation, docs/evidence/2026-07-28-pour-strategy-audit.md Task 3).
_CONTINUITY_EXEMPT_CLASSES = frozenset({"GND", "ACMains", "HighVoltage"})


def _zone_layers_for_net(net_name: str) -> list[str]:
    """Resolve the zone/pour layer(s) for a net from the netclass SSOT.
    Returns empty list for nets that don't get zone treatment.

    FIXED 2026-07-28: this used to hardcode its own 5-class eligibility
    list (``GND``, ``Power``, ``GateDrive``, ``HighVoltage``, ``ACMains``)
    instead of consulting ``NetClassRules.routing_strategy`` -- the
    project's own declared design intent, which marks only ``ACMains``
    and ``HighVoltage`` ``"plane_required"`` (``core/design_rules.py``).
    That drift is why ``Power`` (``+3V3``, ``vcc``, ``+15V``, ``+15V_LS``,
    ``V_BUS_SENSE``) and ``GateDrive`` (``GATE_HS``/``GATE_LS``/
    ``PWM_HS``/``PWM_LS``) nets carried zone pours the netclass metadata
    never requested -- see
    docs/evidence/2026-07-28-pour-strategy-audit.md Task 0. Driving
    eligibility from ``routing_strategy`` keeps this in step with the
    metadata by construction instead of by two hand-maintained lists
    happening to agree.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    nc_name = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    nc = TEMPER_NET_CLASSES.get(nc_name)
    if nc is not None and nc.routing_strategy == "plane_required":
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

    Wave 4: the point-in-polygon (``shapely.Polygon.contains``/``.touches``)
    and nearest-boundary-vertex (``scipy.spatial.cKDTree``) geometry
    delegates to ``temper_geometry.stitch_targets_py`` (see
    ``packages/temper-geometry/src/zone_pour.rs``). The netclass-SSOT
    eligibility check (``_zone_layers_for_net``) and tstamp/segment
    formatting stay here -- they are not geometry.
    """
    from temper_placer.router_v6._adapter_convert import _next_tstamp

    if tstamp_counter is None:
        tstamp_counter = [0]

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

        targets = _tg.stitch_targets_py(positions, [list(pts) for pts in zps])
        if not targets:
            continue

        trace_layer = (
            _zone_layers_for_net(net_name)[0] if _zone_layers_for_net(net_name) else "F.Cu"
        )

        for px, py, nearest_x, nearest_y in targets:
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

    Wave 4: delegates to ``temper_geometry.chamfer_path_points_py`` (pure
    f64 arithmetic, no external library; see
    ``packages/temper-geometry/src/zone_pour.rs``).
    """
    return _tg.chamfer_path_points_py(path_points, chamfer_offset)
