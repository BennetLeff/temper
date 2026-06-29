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

from dataclasses import dataclass

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
    grid_shape: tuple[int, int],
    board_bounds: Array,
) -> Array:
    """
    Compute estimated routing demand per grid cell.

    Uses a simple bounding-box model: each net creates demand along
    its HPWL bounding box edges.

    This is a fully vectorized JAX implementation that supports JIT compilation.

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

    n_nets = context.net_pin_indices.shape[0]
    if n_nets == 0:
        return jnp.zeros((rows, cols), dtype=jnp.float32)

    # Get pin positions for all nets: (M, P, 2)
    all_positions = positions[context.net_pin_indices] + context.net_pin_offsets

    # Compute HPWL bounding box for each net using mask
    # Use where with inf/-inf for proper min/max with masking
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
    bb_min = jnp.min(masked_positions, axis=1)  # (M, 2)
    bb_max = jnp.max(masked_positions_max, axis=1)  # (M, 2)

    # Convert to grid coordinates - fully vectorized
    # col_lo/hi, row_lo/hi for each net: (M,)
    col_lo = jnp.clip((bb_min[:, 0] - x_min) / cell_width, 0, cols - 1).astype(jnp.int32)
    col_hi = jnp.clip((bb_max[:, 0] - x_min) / cell_width, 0, cols - 1).astype(jnp.int32)
    row_lo = jnp.clip((bb_min[:, 1] - y_min) / cell_height, 0, rows - 1).astype(jnp.int32)
    row_hi = jnp.clip((bb_max[:, 1] - y_min) / cell_height, 0, rows - 1).astype(jnp.int32)

    # Compute number of cells per net: (M,)
    n_cells_per_net = jnp.maximum(1, (row_hi - row_lo + 1) * (col_hi - col_lo + 1))

    # Cell demand per net: (M,)
    cell_demand = context.net_weights / n_cells_per_net

    # Mark valid nets (not inf bounding box)
    valid_nets = ~(jnp.isinf(bb_min[:, 0]) | jnp.isinf(bb_max[:, 0]))

    # Use a vectorized approach with outer products and masks
    # Create grid of cell indices
    row_indices = jnp.arange(rows)  # (rows,)
    col_indices = jnp.arange(cols)  # (cols,)

    # For each net, create mask of which cells are in its bounding box
    # (M, rows) - is row in [row_lo, row_hi] for this net?
    row_in_range = (row_indices[None, :] >= row_lo[:, None]) & (
        row_indices[None, :] <= row_hi[:, None]
    )
    # (M, cols) - is col in [col_lo, col_hi] for this net?
    col_in_range = (col_indices[None, :] >= col_lo[:, None]) & (
        col_indices[None, :] <= col_hi[:, None]
    )

    # (M, rows, cols) - cell (r, c) is in net's bounding box
    cell_in_bbox = row_in_range[:, :, None] & col_in_range[:, None, :]

    # Apply valid net mask and multiply by cell demand
    # (M, rows, cols) * (M, 1, 1) -> (M, rows, cols)
    demand_contribution = (
        cell_in_bbox.astype(jnp.float32) * cell_demand[:, None, None] * valid_nets[:, None, None]
    )

    # Sum over all nets to get total demand per cell: (rows, cols)
    demand = jnp.sum(demand_contribution, axis=0)

    return demand


def compute_congestion_penalty(
    positions: Array,
    context: LossContext,
    grid_shape: tuple[int, int] = (10, 10),
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
    board_bounds = context.board.get_relative_bounds_array()
    demand = compute_routing_demand(positions, context, grid_shape, board_bounds)

    # Smooth overflow penalty
    # penalty = sum(max(0, demand - capacity)^2)
    overflow = jnp.maximum(0.0, demand - capacity_per_cell)
    penalty = jnp.sum(overflow**2)

    return penalty


def get_congestion_field(
    positions: Array,
    context: LossContext,
    grid_shape: tuple[int, int] = (20, 20),
) -> Array:
    """
    Generate a spatial congestion field for use in other loss functions.

    Returns a grid where each cell value represents the normalized congestion level.
    1.0 means the cell is at its estimated capacity.

    Args:
        positions: (N, 2) component positions.
        context: LossContext.
        grid_shape: Resolution of the congestion field.

    Returns:
        (rows, cols) normalized congestion field.
    """
    board_bounds = context.board.get_relative_bounds_array()
    demand = compute_routing_demand(positions, context, grid_shape, board_bounds)

    # Simple normalization: assume average demand is a baseline
    avg_demand = jnp.mean(demand) + 1e-6
    normalized_field = demand / avg_demand

    return normalized_field


@dataclass
class CongestionLoss(LossFunction):
    """
    Loss function penalizing routing congestion.

    Divides the board into a grid and estimates routing demand based on
    net connectivity. Penalizes cells where demand exceeds capacity.

    This encourages spreading components to avoid routing bottlenecks.

    The implementation is fully vectorized using JAX operations for
    efficient JIT compilation. Memory usage is O(M * rows * cols) where
    M is the number of nets.

    Attributes:
        grid_shape: (rows, cols) for congestion grid. Higher resolution
            (20x20, 50x50) provides more accurate congestion estimation
            but is more expensive to compute.
        capacity_per_cell: Maximum demand per cell before penalty. Lower
            values create stronger incentives to avoid congestion. Typical
            values: 3.0-10.0 depending on board complexity.
    """

    grid_shape: tuple[int, int] = (20, 20)
    capacity_per_cell: float = 5.0

    @property
    def name(self) -> str:
        return "congestion"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute congestion loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with netlist.
            epoch: Current epoch (unused).
            total_epochs: Total epochs (unused).
            net_virtual_nodes: Optional net virtual nodes (unused).

        Returns:
            LossResult with total congestion penalty and breakdown.
        """
        board_bounds = context.board.get_relative_bounds_array()
        rows, cols = self.grid_shape

        x_min, y_min, x_max, y_max = board_bounds
        cell_width = (x_max - x_min) / cols
        cell_height = (y_max - y_min) / rows

        n_nets = context.net_pin_indices.shape[0]
        if n_nets == 0:
            return LossResult(value=jnp.array(0.0))

        all_positions = positions[context.net_pin_indices] + context.net_pin_offsets

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

        bb_min = jnp.min(masked_positions, axis=1)
        bb_max = jnp.max(masked_positions_max, axis=1)

        col_lo = jnp.clip((bb_min[:, 0] - x_min) / cell_width, 0, cols - 1).astype(jnp.int32)
        col_hi = jnp.clip((bb_max[:, 0] - x_min) / cell_width, 0, cols - 1).astype(jnp.int32)
        row_lo = jnp.clip((bb_min[:, 1] - y_min) / cell_height, 0, rows - 1).astype(jnp.int32)
        row_hi = jnp.clip((bb_max[:, 1] - y_min) / cell_height, 0, rows - 1).astype(jnp.int32)

        n_cells_per_net = jnp.maximum(1, (row_hi - row_lo + 1) * (col_hi - col_lo + 1))
        cell_demand = context.net_weights / n_cells_per_net

        valid_nets = ~(jnp.isinf(bb_min[:, 0]) | jnp.isinf(bb_max[:, 0]))

        row_indices = jnp.arange(rows)
        col_indices = jnp.arange(cols)

        row_in_range = (row_indices[None, :] >= row_lo[:, None]) & (
            row_indices[None, :] <= row_hi[:, None]
        )
        col_in_range = (col_indices[None, :] >= col_lo[:, None]) & (
            col_indices[None, :] <= col_hi[:, None]
        )

        cell_in_bbox = row_in_range[:, :, None] & col_in_range[:, None, :]

        demand_contribution = (
            cell_in_bbox.astype(jnp.float32)
            * cell_demand[:, None, None]
            * valid_nets[:, None, None]
        )

        demand = jnp.sum(demand_contribution, axis=0)

        overflow = jnp.maximum(0.0, demand - self.capacity_per_cell)
        penalty = jnp.sum(overflow**2)

        max_overflow = jnp.max(overflow)
        overflow_cells = jnp.sum(overflow > 0.1)

        breakdown = {
            "congestion_penalty": jnp.array(penalty),
            "max_cell_overflow": jnp.array(max_overflow),
            "overflow_cells": jnp.array(overflow_cells, dtype=jnp.float32),
            "max_utilization": jnp.max(demand / self.capacity_per_cell),
        }

        return LossResult(value=jnp.array(penalty), breakdown=breakdown)


def visualize_congestion(
    positions: Array,
    context: LossContext,
    grid_shape: tuple[int, int] = (10, 10),
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
    board_bounds = context.board.get_relative_bounds_array()
    return compute_routing_demand(positions, context, grid_shape, board_bounds)
