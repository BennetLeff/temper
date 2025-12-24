"""
Grid alignment loss function for manufacturing-friendly placement.

This loss penalizes components that are not aligned to a regular 
manufacturing grid (e.g., 0.5mm or 1.0mm). 
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class GridAlignmentLoss(LossFunction):
    """
    Penalize components not on a regular grid.

    Attributes:
        grid_size: Grid spacing in mm (default 0.5mm).
        anneal_start: Fraction of training (0.0-1.0) when this loss starts.
    """

    def __init__(
        self,
        grid_size: float = 0.5,
        anneal_start: float = 0.5,
    ):
        self.grid_size = grid_size
        self.anneal_start = anneal_start

    @property
    def name(self) -> str:
        return "grid"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        **kwargs: Any,
    ) -> LossResult:
        """
        Compute total grid misalignment penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext.

        Returns:
            LossResult with sum of squared distances to nearest grid points.
        """
        # Distance to nearest grid point
        # x_offset in [0, grid_size)
        x_offset = jnp.mod(positions[:, 0], self.grid_size)
        y_offset = jnp.mod(positions[:, 1], self.grid_size)

        # Wrap to nearest grid (if offset is 0.4 and grid is 0.5, dist is 0.1)
        dist_x = jnp.minimum(x_offset, self.grid_size - x_offset)
        dist_y = jnp.minimum(y_offset, self.grid_size - y_offset)

        # Sum of squared distances
        # We use squared distance for smooth gradients toward grid points
        penalty_per_comp = dist_x**2 + dist_y**2

        total = jnp.sum(penalty_per_comp)

        return LossResult(
            value=total,
            breakdown={
                "per_component": penalty_per_comp,
            },
        )

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Ramp up grid alignment penalty in late training.

        Early on, components should move freely. Late in training,
        they should snap to grid.
        """
        # Ensure total_epochs is at least 1 to avoid division by zero
        total_epochs_safe = jnp.maximum(total_epochs, 1)
        progress = epoch / total_epochs_safe

        # Linear ramp from anneal_start to 1.0
        # Use maximum(..., 1e-6) to avoid division by zero if anneal_start is 1.0
        denom = jnp.maximum(1.0 - self.anneal_start, 1e-6)
        ramp = (progress - self.anneal_start) / denom
        ramp_val = jnp.clip(ramp, 0.0, 1.0)

        # Use jnp.where for conditional logic to be JIT-compatible
        return jnp.where(progress < self.anneal_start, 0.0, ramp_val)


def compute_grid_penalty(
    positions: Array,
    grid_size: float = 0.5,
) -> Array:
    """
    Standalone function to compute grid alignment penalty.

    Args:
        positions: (N, 2) component positions.
        grid_size: Grid spacing.

    Returns:
        Scalar grid penalty value.
    """
    x_offset = jnp.mod(positions[:, 0], grid_size)
    y_offset = jnp.mod(positions[:, 1], grid_size)
    dist_x = jnp.minimum(x_offset, grid_size - x_offset)
    dist_y = jnp.minimum(y_offset, grid_size - y_offset)
    return jnp.sum(dist_x**2 + dist_y**2)
