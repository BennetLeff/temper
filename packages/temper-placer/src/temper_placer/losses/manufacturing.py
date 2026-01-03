"""
Manufacturing-related loss functions.

This module implements losses for manufacturing constraints:
1. ManufacturingOrientationLoss - Enforce allowed component orientations (0, 90, 180, 270)
2. ManufacturingSideLoss - Enforce assembly side (Top, Bottom)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class ManufacturingOrientationLoss(LossFunction):
    """
    Penalize orientations that are not allowed by manufacturing constraints.

    Professional PCB assembly often restricts orientations to 90-degree
    increments, or specific subsets (e.g., all DPAKs must be 0 or 180
    to align with heatsink fins).

    This loss works on the 'rotations' array, which is a (N, 4) soft one-hot
    distribution where:
    - index 0: 0 degrees
    - index 1: 90 degrees
    - index 2: 180 degrees
    - index 3: 270 degrees

    Attributes:
        weight: Base penalty weight.
    """

    weight: float = 10.0

    @property
    def name(self) -> str:
        return "manufacturing_orientation"

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
        Compute orientation penalty.

        Args:
            positions: (N, 2) positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext with orientation_mask.

        Returns:
            LossResult with orientation penalty.
        """
        if context.constraints_data.orientation_mask is None:
            return LossResult(value=jnp.array(0.0))

        # orientation_mask is (N, 4) where True means allowed
        # disallowed_mask is (N, 4) where True means penalized
        disallowed_mask = jnp.logical_not(context.constraints_data.orientation_mask)

        # sum the probability mass on disallowed rotations
        # rotations is (N, 4), sum across axis 1
        disallowed_mass = jnp.sum(rotations * disallowed_mask, axis=1)  # (N,)

        # Total penalty is weighted sum of disallowed mass
        total_penalty = self.weight * jnp.sum(disallowed_mass)

        return LossResult(
            value=total_penalty,
            breakdown={
                "orientation_violations": jnp.sum(disallowed_mass > 0.01),
                "max_orientation_violation": jnp.max(disallowed_mass),
            },
        )


@dataclass
class ManufacturingSideLoss(LossFunction):
    """
    Penalize components placed on the wrong side.

    In the current placers, 'side' is often modeled separately or as part
    of a multi-layer stackup. If 'side' is available, this loss penalizes
    violations of side constraints.

    NOTE: The current Temper placer is primarily 2D/pseudo-3D. If side choice
    is not part of the differentiable state, this loss might be used for
    post-placement validation or in a placer that supports side switching.

    Attributes:
        weight: Base penalty weight.
    """

    weight: float = 10.0

    @property
    def name(self) -> str:
        return "manufacturing_side"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        sides: Array | None = None,
    ) -> LossResult:
        """
        Compute side penalty.

        Args:
            positions: (N, 2) positions.
            rotations: (N, 4) soft one-hot rotations.
            sides: (N, 2) soft one-hot sides (0=Top, 1=Bottom).
            context: LossContext with side_mask.

        Returns:
            LossResult with side penalty.
        """
        if sides is None or context.constraints_data.side_mask is None:
            return LossResult(value=jnp.array(0.0))

        # side_mask is (N, 2) where True means allowed
        # disallowed_mask is (N, 2) where True means penalized
        disallowed_mask = jnp.logical_not(context.constraints_data.side_mask)

        # sum the probability mass on disallowed sides
        disallowed_mass = jnp.sum(sides * disallowed_mask, axis=1)  # (N,)

        # Total penalty
        total_penalty = self.weight * jnp.sum(disallowed_mass)

        return LossResult(
            value=total_penalty,
            breakdown={
                "side_violations": jnp.sum(disallowed_mass > 0.01),
                "max_side_violation": jnp.max(disallowed_mass),
            },
        )


def create_manufacturing_losses(context: LossContext) -> list[LossFunction]:
    """
    Create manufacturing losses based on context constraints.
    """
    losses = []
    if context.constraints_data.orientation_mask is not None:
        losses.append(ManufacturingOrientationLoss())
    
    if context.constraints_data.side_mask is not None:
        losses.append(ManufacturingSideLoss())
        
    return losses
