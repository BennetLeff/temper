"""
Spatial feedback loss for routing-aware placement refinement.

This module implements a loss function that penalizes placing components
near known routing hotspots (areas where previous routing attempts failed).
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


@dataclass
class SpatialFeedbackLoss(LossFunction):
    """
    Penalizes components near routing failure hotspots.

    Attributes:
        penalty_scale: Multiplier for repulsion intensity.
        sigma: Standard deviation of Gaussian repulsion (mm).
    """

    penalty_scale: float = 100.0
    sigma: float = 5.0

    @property
    def name(self) -> str:
        return "spatial_feedback"

    def __call__(
        self,
        positions: Array,
        rotations: Array,  # noqa: ARG002
        context: LossContext,
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        """
        Compute repulsion from routing hotspots.
        """
        # spatial_penalties: (K, 3) -> [x, y, magnitude]
        penalties = context.spatial_penalties

        if penalties.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        hotspot_coords = penalties[:, :2] # (K, 2)
        hotspot_mags = penalties[:, 2]   # (K,)

        # distance from every component to every hotspot
        # positions: (N, 2), hotspots: (K, 2)
        diff = positions[:, None, :] - hotspot_coords[None, :, :]
        dist_sq = jnp.sum(diff**2, axis=-1) # (N, K)

        # Gaussian repulsion: mag * exp(-dist^2 / (2 * sigma^2))
        repulsion = jnp.exp(-dist_sq / (2 * self.sigma**2))

        # Weighted by hotspot magnitude and component importance (area)
        weighted_repulsion = repulsion * hotspot_mags[None, :]

        total = jnp.sum(weighted_repulsion) * self.penalty_scale

        return LossResult(
            value=total,
            breakdown={
                "num_hotspots": jnp.array(penalties.shape[0], dtype=jnp.float32),
                "max_repulsion": jnp.max(weighted_repulsion) if weighted_repulsion.size > 0 else jnp.array(0.0),
            },
        )
