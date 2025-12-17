"""
Overlap loss function for preventing component collisions.

This loss penalizes overlapping components using signed distance functions
for smooth, differentiable collision detection. A squared penalty is applied
to overlaps to create strong gradients pushing components apart.

Optimizations:
- For N < 50 components: Full vectorized (N, N) computation
- For N >= 50 components: Uses chunked computation to reduce peak memory
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult


# Threshold for switching between full vectorized and chunked computation
_VECTORIZED_THRESHOLD = 50


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
        rotation_invariant: If True, use worst-case (square) bounding boxes
            based on max(width, height). This ensures overlap detection works
            regardless of which rotation is ultimately chosen.
    """

    def __init__(
        self,
        margin: float = 0.0,
        use_rotated_bounds: bool = True,
        rotation_invariant: bool = False,
    ):
        """
        Initialize OverlapLoss.

        Args:
            margin: Additional clearance margin (mm).
            use_rotated_bounds: Whether to account for component rotation.
                Ignored if rotation_invariant=True.
            rotation_invariant: If True, use max(width, height) for both
                dimensions of each component. This ensures the overlap
                penalty is consistent regardless of rotation, preventing
                the optimizer from finding placements that only work for
                specific rotations.
        """
        self.margin = margin
        self.use_rotated_bounds = use_rotated_bounds
        self.rotation_invariant = rotation_invariant

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

        # Get effective bounds
        if self.rotation_invariant:
            # Use worst-case bounds: max(width, height) for both dimensions
            # This ensures overlap detection works regardless of rotation
            max_dims = jnp.maximum(bounds[:, 0], bounds[:, 1])
            widths = max_dims
            heights = max_dims
        elif self.use_rotated_bounds:
            widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)
        else:
            widths = bounds[:, 0]
            heights = bounds[:, 1]

        # Compute pairwise overlaps - use optimized version
        total_overlap = _compute_pairwise_overlaps_optimized(
            positions, widths, heights, self.margin
        )

        return LossResult(value=total_overlap)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Overlap is a hard constraint - full weight from early in training.

        Returns 1.0 after a brief warm-up period.
        """
        return 1.0


def _compute_overlap_for_pair(
    pos_i: Array,
    half_w_i: Array,
    half_h_i: Array,
    pos_j: Array,
    half_w_j: Array,
    half_h_j: Array,
) -> Array:
    """Compute squared overlap penalty for a single pair of components."""
    # Absolute position differences
    abs_dx = jnp.abs(pos_i[0] - pos_j[0])
    abs_dy = jnp.abs(pos_i[1] - pos_j[1])

    # Combined half-dimensions
    combined_half_w = half_w_i + half_w_j
    combined_half_h = half_h_i + half_h_j

    # Separation in x and y (negative = overlap)
    sep_x = abs_dx - combined_half_w
    sep_y = abs_dy - combined_half_h

    # Signed distance: max of separations
    signed_dist = jnp.maximum(sep_x, sep_y)

    # Squared overlap penalty
    return jax.nn.relu(-signed_dist) ** 2


def _compute_pairwise_overlaps_vectorized(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float,
) -> Array:
    """
    Compute sum of squared overlaps using full vectorized approach.

    Creates (N, N) matrices - efficient for small N but memory-intensive for large N.
    """
    n = positions.shape[0]

    # Position differences: (N, N, 2)
    pos_diff = positions[:, None, :] - positions[None, :, :]

    # Half-widths and half-heights with margin
    half_w = (widths + margin) / 2.0
    half_h = (heights + margin) / 2.0

    # Combined half-dimensions for each pair: (N, N)
    combined_half_w = half_w[:, None] + half_w[None, :]
    combined_half_h = half_h[:, None] + half_h[None, :]

    # Absolute position differences: (N, N)
    abs_dx = jnp.abs(pos_diff[:, :, 0])
    abs_dy = jnp.abs(pos_diff[:, :, 1])

    # Separation in x and y (negative = overlap)
    sep_x = abs_dx - combined_half_w
    sep_y = abs_dy - combined_half_h

    # Signed distance
    signed_dist = jnp.maximum(sep_x, sep_y)

    # Squared overlap penalty
    overlap_amount = jax.nn.relu(-signed_dist) ** 2

    # Only count upper triangle (i < j)
    mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)

    return jnp.sum(overlap_amount * mask)


def _compute_pairwise_overlaps_chunked(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float,
    chunk_size: int = 32,
) -> Array:
    """
    Compute sum of squared overlaps using chunked approach for memory efficiency.

    Processes pairs in chunks to avoid creating full (N, N) matrices.
    Uses jax.lax.fori_loop for efficient iteration.
    """
    n = positions.shape[0]

    # Half-widths and half-heights with margin
    half_w = (widths + margin) / 2.0
    half_h = (heights + margin) / 2.0

    def process_chunk_i(carry, i):
        """Process all pairs (i, j) where j > i."""
        total = carry

        # Get component i data
        pos_i = positions[i]
        hw_i = half_w[i]
        hh_i = half_h[i]

        # Vectorized computation for all j > i
        # Create mask for valid j indices
        j_indices = jnp.arange(n)
        valid_mask = j_indices > i

        # Compute distances for all j
        abs_dx = jnp.abs(pos_i[0] - positions[:, 0])
        abs_dy = jnp.abs(pos_i[1] - positions[:, 1])

        combined_half_w = hw_i + half_w
        combined_half_h = hh_i + half_h

        sep_x = abs_dx - combined_half_w
        sep_y = abs_dy - combined_half_h

        signed_dist = jnp.maximum(sep_x, sep_y)
        overlap_amount = jax.nn.relu(-signed_dist) ** 2

        # Sum only valid pairs (j > i)
        chunk_sum = jnp.sum(jnp.where(valid_mask, overlap_amount, 0.0))

        return total + chunk_sum, None

    # Use scan for efficient iteration
    total, _ = jax.lax.scan(process_chunk_i, jnp.array(0.0), jnp.arange(n - 1))

    return total


def _compute_pairwise_overlaps_optimized(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float,
) -> Array:
    """
    Compute sum of squared overlaps using the most efficient method for the given N.

    For N < 2: Returns 0 (no pairs to compare)
    For small N (< 50): Uses full vectorized approach
    For large N (>= 50): Uses chunked approach for memory efficiency
    """
    n = positions.shape[0]

    # Edge case: fewer than 2 components means no pairs, so no overlap
    if n < 2:
        return jnp.array(0.0)

    # Use lax.cond for dynamic dispatch based on n
    # Note: Both branches must have same signature, so we pass all args
    return jax.lax.cond(
        n < _VECTORIZED_THRESHOLD,
        lambda args: _compute_pairwise_overlaps_vectorized(*args),
        lambda args: _compute_pairwise_overlaps_chunked(*args),
        (positions, widths, heights, margin),
    )


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
    return _compute_pairwise_overlaps_optimized(positions, widths, heights, margin)
