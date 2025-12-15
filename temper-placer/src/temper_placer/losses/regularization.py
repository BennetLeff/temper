"""
Regularization loss functions.

This module provides regularization losses to improve optimization behavior:
- SpreadLoss: Prevents components from clustering too tightly
- RotationEntropyLoss: Encourages exploration of rotation options (annealed)

These losses help the optimizer escape local minima and explore the solution space.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
    smooth_step,
)


def compute_spread_penalty(
    positions: Array,
    bounds: Array,
    min_distance: float = 2.0,
) -> Array:
    """
    Compute penalty for components that are too close together.

    This is different from overlap - it penalizes components that are
    close even if they don't overlap, encouraging uniform distribution.

    Args:
        positions: (N, 2) component positions.
        bounds: (N, 2) component bounds (width, height).
        min_distance: Minimum desired center-to-center distance.

    Returns:
        Total spread penalty (scalar).
    """
    n = positions.shape[0]
    if n < 2:
        return jnp.array(0.0)

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
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute spread loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused).
            context: LossContext with component bounds.

        Returns:
            LossResult with total spread penalty.
        """
        penalty = compute_spread_penalty(positions, context.bounds, self.min_distance)
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
        positions: Array,
        rotations: Array,
        context: LossContext,
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
        if total_epochs <= 0:
            return 1.0

        progress = epoch / total_epochs

        if progress < self.anneal_start:
            return 1.0
        elif progress > self.anneal_end:
            return 0.0
        else:
            # Linear annealing
            t = (progress - self.anneal_start) / (self.anneal_end - self.anneal_start)
            return 1.0 - t


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
        rotations: Array,
        context: LossContext,
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
                    context.board.origin[0] + context.board.width / 2,
                    context.board.origin[1] + context.board.height / 2,
                ],
                dtype=jnp.float32,
            )

        # Squared distance penalty
        penalty = jnp.sum((com - target) ** 2)

        return LossResult(value=penalty)
