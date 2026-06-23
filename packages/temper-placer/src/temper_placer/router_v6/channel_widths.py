"""
Router V6 Stage 2.4: Compute Channel Widths

Measures channel width (clearance) at each point along the skeleton.
Part of temper-7qu7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


@dataclass
class ChannelWidths:
    """Width measurements for routing channels."""

    layer_name: str
    node_widths: dict[tuple[float, float], float]  # Node position -> width in mm
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float]  # Edge -> min width
    min_width: float  # Minimum width across all channels
    max_width: float  # Maximum width across all channels
    avg_width: float  # Average width

    @property
    def bottleneck_width(self) -> float:
        """Return the minimum channel width (bottleneck)."""
        return self.min_width

    def get_node_width(self, node: tuple[float, float]) -> float:
        """Get width at a specific node."""
        return self.node_widths.get(node, 0.0)


def compute_channel_widths(
    routing_space: RoutingSpace,
    skeleton: ChannelSkeleton,
    sample_distance: float = 1.0,
) -> ChannelWidths:
    """
    Compute channel widths along the skeleton.

    Width is measured as the distance to the nearest obstacle (2x clearance).

    Args:
        routing_space: Routing space from Stage 2.2
        skeleton: Channel skeleton from Stage 2.3
        sample_distance: Distance between width samples along edges (mm)

    Returns:
        ChannelWidths with width measurements

    Example:
        >>> widths = compute_channel_widths(routing_space, skeleton)
        >>> widths.min_width > 0.0  # Some routing space available
        True
    """
    node_widths = {}
    edge_widths = {}

    # Get the available routing area
    available_area = routing_space.available_area

    if available_area.is_empty or skeleton.node_count == 0:
        # No routing space or skeleton
        return ChannelWidths(
            layer_name=routing_space.layer_name,
            node_widths={},
            edge_widths={},
            min_width=0.0,
            max_width=0.0,
            avg_width=0.0,
        )

    # Compute width at each node
    for node in skeleton.graph.nodes():
        width = _compute_width_at_point(node, available_area)
        node_widths[node] = width

    # Compute width along each edge
    for u, v in skeleton.graph.edges():
        # Sample points along the edge
        widths_along_edge = []

        # Add endpoint widths
        widths_along_edge.append(node_widths[u])
        widths_along_edge.append(node_widths[v])

        # Sample intermediate points
        dx = v[0] - u[0]
        dy = v[1] - u[1]
        edge_length = (dx**2 + dy**2)**0.5

        if edge_length > sample_distance:
            num_samples = int(edge_length / sample_distance)
            for i in range(1, num_samples):
                t = i / num_samples
                sample_x = u[0] + t * dx
                sample_y = u[1] + t * dy
                width = _compute_width_at_point((sample_x, sample_y), available_area)
                widths_along_edge.append(width)

        # Edge width is the minimum along the edge (bottleneck)
        edge_widths[(u, v)] = min(widths_along_edge) if widths_along_edge else 0.0

    # Compute statistics
    all_widths = list(node_widths.values()) + list(edge_widths.values())

    if all_widths:
        min_width = min(all_widths)
        max_width = max(all_widths)
        avg_width = sum(all_widths) / len(all_widths)
    else:
        min_width = max_width = avg_width = 0.0

    return ChannelWidths(
        layer_name=routing_space.layer_name,
        node_widths=node_widths,
        edge_widths=edge_widths,
        min_width=min_width,
        max_width=max_width,
        avg_width=avg_width,
    )


def _compute_width_at_point(
    point: tuple[float, float],
    available_area,
) -> float:
    """
    Compute channel width at a point.

    Width is 2x the distance to the nearest boundary (clearance on both sides).

    Args:
        point: (x, y) coordinate
        available_area: Available routing area (Polygon or MultiPolygon)

    Returns:
        Width in mm
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry import Point as ShapelyPoint

    pt = ShapelyPoint(point)

    # Check if point is inside available area
    if not available_area.contains(pt):
        return 0.0

    # Compute distance to boundary
    # For a polygon, the distance to boundary is the distance to exterior ring
    min_distance = float('inf')

    if isinstance(available_area, Polygon):
        polygons = [available_area]
    elif isinstance(available_area, MultiPolygon):
        polygons = list(available_area.geoms)
    else:
        return 0.0

    for polygon in polygons:
        if polygon.contains(pt):
            # Distance to exterior boundary
            dist_to_exterior = pt.distance(polygon.exterior)
            min_distance = min(min_distance, dist_to_exterior)

            # Distance to any interior holes
            for interior in polygon.interiors:
                dist_to_hole = pt.distance(interior)
                min_distance = min(min_distance, dist_to_hole)

    # Width is 2x the clearance (distance on both sides)
    if min_distance == float('inf'):
        return 0.0

    return 2.0 * min_distance


class ChannelWidthsStage(Stage):
    '''Stage 2.4: Compute channel widths along skeletons.'''

    @property
    def name(self) -> str:
        return "ChannelWidths"

    def run(self, state: BoardState) -> BoardState:
        channel_widths: dict[str, ChannelWidths] = {}
        for layer_name, skeleton in state.channel_skeletons.items():
            widths = compute_channel_widths(
                state.routing_spaces[layer_name],
                skeleton,
            )
            channel_widths[layer_name] = widths
        return replace(state, channel_widths=channel_widths)


@register_validator("ChannelWidths")
def validate_channel_widths(state: BoardState) -> list[StageDRCFailure]:
    '''Validate channel width invariants.'''
    failures: list[StageDRCFailure] = []
    if state.channel_widths is None:
        failures.append(StageDRCFailure(
            field="channel_widths", value=None,
            reason="Channel widths not computed", stage="ChannelWidths",
        ))
        return failures

    for layer_name, cw in state.channel_widths.items():
        if cw.min_width < 0:
            failures.append(StageDRCFailure(
                field="channel_widths", value=layer_name,
                reason="Negative minimum width: " + repr(cw.min_width), stage="ChannelWidths",
            ))
        if cw.max_width < 0:
            failures.append(StageDRCFailure(
                field="channel_widths", value=layer_name,
                reason="Negative maximum width: " + repr(cw.max_width), stage="ChannelWidths",
            ))

    return failures
