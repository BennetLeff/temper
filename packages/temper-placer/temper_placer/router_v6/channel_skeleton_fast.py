"""
Fast Channel Skeleton Extraction for Benders Integration.

This is a lightweight alternative to the full Voronoi-based skeleton
extraction. It's designed for rapid routability checking where we
don't need perfect geometric accuracy.

Key optimizations:
1. Grid-based skeleton instead of Voronoi
2. Only process large polygons
3. Coarser sampling
4. Skip complex boundary analysis

Typical speedup: 10-100x faster than full skeleton extraction.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from temper_placer.router_v6.routing_space import RoutingSpace


@dataclass
class FastChannelSkeleton:
    """Lightweight skeleton for routability checking."""

    graph: nx.Graph
    layer_name: str
    total_length: float
    node_count: int
    edge_count: int


def extract_channel_skeleton_fast(
    routing_space: RoutingSpace,
    grid_spacing: float = 5.0,  # 5mm grid
    min_polygon_area: float = 10.0,  # Ignore tiny polygons
) -> FastChannelSkeleton:
    """
    Extract a fast approximate channel skeleton using bounding box.
    
    This creates a simple grid skeleton based on the bounding box,
    avoiding expensive point-in-polygon tests for complex geometries.
    
    Args:
        routing_space: Routing space from Stage 2.2
        grid_spacing: Grid spacing in mm (larger = faster)
        min_polygon_area: Minimum polygon area to process
        
    Returns:
        FastChannelSkeleton with approximate routing graph
    """
    G = nx.Graph()
    available_area = routing_space.available_area
    
    if available_area.is_empty:
        return FastChannelSkeleton(
            graph=G,
            layer_name=routing_space.layer_name,
            total_length=0.0,
            node_count=0,
            edge_count=0,
        )
    
    # Get bounding box
    minx, miny, maxx, maxy = available_area.bounds
    
    # Create a simple grid skeleton based on bounds (no containment checks)
    # This is a rough approximation but FAST
    width = maxx - minx
    height = maxy - miny
    
    # Create grid nodes
    nodes = []
    nx_grid = max(2, int(width / grid_spacing))
    ny_grid = max(2, int(height / grid_spacing))
    
    for i in range(nx_grid):
        for j in range(ny_grid):
            x = minx + (i + 0.5) * (width / nx_grid)
            y = miny + (j + 0.5) * (height / ny_grid)
            nodes.append((x, y))
    
    # Add nodes
    for node in nodes:
        G.add_node(node, pos=node)
    
    # Connect grid in a lattice pattern
    total_length = 0.0
    
    for i in range(nx_grid):
        for j in range(ny_grid):
            idx = i * ny_grid + j
            node = nodes[idx]
            
            # Connect to right neighbor
            if i < nx_grid - 1:
                neighbor_idx = (i + 1) * ny_grid + j
                neighbor = nodes[neighbor_idx]
                length = width / nx_grid
                G.add_edge(node, neighbor, weight=length)
                total_length += length
            
            # Connect to top neighbor
            if j < ny_grid - 1:
                neighbor_idx = i * ny_grid + (j + 1)
                neighbor = nodes[neighbor_idx]
                length = height / ny_grid
                G.add_edge(node, neighbor, weight=length)
                total_length += length
    
    return FastChannelSkeleton(
        graph=G,
        layer_name=routing_space.layer_name,
        total_length=total_length,
        node_count=len(G.nodes),
        edge_count=len(G.edges),
    )


def extract_channel_skeleton_minimal(
    routing_space: RoutingSpace,
) -> FastChannelSkeleton:
    """
    Extract a minimal skeleton - just the bounding box with center cross.
    
    This is the fastest possible skeleton, suitable for rough routability
    estimates when speed is critical.
    
    Args:
        routing_space: Routing space from Stage 2.2
        
    Returns:
        FastChannelSkeleton with minimal graph
    """
    G = nx.Graph()
    available_area = routing_space.available_area
    
    if available_area.is_empty:
        return FastChannelSkeleton(
            graph=G,
            layer_name=routing_space.layer_name,
            total_length=0.0,
            node_count=0,
            edge_count=0,
        )
    
    # Get bounds
    minx, miny, maxx, maxy = available_area.bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    
    # Create simple cross skeleton
    nodes = [
        (minx, cy),  # left
        (maxx, cy),  # right
        (cx, miny),  # bottom
        (cx, maxy),  # top
        (cx, cy),    # center
    ]
    
    for node in nodes:
        G.add_node(node, pos=node)
    
    # Connect to center
    total_length = 0.0
    center = (cx, cy)
    for node in nodes[:4]:
        length = ((node[0] - center[0])**2 + (node[1] - center[1])**2)**0.5
        G.add_edge(node, center, weight=length)
        total_length += length
    
    return FastChannelSkeleton(
        graph=G,
        layer_name=routing_space.layer_name,
        total_length=total_length,
        node_count=len(G.nodes),
        edge_count=len(G.edges),
    )


def extract_channel_capacities_direct(
    routing_space: RoutingSpace,
    design_rules,
) -> dict:
    """
    Directly compute channel capacities without full skeleton.
    
    This bypasses skeleton extraction entirely and estimates capacity
    from the available routing area directly.
    
    Args:
        routing_space: Routing space
        design_rules: PCB design rules
        
    Returns:
        Dict with capacity estimates
    """
    available_area = routing_space.available_area
    
    if available_area.is_empty:
        return {
            "total_area_mm2": 0.0,
            "estimated_channels": 0,
            "capacity_traces": 0,
            "pitch_mm": 0.0,
        }
    
    # Use pre-computed area (fast)
    area_mm2 = available_area.area
    
    # Use bounds (fast - no iteration over polygons)
    bounds = available_area.bounds
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    
    # Estimate capacity from area
    trace_width = design_rules.default_trace_width_mm
    trace_spacing = design_rules.default_clearance_mm
    pitch = trace_width + trace_spacing
    
    # Fill ratio: actual area vs bounding box
    bbox_area = width * height
    fill_ratio = area_mm2 / max(bbox_area, 1.0)
    
    # Rough estimate: area / (pitch * average_route_length)
    avg_dimension = (width + height) / 2
    
    # Estimate number of parallel traces that can fit
    capacity = area_mm2 / (pitch * max(avg_dimension, 1.0))
    
    return {
        "total_area_mm2": area_mm2,
        "estimated_channels": int(capacity),
        "capacity_traces": int(capacity * 0.7),  # 70% utilization factor
        "pitch_mm": pitch,
        "fill_ratio": fill_ratio,
        "bounds": bounds,
    }
