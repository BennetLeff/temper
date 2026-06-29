"""
Routability-aware congestion loss.

This module implements a routability loss function that uses the board's
LayerStackup to determine cell capacity, improving the correlation
between placement and routing feasibility.
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
from temper_placer.losses.congestion import compute_routing_demand


@dataclass
class RoutabilityLoss(LossFunction):
    """
    Routability loss based on LayerStackup capacity.

    Attributes:
        grid_shape: (rows, cols) for congestion grid.
        net_class: Primary net class to evaluate capacity for (default "Signal").
        overflow_weight: Multiplier for demand exceeding capacity.
    """

    grid_shape: tuple[int, int] = (12, 12)
    net_class: str = "Signal"
    overflow_weight: float = 10.0

    @property
    def name(self) -> str:
        return "routability"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute routability loss using layer-aware capacity.
        """
        board_bounds = context.board.get_relative_bounds_array()
        demand = compute_routing_demand(positions, context, self.grid_shape, board_bounds)

        # Determine capacity per cell from LayerStackup
        # grid_size is avg of cell width/height
        x_min, y_min, x_max, y_max = board_bounds
        board_w = x_max - x_min
        board_h = y_max - y_min
        cell_w = board_w / self.grid_shape[1]
        cell_h = board_h / self.grid_shape[0]
        grid_size = (cell_w + cell_h) / 2.0

        if context.board.layer_stackup:
            capacity_per_cell = context.board.layer_stackup.tracks_per_cell(
                grid_size, self.net_class
            )
        else:
            # Fallback to default heuristic if no stackup
            capacity_per_cell = 10.0

        # Penalize overflow: sum(max(0, demand - capacity)^2)
        overflow = jnp.maximum(0.0, demand - capacity_per_cell)
        penalty = jnp.sum(overflow**2) * self.overflow_weight

        return LossResult(
            value=penalty,
            breakdown={
                "max_demand": jnp.max(demand),
                "cell_capacity": jnp.array(capacity_per_cell),
                "overflow_cells": jnp.sum(demand > capacity_per_cell).astype(jnp.float32),
            },
        )
