"""
Validation of actual routed traces.

This module provides functions to analyze physical traces on the PCB
to validate compliance with EMI, Signal Integrity, and Thermal specs.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.board import Board, Trace
    from temper_placer.core.netlist import Netlist


def calculate_actual_trace_length(board: Board, net_name: str) -> float:
    """Calculate total routed length of a specific net."""
    length = 0.0
    for trace in board.traces:
        if trace.net == net_name:
            dx = trace.end[0] - trace.start[0]
            dy = trace.end[1] - trace.start[1]
            length += math.sqrt(dx**2 + dy**2)
    return length


def calculate_actual_loop_area(board: Board, net_names: list[str]) -> float:
    """
    Calculate polygon area formed by traces of multiple nets.
    
    Used for differential pairs or switching loops (e.g. SW and GND).
    """
    # 1. Collect all trace endpoints
    points = []
    for trace in board.traces:
        if trace.net in net_names:
            points.append(trace.start)
            points.append(trace.end)
            
    if len(points) < 3:
        return 0.0
        
    # 2. Convert to convex hull or ordered path?
    # For a simple area estimate, we can use the bounding box or convex hull
    # or try to trace the path if it's a simple loop.
    # Simple bounding box area as proxy if not enough points.
    
    # Better: use actual points and shoelace if they form a closed loop.
    # For validation, we'll use convex hull area as a conservative upper bound.
    from scipy.spatial import ConvexHull
    try:
        hull = ConvexHull(np.array(points))
        return float(hull.volume) # volume of 2D hull is area
    except Exception:
        return 0.0


def validate_signal_integrity(board: Board, spec: Any) -> dict[str, float]:
    """Validate trace lengths against Signal Integrity spec."""
    results = {}
    for net_name, max_len in spec.max_length_mm.items():
        actual_len = calculate_actual_trace_length(board, net_name)
        results[f"{net_name}_length"] = actual_len
        if actual_len > max_len:
            print(f"Warning: Net {net_name} exceeds max length ({actual_len:.1f} > {max_len}mm)")
            
    return results


def validate_emi_traces(board: Board, spec: Any) -> dict[str, float]:
    """Validate loop areas from actual traces."""
    # This is complex because we need to know which nets form the loop
    # TODO: Implement proper loop net identification
    return {}
