"""
Router V6 Stage 2.4: Compute Channel Widths

Measures channel width (clearance) at each point along the skeleton.
Part of temper-7qu7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
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

    # Pre-build the per-call caches for ``_compute_width_at_point``.
    # This is the hot path: the function is called once per
    # node (~2000) plus once per sample along each edge
    # (~10000 total) per layer.  Without these caches, each
    # call re-builds the prepared geometry and re-extracts the
    # exterior / interior rings via ``_get_ring`` (the dominant
    # per-call Shapely cost).  Demonstrated 2.2x speedup in the
    # sampling profile.
    import shapely.prepared
    from shapely.geometry import MultiPolygon
    prepared_area = shapely.prepared.prep(available_area)
    if isinstance(available_area, MultiPolygon):
        cached_polygons = list(available_area.geoms)
    else:
        cached_polygons = [available_area]
    cached_exteriors = [p.exterior for p in cached_polygons]
    cached_interiors = [list(p.interiors) for p in cached_polygons]

    # Compute width at each node
    for node in skeleton.graph.nodes():
        width = _compute_width_at_point(
            node, available_area,
            _prepared=prepared_area,
            _polygons=cached_polygons,
            _exteriors=cached_exteriors,
            _interiors=cached_interiors,
        )
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
                width = _compute_width_at_point(
                    (sample_x, sample_y), available_area,
                    _prepared=prepared_area,
                    _polygons=cached_polygons,
                    _exteriors=cached_exteriors,
                    _interiors=cached_interiors,
                )
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
    _prepared=None,
    _polygons=None,
    _exteriors=None,
    _interiors=None,
) -> float:
    """
    Compute channel width at a point.

    Width is 2x the distance to the nearest boundary (clearance on both sides).

    Args:
        point: (x, y) coordinate
        available_area: Available routing area (Polygon or MultiPolygon)
        _prepared: Optional pre-built ``shapely.prepared.prep`` of
            ``available_area``.  Pass this in for hot loops to skip
            the per-call prepared-geometry build.
        _polygons: Optional pre-extracted polygon list
            (``list(available_area.geoms)`` for MultiPolygon,
            ``[available_area]`` for Polygon).  Pass for hot loops.
        _exteriors: Optional pre-cached list of ``polygon.exterior``
            rings (one per polygon).  Avoids the per-call
            ``_get_ring`` access on each ``polygon.distance``.
        _interiors: Optional pre-cached list of
            ``list(polygon.interiors)`` per polygon.  Same
            rationale as ``_exteriors``.

    Returns:
        Width in mm
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry import Point as ShapelyPoint

    pt = ShapelyPoint(point)

    # Lazy-init the per-call caches (back-compat for callers
    # that don't pre-compute).  In a hot loop the caller should
    # pass these in for the 2x speedup demonstrated in the
    # sampling profile.
    if _prepared is None:
        import shapely.prepared
        _prepared = shapely.prepared.prep(available_area)
    if _polygons is None:
        if isinstance(available_area, Polygon):
            _polygons = [available_area]
        elif isinstance(available_area, MultiPolygon):
            _polygons = list(available_area.geoms)
        else:
            return 0.0

    # Check if point is inside available area (prepared geometry
    # is 5-10x faster than the bare .contains() call).
    if not _prepared.contains(pt):
        return 0.0

    # Distance to boundary.  We pre-cache the exterior / interior
    # rings once per call (or once per run if the caller pre-cached)
    # because each ``polygon.exterior`` / ``polygon.interiors``
    # access goes through Shapely's ``_get_ring`` and is the
    # dominant per-call cost in the original implementation
    # (~700k ``_get_ring`` calls in the sampling profile).
    min_distance = float('inf')
    if _exteriors is None:
        _exteriors = [p.exterior for p in _polygons]
    if _interiors is None:
        _interiors = [list(p.interiors) for p in _polygons]

    for exterior, interiors in zip(_exteriors, _interiors):
        d = pt.distance(exterior)
        if d < min_distance:
            min_distance = d
        for interior in interiors:
            d = pt.distance(interior)
            if d < min_distance:
                min_distance = d

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
        for layer_name, skeleton in state.channel_skeletons.items():  # type: ignore[union-attr]
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
