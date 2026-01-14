"""
Router V6 Stage 2.2: Compute Routing Space

Computes available routing area by subtracting obstacles from board area.
Part of temper-643u (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.strtree import STRtree

from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.stage0_data import ParsedPCB


@dataclass
class RoutingSpace:
    """Available routing space per layer."""

    layer_name: str
    available_area: MultiPolygon  # Routable regions (board - obstacles)
    total_area: float  # Total board area in mm²
    obstacle_area: float  # Total obstacle area in mm²
    routing_area: float  # Available routing area in mm²
    obstacles: MultiPolygon | None = None  # Raw obstacles for SDF generation
    obstacle_tree: STRtree | None = None  # Spatial index for fast queries

    @property
    def utilization_ratio(self) -> float:
        """Ratio of obstacle area to total area."""
        if self.total_area == 0:
            return 0.0
        return self.obstacle_area / self.total_area

    @property
    def available_ratio(self) -> float:
        """Ratio of available routing area to total area."""
        if self.total_area == 0:
            return 0.0
        return self.routing_area / self.total_area


def compute_routing_space(
    pcb: ParsedPCB,
    escape_vias: list | None = None,
) -> dict[str, RoutingSpace]:
    """
    Compute available routing space for each layer.

    Args:
        pcb: Parsed PCB with components and board geometry
        escape_vias: Optional list of escape vias to include as obstacles

    Returns:
        Dictionary mapping layer name to RoutingSpace instance

    Example:
        >>> routing_space = compute_routing_space(pcb)
        >>> top_layer = routing_space["F.Cu"]
        >>> top_layer.available_ratio > 0.5  # At least 50% available
        True
    """
    # Build obstacle map for all layers
    obstacle_map = build_obstacle_map(pcb, escape_vias or [])

    # Get board outline as a polygon
    board_polygon = _get_board_polygon(pcb)
    board_area = board_polygon.area

    routing_spaces = {}

    # Compute routing space for each layer
    for layer_info in pcb.stackup.layers:
        if layer_info.layer_type not in ["signal", "mixed"]:
            continue

        layer_name = layer_info.name

        # Get obstacles for this layer
        obstacles = obstacle_map.get(layer_name, MultiPolygon())

        # Compute available space (board - obstacles)
        if isinstance(obstacles, MultiPolygon) and len(obstacles.geoms) > 0:
            available_area = board_polygon.difference(obstacles)
        else:
            available_area = board_polygon

        # Ensure result is MultiPolygon
        if isinstance(available_area, Polygon):
            available_area = MultiPolygon([available_area])

        # Calculate areas
        obstacle_area = obstacles.area if hasattr(obstacles, "area") else 0.0
        routing_area = available_area.area if hasattr(available_area, "area") else board_area

        # Build spatial index
        obstacle_tree = None
        if isinstance(obstacles, MultiPolygon) and len(obstacles.geoms) > 0:
            obstacle_tree = STRtree(obstacles.geoms)
        elif isinstance(obstacles, Polygon):
            obstacle_tree = STRtree([obstacles])

        routing_spaces[layer_name] = RoutingSpace(
            layer_name=layer_name,
            available_area=available_area,
            total_area=board_area,
            obstacle_area=obstacle_area,
            routing_area=routing_area,
            obstacles=obstacles,
            obstacle_tree=obstacle_tree,
        )

    return routing_spaces


def _get_board_polygon(pcb: ParsedPCB) -> Polygon:
    """
    Get board outline as a Shapely Polygon.

    Args:
        pcb: Parsed PCB data

    Returns:
        Board polygon
    """
    # If PCB has explicit board geometry, use it
    if hasattr(pcb, "board") and pcb.board:
        board = pcb.board
        if hasattr(board, "outline_polygon") and board.outline_polygon:
            return Polygon(board.outline_polygon)

        # Otherwise use bounds
        try:
            # Board.get_bounds_array returns [xmin, ymin, xmax, ymax]
            bounds = board.get_bounds_array()
            return box(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
        except (AttributeError, IndexError):
            if hasattr(board, "width") and hasattr(board, "height"):
                # Default to origin-based box if bounds calculation fails
                ox, oy = getattr(board, "origin", (0.0, 0.0))
                return box(ox, oy, ox + board.width, oy + board.height)

    # Fallback: compute bounding box from components
    if pcb.components:
        x_coords = []
        y_coords = []

        for comp in pcb.components:
            if comp.initial_position:
                x, y = comp.initial_position
                w, h = comp.bounds
                x_coords.extend([x - w / 2, x + w / 2])
                y_coords.extend([y - h / 2, y + h / 2])

        if x_coords and y_coords:
            margin = 5.0  # 5mm margin
            return box(
                min(x_coords) - margin,
                min(y_coords) - margin,
                max(x_coords) + margin,
                max(y_coords) + margin,
            )

    # Ultimate fallback: standard board size
    return box(0, 0, 100, 100)
