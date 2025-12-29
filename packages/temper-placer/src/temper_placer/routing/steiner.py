"""
Steiner tree algorithms for optimal multi-pin net routing (temper-tos3.2).

This module provides:
1. Minimum Spanning Tree (MST) computation using Prim's algorithm
2. Rectilinear Steiner Tree (RST) approximation
3. Optimal routing order for multi-terminal nets

The RST problem is NP-hard, so we use MST as a 1.5-approximation.
"""

import math
from typing import List, Tuple


def compute_mst(pins: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
    """Compute Minimum Spanning Tree using Prim's algorithm.
    
    Args:
        pins: List of (x, y) coordinates
        
    Returns:
        List of edges as (pin_index_a, pin_index_b) tuples
        
    Example:
        >>> pins = [(0, 0), (10, 0), (5, 5)]
        >>> edges = compute_mst(pins)
        >>> len(edges) == 2  # 3 pins → 2 edges
        True
    """
    if len(pins) < 2:
        return []
    
    n = len(pins)
    
    # Prim's algorithm
    in_tree = [False] * n
    edges = []
    
    # Start with pin 0
    in_tree[0] = True
    
    for _ in range(n - 1):
        min_dist = float('inf')
        best_edge = None
        
        # Find minimum edge connecting tree to non-tree vertex
        for i in range(n):
            if not in_tree[i]:
                continue
            for j in range(n):
                if in_tree[j]:
                    continue
                
                # Manhattan distance
                dist = abs(pins[i][0] - pins[j][0]) + abs(pins[i][1] - pins[j][1])
                
                if dist < min_dist:
                    min_dist = dist
                    best_edge = (i, j)
        
        if best_edge is None:
            break
        
        edges.append(best_edge)
        in_tree[best_edge[1]] = True
    
    return edges


def compute_rst_approximation(pins: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Compute Rectilinear Steiner Tree approximation.
    
    Uses Hanan grid heuristic: Steiner points lie on grid defined by pin coordinates.
    This is a simple approximation; exact RST is NP-hard.
    
    Args:
        pins: List of (x, y) pin coordinates
        
    Returns:
        List of suggested Steiner point coordinates
    """
    if len(pins) < 3:
        return []  # No Steiner points needed for 2 pins
    
    # Hanan grid: all x and y coordinates from pins
    x_coords = sorted(set(p[0] for p in pins))
    y_coords = sorted(set(p[1] for p in pins))
    
    # For simple cases, suggest center points
    steiner_points = []
    
    # Find bounding box center
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    
    # Check if center is beneficial (e.g., for plus/cross patterns)
    is_beneficial = False
    for px, py in pins:
        # If pins are spread in different quadrants, center helps
        if (px < center_x and py < center_y) or (px > center_x and py > center_y):
            is_beneficial = True
            break
        if (px < center_x and py > center_y) or (px > center_x and py < center_y):
            is_beneficial = True
            break
    
    if is_beneficial:
        # Snap center to grid
        center_x_snapped = min(x_coords, key=lambda x: abs(x - center_x))
        center_y_snapped = min(y_coords, key=lambda y: abs(y - center_y))
        steiner_points.append((center_x_snapped, center_y_snapped))
    
    return steiner_points


def mst_routing_order(pins: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
    """Determine routing order based on MST.
    
    Returns pairs of pin indices to route in sequence.
    
    Args:
        pins: List of pin coordinates
        
    Returns:
        List of (from_index, to_index) routing pairs
    """
    if len(pins) < 2:
        return []
    
    edges = compute_mst(pins)
    return edges
