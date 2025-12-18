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

from typing import Optional, Tuple

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
        inflation_ramp: float = 0.0,
    ):
        """
        Initialize OverlapLoss.

        Args:
            margin: Additional clearance margin (mm).
            use_rotated_bounds: Whether to account for component rotation.
                Ignored if rotation_invariant=True.
            rotation_invariant: If True, use max(width, height) for both
                dimensions of each component.
            inflation_ramp: Fraction of total epochs (0.0 to 1.0) over which
                component sizes ramp from 5% to 100%. Prevents entanglement.
        """
        self.margin = margin
        self.use_rotated_bounds = use_rotated_bounds
        self.rotation_invariant = rotation_invariant
        self.inflation_ramp = inflation_ramp

    @property
    def name(self) -> str:
        return "overlap"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute total overlap penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with component bounds.
            epoch: Current training epoch.
            total_epochs: Total number of epochs.

        Returns:
            LossResult with sum of squared overlap amounts.
        """
        n = positions.shape[0]
        bounds = context.bounds  # (N, 2) - (width, height)

        # Apply soft-body inflation ramp
        if self.inflation_ramp > 0:
            # Calculate multiplier: 0.05 at start, 1.0 at ramp_end
            ramp_end = self.inflation_ramp * total_epochs
            progress = jnp.clip(epoch / jnp.maximum(ramp_end, 1.0), 0.0, 1.0)
            # Quadratic ramp for smoother transition
            multiplier = 0.05 + 0.95 * (progress**2)
            bounds = bounds * multiplier

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

        # Use centrality for weighting if available
        centrality = context.centrality if hasattr(context, "centrality") else None

        # Compute pairwise overlaps - use optimized version
        total_overlap, per_component_overlap = _compute_pairwise_overlaps_optimized(
            positions, widths, heights, self.margin, centrality
        )

        return LossResult(value=total_overlap, breakdown={"per_component": per_component_overlap})

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
    centrality: Optional[Array] = None,
) -> Tuple[Array, Array]:
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

    # Apply centrality weighting if provided
    if centrality is not None and centrality.shape[0] > 0:
        # Boost overlap penalty based on max centrality of pair
        # Scale by n/2 to keep average weight consistent (avg centrality ~ 1/n)
        pair_weight = (centrality[:, None] + centrality[None, :]) * (n / 2.0)
        overlap_amount = overlap_amount * pair_weight

    # For total loss, only count upper triangle (i < j) to avoid double counting
    mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)
    total_overlap = jnp.sum(overlap_amount * mask)

    # For per-component breakdown, sum across rows (all overlaps for each component)
    # We use the full symmetric matrix here but zero out diagonal
    per_component_overlap = jnp.sum(overlap_amount * (1.0 - jnp.eye(n)), axis=1)

    return total_overlap, per_component_overlap


def _compute_pairwise_overlaps_chunked(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float,
    centrality: Optional[Array] = None,
) -> Tuple[Array, Array]:
    """
    Compute sum of squared overlaps using chunked approach for memory efficiency.

    Processes pairs in chunks to avoid creating full (N, N) matrices.
    Uses jax.lax.scan for efficient iteration.
    """
    n = positions.shape[0]

    # Half-widths and half-heights with margin
    half_w = (widths + margin) / 2.0
    half_h = (heights + margin) / 2.0

    def process_i(carry, i):
        """Process component i and sum its overlaps with ALL other components."""
        total_sum = carry

        # Get component i data
        pos_i = positions[i]
        hw_i = half_w[i]
        hh_i = half_h[i]

        # Compute distances for all j
        abs_dx = jnp.abs(pos_i[0] - positions[:, 0])
        abs_dy = jnp.abs(pos_i[1] - positions[:, 1])

        combined_half_w = hw_i + half_w
        combined_half_h = hh_i + half_h

        sep_x = abs_dx - combined_half_w
        sep_y = abs_dy - combined_half_h

        signed_dist = jnp.maximum(sep_x, sep_y)
        overlap_amount = jax.nn.relu(-signed_dist) ** 2

        # Apply centrality weighting if provided
        if centrality is not None and centrality.shape[0] > 0:
            pair_weight = (centrality[i] + centrality) * (n / 2.0)
            overlap_amount = overlap_amount * pair_weight

        # Sum overlaps for component i
        comp_i_sum = jnp.sum(overlap_amount * (1.0 - jax.nn.one_hot(i, n)))

        # For the total global sum, only count j > i
        j_indices = jnp.arange(n)
        upper_mask = j_indices > i
        global_pair_sum = jnp.sum(jnp.where(upper_mask, overlap_amount, 0.0))

        return total_sum + global_pair_sum, comp_i_sum

    # total_global_sum: scalar, per_comp_sums: (N,) array
    total_global_sum, per_comp_sums = jax.lax.scan(process_i, jnp.array(0.0), jnp.arange(n))

    return total_global_sum, per_comp_sums


def _compute_pairwise_overlaps_optimized(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float,
    centrality: Optional[Array] = None,
) -> Tuple[Array, Array]:
    """
    Compute sum of squared overlaps using the most efficient method for the given N.

    For N < 2: Returns (0, zeros) (no pairs to compare)
    For small N (< 50): Uses full vectorized approach
    For large N (>= 50): Uses chunked approach for memory efficiency
    """
    n = positions.shape[0]

    # Use lax.cond for dynamic dispatch based on n
    # Note: We handle n < 2 inside the branches or via another cond to keep structure same
    return jax.lax.cond(
        n < 2,
        lambda _: (jnp.array(0.0), jnp.zeros(n)),
        lambda args: jax.lax.cond(
            args[0].shape[0] < _VECTORIZED_THRESHOLD,
            lambda a: _compute_pairwise_overlaps_vectorized(*a),
            lambda a: _compute_pairwise_overlaps_chunked(*a),
            args,
        ),
        (positions, widths, heights, margin, centrality),
    )


def compute_overlap_penalty(
    positions: Array,
    widths: Array,
    heights: Array,
    margin: float = 0.0,
    centrality: Optional[Array] = None,
) -> Array:
    """
    Standalone function to compute overlap penalty.

    Args:
        positions: (N, 2) component positions.
        widths: (N,) component widths.
        heights: (N,) component heights.
        margin: Additional clearance margin.
        centrality: Optional centrality weights.

    Returns:
        Scalar overlap penalty value.
    """
    total, _ = _compute_pairwise_overlaps_optimized(positions, widths, heights, margin, centrality)
    return total
