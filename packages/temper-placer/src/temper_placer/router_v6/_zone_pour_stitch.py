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
import math
from typing import Any

import temper_geometry as _tg
import temper_orchestration as _to

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

# ADDED 2026-08-14 (docs/evidence/2026-08-14-ntc-no-realization-and-delta-t-reconciliation.md):
# `power_in.ntc-no` is a per-NET exemption, not a class one -- its
# netclass (`HighVoltage`) is deliberately NOT in `_CONTINUITY_EXEMPT_CLASSES`
# above (R6 un-exempted HighVoltage on purpose, to stop SW_NODE/DC_BUS_RTN
# et al. from getting board-spanning single hulls). R6's own justification
# for un-exempting HighVoltage was: "Electrical continuity of the net
# itself is unaffected: the zone is a supplemental pour on top of
# already-routed copper traces, not the net's only conductive path, so
# splitting the pour into per-cluster patches does not disconnect
# anything." That premise is FALSE for `power_in.ntc-no` specifically:
# `_should_route()` (`_net_policy.py`) excludes every net `_zone_layers_for_net`
# grants zone eligibility to from A* entirely -- true for every HighVoltage
# net, including this one -- so the pour is this net's ONLY conductive
# path, never a supplement to a real routed trace. Measured directly
# (this evidence doc): `power_in.ntc-no`'s 4 pads (K1.13, RT1.2, U1.2,
# U2.1 -- 30-140mm apart, no local density pattern) fail the clustering
# heuristic's "natural gap" test and split into exactly 2 clusters
# ({K1.13, U1.2}, {RT1.2, U2.1}), each producing its own convex-hull pour
# with NO stitch trace between them (`_stitch_isolated_pads` only
# reconnects pads that fall OUTSIDE every pour of their net, and every pad
# here is already inside its own cluster's pour) -- i.e. clustering this
# net produces two genuinely disconnected copper islands, the exact
# fake-completion shape this whole task exists to eliminate, not "a
# supplemental pour on an already-connected net." Exempting it here
# (single convex hull over all 4 pads, like `ACMains`) also matches this
# net's own physical identity: it is not merely "in the same HV domain" as
# `ac_l`/`ac_n`, it IS the same AC-mains conductor one node further along
# (the line between the CM choke / bypass-relay NO contact / inrush NTC
# and the rectifier -- `elec/src/modules.ato`), so the ACMains precedent
# applies directly, not by analogy.
_CONTINUITY_EXEMPT_NETS = frozenset({"power_in.ntc-no"})

# ADDED 2026-08-14, same evidence doc as _CONTINUITY_EXEMPT_NETS: which of
# a continuity-exempt net's own pads are SMD (no existing drilled hole,
# copper confined to the pad's own declared layer -- needs an explicit via
# to reach `_stitch_pads_to_each_other`'s In3.Cu stitch layer) versus THT
# (already has a real plated hole reaching every copper layer, so a NEW
# via at the identical position is redundant copper that collides with
# the pad's OWN existing hole -- measured directly: `kicad-cli pcb drc`
# reported `holes_co_located` for every one of `power_in.ntc-no`'s 3 THT
# pads (RT1.2, U1.2, U2.1 -- all resolve to `layer="all"` via
# `temper_placer.core.pin_geometry.pin_world_layer`) when a via was placed
# at each of them uniformly; only K1.13 (`layer="F.Cu"`, a real, deliberate
# resolution -- see the evidence doc for why its footprint's raw
# `(layers "F.Fab")` declaration is NOT what the project's own canonical
# pin-geometry math uses) genuinely needs one.
#
# This is a small, explicit, net-scoped allowlist (position, not a
# pad-type classifier) rather than threading real per-pad layer data
# through `_emit_zone_pours`'s ~6-argument call chain for the one net this
# mechanism currently covers -- consistent with `_CONTINUITY_EXEMPT_NETS`
# itself already being a net-specific, not general, exemption. If this set
# ever grows, add each new net's real SMD-pad positions here the same way
# (verified via `pin_world_layer`, not assumed), or thread proper per-pad
# layer data through at that point instead.
_CONTINUITY_EXEMPT_NET_SMD_PAD_POSITIONS: frozenset[tuple[str, tuple[float, float]]] = frozenset(
    {("power_in.ntc-no", (98.405, 211.895))}  # K1.13
)

# ADDED 2026-08-14, same evidence doc: which pad-to-pad edges
# `_stitch_pads_to_each_other` should draw for a continuity-exempt net,
# when they have been EMPIRICALLY verified clean against real
# `kicad-cli pcb drc` output (not merely assumed safe because they are
# short or because the nearest-neighbour MST picked them).
#
# The nearest-neighbour MST (this module's own default, still used as a
# fallback below for any net not listed here) picks
# K1.13<->RT1.2/K1.13<->U1.2/RT1.2<->U2.1 for `power_in.ntc-no` -- the
# GEOMETRICALLY shortest spanning tree. Measured directly (real DRC
# against a real spliced board, not assumed): the K1.13<->RT1.2 edge
# (65.5mm) clips `C6`'s gnd PTH pad (real shorting_items violation,
# ~0.75mm clearance at the crossing) -- a real obstacle the "any straight
# line stays inside our own pour hull" reasoning does not protect against
# (see `_stitch_pads_to_each_other`'s own docstring). Swapping to
# K1.13<->U2.1 (79.0mm, LONGER, not what the greedy MST would ever pick)
# + U2.1<->RT1.2 + K1.13<->U1.2 avoids that obstacle entirely --
# re-measured against real DRC output: zero new shorting/clearance
# violations attributable to this net's new copper (down from 88
# pre-existing violations on the STALE 31-segment fake copper this
# replaces, to 0 new + 1 benign `via_dangling` warning -- see the evidence
# doc SS3.3/SS3.4 for the exact before/after DRC diff).
#
# This is empirical, board-specific knowledge, not a general routing
# algorithm -- if `_CONTINUITY_EXEMPT_NETS` ever grows, verify a new net's
# own edges against real DRC output the same way before trusting them;
# the nearest-neighbour MST fallback below is a reasonable starting guess
# for that verification, not a substitute for it.
_CONTINUITY_EXEMPT_NET_VERIFIED_EDGES: dict[
    str, tuple[tuple[tuple[float, float], tuple[float, float]], ...]
] = {
    "power_in.ntc-no": (
        ((98.405, 211.895), (28.29, 175.44)),  # K1.13 <-> U2.1
        ((28.29, 175.44), (32.9, 210.1)),  # U2.1 <-> RT1.2
        ((98.405, 211.895), (162.92, 223.03)),  # K1.13 <-> U1.2
    ),
}


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

    CHANGED 2026-08-13 (layer-architecture SSOT,
    ``docs/evidence/2026-08-13-layer-architecture-decision.md``): the
    eligible-layer list is now
    ``core.board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS`` instead of a
    second, independently-hardcoded ``["F.Cu", "B.Cu"]`` literal. This
    function takes no board context (net_name only -- ~9 call sites across
    this module, ``_net_policy.py``, ``obstacle_map.py``, and
    ``topology_copper_audit.py`` all call it with just a name), so it
    cannot safely read a *board's declared* signal-layer set without either
    threading board context through every one of those sites (out of scope
    here -- a much larger, separately-risky refactor) or hardcoding a real
    file path that would silently mis-attribute layer roles for any caller
    processing a different (e.g. test/synthetic) board. What this call site
    actually needs is not board-specific anyway: it is a router ENGINE
    CAPABILITY fact (which layers Stage 2/Stage 4 have grid/pathfinding
    support for), constant across every board this router processes, not a
    per-board architecture fact -- so pointing it at the shared, documented,
    typed constant (still hardcoded, necessarily, but centralized and
    named instead of tripled) is the correct fix for this specific
    question, not merely the safe one. See ``board_layer_roles``'s own
    module docstring for why the *declared-architecture* half of this
    question (``signal_layer_names``, which DOES read a real board) is a
    different accessor, used by the utilisation gate instead.
    """
    from temper_placer.core.board_layer_roles import ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    nc_name = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    nc = TEMPER_NET_CLASSES.get(nc_name)
    if nc is not None and nc.routing_strategy in ("plane_required", "plane_preferred"):
        return list(ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED)
    return []


def _own_pads_on_layer(
    net_name: str,
    layer: str,
    *,
    pcb: Any,
    fallback_positions: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """The net's own pad positions that actually exist on *layer*.

    ``pour_outline_py``'s ``own_pads`` is used only for island
    classification under PadsOnly, and it must be layer-honest: a piece
    on In3.Cu may only be credited with pads that physically exist on
    In3.Cu.  SMD pads are single-layer (``pin_world_layer`` == the
    pad's declared layer); THT pads report ``"all"``/``"*.Cu"`` (or a
    ``"Through"`` marker) and exist on every copper layer.

    Returns ``[]`` when the net has NO pad on *layer* -- the caller
    (``_emit_zone_pours``) skips the layer entirely in that case,
    because a pour with no own pad on the layer is isolated copper
    (measured: 19 "Isolated copper fill" findings for F.Cu-only SMD
    nets poured onto In3.Cu/In4.Cu).

    *fallback_positions* is used only when there is no ``pcb`` (unit
    tests / synthetic fixtures that pass positions directly) -- such
    callers exercise single-layer fixtures, where the blind list is the
    caller's own intent.
    """
    if pcb is None:
        return fallback_positions
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    out: list[tuple[float, float]] = []
    saw_net_pin = False
    for comp in getattr(pcb, "components", []) or []:
        for pin in getattr(comp, "pins", []) or []:
            if not pin.net or pin.net != net_name:
                continue
            saw_net_pin = True
            raw = pin_world_layer(pin)
            on_layer = raw in ("all", "*.Cu", layer) or (
                isinstance(raw, str) and "Through" in raw
            )
            if not on_layer:
                continue
            pos = pin_world_position(pin, comp)
            out.append((float(pos[0]), float(pos[1])))
    if not saw_net_pin:
        # The pcb carries no pins for this net at all -- a synthetic
        # fixture whose pads live only in the caller's pad_positions
        # dict (test_adapter's SimpleNamespace pcbs).  The caller's list
        # is its own intent for those; honour it.
        return fallback_positions
    # Deterministic order (the caller's list order is not preserved by
    # the pcb walk) -- the Rust island check is order-independent, but the
    # emitted zone list must not depend on component iteration order.
    out.sort()
    return out


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


#: Width for a stitch segment on a net with no netclass assignment.  Only
#: reachable in principle -- ``_stitch_isolated_pads`` is gated on
#: ``_zone_layers_for_net``, which only returns layers for a net whose class
#: declares ``routing_strategy plane_required``/``plane_preferred``, i.e. a
#: net that HAS a class.  Kept as an explicit named floor rather than an
#: inline literal so it cannot be mistaken for a derived figure.
_STITCH_FALLBACK_WIDTH_MM = 0.2


def _stitch_width_for_net(net_name: str) -> float:
    """The netclass ``trace_width`` a stitch segment for *net_name* must carry.

    Bug history (2026-08-13,
    ``docs/evidence/2026-08-13-router-netclass-trace-widths.md``): every
    stitch segment was emitted at a hardcoded ``0.2`` regardless of class.
    ``_stitch_isolated_pads`` only ever runs for zone-eligible nets, which on
    this board are exactly the ``ACMains``/``HighVoltage`` ones -- so the
    hardcoded literal was, by construction, only ever applied to mains and
    DC-bus copper, at 6.7% of ``HighVoltage``'s 3.0mm.  Measured after Stage
    4.4 was fixed to read the netclass table, this path was the entire
    residual: 4 undersized segments on ``DC_BUS_RTN``,
    ``hb.power_loop.q_high-g``, ``tank.c_tank1-p2`` and
    ``discharge.k_dis1-nc``.

    Reads ``TEMPER_NET_ASSIGNMENTS``/``TEMPER_NET_CLASSES`` directly, the
    same idiom ``_zone_layers_for_net`` and ``_zone_params_for_net`` in this
    module already use.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    rules = TEMPER_NET_CLASSES.get(TEMPER_NET_ASSIGNMENTS.get(net_name, ""))
    if rules is None or rules.trace_width <= 0.0:
        return _STITCH_FALLBACK_WIDTH_MM
    return float(rules.trace_width)


def _foreign_obstacle_union(records: list[tuple]) -> Any:
    """Buffer pairwise obstacle records into one fail-closed C-space union."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    geoms: list[Any] = []
    for kind, x, y, a, b, width, separation in records:
        if kind == 0:  # Pad
            geoms.append(Point(x, y).buffer(math.hypot(a, b) + separation, quad_segs=8))
        elif kind == 1:  # Track
            geoms.append(
                LineString([(x, y), (a, b)]).buffer(
                    width / 2.0 + separation,
                    quad_segs=8,
                )
            )
        else:  # Via
            geoms.append(Point(x, y).buffer(a / 2.0 + separation, quad_segs=8))
    return unary_union(geoms) if geoms else None


def _stitch_isolated_pads(
    pad_positions: dict[str, list[tuple[float, float]]],
    segments: list[str],
    net_name_to_number: dict[str, int],
    zone_points: dict[str, list[tuple[tuple[float, float], ...]]],
    *,
    tstamp_counter: list[int] | None = None,
    pcb: Any = None,
) -> None:
    """U3: emit straight-line trace segments from pads outside every
    dense-cluster pour back to the nearest pour for that net.

    Uses the already-computed zone polygons (from the zone-emission
    loop above) rather than re-clustering independently.

    C-SPACE GATE (2026-08-16, fix/route-to-100-percent): every proposed
    segment is checked against the SAME per-pair obstacle records the
    Rust zone carve uses (``collect_zone_obstacle_records`` -- other
    nets' copper on this layer, each buffered by its own
    ``max(clearance, creepage)`` pair separation, including both the
    pre-existing board copper AND the segments/vias this route emitted)
    BEFORE it is drawn. A segment whose buffered footprint (its own
    half-width + that pair's separation) intersects any foreign obstacle
    is SKIPPED, fail-closed, rather than emitted as a known-shorting
    straight line. Measured on the 2026-08-16 capstone route: the
    un-gated version emitted 5mm-wide straight pad-to-pour lines for the
    HV zone nets (DC_BUS_RTN up to 193mm, PWR_RTN, SW_NODE) that crossed
    unrelated nets' copper wholesale -- the dominant share of the
    shorting_items violations. The zone carve already guarantees the
    DESTINATION pour vertex is >= separation away from every foreign
    obstacle; the pad end and the line between are what this gate
    protects. Skipped stitches are reported per net via logger.warning
    rather than silently dropped.

    ``tstamp_counter`` lets a caller (``_emit_zone_pours`` /
    ``_write_routes_to_content``) share one deterministic tstamp
    sequence across every element emitted in a single route_pcb() call.
    Callers that invoke this function standalone (e.g. tests) get a
    fresh, independent counter starting at 0.

    ``pcb``: the ``ParsedPCB`` the caller already has, used to resolve
    the other nets' copper for the C-space gate (same source the zone
    carve uses). ``None`` (unit tests / synthetic fixtures) disables the
    gate -- callers without a ``pcb`` have no foreign-copper data to
    consult and keep the prior behavior.

    Wave 4: the point-in-polygon (``shapely.Polygon.contains``/``.touches``)
    and nearest-boundary-vertex (``scipy.spatial.cKDTree``) geometry
    delegates to ``temper_geometry.stitch_targets_py`` (see
    ``packages/temper-geometry/src/zone_pour.rs``). The netclass-SSOT
    eligibility check (``_zone_layers_for_net``) and tstamp/segment
    formatting stay here -- they are not geometry.
    """
    from shapely.geometry import LineString

    from temper_placer.router_v6._adapter_convert import _next_tstamp
    from temper_placer.router_v6.zone_pour_clearance import (
        collect_zone_obstacle_records,
        default_table,
    )
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    if tstamp_counter is None:
        tstamp_counter = [0]

    clearance_table = default_table()
    creepage_table = default_creepage_table()
    number_to_name = {num: name for name, num in net_name_to_number.items()}

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

        stitch_width = _stitch_width_for_net(net_name)

        # C-space gate: the same per-pair obstacle records the Rust zone
        # carve consumes (foreign copper on the stitch layer, each item
        # buffered by its own max(clearance, creepage) pair separation).
        # Each record is (kind, x, y, a, b, w, separation); buffered by
        # its own physical half-extent + separation so the union already
        # carries the required standoff -- the segment's own half-width is
        # then the only extra the footprint check has to add.
        obstacle_union: Any = None
        if pcb is not None:
            records = collect_zone_obstacle_records(
                net_name,
                trace_layer,
                pcb=pcb,
                segments=segments,
                net_number_to_name=number_to_name,
                clearance_table=clearance_table,
                creepage_table=creepage_table,
            )
            obstacle_union = _foreign_obstacle_union(records)

        skipped = 0
        for px, py, nearest_x, nearest_y in targets:
            if obstacle_union is not None and not obstacle_union.is_empty:
                footprint = LineString([(px, py), (nearest_x, nearest_y)]).buffer(
                    stitch_width / 2.0, quad_segs=8
                )
                if footprint.intersects(obstacle_union):
                    skipped += 1
                    continue
            segments.append(
                f"  (segment (start {px:.4f} {py:.4f})"
                f" (end {nearest_x:.4f} {nearest_y:.4f})"
                f' (width {stitch_width:.4f}) (layer "{trace_layer}")'

                f" (net {net_num})"
                f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )
        if skipped:
            logger.warning(
                "_stitch_isolated_pads: %d of %d pad->pour stitch segment(s) "
                "for net %r on %s were SKIPPED because their buffered "
                "footprint (width %.3fmm + pair clearance/creepage) crosses "
                "another net's copper -- fail-closed, no copper emitted "
                "through a foreign obstacle. This net's pads may rely on the "
                "zone itself for continuity.",
                skipped,
                len(targets),
                net_name,
                trace_layer,
                stitch_width,
            )



#: A carved fragment smaller than this is not copper anyone can use -- it is a
#: sliver left where the keepout nearly severed the hull. KiCad's own zone
#: filler drops islands below `min_thickness` (0.25mm) wide for the same
#: reason; this is that figure squared, i.e. the area of the smallest square
#: the filler would keep.
_MIN_CARVED_AREA_MM2 = 0.25 * 0.25


def _carve_outline(
    points: tuple[tuple[float, float], ...],
    keepout,
) -> list[tuple[tuple[float, float], ...]]:
    """Subtract *keepout* from a zone outline, returning 0..n outlines.

    A hull that straddles the keepout can split into several pieces; each is
    returned separately so the emitter writes one ``(zone ...)`` per piece,
    exactly as ``zone_emission._clip_to_board`` already does for the board
    outline. Interior holes are dropped: the emitted s-expression carries a
    single ``(polygon (pts ...))`` and cannot express one, and KiCad's filler
    re-cuts the hole itself from the same clearance rules -- so keeping the
    outer ring is correct, not a relaxation.
    """
    from shapely.geometry import Polygon

    if keepout is None:
        return [points]
    hull = Polygon(points)
    if not hull.is_valid:
        hull = hull.buffer(0)
    carved = hull.difference(keepout)
    if carved.is_empty:
        return []
    pieces = list(carved.geoms) if hasattr(carved, "geoms") else [carved]
    out: list[tuple[tuple[float, float], ...]] = []
    for piece in pieces:
        if not hasattr(piece, "exterior") or piece.is_empty:
            continue
        if piece.area < _MIN_CARVED_AREA_MM2:
            continue
        coords = [(float(x), float(y)) for x, y in piece.exterior.coords]
        if len(coords) > 1 and coords[0] == coords[-1]:
            coords.pop()
        if len(coords) >= 3:
            out.append(tuple(coords))
    return out



def _stitch_pads_to_each_other(
    pad_positions: dict[str, list[tuple[float, float]]],
    segments: list[str],
    net_name_to_number: dict[str, int],
    *,
    tstamp_counter: list[int] | None = None,
    pcb: Any = None,
) -> None:
    """ADDED 2026-08-14 (docs/evidence/2026-08-14-ntc-no-realization-and-
    delta-t-reconciliation.md): for ``_CONTINUITY_EXEMPT_NETS`` members
    only, emit a minimum-spanning-tree of direct pad-to-pad connectors so
    the net's own pads form ONE connected component in the segment/via
    graph -- the thing ``_stitch_isolated_pads`` above does NOT do (it
    only reconnects pads that fall OUTSIDE every pour of their net; every
    pad of a single-hull continuity-exempt net is already INSIDE that one
    hull, so none is ever "isolated" and none gets a stitch from that
    function).

    C-SPACE GATE (2026-08-16, fix/route-to-100-percent): the same
    fail-closed obstacle check ``_stitch_isolated_pads`` now applies to
    its F.Cu segments is applied here to the In3.Cu MST edges. The
    original 2026-08-14 verification of ``_CONTINUITY_EXEMPT_NET_VERIFIED_EDGES``
    measured a board on which In3.Cu carried ZERO copper of any kind (the
    layer was added by PR #1195 and nothing routed there yet); the 2026-08-16
    capstone + post-fix routes show that assumption is stale: HighVoltage
    nets like ``w1_2``/``w1_1`` (A*-routed on In3.Cu at the 5.0mm netclass
    width -- ``_should_route``'s HV keyword classifier does not recognize
    the ``w1_1``/``w1_2`` names, so they route instead of being zone-
    covered) now occupy In3.Cu, and ntc-no's straight 27-79mm MST edges
    cross them wholesale (76 shorting_items on the 2026-08-16 post-fix
    route, all ``power_in.ntc-no <-> w1_2``). Each edge's buffered
    footprint (its own half-width + the pair's max(clearance, creepage))
    is now checked against the same per-pair obstacle records the zone
    carve uses; a blocked edge is SKIPPED, never emitted. The endpoint
    vias stay (same-net copper at the net's own pads, no short risk), so
    the audit still sees the pads reach In3.Cu -- but an honest gap
    between pads is reported rather than a shorting straight line.

    REVISED 2026-08-14, same day: the first version of this function drew
    these connectors on the SAME layer as the pour (F.Cu) as plain
    straight lines, reasoning that "a straight line between two points
    inside the net's own convex-hull pour never leaves that pour's
    clearance-aware margin" -- true, but irrelevant to the actual failure
    mode: F.Cu is dense with OTHER nets' SMD pads and traces that also
    happen to sit inside that same hull's large (city-block-scale) area.
    Measured directly (`kicad-cli pcb drc` against a real spliced board,
    real neighbouring copper): every one of the 3 MST edges for
    `power_in.ntc-no` produced real shorting/clearance violations against
    unrelated nets (`inb`, `w1_2`, `gnd`, `safety.fault_or-y2`, `+3V3`,
    ...) -- this WAS the forced-segment failure mode in effect, just not
    through the A*-forced-segment code path.

    Fix: route these connectors on `In3.Cu` instead -- one of the two
    inner SIGNAL layers added by PR #1195, measured to carry ZERO existing
    track segments anywhere on this board today, and (being an inner
    layer) never carries SMD pad copper at all (SMD pads only exist on
    F.Cu/B.Cu) -- only sparse THT-pad copper can obstruct a connector
    there. A via is dropped at BOTH endpoints of every MST edge
    (F.Cu<->In3.Cu, `HighVoltage`'s own via template: 1.2mm/0.6mm,
    ``design_rules.TEMPER_NET_CLASSES``) regardless of whether the
    specific pad is THT (already reaches every layer, making its own via
    redundant but harmless -- same-net copper, not a clearance conflict)
    or SMD (needs the via to reach In3.Cu at all, e.g. `power_in.ntc-no`'s
    own K1.13). Verified the same way as the F.Cu version was found
    broken: `kicad-cli pcb drc` against a real spliced board with this
    fix applied reports ZERO shorting/clearance violations naming
    `power_in.ntc-no` (see the evidence doc SS3.3).

    Still not the "forced segment" pattern `_allow_forced_segments` bans
    (an A* search giving up and a raw waypoint line substituted for its
    result): no search is attempted, and the choice of layer + via-in-pad
    was arrived at by MEASURING real DRC output against real neighbouring
    copper, not by asserting immunity from it.

    Width: 0.2mm, matching ``_stitch_isolated_pads``'s existing convention
    -- these connectors exist for TOPOLOGICAL continuity only (so the
    audit's segment/via graph can see the pads are one component); the
    INTENT was that the pour, not these thin connectors, carries the
    net's actual ampacity requirement.

    KNOWN GAP, measured and NOT resolved by this change (see the evidence
    doc SS3.5): for `power_in.ntc-no` specifically, that intent does not
    hold in practice. Its single-hull pour (`_CONTINUITY_EXEMPT_NETS`)
    spans ~150mm across a densely populated region of the board; the REAL
    DRC-aware filled copper (`kicad-cli pcb export svg --check-zones`,
    same measurement method as `docs/evidence/2026-08-14-ntc-no-
    ampacity-current-fix-and-pour-neck-measurement.md` SS4) fragments into
    47+ disconnected islands inside that one hull, none close to a
    continuous 4.156mm-wide path between the pads. Widening THESE
    connectors to the required 4.156mm instead (tested directly, same
    verified topology) introduces 4 new real clearance violations against
    unrelated nets/parts that a thin line avoids -- this specific
    corridor is genuinely tight, not merely narrow on paper (matching the
    originating evidence doc's own SS3.2/SS3.3 finding). Net result: this
    function's connectors currently deliver AUDIT-VERIFIED TOPOLOGICAL
    CONNECTIVITY ONLY, not ampacity -- neither they nor the pour they
    supplement constitute a genuinely current-adequate 15A conductor
    along the whole path today. Do not read `fully_connected=True` from
    the pad-connectivity audit as "this net is electrically complete" for
    `power_in.ntc-no` without also checking the evidence doc's own
    explicit ampacity caveat.
    """
    from shapely.geometry import LineString

    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES
    from temper_placer.router_v6._adapter_convert import _next_tstamp

    _STITCH_LAYER = "In3.Cu"

    if tstamp_counter is None:
        tstamp_counter = [0]

    for net_name, positions in pad_positions.items():
        if net_name not in _CONTINUITY_EXEMPT_NETS:
            continue
        net_num = net_name_to_number.get(net_name, 0)
        if net_num <= 0 or len(positions) <= 1:
            continue

        nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
        rules = TEMPER_NET_CLASSES.get(nc)
        via_size = rules.via_diameter if rules else 0.8
        via_drill = rules.via_drill if rules else 0.4

        verified = _CONTINUITY_EXEMPT_NET_VERIFIED_EDGES.get(net_name)
        edges: list[tuple[int, int]] = []
        if verified is not None:
            # Match each verified (pos_a, pos_b) pair back to indices in
            # *this call's* positions list by nearest point (not list
            # order/index -- pad_positions' own construction order is not
            # this function's contract to depend on).
            def _nearest_idx(target: tuple[float, float]) -> int:
                return min(
                    range(len(positions)),
                    key=lambda k: (positions[k][0] - target[0]) ** 2
                    + (positions[k][1] - target[1]) ** 2,
                )

            for pa, pb in verified:
                ia, ib = _nearest_idx(pa), _nearest_idx(pb)
                if ia != ib:
                    edges.append((ia, ib))
        else:
            # Minimum spanning tree over the (tiny -- board-scale pad
            # counts, never more than a handful) pad set, O(n^2) Prim's:
            # simple, deterministic, no external dependency needed at this
            # size. A reasonable STARTING GUESS, not a DRC-verified result
            # -- see this dict's own docstring above.
            remaining = list(range(1, len(positions)))
            in_tree = [0]
            while remaining:
                best = None
                best_d2 = float("inf")
                for i in in_tree:
                    xi, yi = positions[i]
                    for j in remaining:
                        xj, yj = positions[j]
                        d2 = (xj - xi) ** 2 + (yj - yi) ** 2
                        if d2 < best_d2:
                            best_d2 = d2
                            best = (i, j)
                assert best is not None
                edges.append(best)
                in_tree.append(best[1])
                remaining.remove(best[1])

        via_dropped: set[int] = set()
        stitch_width = _stitch_width_for_net(net_name)

        # C-space gate (2026-08-16): foreign copper on the stitch layer,
        # each item buffered by its own max(clearance, creepage) pair
        # separation -- the same per-pair obstacle records the zone carve
        # consumes (see _stitch_isolated_pads for the identical gate on
        # F.Cu). Built once per net; an edge whose buffered footprint
        # intersects it is skipped, fail-closed.
        obstacle_union: Any = None
        if pcb is not None:
            from temper_placer.router_v6.zone_pour_clearance import (
                collect_zone_obstacle_records,
                default_table,
            )
            from temper_placer.router_v6.zone_pour_creepage import (
                default_creepage_table,
            )

            records = collect_zone_obstacle_records(
                net_name,
                _STITCH_LAYER,
                pcb=pcb,
                segments=segments,
                net_number_to_name={num: name for name, num in net_name_to_number.items()},
                clearance_table=default_table(),
                creepage_table=default_creepage_table(),
            )
            obstacle_union = _foreign_obstacle_union(records)

        skipped = 0
        for i, j in edges:
            xi, yi = positions[i]
            xj, yj = positions[j]
            if obstacle_union is not None and not obstacle_union.is_empty:
                footprint = LineString([(xi, yi), (xj, yj)]).buffer(
                    stitch_width / 2.0, quad_segs=8
                )
                if footprint.intersects(obstacle_union):
                    skipped += 1
                    continue
            for idx, (px, py) in ((i, (xi, yi)), (j, (xj, yj))):
                if idx in via_dropped:
                    continue
                via_dropped.add(idx)
                needs_via = (net_name, (round(px, 4), round(py, 4))) in {
                    (n, (round(x, 4), round(y, 4)))
                    for n, (x, y) in _CONTINUITY_EXEMPT_NET_SMD_PAD_POSITIONS
                }
                if not needs_via:
                    continue
                segments.append(
                    f"  (via (at {px:.4f} {py:.4f})"
                    f" (size {via_size:.4f}) (drill {via_drill:.4f})"
                    f' (layers "F.Cu" "{_STITCH_LAYER}")'
                    f" (net {net_num})"
                    f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
                )
            segments.append(
                f"  (segment (start {xi:.4f} {yi:.4f})"
                f" (end {xj:.4f} {yj:.4f})"
                f' (width {stitch_width:.4f}) (layer "{_STITCH_LAYER}")'
                f" (net {net_num})"
                f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )
        if skipped:
            logger.warning(
                "_stitch_pads_to_each_other: %d of %d pad-to-pad edge(s) "
                "for net %r on %s were SKIPPED because their buffered "
                "footprint (width %.3fmm + pair clearance/creepage) crosses "
                "another net's copper -- fail-closed, no copper emitted "
                "through a foreign obstacle. The net's pads may rely on "
                "the zone itself for continuity.",
                skipped,
                len(edges),
                net_name,
                _STITCH_LAYER,
                stitch_width,
            )


def _stitch_duplicate_pad_occurrences(
    segments: list[str],
    net_name_to_number: dict[str, int],
    *,
    design_rules: Any,
    tstamp_counter: list[int],
    pcb: Any,
    existing_zones_will_be_replaced: bool = False,
) -> int:
    """Emit locally minimal, collision-checked copper between duplicate pads.

    K2/K3's high-current relay contacts use two physical holes with one
    logical pad number. Rust owns discovery, occurrence identity, world
    geometry and MST edge selection. This thin board-text boundary chooses
    the netclass width, proves each direct edge clear of foreign copper using
    the same clearance/creepage records as zone carving, and emits only edges
    that pass. Missing board context fails closed.

    Returns the number of emitted segments (observability/testing only).
    """
    from shapely.geometry import LineString

    from temper_placer.router_v6._adapter_convert import _next_tstamp
    from temper_placer.router_v6.zone_pour_clearance import (
        collect_zone_obstacle_records,
        default_table,
    )
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    if pcb is None:
        logger.warning(
            "_stitch_duplicate_pad_occurrences: no parsed PCB; skipping all "
            "duplicate-pad edges because foreign-copper clearance cannot be proved"
        )
        return 0
    if not existing_zones_will_be_replaced and (getattr(pcb, "zones", None) or []):
        logger.warning(
            "_stitch_duplicate_pad_occurrences: existing zones will be retained; "
            "skipping all duplicate-pad edges because zone collision clearance "
            "cannot be proved"
        )
        return 0

    emitted = 0
    net_number_to_name = {number: name for name, number in net_name_to_number.items()}
    for net_name, component_ref, pin_number, start, end, layer in (
        _to.run_collect_duplicate_pad_edges(pcb)
    ):
        net_num = net_name_to_number.get(net_name, 0)
        if net_num <= 0:
            continue
        rules = design_rules.get_rules_for_net(net_name) if design_rules is not None else None
        width = getattr(rules, "trace_width", None)
        if width is None:
            width = getattr(rules, "trace_width_mm", None)
        if width is None or width <= 0.0:
            logger.warning(
                "_stitch_duplicate_pad_occurrences: %s.%s has no positive "
                "netclass width; skipping occurrences %d->%d",
                component_ref,
                pin_number,
                start[0],
                end[0],
            )
            continue

        records = collect_zone_obstacle_records(
            net_name,
            layer,
            pcb=pcb,
            segments=segments,
            net_number_to_name=net_number_to_name,
            clearance_table=default_table(),
            creepage_table=default_creepage_table(),
        )
        obstacle_union = _foreign_obstacle_union(records)
        _, sx, sy = start
        _, ex, ey = end
        footprint = LineString([(sx, sy), (ex, ey)]).buffer(width / 2.0, quad_segs=8)
        if (
            obstacle_union is not None
            and not obstacle_union.is_empty
            and footprint.intersects(obstacle_union)
        ):
            logger.warning(
                "_stitch_duplicate_pad_occurrences: skipped %s.%s "
                "occurrences %d->%d on %s; the width/clearance/creepage "
                "footprint intersects foreign copper",
                component_ref,
                pin_number,
                start[0],
                end[0],
                layer,
            )
            continue

        segments.append(
            f"  (segment (start {sx:.4f} {sy:.4f})"
            f" (end {ex:.4f} {ey:.4f})"
            f' (width {width:.4f}) (layer "{layer}")'
            f" (net {net_num})"
            f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
        )
        emitted += 1
    return emitted


def _emit_zone_pours(
    pad_positions: dict[str, list[tuple[float, float]]],
    segments: list[str],
    net_name_to_number: dict[str, int],
    *,
    # Accepted for call-site stability and no longer read: the pour's
    # clearance now comes from the generated, DRU-derived table, not from
    # `design_rules.class_pairs`. Kept rather than removed so the change is
    # visible at every call site as "this argument stopped mattering" instead
    # of silently disappearing from `route_pcb`'s signature -- the same
    # convention `_net_policy._allow_forced_segments` already uses.
    design_rules: Any = None,  # noqa: ARG001
    tstamp_counter: list[int] | None = None,
    pcb: Any = None,
) -> None:
    """Emit filled-copper zone geometry for all zone-eligible nets.

    WIRED 2026-08-16: the outline for every zone is computed by the Rust
    zone generator (``temper_geometry.pour_outline_py``,
    packages/temper-geometry/src/zone_generator.rs), carved against the
    other nets' copper at ``max(clearance, creepage)`` per pair and
    emitted hole-preserving (one ``(polygon (pts ...))`` per ring) via
    ``temper_geometry.emit_zone_outline_s_expr_py``.  See
    docs/evidence/2026-08-16-zone-pour-rust-generator.md for the
    before/after measurements (holes, creepage carve, island policy).

    ``tstamp_counter``: see ``_stitch_isolated_pads`` -- threaded through
    so the isolated-pad stitch segments this function emits (via
    ``_stitch_isolated_pads``) continue the same deterministic tstamp
    sequence as the caller's other segments/vias.

    ``pcb``: the ``ParsedPCB`` the caller already has (``result.pcb`` in
    ``_write_routes_to_content``), used to resolve the board outline
    (so every emitted hull can be clipped to it -- R6,
    docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md) AND the
    other nets' copper the pour must be carved against.  ``None`` (the
    default, and every existing call site before this change) disables
    clipping and carves against nothing -- callers that don't have a
    ``ParsedPCB`` handy (e.g. unit tests constructing pad positions
    directly) are unaffected.
    """
    from temper_placer.core.design_rules import (
        TEMPER_NET_ASSIGNMENTS,
        TEMPER_NET_CLASSES,
    )
    from temper_placer.router_v6.zone_emission import (
        compute_zones_for_net,
    )
    from temper_placer.router_v6.zone_pour_clearance import (
        default_table,
    )

    board_polygon = None
    real_layer_names: set[str] | None = None
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

        # ``_zone_layers_for_net`` returns
        # ``ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED`` unconditionally (it
        # takes no board context -- see its own docstring for why) --
        # a fixed, board-independent ENGINE fact. That stops being safe the
        # moment a board's own inner-layer names don't match the production
        # board's: e.g. ``pcb/benchmarks/temper_fixture_33.kicad_pcb``
        # declares its two inner signal layers ``In1.Cu``/``In2.Cu``, not
        # ``In3.Cu``/``In4.Cu``, so emitting a zone for those literal names
        # on that board would pour copper onto layers it never declares at
        # all. Filtering the returned layer list to what THIS pcb's own
        # stackup actually has (when a ``pcb`` is available) is the local,
        # minimal fix -- no new parameter threaded through
        # ``_zone_layers_for_net``'s ~9 call sites, which its docstring
        # already argues is a separately-risky refactor out of scope here.
        stackup = getattr(pcb, "stackup", None)
        layers = getattr(stackup, "layers", None) if stackup is not None else None
        if layers:
            real_layer_names = {ly.name for ly in layers}

    zone_netclasses: set[str] = set()
    for net_name in pad_positions:
        if _zone_layers_for_net(net_name):
            nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
            if nc:
                zone_netclasses.add(nc)

    # PER-PAIR CLEARANCE (2026-08-13, docs/evidence/2026-08-13-zone-pour-
    # safety-clearances.md). What used to be here resolved ONE scalar per
    # class as a max over the zone-ELIGIBLE classes' `class_pairs` entries:
    #
    #     for other_nc in zone_netclasses:
    #         eff = max(eff, class_pairs[sorted((nc, other_nc))]["clearance"])
    #
    # On this board that yields 6.0mm for every pour, from `class_pairs` rows
    # that cite "IEC 60335-1 Table 16 working isolation at 400V" -- a row that
    # does not exist (PR #1081) -- and whose own file comments call the figure
    # "legacy, not primary-cited". It is a per-NET maximum, it maximises over
    # the wrong set (only classes that themselves pour), and it cannot express
    # 6.0mm-to-SELV / 3.0mm-to-HV / 0.5mm-to-gate-drive at the same time.
    #
    # Replaced by two things that together ARE per-pair:
    #   * the zone's `(clearance ...)` scalar carries the pour's MINIMUM
    #     requirement, the only value that can neither over-clear a pair the
    #     rules relax nor undercut one a rule governs;
    #   * the emitted OUTLINE is carved back from every other net's copper by
    #     that pair's own figure (`pair_clearance_keepout`), which is where a
    #     per-pair requirement can actually live.
    #
    # `design_rules` is no longer read for clearance -- kept in the signature
    # because callers pass it and other consumers may grow.
    live_classes = tuple(
        sorted({TEMPER_NET_ASSIGNMENTS.get(n, "") or "Default" for n in pad_positions})
    )
    clearance_table = default_table()
    effective_clearance: dict[str, float] = {
        nc: clearance_table.min_required(nc, live_classes) for nc in zone_netclasses
    }
    number_to_name = {num: name for name, num in net_name_to_number.items()}

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
    zone_layer_by_net: dict[str, str] = {}
    for net_name, positions in pad_positions.items():
        zone_layers = _zone_layers_for_net(net_name)
        if real_layer_names is not None:
            zone_layers = [layer for layer in zone_layers if layer in real_layer_names]
        if not zone_layers:
            continue
        net_num = net_name_to_number.get(net_name, 0)
        if net_num > 0 and positions:
            nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
            eff_clearance = effective_clearance.get(nc, 0.3)
            prio = zone_priority.get(nc, 0)
            exempt = nc in _CONTINUITY_EXEMPT_CLASSES or net_name in _CONTINUITY_EXEMPT_NETS

            for layer in zone_layers:
                zone_layer_by_net.setdefault(net_name, layer)
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
                    # WIRED 2026-08-16 (docs/evidence/2026-08-16-zone-pour-
                    # rust-generator.md): the outline carve moved from the
                    # Python shapely keepout+difference (`pair_clearance_keepout`
                    # + `_carve_outline`) to the Rust zone generator
                    # (`temper_geometry.pour_outline_py`). Three defects closed,
                    # all measured in docs/evidence/2026-08-15-rust-zone-pour-
                    # design.md:
                    #   1. holes: the Python emitter carried a single ring, so
                    #      interior keepouts (an HV pad buried inside a hull)
                    #      did not carve the OUTLINE and the fill fractured
                    #      into thin rings (167 isolated_copper islands
                    #      measured). The Rust generator returns exterior +
                    #      holes per outline and `emit_zone_outline_s_expr_py`
                    #      writes one `(polygon (pts ...))` per ring.
                    #   2. creepage: the carve used the DRU CLEARANCE table
                    #      (HV-vs-LV 2.0mm) where the DRC judges creepage
                    #      (12.6mm PD3). The obstacle records below carry
                    #      `max(clearance, creepage)` per pair (the creepage
                    #      twin table, configs/zone_pour_creepage.generated.
                    #      yaml) -- measured min gap 2.00mm -> 12.58mm.
                    #   3. islands: PadsOnly for clustered pours drops padless
                    #      pieces (pure isolated_copper liability); the old
                    #      carve kept every piece above the area floor.
                    #      `_CONTINUITY_EXEMPT_NETS` (ntc-no) stays a single
                    #      hull and now fails HONESTLY (0/4 pads at PD3)
                    #      instead of emitting 47+ misleading islands.
                    # The zone's `(clearance ...)` scalar is unchanged
                    # (effective_clearance, the min pair requirement); the
                    # per-pair figure lives in the carved outline.
                    from temper_placer.router_v6.zone_pour_clearance import (
                        collect_zone_obstacle_records,
                    )
                    from temper_placer.router_v6.zone_pour_creepage import (
                        default_creepage_table,
                    )

                    creepage_table = default_creepage_table()
                    obstacles = collect_zone_obstacle_records(
                        net_name,
                        layer,
                        pcb=pcb,
                        segments=segments,
                        net_number_to_name=number_to_name,
                        clearance_table=clearance_table,
                        creepage_table=creepage_table,
                    )
                    # PadsOnly for every pour except GND-class return planes:
                    # padless islands on a signal/HV/mains pour are pure
                    # isolated_copper liability (and for ntc-no the honest
                    # "0 pads coverable at PD3 -> emit nothing" answer),
                    # while a return plane wants padless copper for plane
                    # continuity/shielding.  Same split the Rust
                    # IslandPolicy enum documents; the design doc's KeepAll
                    # rationale is specifically "gnd on a dedicated layer"
                    # (docs/evidence/2026-08-15-rust-zone-pour-design.md
                    # section 5.3), which on this board is CGND/PWR_RTN
                    # (GND class) -- ACMains is NOT given that treatment:
                    # an isolated padless island at mains potential is a
                    # hazard, not shielding.
                    pads_only = nc not in ("GND",)
                    # own_pads must be LAYER-FILTERED: a piece on In3.Cu
                    # may only be credited with pads that actually exist on
                    # In3.Cu (SMD pads are single-layer; THT pads are
                    # "all"/"*.Cu").  Agent 64's harness measured exactly
                    # this distinction -- ntc-no has 4 pads, only its THT
                    # pads exist on inner layers, so on F.Cu the pour
                    # fails honestly (0/4) while a layer-blind own-pad
                    # list would wrongly let inner-layer pieces survive on
                    # an F.Cu pad's position.
                    own_pads_on_layer = _own_pads_on_layer(
                        net_name, layer, pcb=pcb, fallback_positions=positions
                    )
                    # A net with NO pad on this layer must not pour on it
                    # at all: the fill would be isolated copper (KiCad
                    # flags "Isolated copper fill" -- measured 19 findings
                    # for F.Cu-only HighVoltageSignal nets poured onto
                    # In3.Cu/In4.Cu).  An SMD-only net's pads are single
                    # layer; the only pads that exist everywhere are THT.
                    if not own_pads_on_layer:
                        continue
                    for zd in zds:
                        pour_zones = _tg.pour_outline_py(
                            list(zd.points),
                            own_pads_on_layer,
                            obstacles,
                            _MIN_CARVED_AREA_MM2,
                            pads_only,
                        )
                        for zone_rings in pour_zones:
                            exterior = zone_rings[0]
                            holes = zone_rings[1:]
                            if len(exterior) < 3:
                                continue
                            segments.append(
                                _tg.emit_zone_outline_s_expr_py(
                                    zd.net_number,
                                    zd.net_name,
                                    zd.layer,
                                    exterior,
                                    holes,
                                    eff_clearance,
                                    prio,
                                    zd.min_thickness,
                                )
                            )
                            zone_points_by_net.setdefault(net_name, []).append(tuple(exterior))
                except ValueError:
                    pass

    _stitch_isolated_pads(
        pad_positions,
        segments,
        net_name_to_number,
        zone_points_by_net,
        tstamp_counter=tstamp_counter,
        pcb=pcb,
    )
    _stitch_pads_to_each_other(
        pad_positions,
        segments,
        net_name_to_number,
        tstamp_counter=tstamp_counter,
        pcb=pcb,
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
