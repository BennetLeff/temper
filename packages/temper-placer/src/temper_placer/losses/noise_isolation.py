"""
Noise-sensitive isolation loss function for PCB placement.

This module implements a loss function that penalizes noise-sensitive components
(like analog sensors and MCU inputs) being placed too close to noisy
switching nodes or high di/dt paths.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


class NoiseSensitiveIsolationLoss(LossFunction):
    """
    Penalize noise-sensitive components being too close to noise sources.

    This loss function enforces physical separation between sensitive analog
    circuitry and noisy power electronics switching nodes.

    Attributes:
        min_distance_mm: Default minimum separation distance in mm.
    """

    def __init__(self, min_distance_mm: float = 10.0):
        """
        Initialize NoiseSensitiveIsolationLoss.

        Args:
            min_distance_mm: Default minimum separation distance.
        """
        self.min_distance_mm = min_distance_mm

    @property
    def name(self) -> str:
        return "noise_isolation"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute total penalty for noise isolation violations.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with pre-computed noise isolation constraints.

        Returns:
            LossResult with total penalty value.
        """
        if not context.noise_isolation_constraints:
            return LossResult(value=jnp.array(0.0))

        total_penalty = jnp.array(0.0)

        for rule in context.noise_isolation_constraints:
            # Get positions of sensitive components and noise sources
            sensitive_pos = positions[jnp.array(rule.sensitive_indices)]  # (S, 2)
            source_pos = positions[jnp.array(rule.noise_source_indices)]    # (N_src, 2)

            # Compute pairwise distances using broadcasting
            # (S, 1, 2) - (1, N_src, 2) -> (S, N_src, 2)
            diff = sensitive_pos[:, None, :] - source_pos[None, :, :]
            dist_sq = jnp.sum(diff**2, axis=-1)
            dist = jnp.sqrt(jnp.maximum(dist_sq, 1e-9))  # (S, N_src)

            # Penalize distances below threshold
            deficit = jnp.maximum(0.0, rule.min_distance - dist)
            penalty = jnp.sum(rule.weight * deficit**2)

            total_penalty = total_penalty + penalty

        return LossResult(value=total_penalty)
