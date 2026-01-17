"""
Steiner Tree / MST computation for multi-pin net routing.

Instead of routing multi-pin nets as sequential chains (Pin0→Pin1→Pin2→...),
we compute a Minimum Spanning Tree (MST) to find optimal edge pairs.

This ensures:
1. Minimum total wire length
2. Tree structure (no cycles, no blocking self)
3. Shared routing segments where beneficial
"""

from dataclasses import dataclass
import math


@dataclass
class MSTEdge:
    """An edge in the minimum spanning tree."""
    
    start: tuple[float, float]
    end: tuple[float, float]
    length: float
    
    def __hash__(self):
        # Make edges hashable for deduplication
        return hash((self.start, self.end))


def compute_mst_edges(waypoints: list[tuple[float, float]]) -> list[MSTEdge]:
    """
    Compute Minimum Spanning Tree edges for a set of waypoints.
    
    Uses Prim's algorithm for simplicity and correctness.
    
    Args:
        waypoints: List of (x, y) pin/waypoint locations
        
    Returns:
        List of MSTEdge objects representing the tree edges to route
    """
    if len(waypoints) < 2:
        return []
    
    if len(waypoints) == 2:
        # Trivial case: single edge
        d = _distance(waypoints[0], waypoints[1])
        return [MSTEdge(start=waypoints[0], end=waypoints[1], length=d)]
    
    # Prim's algorithm
    # Start with first waypoint in the tree
    in_tree = {0}
    edges = []
    
    while len(in_tree) < len(waypoints):
        # Find minimum edge from tree to non-tree vertex
        min_edge = None
        min_dist = float('inf')
        min_to = -1
        
        for i in in_tree:
            for j in range(len(waypoints)):
                if j not in in_tree:
                    d = _distance(waypoints[i], waypoints[j])
                    if d < min_dist:
                        min_dist = d
                        min_edge = (i, j)
                        min_to = j
        
        if min_edge is None:
            break  # No more reachable vertices
        
        # Add edge to MST
        i, j = min_edge
        edges.append(MSTEdge(
            start=waypoints[i],
            end=waypoints[j],
            length=min_dist
        ))
        in_tree.add(min_to)
    
    return edges


def compute_routing_order(mst_edges: list[MSTEdge]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """
    Determine optimal routing order for MST edges.
    
    Routes from center outward to minimize blocking.
    
    Args:
        mst_edges: List of MST edges
        
    Returns:
        List of (start, end) tuples in routing order
    """
    if not mst_edges:
        return []
    
    # Find centroid of all points
    all_points = set()
    for e in mst_edges:
        all_points.add(e.start)
        all_points.add(e.end)
    
    cx = sum(p[0] for p in all_points) / len(all_points)
    cy = sum(p[1] for p in all_points) / len(all_points)
    centroid = (cx, cy)
    
    # Sort edges by distance from centroid (route center first)
    def edge_center_dist(e: MSTEdge) -> float:
        mid_x = (e.start[0] + e.end[0]) / 2
        mid_y = (e.start[1] + e.end[1]) / 2
        return _distance((mid_x, mid_y), centroid)
    
    sorted_edges = sorted(mst_edges, key=edge_center_dist)
    
    return [(e.start, e.end) for e in sorted_edges]


def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def analyze_net_topology(waypoints: list[tuple[float, float]]) -> dict:
    """
    Analyze the topology improvement from MST vs sequential routing.
    
    Returns metrics for debugging and comparison.
    """
    if len(waypoints) < 2:
        return {"pin_count": len(waypoints), "improvement": 0}
    
    # Sequential (chain) length
    seq_length = 0
    for i in range(len(waypoints) - 1):
        seq_length += _distance(waypoints[i], waypoints[i + 1])
    
    # MST length
    mst_edges = compute_mst_edges(waypoints)
    mst_length = sum(e.length for e in mst_edges)
    
    improvement = (seq_length - mst_length) / seq_length * 100 if seq_length > 0 else 0
    
    return {
        "pin_count": len(waypoints),
        "sequential_length_mm": seq_length,
        "mst_length_mm": mst_length,
        "improvement_percent": improvement,
        "edge_count": len(mst_edges),
    }
