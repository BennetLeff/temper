"""Geometry utilities for PCB placement and routing."""

from geometry.minkowski import (
    compute_minkowski_clearance,
    compute_trace_corridor,
    required_gap_for_traces,
    compute_c_obstacle,
    compute_obstacle_with_clearance,
    compute_parallel_trace_forbidden_region,
    min_minkowski_distance,
    TraceSpec,
)

__all__ = [
    "compute_minkowski_clearance",
    "compute_trace_corridor",
    "required_gap_for_traces",
    "compute_c_obstacle",
    "compute_obstacle_with_clearance",
    "compute_parallel_trace_forbidden_region",
    "min_minkowski_distance",
    "TraceSpec",
]
