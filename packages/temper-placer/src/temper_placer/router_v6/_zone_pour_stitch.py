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
# UPDATE 2026-08-07 (R3/R4, docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md):
# "GND" was dormant here from 2026-07-28 through this fix -- GND declared no
# routing_strategy, so _zone_layers_for_net() (which now drives eligibility
# from routing_strategy) never let a GND net reach this membership check.
# core/design_rules.py's GND entry now sets routing_strategy="plane_preferred"
# (matching the human-authored temper_constraints.yaml SSOT, which already
# said so) and _zone_layers_for_net() now recognizes that tier -- so this
# entry is live again for PWR_RTN (GND's only member with committed zones).
# It was left in place rather than removed while dormant precisely so this
# reactivation would not require re-deriving it.
#
# UPDATE 2026-08-07 (R6, same plan): "HighVoltage" REMOVED from this set.
# Reproducing compute_zones_for_net() against the current board's real pad
# positions (docs/evidence/2026-08-07-zone-emission-clustering-defect.md)
# showed the exemption was not merely "generous" for this class -- every
# HighVoltage net whose pads are genuinely spread across the board (SW_NODE,
# DC_BUS_RTN, and more: +170V_BUS, zcd, w1_1/w1_2, tank.c_tank1-p2,
# power_in.ntc-no, discharge.k_dis1-nc/k_dis2-nc, hb.power_loop.q_high-g, a)
# produced a SINGLE convex hull covering 5-71% of the board per net,
# several exceeding the physical board outline outright (R6's own framing:
# "SW_NODE's existing hull covers 40% of board area"). This is the opposite
# of the class's own documented intent: TRACE_WIDTH_CALCULATIONS.md SS3.1
# says of the DC bus "multiple parallel traces or zones acceptable", and
# SS3.2 says of the switch node "keep switch node AREA minimal (EMI
# source)" -- clustering-exemption was never justified for this class in
# the first place, unlike GND/ACMains (see below). Un-exempting HighVoltage
# lets compute_zones_for_net() cluster it like every other class: measured
# 5-6 tight per-component hulls per net instead of one board-spanning hull,
# 88-94% smaller in aggregate area for SW_NODE/DC_BUS_RTN specifically, and
# each cluster still carries 12-34mm of hull width -- well over the 5-10mm
# minimum copper width TRACE_WIDTH_CALCULATIONS.md SS3.1-3.3 requires for
# this board's tank current (24.5A rms / 34.5A peak per the 2026-08-07
# part-stress/ZVS work). Electrical continuity of the net itself is
# unaffected: the zone is a supplemental pour on top of already-routed
# copper traces, not the net's only conductive path, so splitting the pour
# into per-cluster patches does not disconnect anything.
#
# GND and ACMains are NOT touched by this update. PWR_RTN (GND's only
# zoned member) is a genuine return-plane request (KD2 of the same plan:
# "plane_preferred" is a deliberate SSOT declaration, not an accident) and
# its measured hull, while large (60.5% of board), does not exceed the
# physical board outline -- a real oversizing concern, but a different one
# from R6's "board-spanning past the board edge" defect, and out of this
# fix's scope (R6 names SW_NODE/DC_BUS_RTN specifically; GND's plane-vs-
# clustered sizing is inner-layer/plane architecture, U2/R8, deferred).
# ac_l/ac_n (ACMains) measured 3.9%/7.0% of board, within the outline --
# not pathological today, left as-is.
_CONTINUITY_EXEMPT_CLASSES = frozenset({"GND", "ACMains"})


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

    FIXED 2026-08-07 (R4, docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md):
    also recognize ``"plane_preferred"``, not only ``"plane_required"``.
    ``routing_strategy`` has four documented values
    (``netclass_rules_gen.py``'s field comment: ``plane_required``,
    ``plane_preferred``, ``wide_trace``, ``standard``) but this check only
    ever branched on one of them. ``GND`` declares ``"plane_preferred"``
    (paired fix: ``core/design_rules.py``'s ``GND`` entry, R3) -- without
    this half of the pair, ``GND``'s corrected SSOT field would still be
    silently ignored here, reproducing the exact accident R3-R5 exist to
    fix. In practice this changes eligibility for exactly one net on the
    production board: ``PWR_RTN`` (``GND``'s only member with committed
    zones today; ``CGND`` carries none regardless -- R5).

    NOT CHANGED 2026-08-11 (In2.Cu power islands, feat/in2cu-power-islands),
    and deliberately so -- see ``router_v6/_power_islands.py``'s module
    docstring for the full reasoning. The obvious-looking fix (grant the
    ``"Power"`` netclass -- whose only members are exactly ``+3V3``,
    ``+15V``, ``vcc``, ``V_BUS_SENSE`` -- an ``"In2.Cu"`` branch here,
    driven by ``routing_strategy`` same as GND's R3/R4 fix above) was
    prototyped and reverted: ``Power`` staying trace-only (no default pour
    of any kind) is an already-landed, evidence-corroborated, actively
    tested decision (R1/R7,
    docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md --
    ``TestZoneLayersForNet.test_power_class_is_not_zone_eligible`` and
    roughly a dozen other fixtures across ``tests/router_v6/test_adapter.py``
    were deliberately re-written 2026-07-28/2026-07-30 to stop assuming
    ``vcc``/``+3V3`` are zone-eligible), not an accidental gap like GND's
    was. Flipping it back here would silently revert that fix for every
    production ``route_pcb()`` call, not just add an In2.Cu option.
    ``_power_islands.py`` instead follows the same precedent
    ``_ground_plane.py`` already set for ``In1.Cu``/``gnd``: a standalone
    generator that calls the zone-emission primitives
    (``zone_emission.compute_zones_for_net``/``emit_zone_s_expr``)
    directly, never going through this function at all -- so the inner
    layer becomes expressible without touching this function's return
    value for any net class.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    nc_name = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    nc = TEMPER_NET_CLASSES.get(nc_name)
    if nc is not None and nc.routing_strategy in ("plane_required", "plane_preferred"):
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
    pcb: Any = None,
) -> None:
    """Emit filled-copper zone geometry for all zone-eligible nets.

    ``tstamp_counter``: see ``_stitch_isolated_pads`` -- threaded through
    so the isolated-pad stitch segments this function emits (via
    ``_stitch_isolated_pads``) continue the same deterministic tstamp
    sequence as the caller's other segments/vias.

    ``pcb``: the ``ParsedPCB`` the caller already has (``result.pcb`` in
    ``_write_routes_to_content``), used only to resolve the board outline
    so every emitted hull can be clipped to it (R6,
    docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md --
    ``zone_emission.compute_zones_for_net``'s ``board_polygon`` argument).
    ``None`` (the default, and every existing call site before this
    change) disables clipping and reproduces the prior unclipped
    behavior -- callers that don't have a ``ParsedPCB`` handy (e.g. unit
    tests constructing pad positions directly) are unaffected.
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

    board_polygon = None
    if pcb is not None:
        from temper_placer.router_v6.routing_space import _get_board_polygon

        try:
            board_polygon = _get_board_polygon(pcb)
        except Exception:
            # Board outline resolution is best-effort here: a malformed or
            # missing board geometry should degrade to "no clip" (prior
            # behavior), not break zone emission outright.
            board_polygon = None
        if board_polygon is not None and (
            not hasattr(board_polygon, "is_empty") or board_polygon.is_empty
        ):
            board_polygon = None

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
                        board_polygon=board_polygon,
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
