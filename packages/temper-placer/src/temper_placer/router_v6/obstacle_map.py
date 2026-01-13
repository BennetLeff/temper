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


def build_obstacle_map(pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> dict[str, MultiPolygon]:
    """
    Build a map of obstacles for each copper layer.

    Obstacles include:
    1. Component pads (on their respective layers).
    2. Escape vias (on all layers, assuming through-hole for now).
    3. Keepout zones (from PCB data).
    4. Board edge (optional: treated as outer boundary or inverted obstacle).

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
    # TODO: Parse zones from pcb.zones if available and extract geometry.
    # Currently pcb.zones might be raw objects.
    # If pcb.zones contains keepouts, we should add them.
    # For now, we skip complex zone parsing as it requires inspecting the specific object structure.

    # 4. Board Edge (Constraint)
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
