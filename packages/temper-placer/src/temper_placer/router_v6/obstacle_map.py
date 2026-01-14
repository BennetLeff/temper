"""
Router V6 Stage 2.1: Build Obstacle Map

Constructs a geometric representation of routing obstacles (pads, keepouts, vias)
using Shapely for topological analysis.

Part of temper-ewjb (Stage 2 - Topology Extraction)
"""

from __future__ import annotations

import math
from collections import defaultdict

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from temper_placer.core.netlist import Pin
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import ParsedPCB


def build_obstacle_map(
    pcb: ParsedPCB,
    escape_vias: list[EscapeVia],
    exclude_net_name: str | None = None,
    exclude_nets: list[str] | None = None,
) -> dict[str, MultiPolygon]:
    """
    Build a map of obstacles for each copper layer.

    Args:
        pcb: Parsed PCB data containing components, nets, and design rules.
        escape_vias: List of generated escape vias.
        exclude_net_name: Optional net name to exclude (legacy).
        exclude_nets: List of net names to exclude from obstacles.

    Returns:
        Dictionary mapping layer name (e.g. "F.Cu") to a Shapely MultiPolygon.
    """
    layer_obstacles = defaultdict(list)

    excluded = set()
    if exclude_net_name:
        excluded.add(exclude_net_name)
    if exclude_nets:
        excluded.update(exclude_nets)

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
            # Skip if this pin belongs to the excluded net(s)
            if pin.net in excluded:
                continue

            # Get absolute position
            px, py = pin.absolute_position((comp_x, comp_y), angle)

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

    # 5. Board Edge (Constraint)
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


def _create_pad_polygon(pin: Pin, x: float, y: float, comp_angle: float) -> Polygon:
    """
    Create a shapely Polygon for a pin pad.

    Args:
        pin: The Pin object.
        x, y: Absolute center coordinates.
        comp_angle: Component rotation in radians.
    """
    # Simple shape handling
    if pin.shape in ["circle", "oval"]:
        # Use circle approximation
        radius = max(pin.width, pin.height) / 2.0
        return Point(x, y).buffer(radius, quad_segs=8)
    else:
        # Rectangle / RoundedRect
        # Create centered box
        w = pin.width
        h = pin.height

        # Vertices of unrotated rectangle centered at 0,0
        coords = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]

        # Rotate and translate
        # Pad might have its own rotation? KiCad pads can.
        # pin.rotation is likely relative to component.
        # But Pin dataclass has 'rotation' field?
        # Checking Pin definition in netlist.py:
        # rotation: float = 0.0  # degrees

        pin_rot_rad = math.radians(pin.rotation if hasattr(pin, "rotation") else 0.0)
        total_angle = comp_angle + pin_rot_rad

        cos_a = math.cos(total_angle)
        sin_a = math.sin(total_angle)

        transformed_coords = []
        for cx, cy in coords:
            rx = cx * cos_a - cy * sin_a + x
            ry = cx * sin_a + cy * cos_a + y
            transformed_coords.append((rx, ry))

        return Polygon(transformed_coords)
