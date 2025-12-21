"""
Manufacturing margin loss function.

This loss encourages maximizing manufacturing margins (spacing beyond minimum DRC)
to improve yield and reliability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult

if TYPE_CHECKING:
    from temper_placer.io.config_loader import PlacementConstraints
    from temper_placer.losses.base import WeightedLoss


@dataclass
class ManufacturingMarginLoss(LossFunction):
    """
    Penalize tight manufacturing margins.

    Attributes:
        target_margin_mm: Margin at which penalty becomes zero (comfortable).
        weight: Importance of maximizing margins.
        sharpness: Steepness of the margin penalty curve.
    """

    target_margin_mm: float = 0.1
    sharpness: float = 5.0

    @property
    def name(self) -> str:
        return "manufacturing_margin"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        n = positions.shape[0]
        if n < 2:
            return LossResult(value=jnp.array(0.0))

        # 1. Get component dimensions
        bounds = context.netlist.get_bounds_array()
        widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)

        # 2. Compute pairwise edge-to-edge distances
        # Simplified AABB distance for performance
        # dx = max(0, abs(x1-x2) - (w1+w2)/2)
        # dy = max(0, abs(y1-y2) - (h1+h2)/2)
        # However, for margins, we care about near-misses too.
        
        # Center-to-center distances
        dx_cc = jnp.abs(positions[:, None, 0] - positions[None, :, 0])
        dy_cc = jnp.abs(positions[:, None, 1] - positions[None, :, 1])
        
        # Combined half-dims
        hw_sum = (widths[:, None] + widths[None, :]) / 2.0
        hh_sum = (heights[:, None] + heights[None, :]) / 2.0
        
        # Separation in X and Y
        # Negative means overlap
        sep_x = dx_cc - hw_sum
        sep_y = dy_cc - hh_sum
        
        # Minimum distance between AABBs is approx max(sep_x, sep_y) if not overlapping in both
        # But we want a smooth differentiable distance.
        # Let's use the same logic as OverlapLoss but focus on positive margins.
        
        # For each pair i,j where i < j
        i_indices, j_indices = jnp.triu_indices(n, k=1)
        
        sx = sep_x[i_indices, j_indices]
        sy = sep_y[i_indices, j_indices]
        
        # 2D distance between boxes
        # dist = max(sx, sy) if sx > 0 or sy > 0
        # If sx < 0 and sy < 0, it's overlap.
        margins = jnp.maximum(sx, sy)
        
        # 3. Compute loss
        # Soft penalty: softplus(-margins / target * sharpness)
        # Increases as margin decreases.
        normalized_margins = margins / jnp.maximum(self.target_margin_mm, 1e-6)
        
        # Smooth penalty for tight margins
        margin_penalty = jnp.sum(jax.nn.softplus(-normalized_margins * self.sharpness))
        
        # Strong penalty for violations (negative margins)
        violations = jax.nn.relu(-margins)
        violation_penalty = jnp.sum(violations**2) * 100.0
        
        total = margin_penalty + violation_penalty
        
        return LossResult(
            value=total,
            breakdown={
                "margin_penalty": margin_penalty,
                "violation_penalty": violation_penalty,
            }
        )


def create_manufacturing_losses(
    constraints: PlacementConstraints,
) -> list[WeightedLoss]:
    """
    Create manufacturing-related losses based on constraints.

    Args:
        constraints: Placement constraints.

    Returns:
        List of WeightedLoss instances.
    """
    from temper_placer.losses.base import WeightedLoss

    losses = []
    mfg_cfg = constraints.manufacturing

    if mfg_cfg.margin_weight > 0:
        losses.append(
            WeightedLoss(
                ManufacturingMarginLoss(target_margin_mm=mfg_cfg.target_margin_mm),
                weight=mfg_cfg.margin_weight,
            )
        )

    return losses

