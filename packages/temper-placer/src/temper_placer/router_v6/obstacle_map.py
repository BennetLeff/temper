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

from shapely.geometry import MultiPolygon, Point, Polygon
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
        if comp.initial_rotation is not None:
            # rotation index 0-3 -> radians
            angle = float(comp.initial_rotation) * math.pi / 2.0

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
        # Create via polygon (circle)
        # Resolution: 8-16 points is usually enough for topological routing approximation
        # Use quad_segs instead of deprecated resolution
        via_poly = Point(via.position).buffer(via.diameter / 2.0, quad_segs=8)

        for layer_info in pcb.stackup.layers:
            if layer_info.layer_type in ["signal", "mixed"]:
                layer_obstacles[layer_info.name].append(via_poly)

    # 3. Zones / Keepouts
    if hasattr(pcb, "zones") and pcb.zones:
        for zone in pcb.zones:
            # Skip if no polygon data
            if not hasattr(zone, "polygon") or not zone.polygon:
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
                # Add to layer obstacles
                # If it's a Keepout (usually indicated by no net or specific flag?)
                # Or if it's a Copper Zone of a DIFFERENT net, it's an obstacle.
                # Ideally we should filter by net, but ObstacleMap is usually "Static Obstacles".
                # For simplicity, we treat ALL Zones as obstacles.
                # TODO: If we route the SAME net, we should allow entering the zone.
                # But Router V6 treats zones as "Targets" (via pads) usually.
                # If we treat them as obstacles, we might block access.
                # However, for the "Missing Obstacles" bug (AC_L vs CGND), CGND zone is definitely an obstacle for AC_L.
                # Safe default: Treat as obstacle. The router connects to PADS, not zones directly yet.
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
                via_poly = Point(via.position).buffer(via.diameter / 2.0, quad_segs=8)
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

    pad_rot_rad = math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0)
    total_angle = comp_angle + pad_rot_rad
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
