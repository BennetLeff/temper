"""
Min-Cut to Component Mapper for Benders Decomposition.

Maps min-cut edges from Max-Flow analysis to blocking components in the placement.
This enables the generation of routability cuts for the ILP Master Problem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.placement.benders_master import ComponentData
else:
    # Runtime placeholder - any object with ref, x_mm, y_mm, width_mm, height_mm will work
    ComponentData = Any


class CutDirection(Enum):
    """Direction of the required cut/separation."""

    HORIZONTAL = "horizontal"  # Components need horizontal separation (left-right)
    VERTICAL = "vertical"  # Components need vertical separation (up-down)


@dataclass
class BlockingComponent:
    """
    A component identified as blocking a routing channel.

    Attributes:
        component_ref: Component reference designator (e.g., "U1", "Q2")
        direction: Direction of required separation
        position: Center position of the component (x, y)
        edges_involved: Number of min-cut edges near this component
    """

    component_ref: str
    direction: CutDirection
    position: tuple[float, float]
    edges_involved: int = 1

    def __eq__(self, other):
        if not isinstance(other, BlockingComponent):
            return False
        return (
            self.component_ref == other.component_ref
            and self.direction == other.direction
            and self.position == other.position
            and self.edges_involved == other.edges_involved
        )

    def __hash__(self):
        return hash((self.component_ref, self.direction, self.position))


class MinCutMapper:
    """
    Maps min-cut edges from Max-Flow analysis to blocking components.

    The Max-Flow analyzer returns min-cut edges as tuples:
        ((layer, (x1, y1)), (layer, (x2, y2)), capacity)

    This mapper:
    1. Identifies which components' bounding boxes intersect or are near these edges
    2. Determines the direction of flow being blocked (horizontal vs vertical)
    3. Returns BlockingComponent objects for cut generation
    """

    def __init__(self, components: list[ComponentData], tolerance_mm: float = 2.0):
        """
        Initialize the mapper.

        Args:
            components: List of component data with positions and dimensions
            tolerance_mm: Distance tolerance for considering a component "near" an edge
        """
        self.components = {c.ref: c for c in components}
        self.tolerance_mm = tolerance_mm

    def map_mincut_to_components(
        self, min_cut_edges: list[tuple[tuple, tuple, float]]
    ) -> list[BlockingComponent]:
        """
        Map min-cut edges to blocking components.

        Strategy:
        1. For each min-cut edge, determine its orientation (horizontal/vertical)
        2. Find components on both sides of the edge
        3. Components on opposite sides are causing the bottleneck

        Args:
            min_cut_edges: List of ((layer, pos1), (layer, pos2), capacity) from MaxFlowAnalyzer

        Returns:
            List of BlockingComponent objects
        """
        if not min_cut_edges:
            return []

        blocking_map: dict[tuple[str, CutDirection], BlockingComponent] = {}

        for edge in min_cut_edges:
            # Unpack edge
            node_u, node_v, capacity = edge

            # Extract layer and positions
            # node_u and node_v are tuples: (layer_name, (x, y))
            if not isinstance(node_u, tuple) or not isinstance(node_v, tuple):
                continue

            layer_u, pos_u = node_u
            layer_v, pos_v = node_v

            # Determine edge direction and midpoint
            dx = abs(pos_v[0] - pos_u[0])
            dy = abs(pos_v[1] - pos_u[1])
            mid_x = (pos_u[0] + pos_v[0]) / 2
            mid_y = (pos_u[1] + pos_v[1]) / 2

            # Edge orientation determines what flow is blocked
            # Vertical edge (dx small, dy large) blocks horizontal flow
            # Horizontal edge (dx large, dy small) blocks vertical flow
            if dy > dx:
                # Vertical edge -> blocks horizontal flow -> need HORIZONTAL separation
                cut_direction = CutDirection.HORIZONTAL
                # Find components on left and right of the edge
                for component in self.components.values():
                    dist_to_edge = abs(component.x_mm - mid_x)
                    # Check if component is near the edge in X and within the Y range
                    if dist_to_edge <= (component.width_mm / 2 + self.tolerance_mm + 10):  # Relaxed threshold
                        y_min = min(pos_u[1], pos_v[1]) - self.tolerance_mm
                        y_max = max(pos_u[1], pos_v[1]) + self.tolerance_mm
                        # Check if component's Y overlaps with edge's Y span
                        comp_y_min = component.y_mm - component.height_mm / 2
                        comp_y_max = component.y_mm + component.height_mm / 2
                        if comp_y_max >= y_min and comp_y_min <= y_max:
                            key = (component.ref, cut_direction)
                            if key in blocking_map:
                                blocking_map[key].edges_involved += 1
                            else:
                                blocking_map[key] = BlockingComponent(
                                    component_ref=component.ref,
                                    direction=cut_direction,
                                    position=(component.x_mm, component.y_mm),
                                    edges_involved=1,
                                )
            else:
                # Horizontal edge -> blocks vertical flow -> need VERTICAL separation
                cut_direction = CutDirection.VERTICAL
                # Find components above and below the edge
                for component in self.components.values():
                    dist_to_edge = abs(component.y_mm - mid_y)
                    # Check if component is near the edge in Y and within the X range
                    if dist_to_edge <= (component.height_mm / 2 + self.tolerance_mm + 10):  # Relaxed threshold
                        x_min = min(pos_u[0], pos_v[0]) - self.tolerance_mm
                        x_max = max(pos_u[0], pos_v[0]) + self.tolerance_mm
                        # Check if component's X overlaps with edge's X span
                        comp_x_min = component.x_mm - component.width_mm / 2
                        comp_x_max = component.x_mm + component.width_mm / 2
                        if comp_x_max >= x_min and comp_x_min <= x_max:
                            key = (component.ref, cut_direction)
                            if key in blocking_map:
                                blocking_map[key].edges_involved += 1
                            else:
                                blocking_map[key] = BlockingComponent(
                                    component_ref=component.ref,
                                    direction=cut_direction,
                                    position=(component.x_mm, component.y_mm),
                                    edges_involved=1,
                                )

        return list(blocking_map.values())

    def get_component_pairs(
        self, blocking_components: list[BlockingComponent]
    ) -> list[tuple[str, str, CutDirection]]:
        """
        Identify pairs of components that need separation.

        Groups blocking components by direction and finds pairs that should be separated.

        Args:
            blocking_components: List of blocking components from map_mincut_to_components

        Returns:
            List of (component1_ref, component2_ref, direction) tuples
        """
        pairs = []

        # Group by direction
        horizontal_blockers = [b for b in blocking_components if b.direction == CutDirection.HORIZONTAL]
        vertical_blockers = [b for b in blocking_components if b.direction == CutDirection.VERTICAL]

        # For horizontal cuts, pair components that are left-right of each other
        if len(horizontal_blockers) >= 2:
            # Sort by x position
            sorted_h = sorted(horizontal_blockers, key=lambda b: b.position[0])
            # Create pairs of adjacent components
            for i in range(len(sorted_h) - 1):
                pairs.append(
                    (sorted_h[i].component_ref, sorted_h[i + 1].component_ref, CutDirection.HORIZONTAL)
                )

        # For vertical cuts, pair components that are above-below each other
        if len(vertical_blockers) >= 2:
            # Sort by y position
            sorted_v = sorted(vertical_blockers, key=lambda b: b.position[1])
            # Create pairs of adjacent components
            for i in range(len(sorted_v) - 1):
                pairs.append((sorted_v[i].component_ref, sorted_v[i + 1].component_ref, CutDirection.VERTICAL))

        return pairs

    def _edge_intersects_bbox(
        self, pos1: tuple[float, float], pos2: tuple[float, float], component: ComponentData
    ) -> bool:
        """
        Check if an edge intersects or is near a component's bounding box.

        Args:
            pos1: Edge start position (x, y)
            pos2: Edge end position (x, y)
            component: Component with position and dimensions

        Returns:
            True if edge intersects the component's bbox (with tolerance)
        """
        # Component bounding box (center-based)
        cx, cy = component.x_mm, component.y_mm
        w, h = component.width_mm, component.height_mm

        # Bounding box corners with tolerance
        tol = self.tolerance_mm
        x_min, x_max = cx - w / 2 - tol, cx + w / 2 + tol
        y_min, y_max = cy - h / 2 - tol, cy + h / 2 + tol

        # Check if either endpoint is near the bbox
        if self._point_near_bbox(pos1, component) or self._point_near_bbox(pos2, component):
            return True

        # Check if edge crosses the bounding box using line-box intersection
        # Simplified: check if edge's bounding box overlaps component's bounding box
        edge_x_min = min(pos1[0], pos2[0])
        edge_x_max = max(pos1[0], pos2[0])
        edge_y_min = min(pos1[1], pos2[1])
        edge_y_max = max(pos1[1], pos2[1])

        # Check overlap
        x_overlap = edge_x_max >= x_min and edge_x_min <= x_max
        y_overlap = edge_y_max >= y_min and edge_y_min <= y_max

        return x_overlap and y_overlap

    def _point_near_bbox(self, point: tuple[float, float], component: ComponentData) -> bool:
        """
        Check if a point is near a component's bounding box.

        Args:
            point: Point coordinates (x, y)
            component: Component with position and dimensions

        Returns:
            True if point is within tolerance of the bbox
        """
        px, py = point
        cx, cy = component.x_mm, component.y_mm
        w, h = component.width_mm, component.height_mm
        tol = self.tolerance_mm

        x_min, x_max = cx - w / 2 - tol, cx + w / 2 + tol
        y_min, y_max = cy - h / 2 - tol, cy + h / 2 + tol

        return x_min <= px <= x_max and y_min <= py <= y_max


def estimate_required_gap(
    blocking_components: list[BlockingComponent], design_rules: dict | None = None
) -> float:
    """
    Estimate the routing channel width required to resolve a bottleneck.

    Args:
        blocking_components: List of blocking components
        design_rules: Optional design rules dict with trace_width, clearance, etc.

    Returns:
        Estimated gap width in mm
    """
    if not design_rules:
        # Default assumptions for PCB routing
        trace_width = 0.2  # mm
        clearance = 0.2  # mm
        design_rules = {"trace_width": trace_width, "clearance": clearance}

    trace_width = design_rules.get("trace_width", 0.2)
    clearance = design_rules.get("clearance", 0.2)
    pitch = trace_width + clearance

    # Estimate based on number of edges involved
    max_edges = max(b.edges_involved for b in blocking_components) if blocking_components else 1

    # Conservative estimate: allow space for max_edges traces
    required_gap = max_edges * pitch + 1.0  # Add 1mm margin

    # Clamp to reasonable range
    return min(max(required_gap, 2.0), 10.0)  # Between 2mm and 10mm
