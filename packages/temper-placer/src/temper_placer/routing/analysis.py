"""
Routability analysis for PCB placements.

This module provides tools to analyze how easy a placement is to route,
identifying potential bottlenecks and providing actionable advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext
from temper_placer.losses.congestion import compute_routing_demand


from enum import Enum

class FailureType(Enum):
    """Types of routing failures."""
    NO_PATH = 'no_path'
    CONGESTION = 'congestion'
    CLEARANCE = 'clearance'

@dataclass
class RoutingDiagnostic:
    """Diagnostic info for a routing failure."""
    failure_type: FailureType
    net: str | None = None
    blocking_elements: list[str] = field(default_factory=list)
    location: tuple[float, float] | None = None
    message: str = ""

@dataclass
class RoutabilityReport:
    """Detailed routability analysis report."""
    total_congestion: float
    max_congestion: float
    bottleneck_cells: list[tuple[int, int, float]]
    unrouted_estimate: int
    advice: list[str]
    feasible: bool = True
    diagnostics: list[RoutingDiagnostic] = field(default_factory=list)

def analyze_routability(
    positions: Array,
    context: LossContext,
    grid_shape: tuple[int, int] = (20, 20),
    capacity_per_cell: float = 10.0,
) -> RoutabilityReport:
    """
    Perform a detailed routability analysis.
    
    Args:
        positions: Component positions.
        context: LossContext.
        grid_shape: Resolution of analysis grid.
        capacity_per_cell: Threshold for congestion.
        
    Returns:
        RoutabilityReport with metrics and advice.
    """
    board_bounds = context.board.get_bounds_array()
    demand = compute_routing_demand(positions, context, grid_shape, board_bounds)

    total_congestion = float(jnp.sum(jnp.maximum(0.0, demand - capacity_per_cell)))
    max_congestion = float(jnp.max(demand))

    # Find top bottleneck cells
    bottlenecks = []
    flat_indices = jnp.argsort(demand.ravel())[::-1]
    for i in range(min(10, len(flat_indices))):
        idx = flat_indices[i]
        r, c = divmod(int(idx), grid_shape[1])
        val = float(demand[r, c])
        if val > capacity_per_cell:
            bottlenecks.append((r, c, val))

    # Estimate unrouted nets based on severe congestion
    unrouted_estimate = int(total_congestion / capacity_per_cell)

    # Generate advice
    advice = []
    if max_congestion > capacity_per_cell * 2:
        advice.append("Severe routing bottleneck detected. Consider spreading components in high-congestion zones.")

    if total_congestion > 0:
        advice.append(f"Estimated {unrouted_estimate} nets may be difficult to route due to congestion.")

    # Find components near bottlenecks
    for r, c, val in bottlenecks[:3]:
        # Convert cell to coordinates
        cell_x = board_bounds[0] + (c + 0.5) * (board_bounds[2] - board_bounds[0]) / grid_shape[1]
        cell_y = board_bounds[1] + (r + 0.5) * (board_bounds[3] - board_bounds[1]) / grid_shape[0]

        # Find nearest component
        dists = jnp.linalg.norm(positions - jnp.array([cell_x, cell_y]), axis=1)
        nearest_idx = jnp.argmin(dists)
        nearest_ref = context.netlist.components[nearest_idx].ref

        advice.append(f"Congestion hotspot at ({cell_x:.1f}, {cell_y:.1f}) near {nearest_ref}. Move {nearest_ref} slightly to relieve.")

    return RoutabilityReport(
        total_congestion=total_congestion,
        max_congestion=max_congestion,
        bottleneck_cells=bottlenecks,
        unrouted_estimate=unrouted_estimate,
        advice=advice
    )
