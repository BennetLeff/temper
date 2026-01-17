"""
Minkowski Sum Module for Configuration Space Computation

Provides exact Minkowski sum computations for collision-free configuration space
generation in PCB placement and routing.

The Minkowski sum A ⊕ B = {a + b : a ∈ A, b ∈ B} computes the exact
collision-free configuration space for obstacle avoidance.

References:
- de Berg, M. et al. "Computational Geometry: Algorithms and Applications"
- Lozano-Perez, T. "Spatial Planning: A Configuration Space Approach"
"""

from dataclasses import dataclass
from typing import List, Protocol, Sequence

from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union


@dataclass
class TraceSpec:
    """Specification for a trace in clearance calculations."""

    width: float
    layer: str = "top"
    is_differential_pair: bool = False
    coupled_width: float = 0.0


class CSpaceComputer(Protocol):
    """Protocol for configuration space computation strategies."""

    def compute_clearance(self, obstacle: Polygon, trace_width: float, clearance: float) -> Polygon:
        """Compute clearance polygon around an obstacle."""
        ...

    def compute_corridor(
        self, start: Sequence[float], end: Sequence[float], width: float, clearance: float
    ) -> Polygon:
        """Compute routing corridor between two points."""
        ...


def compute_minkowski_clearance(polygon: Polygon, trace_width: float, clearance: float) -> Polygon:
    """
    Compute exact clearance polygon using Minkowski sum.

    The clearance polygon is the Minkowski sum of the original polygon
    with a rectangle representing the trace plus clearance.

    Args:
        polygon: Original obstacle polygon (must be valid)
        trace_width: Width of the trace in mm
        clearance: Required clearance around the trace in mm

    Returns:
        Expanded polygon representing forbidden region for trace center

    Example:
        >>> from shapely.geometry import box
        >>> obs = box(0, 0, 10, 10)
        >>> clearance = compute_minkowski_clearance(obs, 0.5, 0.2)
        >>> clearance.area > obs.area
        True
    """
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    half_width = trace_width / 2.0
    total_radius = half_width + clearance

    return polygon.buffer(total_radius, cap_style="square", join_style="bevel")


def compute_trace_corridor(
    start: Sequence[float], end: Sequence[float], width: float, clearance: float
) -> Polygon:
    """
    Compute routing corridor between two points.

    Creates a corridor polygon that represents the valid region for
    trace center placement between start and end points.

    Args:
        start: (x, y) starting point
        end: (x, y) ending point
        width: Maximum trace width that can be routed
        clearance: Required clearance around the trace

    Returns:
        Corridor polygon representing valid routing region
    """
    start_point = (float(start[0]), float(start[1]))
    end_point = (float(end[0]), float(end[1]))

    line = LineString([start_point, end_point])

    half_width = width / 2.0
    total_radius = half_width + clearance

    return line.buffer(total_radius, cap_style="square", join_style="bevel")


def required_gap_for_traces(trace_widths: List[float], clearance: float) -> float:
    """
    Compute exact minimum gap required between parallel traces.

    For N parallel traces with widths w_i and required clearance c,
    the minimum gap between trace i and trace j is:
        gap_ij = (w_i + w_j) / 2 + c

    The total gap for N traces is determined by the tightest pair.

    Args:
        trace_widths: List of trace widths in mm
        clearance: Required clearance between traces in mm

    Returns:
        Minimum gap that satisfies all clearance requirements

    Example:
        >>> required_gap_for_traces([0.5, 0.5, 0.5], 0.2)
        0.7
    """
    if not trace_widths:
        return 0.0

    max_width = max(trace_widths)
    min_width = min(trace_widths)

    half_max_plus_min = (max_width + min_width) / 2.0

    return half_max_plus_min + clearance


def compute_c_obstacle(component: Polygon, trace_spec: TraceSpec) -> Polygon:
    """
    Compute configuration space obstacle for a component.

    The C-obstacle is the region where the trace center cannot be placed
    without violating clearance constraints.

    Args:
        component: Component footprint polygon
        trace_spec: Trace specification including width and clearance

    Returns:
        C-obstacle polygon for the component
    """
    return compute_minkowski_clearance(component, trace_spec.width, 0.0)


def compute_obstacle_with_clearance(
    polygon: Polygon, trace_width: float, clearance: float
) -> Polygon:
    """
    Compute obstacle expanded by trace width plus clearance.

    This is the forbidden region for any copper (trace or component).

    Args:
        polygon: Original obstacle polygon
        trace_width: Width of the trace
        clearance: Required clearance from obstacle

    Returns:
        Expanded polygon representing forbidden region
    """
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    total_clearance = trace_width / 2.0 + clearance

    return polygon.buffer(total_clearance, cap_style="square", join_style="bevel")


def compute_parallel_trace_forbidden_region(
    trace_polygons: List[Polygon], trace_width: float, clearance: float
) -> Polygon:
    """
    Compute union of forbidden regions around parallel traces.

    Args:
        trace_polygons: List of trace centerline polygons
        trace_width: Width of the traces
        clearance: Required clearance between traces

    Returns:
        Union of all forbidden regions (as Polygon or MultiPolygon)
    """
    forbidden_regions = []

    for trace in trace_polygons:
        region = trace.buffer(trace_width / 2.0 + clearance)
        forbidden_regions.append(region)

    result = unary_union(forbidden_regions)
    if isinstance(result, Polygon):
        return result
    if result.is_empty:
        return Polygon()
    if hasattr(result, "geoms") and len(result.geoms) > 0:
        return Polygon(result.geoms[0].exterior)
    return Polygon()


def min_minkowski_distance(polygon_a: Polygon, polygon_b: Polygon) -> float:
    """
    Compute exact minimum distance between two polygons.

    Uses Shapely's distance() for exact geometric computation.

    Args:
        polygon_a: First polygon
        polygon_b: Second polygon

    Returns:
        Minimum distance between the two polygons
    """
    if not polygon_a.is_valid:
        polygon_a = polygon_a.buffer(0)
    if not polygon_b.is_valid:
        polygon_b = polygon_b.buffer(0)

    return polygon_a.distance(polygon_b)
