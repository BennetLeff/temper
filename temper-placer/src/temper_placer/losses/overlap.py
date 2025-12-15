"""
Overlap loss function for preventing component collisions.

This loss penalizes overlapping components using signed distance functions
for smooth, differentiable collision detection. A squared penalty is applied
to overlaps to create strong gradients pushing components apart.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.overlap import box_box_distance
from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class OverlapLoss(LossFunction):
    """
    Penalize overlapping components using SDF-based collision detection.

    For each pair of components, computes the minimum distance between their
    bounding boxes. Negative distance indicates overlap. A squared penalty
    is applied to overlaps: relu(-distance)².

    This is a hard constraint that should have high weight in the total loss.

    Attributes:
        margin: Additional clearance margin beyond component bounds (mm).
        use_rotated_bounds: If True, use rotation-aware bounding boxes.
    """

    def __init__(
        self,
        margin: float = 0.0,
        use_rotated_bounds: bool = True,
    ):
        """
        Initialize OverlapLoss.

        Args:
            margin: Additional clearance margin (mm).
            use_rotated_bounds: Whether to account for component rotation.
        """
        self.margin = margin
        self.use_rotated_bounds = use_rotated_bounds

    @property
    def name(self) -> str:
        return "overlap"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total overlap penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with component bounds.

        Returns:
            LossResult with sum of squared overlap amounts.
        """
        n = positions.shape[0]
        bounds = context.bounds  # (N, 2) - (width, height)

        # Get effective bounds after rotation
        if self.use_rotated_bounds:
            widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)
        else:
            widths = bounds[:, 0]
            heights = bounds[:, 1]

        # Compute pairwise overlaps
        total_overlap = jnp.array(0.0)

        # Use vectorized pairwise computation for efficiency
        # Create index pairs for upper triangle (i < j)
        total_overlap = self._compute_pairwise_overlaps(positions, widths, heights, n)

        return LossResult(value=total_overlap)

    def _compute_pairwise_overlaps(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        n: int,
    ) -> Array:
        """
        Compute sum of squared overlaps for all component pairs.

        Uses vectorized operations for efficiency.
        """
        # Vectorized computation of all pairwise distances
        # positions: (N, 2), create (N, N, 2) for pairwise differences
        pos_diff = positions[:, None, :] - positions[None, :, :]  # (N, N, 2)

        # Half-widths and half-heights
        half_w = (widths + self.margin) / 2.0
        half_h = (heights + self.margin) / 2.0

        # For each pair (i, j), the box-box distance is:
        # max(|dx| - (half_w_i + half_w_j), |dy| - (half_h_i + half_h_j), 0)
        # But we use signed distance (negative = overlap)

        # Combined half-dimensions for each pair
        combined_half_w = half_w[:, None] + half_w[None, :]  # (N, N)
        combined_half_h = half_h[:, None] + half_h[None, :]  # (N, N)

        # Absolute position differences
        abs_dx = jnp.abs(pos_diff[:, :, 0])  # (N, N)
        abs_dy = jnp.abs(pos_diff[:, :, 1])  # (N, N)

        # Separation in x and y (negative = overlap in that dimension)
        sep_x = abs_dx - combined_half_w  # (N, N)
        sep_y = abs_dy - combined_half_h  # (N, N)

        # Box-box signed distance:
        # - If both sep_x and sep_y positive: distance = sqrt(sep_x² + sep_y²)
        # - If one is negative: distance = max(sep_x, sep_y)
        # - If both negative: distance = max(sep_x, sep_y) which is negative (overlap)

        # Simplified: signed distance = max(sep_x, sep_y) when either is negative
        # For non-overlapping with both positive: Euclidean distance
        # For overlap penalty, we only care about negative distances

        # Use max of separations (this gives negative value for overlaps)
        signed_dist = jnp.maximum(sep_x, sep_y)  # (N, N)

        # Squared overlap penalty: relu(-distance)²
        overlap_amount = jax.nn.relu(-signed_dist) ** 2  # (N, N)

        # Only count upper triangle (i < j) to avoid double counting
        # Also exclude diagonal (i == i)
        mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)

        # Sum overlaps (only upper triangle)
        total = jnp.sum(overlap_amount * mask)

        return total

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Overlap is a hard constraint - full weight from early in training.

        Returns 1.0 after a brief warm-up period.
        """
        return 1.0


def compute_overlap_penalty(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float = 0.0,
) -> Array:
    """
    Standalone function to compute overlap penalty.

    Args:
        positions: (N, 2) component positions.
        widths: (N,) component widths.
        heights: (N,) component heights.
        margin: Additional clearance margin.

    Returns:
        Scalar overlap penalty value.
    """
    n = positions.shape[0]

    # Position differences
    pos_diff = positions[:, None, :] - positions[None, :, :]

    # Half dimensions with margin
    half_w = (widths + margin) / 2.0
    half_h = (heights + margin) / 2.0

    # Combined half-dimensions
    combined_half_w = half_w[:, None] + half_w[None, :]
    combined_half_h = half_h[:, None] + half_h[None, :]

    # Separations
    sep_x = jnp.abs(pos_diff[:, :, 0]) - combined_half_w
    sep_y = jnp.abs(pos_diff[:, :, 1]) - combined_half_h

    # Signed distance and penalty
    signed_dist = jnp.maximum(sep_x, sep_y)
    overlap_amount = jax.nn.relu(-signed_dist) ** 2

    # Upper triangle mask
    mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)

    return jnp.sum(overlap_amount * mask)
