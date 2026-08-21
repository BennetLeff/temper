"""
Router V6 Stage 2.1: Build Obstacle Map

Constructs a geometric representation of routing obstacles (pads, keepouts, vias)
using Shapely for topological analysis.

Part of temper-ewjb (Stage 2 - Topology Extraction)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace

import temper_geometry as _tg
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from temper_placer.core.netlist import Pin
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


def _circle_buffer_ring(x: float, y: float, radius: float, quad_segs: int = 8) -> list[tuple[float, float]]:
    """Closed exterior ring of ``Point((x, y)).buffer(radius, quad_segs=q)``.

    Wave 4 migration note: the two via sites in :func:`build_obstacle_map`
    call this instead of shapely's ``Point.buffer``.  The S1 spike
    (``docs/evidence/2026-08-04-geos-polygon-algebra-spike.md`` §4.1) proved
    ``Point.buffer(r, quad_segs=q)`` is exactly reconstructible — GEOS emits
    a ``4q``-gon on ``(cx + r·cos(−kπ/2q), cy + r·sin(−kπ/2q))`` with
    host-libm trig and a near-zero snap (``Angle::sinCosSnap``); this is
    reproduced bit-for-bit in ``temper-geometry``'s ``obstacle_map_kernels``.
    ``radius <= 0`` returns the empty ring (GEOS ``isLineOffsetEmpty``),
    matching ``Point.buffer(r <= 0)`` == ``POLYGON EMPTY``.
    """
    return list(_tg.circle_buffer_ring_py(float(x), float(y), float(radius), int(quad_segs)))


def build_obstacle_map(pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> dict[str, MultiPolygon]:
    """
    Build a map of obstacles for each copper layer.

    Obstacles include:
    1. Component pads (on their respective layers).
    2. Escape vias (on all layers, assuming through-hole for now).
    3. Keepout zones (from PCB data).
    4. Pre-routed tracks already on the board.
    5. Pre-existing vias already on the board.
    6. Board edge (optional: treated as outer boundary or inverted obstacle).

    Args:
        pcb: Parsed PCB data containing components, nets, and design rules.
        escape_vias: List of generated escape vias.

    Returns:
        Dictionary mapping layer name (e.g. "F.Cu") to a Shapely MultiPolygon
        representing the union of all obstacles on that layer.
    """
    layer_obstacles = defaultdict(list)

    # 1. Component Pads
    for comp in pcb.components:
        comp_x, comp_y = 0.0, 0.0
        if comp.initial_position:
            comp_x, comp_y = comp.initial_position

        angle = 0.0
        if comp.initial_rotation_quadrant is not None:
            # rotation index 0-3 -> radians
            angle = float(comp.initial_rotation_quadrant) * math.pi / 2.0

        for pin in comp.pins:
            # Get absolute position
            px, py = pin_world_position(pin, comp)

            # Create pad geometry
            # Approximate as bounding box for Rect, or buffered point for Circle
            # For robustness, we'll use a rotated rectangle or circle approximation.

            pad_poly = _create_pad_polygon(pin, px, py, angle)

            # Add to appropriate layer(s)
            if pin.layer in ["All", "all"] or "*.Cu" in pin.layer or "Through" in pin.layer:
                # Add to all signal layers
                for layer_info in pcb.stackup.layers:
                    if layer_info.layer_type in ["signal", "mixed"]:
                        layer_obstacles[layer_info.name].append(pad_poly)
            else:
                # Specific layer (e.g. "F.Cu")
                layer_obstacles[pin.layer].append(pad_poly)

    # 2. Escape Vias
    # Assume Through-Hole Vias for now (blocking all layers)
    for via in escape_vias:
        # Create via polygon (circle).  `Point.buffer(quad_segs=8)` is
        # reproduced bit-exactly by `_circle_buffer_ring` (see its docstring
        # and obstacle_map_kernels.rs); the Polygon() wrap is the container
        # step, not compute.
        via_poly = Polygon(
            _circle_buffer_ring(via.position[0], via.position[1], via.diameter / 2.0, 8)
        )

        for layer_info in pcb.stackup.layers:
            if layer_info.layer_type in ["signal", "mixed"]:
                layer_obstacles[layer_info.name].append(via_poly)

    # 3. Zones / Keepouts
    if hasattr(pcb, "zones") and pcb.zones:
        # Net-aware pour handling (U2's routing_space.py sub-requirement of
        # docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md
        # -- landed for stackup role classification via
        # use_declared_layer_roles, but never landed here, which is what this
        # fixes).
        #
        # This loop used to union EVERY zone into its layer's obstacle
        # polygon unconditionally (the "TODO: filter by net" immediately
        # below, now resolved). Measured on pcb/temper.kicad_pcb: that made
        # F.Cu/B.Cu ~25% available (vs. ~98% on the pour-free inner layers)
        # and fragmented the medial-axis skeleton into 150+ islands (see
        # docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md Sec 5).
        #
        # 84 of this board's 96 committed zones belong to net classes
        # (`Power`, `GateDrive`) that `_zone_layers_for_net()` -- the SAME
        # eligibility rule `_write_routes_to_content` already uses to decide
        # which pours survive into the routed output (`strip_existing_zones`
        # unconditionally strips every existing zone; `_emit_zone_pours`
        # only re-emits one for an eligible net class) -- says get NO pour
        # in the final board. Treating those 84 zones as routing obstacles
        # here contradicts what the write path already does with them: they
        # are stale, pending-regeneration input, not a real constraint any
        # net will ever have to route around, since none of them survive to
        # the output regardless of which net is being routed.
        #
        # A zone whose net class IS pour-eligible (`ACMains`/`HighVoltage`
        # `plane_required`, `GND` `plane_preferred` -- 14 of 96 zones) DOES
        # survive into the routed output on a comparable footprint, and
        # remains a real obstacle to every OTHER net -- kept unconditionally
        # obstructive here, deliberately not exempted for its own owning
        # net. A fully net-scoped "net N may enter its own eligible pour"
        # view would need a per-net (not per-layer, shared-across-all-nets)
        # topology, which this stage does not have; ModelBuilder
        # (constraint_model.py) offers every NetChannelVar to every net over
        # this SAME shared skeleton/obstacle view, so opening an eligible
        # zone's interior here would hand every OTHER net a channel through
        # copper it must keep clearance to -- the exact "diagnosis without
        # measuring the consequence" trap
        # docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md
        # documents. Excluding only the 84 never-regenerated zones has no
        # such risk: that geometry will not exist in the output for ANY net,
        # so no other net's clearance is ever at stake.
        #
        # Measured effect (docs/evidence/2026-08-07-channel-skeleton-net-aware-pours.md):
        # smaller than the raw 25%->~98% gap might suggest, because 2 of the
        # 14 still-eligible zones (SW_NODE, DC_BUS_RTN, both HighVoltage)
        # are themselves pathological board-spanning hulls -- a SEPARATE,
        # already-diagnosed defect (R6 of
        # docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md,
        # zone_emission.py's clustering-exemption for plane_required
        # classes) this change deliberately does not also fix.
        from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

        for zone in pcb.zones:
            # Skip if no polygon data
            if not hasattr(zone, "polygon") or not zone.polygon:
                continue

            # A zone with no net at all is a true keepout (no net-class
            # eligibility to resolve) and keeps the unconditional-obstacle
            # treatment this replaces for net-owned zones. A zone whose
            # every declared net belongs to a non-pour-eligible class is
            # stale, never-regenerated input -- see the module-level note
            # above -- and is excluded from the obstacle map entirely.
            net_names = [n for n in (getattr(zone, "net_classes", None) or []) if n]
            if net_names and not any(_zone_layers_for_net(n) for n in net_names):
                continue

            # Create Polygon from points
            # zone.polygon is list of (x,y)
            try:
                poly = Polygon(zone.polygon)
                if not poly.is_valid:
                    poly = poly.buffer(0)
            except Exception:
                continue

            # Determine layers
            layers = zone.layers if hasattr(zone, "layers") else ["F.Cu"]

            for layer in layers:
                layer_obstacles[layer].append(poly)

    # 4. Pre-routed Tracks
    if hasattr(pcb, "tracks") and pcb.tracks:
        from shapely.geometry import LineString

        for track in pcb.tracks:
            # Create buffered line
            try:
                line = LineString([track.start, track.end])
                # Buffer by half width
                poly = line.buffer(track.width / 2.0, cap_style=1)  # 1=Round
                layer_obstacles[track.layer].append(poly)
            except Exception:
                continue

    # 5. Pre-existing Vias
    #
    # Before this, ``ParsedPCB`` carried no via list at all (see stage0_data.py
    # / kicad_parser.py) -- a re-route pass over an already-routed board had
    # zero visibility into where existing vias sat, so new copper (tracks or
    # new vias) could land directly on top of a different net's via with no
    # clearance check whatsoever. That is a straightforward missing-obstacle
    # bug, not a net-scoping one: unlike pads and tracks below, vias are not
    # filtered by net here -- the routing net's own vias are re-opened later,
    # at route time, in ``_unblock_net_pads`` (astar_grid.py), which mirrors
    # the existing pad/escape-via unblock pattern. See
    # docs/evidence/2026-07-30-router-copper-shorts.md.
    if hasattr(pcb, "vias") and pcb.vias:
        for via in pcb.vias:
            try:
                via_poly = Polygon(
                    _circle_buffer_ring(via.position[0], via.position[1], via.diameter / 2.0, 8)
                )
            except Exception:
                continue

            # A drilled through-hole via's declared ``layers`` names only its
            # two connected endpoint layers (e.g. "F.Cu"/"B.Cu"), matching
            # KiCad's own file convention -- but the physical drill passes
            # through every copper layer in between, including inner
            # signal/mixed layers. Escape vias two sections up already treat
            # through-hole vias as blocking all signal/mixed layers for
            # exactly this reason; pre-existing vias get the same treatment
            # for consistency, not just their two declared endpoints.
            for layer_info in pcb.stackup.layers:
                if layer_info.layer_type in ["signal", "mixed"]:
                    layer_obstacles[layer_info.name].append(via_poly)

    # 6. Board Edge (Constraint)
    # Usually we route *inside* the board. The obstacle map represents *blocked* areas.
    # The inverse of the board polygon is the "infinite" obstacle.
    # For this function, we return internal obstacles.
    # The router should handle the board boundary separately.

    # Union all obstacles per layer
    result_map = {}
    for layer, obstacles in layer_obstacles.items():
        if not obstacles:
            result_map[layer] = MultiPolygon()
            continue

        # Efficient union
        merged = unary_union(obstacles)

        # Ensure result is MultiPolygon
        if isinstance(merged, Polygon):
            merged = MultiPolygon([merged])

        result_map[layer] = merged

    return result_map


class ObstacleMapStage(Stage):
    """Stage 2.1: Build obstacle maps for each copper layer."""

    @property
    def name(self) -> str:
        return "ObstacleMap"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        escape_vias = list(state._escape_vias) if state._escape_vias else []
        obstacle_maps = build_obstacle_map(pcb, escape_vias)
        return replace(state, obstacle_maps=obstacle_maps)


def _create_pad_polygon(pin: Pin, x: float, y: float, comp_angle: float) -> Polygon:
    """
    Create a shapely Polygon for a pin pad.

    Args:
        pin: The Pin object.
        x, y: Absolute center coordinates.
        comp_angle: Component rotation in radians.

    Delegates to the shared, shape-correct ``core.pad_geometry.pad_polygon``
    (see that module's docstring for the exact circle/oval/rect/roundrect
    Minkowski-sum model and its never-under-reports proof) instead of this
    module's own prior ad hoc handling, which grouped "circle" and "oval"
    together under a single ``max(width, height) / 2`` circle -- exact for
    "circle" and (coincidentally, an oval's true furthest point IS along its
    own long axis) also exact for "oval", but duplicated the same formula
    this fix plan is removing from every other consumer (R4: one shared
    implementation, not five copies that can silently drift apart).
    ``pin.pad_rotation_deg`` (the pad's own intrinsic rotation, additive to
    the component's -- zero on every real pad today, see
    ``core.pad_geometry`` for why it is honoured rather than assumed away)
    is added to ``comp_angle`` here.
    """
    from temper_placer.core.pad_geometry import pad_polygon
    from temper_placer.geometry.pad_world import pad_world_rotation_rad

    total_angle = pad_world_rotation_rad(comp_angle, getattr(pin, "pad_rotation_deg", 0.0))
    roundrect_ratio = getattr(pin, "roundrect_ratio", None) or 0.25
    return pad_polygon(
        pin.width,
        pin.height,
        pin.shape,
        cx=x,
        cy=y,
        rotation_rad=total_angle,
        roundrect_ratio=roundrect_ratio,
    )


@register_validator("ObstacleMap")
def validate_obstacle_map(state: BoardState) -> list[StageDRCFailure]:
    """Validate obstacle map invariants."""
    failures: list[StageDRCFailure] = []
    if state.obstacle_maps is None:
        failures.append(
            StageDRCFailure(
                field="obstacle_maps",
                value=None,
                reason="Obstacle maps not computed",
                stage="ObstacleMap",
            )
        )
        return failures

    assert state._parsed_pcb is not None
    pcb: ParsedPCB = state._parsed_pcb
    declared_layers = {ly.name for ly in pcb.stackup.layers if ly.layer_type in ("signal", "mixed")}

    for layer_name, _obstacles in state.obstacle_maps.items():
        if layer_name not in declared_layers:
            failures.append(
                StageDRCFailure(
                    field="obstacle_maps",
                    value=layer_name,
                    reason=f"Layer {layer_name} has obstacles but is not a declared signal/mixed layer",
                    stage="ObstacleMap",
                )
            )

    for layer_name in declared_layers:
        if layer_name not in state.obstacle_maps:
            failures.append(
                StageDRCFailure(
                    field="obstacle_maps",
                    value=layer_name,
                    reason=f"Declared layer {layer_name} missing from obstacle maps",
                    stage="ObstacleMap",
                )
            )

    return failures
