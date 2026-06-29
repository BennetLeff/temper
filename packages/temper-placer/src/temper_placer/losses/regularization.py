"""
Regularization loss functions.

This module provides regularization losses to improve optimization behavior:
- SpreadLoss: Prevents components from clustering too tightly
- RotationEntropyLoss: Encourages exploration of rotation options (annealed)

These losses help the optimizer escape local minima and explore the solution space.

Optimizations:
- For N < 50 components: Full vectorized (N, N) computation
- For N >= 50 components: Uses chunked computation to reduce peak memory
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)

# Threshold for switching between full vectorized and chunked computation
_VECTORIZED_THRESHOLD = 50


def _compute_spread_penalty_vectorized(
    positions: Array,
    bounds: Array,
    min_distance: float = 2.0,
) -> Array:
    """
    Compute spread penalty using full vectorized approach.

    Creates (N, N) matrices - efficient for small N but memory-intensive for large N.

    Args:
        positions: (N, 2) component positions.
        bounds: (N, 2) component bounds (width, height).
        min_distance: Minimum desired center-to-center distance.

    Returns:
        Total spread penalty (scalar).
    """
    n = positions.shape[0]

    # Compute pairwise distances (center-to-center)
    # (N, 1, 2) - (1, N, 2) = (N, N, 2)
    diff = positions[:, None, :] - positions[None, :, :]
    distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-6)  # (N, N)

    # Create mask for unique pairs (upper triangle)
    mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)

    # Compute minimum separation based on component sizes
    # Use half-diagonals as minimum clearance
    half_diag = jnp.sqrt(jnp.sum(bounds**2, axis=-1)) / 2  # (N,)
    min_sep = half_diag[:, None] + half_diag[None, :] + min_distance  # (N, N)

    # Soft penalty for being too close
    deficit = min_sep - distances
    penalties = jnp.maximum(0.0, deficit) ** 2

    # Sum penalties for unique pairs only
    total_penalty = jnp.sum(penalties * mask)

    return total_penalty


def _compute_spread_penalty_chunked(
    positions: Array,
    bounds: Array,
    min_distance: float = 2.0,
) -> Array:
    """
    Compute spread penalty using chunked approach for memory efficiency.

    Processes pairs row-by-row to avoid creating full (N, N) matrices.
    Uses jax.lax.scan for efficient iteration.

    Args:
        positions: (N, 2) component positions.
        bounds: (N, 2) component bounds (width, height).
        min_distance: Minimum desired center-to-center distance.

    Returns:
        Total spread penalty (scalar).
    """
    n = positions.shape[0]

    # Precompute half-diagonals for minimum separation
    half_diag = jnp.sqrt(jnp.sum(bounds**2, axis=-1)) / 2  # (N,)

    def process_row_i(carry, i):
        """Process all pairs (i, j) where j > i."""
        total = carry

        # Get component i data
        pos_i = positions[i]
        half_diag_i = half_diag[i]

        # Create mask for valid j indices (j > i)
        j_indices = jnp.arange(n)
        valid_mask = j_indices > i

        # Compute distances for all j (vectorized over j)
        diff = pos_i - positions  # (N, 2)
        distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-6)  # (N,)

        # Minimum separation for all pairs with i
        min_sep = half_diag_i + half_diag + min_distance  # (N,)

        # Soft penalty for being too close
        deficit = min_sep - distances
        penalties = jnp.maximum(0.0, deficit) ** 2

        # Sum only valid pairs (j > i)
        row_sum = jnp.sum(jnp.where(valid_mask, penalties, 0.0))

        return total + row_sum, None

    # Use scan for efficient iteration over rows
    # Only need to process rows 0 to n-2 (last row has no j > i)
    total, _ = jax.lax.scan(process_row_i, jnp.array(0.0), jnp.arange(n - 1))

    return total


def _compute_edge_spread_penalty(
    positions: Array,
    bounds: Array,
    board_bounds: Array,
    min_distance: float = 2.0,
) -> Array:
    """
    Compute spread penalty against board edges.

    This treats each board edge as a fixed obstacle, providing a repulsive
    force to components near the boundary. This balances the 'edge effect'
    where components at the perimeter have fewer neighbors to push them inwards.
    """
    x_min, y_min, x_max, y_max = board_bounds
    # Use half-diagonal for consistency with pairwise spread computation
    half_diag = jnp.sqrt(jnp.sum(bounds**2, axis=-1)) / 2  # (N,)

    # Distance from center to each edge
    dist_left = positions[:, 0] - x_min
    dist_right = x_max - positions[:, 0]
    dist_bottom = positions[:, 1] - y_min
    dist_top = y_max - positions[:, 1]

    # Required distance = component radius + min_distance
    req = half_diag + min_distance

    # Soft penalty for being too close to any edge
    # We use squared penalty to match pairwise spread penalty
    penalty_left = jnp.maximum(0.0, req - dist_left) ** 2
    penalty_right = jnp.maximum(0.0, req - dist_right) ** 2
    penalty_bottom = jnp.maximum(0.0, req - dist_bottom) ** 2
    penalty_top = jnp.maximum(0.0, req - dist_top) ** 2

    return jnp.sum(penalty_left + penalty_right + penalty_bottom + penalty_top)


def compute_spread_penalty(
    positions: Array,
    bounds: Array,
    board_bounds: Array | None = None,
    min_distance: float = 2.0,
) -> Array:
    """
    Compute penalty for components that are too close together.

    This is different from overlap - it penalizes components that are
    close even if they don't overlap, encouraging uniform distribution.

    Uses optimized computation based on number of components:
    - For N < 50: Full vectorized (N, N) computation
    - For N >= 50: Chunked computation to reduce peak memory

    Args:
        positions: (N, 2) component positions.
        bounds: (N, 2) component bounds (width, height).
        min_distance: Minimum desired center-to-center distance.

    Returns:
        Total spread penalty (scalar) including boundary repulsion if board_bounds provided.
    """
    n = positions.shape[0]
    if n < 2:
        # Still compute edge penalty even for single component
        if board_bounds is not None:
            return _compute_edge_spread_penalty(positions, bounds, board_bounds, min_distance)
        return jnp.array(0.0)

    # Pairwise component-to-component spread
    # Use lax.cond for dynamic dispatch based on n
    pairwise_penalty = jax.lax.cond(
        n < _VECTORIZED_THRESHOLD,
        lambda: _compute_spread_penalty_vectorized(positions, bounds, min_distance),
        lambda: _compute_spread_penalty_chunked(positions, bounds, min_distance),
    )

    # Component-to-edge spread (optional)
    edge_penalty = jnp.array(0.0)
    if board_bounds is not None:
        edge_penalty = _compute_edge_spread_penalty(positions, bounds, board_bounds, min_distance)

    return pairwise_penalty + edge_penalty


def compute_rotation_entropy(
    rotations: Array,
) -> Array:
    """
    Compute negative entropy of rotation distributions.

    Higher entropy = more uniform distribution across rotations.
    This loss DECREASES entropy, so use negative weight or invert.

    For encouraging exploration, use negative weight on this loss.

    Args:
        rotations: (N, 4) soft one-hot rotation indicators.

    Returns:
        Negative entropy (higher = more peaked distribution).
    """
    # Normalize to ensure valid probability distribution
    probs = rotations / (jnp.sum(rotations, axis=-1, keepdims=True) + 1e-8)

    # Compute entropy per component
    # H = -sum(p * log(p))
    log_probs = jnp.log(probs + 1e-8)
    entropy = -jnp.sum(probs * log_probs, axis=-1)  # (N,)

    # Return negative mean entropy (minimize this to maximize entropy)
    return -jnp.mean(entropy)


@dataclass
class SpreadLoss(LossFunction):
    """
    Loss function encouraging uniform component distribution.

    Penalizes components that are close together, even if not overlapping.
    This helps spread components across the board and can improve
    routability by reducing local congestion.

    Attributes:
        min_distance: Minimum desired center-to-center distance beyond
            component sizes (mm).
    """

    min_distance: float = 2.0

    @property
    def name(self) -> str:
        return "spread"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        **_kwargs: Any,
    ) -> LossResult:
        """
        Compute spread loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with component bounds and board.

        Returns:
            LossResult with total spread penalty.
        """
        board_bounds = context.board.get_relative_bounds_array()
        penalty = compute_spread_penalty(positions, context.bounds, board_bounds, self.min_distance)
        return LossResult(value=penalty)


@dataclass
class RotationEntropyLoss(LossFunction):
    """
    Loss function encouraging rotation exploration.

    Returns negative entropy of rotation distributions, so minimizing this
    loss MAXIMIZES entropy (more uniform rotation probabilities).

    This is typically annealed during training:
    - Early: High weight encourages exploration
    - Late: Low/zero weight allows convergence to discrete rotations

    Attributes:
        anneal_start: Epoch fraction to start annealing (0.0-1.0).
        anneal_end: Epoch fraction to finish annealing.
    """

    anneal_start: float = 0.0
    anneal_end: float = 0.5  # Anneal to zero by halfway through training

    @property
    def name(self) -> str:
        return "rotation_entropy"

    def __call__(
        self,
        _positions: Array,
        rotations: Array,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute rotation entropy loss.

        Args:
            positions: (N, 2) component positions (unused).
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext (unused).

        Returns:
            LossResult with negative entropy.
        """
        neg_entropy = compute_rotation_entropy(rotations)
        return LossResult(value=neg_entropy)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Anneal weight from 1.0 to 0.0.

        Early in training, entropy regularization helps exploration.
        Later, we want to converge to discrete rotations.
        """
        # Use jnp.maximum to avoid division by zero and be JAX-compatible
        epochs_safe = jnp.maximum(total_epochs, 1)
        progress = epoch / epochs_safe

        # Use jnp.where to be JAX-compatible (avoid Python if/else on tracers)
        # Linear annealing: 1.0 -> 0.0 between anneal_start and anneal_end
        t = (progress - self.anneal_start) / jnp.maximum(self.anneal_end - self.anneal_start, 1e-6)
        linear_val = jnp.clip(1.0 - t, 0.0, 1.0)

        result = jnp.where(
            progress < self.anneal_start,
            1.0,
            jnp.where(progress > self.anneal_end, 0.0, linear_val),
        )
        return cast(float, result)


@dataclass
class CenterOfMassLoss(LossFunction):
    """
    Loss function penalizing deviation from desired center of mass.

    Useful for ensuring balanced weight distribution on the board,
    particularly for thermal management or mechanical stability.

    Attributes:
        target: (x, y) target center of mass position.
            If None, uses board center.
    """

    target: tuple[float, float] | None = None

    @property
    def name(self) -> str:
        return "center_of_mass"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **_kwargs: Any,
    ) -> LossResult:
        """
        Compute center of mass deviation loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with board info.

        Returns:
            LossResult with squared distance from target.
        """
        # Compute center of mass (uniform weights for now)
        com = jnp.mean(positions, axis=0)

        # Get target
        if self.target is not None:
            target = jnp.array(self.target, dtype=jnp.float32)
        else:
            # Use board center
            target = jnp.array(
                [
                    context.board.width / 2,
                    context.board.height / 2,
                ],
                dtype=jnp.float32,
            )

        # Squared distance penalty
        penalty = jnp.sum((com - target) ** 2)

        return LossResult(value=penalty)


@dataclass
class EdgeAvoidanceLoss(LossFunction):
    """
    Loss function penalizing components near board edges.

    This counteracts the edge-pushing effect of SpreadLoss, which can hurt
    routing completion by placing components in hard-to-route edge locations.

    The loss increases quadratically as components approach within 'margin'
    of any board edge, encouraging an internal placement region.

    Attributes:
        margin: Distance from edge (in mm) within which penalty applies.
            Components further than margin from all edges have zero penalty.
    """

    margin: float = 10.0

    @property
    def name(self) -> str:
        return "edge_avoidance"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        **_kwargs: Any,
    ) -> LossResult:
        """
        Compute edge avoidance loss.

        Args:
            positions: (N, 3) component positions (x, y, rotation_idx).
            _rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with board and bounds info.
            _epoch: Current epoch (unused).
            _total_epochs: Total epochs (unused).

        Returns:
            LossResult with total edge avoidance penalty.
        """
        # Extract x, y positions (ignore rotation index in positions[:, 2])
        xy = positions[:, :2]  # (N, 2)
        bounds = context.bounds  # (N, 2)

        # Component half-widths and half-heights
        half_w = bounds[:, 0] / 2.0  # (N,)
        half_h = bounds[:, 1] / 2.0  # (N,)

        # Board boundaries
        x_min = 0.0
        y_min = 0.0
        x_max = context.board.width
        y_max = context.board.height

        # Distance from component edges to board edges
        # Positive = safe, negative = component extends beyond board
        dist_left = xy[:, 0] - half_w - x_min  # (N,)
        dist_right = x_max - (xy[:, 0] + half_w)  # (N,)
        dist_bottom = xy[:, 1] - half_h - y_min  # (N,)
        dist_top = y_max - (xy[:, 1] + half_h)  # (N,)

        # Deficit = how far component is within the margin zone
        # Positive deficit = within margin, needs penalty
        deficit_left = self.margin - dist_left  # (N,)
        deficit_right = self.margin - dist_right  # (N,)
        deficit_bottom = self.margin - dist_bottom  # (N,)
        deficit_top = self.margin - dist_top  # (N,)

        # Quadratic penalty for being within margin
        # max(0, deficit)^2 ensures penalty only when deficit > 0
        penalty_left = jnp.maximum(0.0, deficit_left) ** 2
        penalty_right = jnp.maximum(0.0, deficit_right) ** 2
        penalty_bottom = jnp.maximum(0.0, deficit_bottom) ** 2
        penalty_top = jnp.maximum(0.0, deficit_top) ** 2

        # Sum across all edges and all components
        total_penalty = jnp.sum(penalty_left + penalty_right + penalty_bottom + penalty_top)

        return LossResult(value=total_penalty)
