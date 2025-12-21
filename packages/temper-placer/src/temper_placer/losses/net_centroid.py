"""
Pin-to-Net-Centroid Attraction loss function.

Encourages pins on the same net to cluster around their shared geometric center.
Provides smoother gradients than HPWL for global placement.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class NetCentroidAttractionLoss(LossFunction):
    """
    Minimizes the sum of squared distances between each pin and its net's centroid.

    This loss provides a strong attraction force that helps components find
    their globally optimal relative positions.
    """

    @property
    def name(self) -> str:
        return "net_centroid_attraction"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        if context.net_pin_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # 1. Compute absolute pin positions: (M, P, 2)
        # pin_comp_pos: (M, P, 2)
        pin_comp_pos = positions[context.net_pin_indices]
        
        # Apply rotations to offsets (simplified for now - assume 0 rotation or handled by context)
        # In full implementation, we'd use get_rotation_angles
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
        comp_angles = jnp.sum(rotations * angles[None, :], axis=1)
        pin_angles = comp_angles[context.net_pin_indices]
        
        cos_a = jnp.cos(pin_angles)
        sin_a = jnp.sin(pin_angles)
        px, py = context.net_pin_offsets[:, :, 0], context.net_pin_offsets[:, :, 1]
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        
        abs_pin_pos = pin_comp_pos + jnp.stack([rx, ry], axis=-1)
        
        # 2. Compute Net Centroids: (M, 2)
        mask = context.net_pin_mask
        n_pins = jnp.sum(mask, axis=1, keepdims=True)
        # Sum only valid pins
        centroids = jnp.sum(abs_pin_pos * mask[:, :, None], axis=1) / jnp.maximum(n_pins, 1.0)
        
        # 3. Compute Squared Distance from Pin to Centroid
        # (M, P, 2) - (M, 1, 2) -> (M, P, 2)
        diff_sq = (abs_pin_pos - centroids[:, None, :]) ** 2
        # Sum over components, pins, and dimensions
        penalty = jnp.sum(jnp.sum(diff_sq, axis=2) * mask * context.net_weights[:, None])
        
        return LossResult(value=penalty)
