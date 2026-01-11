"""
Router V6 Stage 2.3: Extract Channel Skeleton

Extracts channel centerlines using medial axis transform to find routing paths.
Part of temper-h6t7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import voronoi_diagram

from temper_placer.router_v6.routing_space import RoutingSpace


@dataclass
class ChannelSkeleton:
    """Skeleton graph representing routing channels."""

    graph: nx.Graph  # Nodes are (x, y) positions, edges are channel segments
    layer_name: str
    total_length: float  # Total channel length in mm

    @property
    def is_connected(self) -> bool:
        """Check if the channel graph is fully connected."""
        return nx.is_connected(self.graph) if len(self.graph.nodes) > 0 else True

    @property
    def node_count(self) -> int:
        """Number of nodes in the skeleton."""
        return len(self.graph.nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the skeleton."""
        return len(self.graph.edges)


def extract_channel_skeleton(
    routing_space: RoutingSpace,
    simplify_tolerance: float = 0.5,
) -> ChannelSkeleton:
    """
    Extract routing channel skeleton using medial axis approximation.

    Args:
        routing_space: Routing space from Stage 2.2
        simplify_tolerance: Tolerance for simplifying skeleton (mm)

    Returns:
        ChannelSkeleton with graph representation

    Example:
        >>> skeleton = extract_channel_skeleton(routing_space)
        >>> skeleton.is_connected
        True
    """
    # Create graph
    G = nx.Graph()

    # Get available routing area
    available_area = routing_space.available_area

    if available_area.is_empty:
        # No routing space available
        return ChannelSkeleton(
            graph=G,
            layer_name=routing_space.layer_name,
            total_length=0.0,
        )

    # Extract skeleton using Voronoi-based medial axis approximation
    skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance)

    total_length = 0.0

    # Build graph from skeleton lines
    for line in skeleton_lines:
        coords = list(line.coords)
        
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            
            # Add nodes (use tuple for hashability)
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)
            
            # Calculate edge weight (length)
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = (dx**2 + dy**2)**0.5
            
            # Add edge with length weight
            G.add_edge(p1, p2, weight=length)
            total_length += length

    return ChannelSkeleton(
        graph=G,
        layer_name=routing_space.layer_name,
        total_length=total_length,
    )


def _extract_medial_axis(
    polygon_or_multipolygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis using Voronoi diagram approach.

    Args:
        polygon_or_multipolygon: Available routing area
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings representing skeleton
    """
    from shapely.geometry import MultiPolygon, Polygon

    # Handle MultiPolygon
    if isinstance(polygon_or_multipolygon, MultiPolygon):
        all_lines = []
        for polygon in polygon_or_multipolygon.geoms:
            lines = _extract_medial_axis_single(polygon, simplify_tolerance)
            all_lines.extend(lines)
        return all_lines
    elif isinstance(polygon_or_multipolygon, Polygon):
        return _extract_medial_axis_single(polygon_or_multipolygon, simplify_tolerance)
    else:
        return []


def _extract_medial_axis_single(
    polygon: "Polygon",
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis for a single polygon using simplified approach.

    Args:
        polygon: Single polygon
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings
    """
    # Simplified medial axis: use buffer -> unbuffer technique
    # This creates an approximation of the medial axis
    
    # Get the polygon boundary
    boundary = polygon.boundary
    
    # Create points along the boundary for Voronoi
    # Sample points every ~1mm
    points = []
    if hasattr(boundary, 'coords'):
        coords = list(boundary.coords)
    elif hasattr(boundary, 'geoms'):
        # MultiLineString boundary
        coords = []
        for line in boundary.geoms:
            coords.extend(list(line.coords))
    else:
        return []
    
    # Sample points along the boundary
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        
        # Calculate distance
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = (dx**2 + dy**2)**0.5
        
        # Add intermediate points
        num_points = max(2, int(dist))
        for j in range(num_points):
            t = j / num_points
            x = p1[0] + t * dx
            y = p1[1] + t * dy
            points.append(Point(x, y))
    
    if len(points) < 3:
        # Not enough points for Voronoi
        # Return simplified centerline
        centroid = polygon.centroid
        return [LineString([centroid.coords[0], centroid.coords[0]])]
    
    # Create Voronoi diagram
    try:
        voronoi = voronoi_diagram(MultiLineString([LineString([p.coords[0], p.coords[0]]) for p in points[:100]]))
        
        # Filter Voronoi edges that are inside the polygon
        skeleton_lines = []
        
        if hasattr(voronoi, 'geoms'):
            for geom in voronoi.geoms:
                if isinstance(geom, LineString):
                    # Check if line is mostly inside polygon
                    midpoint = geom.interpolate(0.5, normalized=True)
                    if polygon.contains(midpoint):
                        # Simplify the line
                        simplified = geom.simplify(simplify_tolerance)
                        if simplified.length > 0:
                            skeleton_lines.append(simplified)
        
        if skeleton_lines:
            return skeleton_lines
            
    except Exception:
        # Voronoi failed, use fallback
        pass
    
    # Fallback: return polygon centroid as a simple skeleton
    centroid = polygon.centroid
    bounds = polygon.bounds  # (minx, miny, maxx, maxy)
    
    # Create simple cross pattern through centroid
    cx, cy = centroid.x, centroid.y
    minx, miny, maxx, maxy = bounds
    
    return [
        LineString([(minx, cy), (maxx, cy)]),  # Horizontal
        LineString([(cx, miny), (cx, maxy)]),  # Vertical
    ]
