"""
Congestion loss function.

This module estimates routing congestion to encourage balanced component
placement that doesn't create routing hotspots.

Congestion is estimated by:
1. Dividing the board into a grid
2. Estimating demand in each cell based on net connectivity
3. Penalizing cells where demand exceeds capacity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)


def compute_routing_demand(
    positions: Array,
    context: LossContext,
    grid_shape: Tuple[int, int],
    board_bounds: Array,
) -> Array:
    """
    Compute estimated routing demand per grid cell.

    Uses a simple bounding-box model: each net creates demand along
    its HPWL bounding box edges.

    Args:
        positions: (N, 2) component positions.
        context: LossContext with netlist.
        grid_shape: (rows, cols) grid dimensions.
        board_bounds: [x_min, y_min, x_max, y_max] board bounds.

    Returns:
        (rows, cols) demand array.
    """
    rows, cols = grid_shape
    x_min, y_min, x_max, y_max = board_bounds

    cell_width = (x_max - x_min) / cols
    cell_height = (y_max - y_min) / rows

    demand = jnp.zeros((rows, cols), dtype=jnp.float32)

    # Process nets with vectorized operations
    n_nets = context.net_pin_indices.shape[0]
    if n_nets == 0:
        return demand

    # Get pin positions for all nets
    # (M, P, 2) = positions[indices] + offsets
    all_positions = positions[context.net_pin_indices] + context.net_pin_offsets

    # Compute HPWL bounding box for each net using mask
    # Set invalid positions to inf/-inf for min/max
    masked_positions = jnp.where(
        context.net_pin_mask[:, :, None],
        all_positions,
        jnp.array([jnp.inf, jnp.inf]),
    )
    masked_positions_max = jnp.where(
        context.net_pin_mask[:, :, None],
        all_positions,
        jnp.array([-jnp.inf, -jnp.inf]),
    )

    # (M, 2) bounding boxes
    bb_min = jnp.min(masked_positions, axis=1)
    bb_max = jnp.max(masked_positions_max, axis=1)

    # Estimate demand: distribute net's weight across cells in bounding box
    # This is a simplified model that accumulates demand in touched cells
    for net_idx in range(n_nets):
        x_lo, y_lo = bb_min[net_idx]
        x_hi, y_hi = bb_max[net_idx]
        weight = float(context.net_weights[net_idx])

        # Skip invalid nets
        if jnp.isinf(x_lo) or jnp.isinf(x_hi):
            continue

        # Convert to grid coordinates
        col_lo = int(jnp.clip((x_lo - x_min) / cell_width, 0, cols - 1))
        col_hi = int(jnp.clip((x_hi - x_min) / cell_width, 0, cols - 1))
        row_lo = int(jnp.clip((y_lo - y_min) / cell_height, 0, rows - 1))
        row_hi = int(jnp.clip((y_hi - y_min) / cell_height, 0, rows - 1))

        # Add demand to cells in bounding box
        # Weight distributed by net weight and number of cells
        n_cells = max(1, (row_hi - row_lo + 1) * (col_hi - col_lo + 1))
        cell_demand = weight / n_cells

        for r in range(row_lo, row_hi + 1):
            for c in range(col_lo, col_hi + 1):
                demand = demand.at[r, c].add(cell_demand)

    return demand


def compute_congestion_penalty(
    positions: Array,
    context: LossContext,
    grid_shape: Tuple[int, int] = (10, 10),
    capacity_per_cell: float = 10.0,
) -> Array:
    """
    Compute routing congestion penalty.

    Penalizes grid cells where estimated demand exceeds capacity.

    Args:
        positions: (N, 2) component positions.
        context: LossContext with netlist.
        grid_shape: (rows, cols) congestion grid.
        capacity_per_cell: Maximum demand per cell before penalty.

    Returns:
        Total congestion penalty (scalar).
    """
    board_bounds = context.board.get_bounds_array()
    demand = compute_routing_demand(positions, context, grid_shape, board_bounds)

    # Smooth overflow penalty
    # penalty = sum(max(0, demand - capacity)^2)
    overflow = jnp.maximum(0.0, demand - capacity_per_cell)
    penalty = jnp.sum(overflow**2)

    return penalty


@dataclass
class CongestionLoss(LossFunction):
    """
    Loss function penalizing routing congestion.

    Divides the board into a grid and estimates routing demand based on
    net connectivity. Penalizes cells where demand exceeds capacity.

    This encourages spreading components to avoid routing bottlenecks.

    Attributes:
        grid_shape: (rows, cols) for congestion grid.
        capacity_per_cell: Maximum demand per cell before penalty.

    Note:
        Current implementation uses Python loops for demand accumulation.
        For full JIT compatibility, this should be rewritten using
        scatter operations or pre-computed cell indices.
    """

    grid_shape: Tuple[int, int] = (10, 10)
    capacity_per_cell: float = 10.0

    @property
    def name(self) -> str:
        return "congestion"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute congestion loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with netlist.

        Returns:
            LossResult with total congestion penalty.
        """
        penalty = compute_congestion_penalty(
            positions, context, self.grid_shape, self.capacity_per_cell
        )
        return LossResult(value=penalty)


def visualize_congestion(
    positions: Array,
    context: LossContext,
    grid_shape: Tuple[int, int] = (10, 10),
) -> Array:
    """
    Generate congestion heatmap for visualization.

    Args:
        positions: (N, 2) component positions.
        context: LossContext with netlist.
        grid_shape: (rows, cols) for congestion grid.

    Returns:
        (rows, cols) demand array for plotting.
    """
    board_bounds = context.board.get_bounds_array()
    return compute_routing_demand(positions, context, grid_shape, board_bounds)
