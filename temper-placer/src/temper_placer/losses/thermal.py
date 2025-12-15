"""
Thermal placement loss function.

This module enforces thermal placement constraints, ensuring heat-generating
components (like IGBTs) are placed near board edges where heatsinks can be mounted.

For the Temper induction cooker:
- Q1, Q2 (IGBTs) must be within 5mm of TOP edge for heatsink mounting
- Gate drive components should be close to their respective IGBTs
"""

from __future__ import annotations

from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
    ThermalConstraint,
)


def compute_edge_distance(
    position: Array,
    board_bounds: Array,
    edge: str,
) -> Array:
    """
    Compute distance from a position to a board edge.

    Args:
        position: (2,) position [x, y] in mm.
        board_bounds: [x_min, y_min, x_max, y_max] board bounds.
        edge: Edge name ("TOP", "BOTTOM", "LEFT", "RIGHT").

    Returns:
        Scalar distance to edge in mm.
    """
    x, y = position[0], position[1]
    x_min, y_min, x_max, y_max = board_bounds

    if edge == "TOP":
        return y_max - y
    elif edge == "BOTTOM":
        return y - y_min
    elif edge == "LEFT":
        return x - x_min
    elif edge == "RIGHT":
        return x_max - x
    else:
        # Unknown edge, return large distance
        return jnp.array(1000.0)


def compute_thermal_penalty(
    positions: Array,
    context: LossContext,
    margin: float = 0.1,
) -> Array:
    """
    Compute thermal placement penalty.

    Penalizes components that are farther from their required board edge
    than the maximum allowed distance.

    Args:
        positions: (N, 2) component center positions.
        context: LossContext with thermal_constraints and board.
        margin: Soft margin for smooth penalty (mm).

    Returns:
        Total thermal penalty (scalar).
    """
    if not context.thermal_constraints:
        return jnp.array(0.0)

    board_bounds = context.board.get_bounds_array()
    total_penalty = jnp.array(0.0)

    for tc in context.thermal_constraints:
        comp_idx = context.get_component_index(tc.component_ref)
        position = positions[comp_idx]

        # Distance to required edge
        distance = compute_edge_distance(position, board_bounds, tc.edge)

        # Soft penalty: 0 if distance <= max_distance, grows quadratically beyond
        # Using softplus for smooth gradient: log(1 + exp(x))
        excess = distance - tc.max_distance
        # Quadratic penalty for violation, scaled by weight
        penalty = tc.weight * jnp.maximum(0.0, excess) ** 2

        total_penalty = total_penalty + penalty

    return total_penalty


@dataclass
class ThermalLoss(LossFunction):
    """
    Loss function penalizing components far from required board edges.

    For heat-generating components like IGBTs, this loss ensures they are
    placed near board edges where heatsinks can be mounted.

    The penalty is quadratic in the distance beyond the maximum allowed:
    penalty = weight * max(0, distance - max_distance)²

    Attributes:
        margin: Soft margin for penalty calculation (mm).
    """

    margin: float = 0.1

    @property
    def name(self) -> str:
        return "thermal"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute thermal placement loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused for thermal).
            context: LossContext with thermal_constraints.

        Returns:
            LossResult with total thermal penalty.
        """
        penalty = compute_thermal_penalty(positions, context, self.margin)
        return LossResult(value=penalty)


def create_temper_thermal_constraints() -> list[ThermalConstraint]:
    """
    Create default thermal constraints for Temper board.

    The IGBTs (Q1, Q2) must be within 5mm of the TOP edge for heatsink mounting.

    Returns:
        List of ThermalConstraint for Temper board.
    """
    return [
        ThermalConstraint(
            component_ref="Q1",
            edge="TOP",
            max_distance=5.0,
            weight=10.0,  # High weight - critical for thermal management
        ),
        ThermalConstraint(
            component_ref="Q2",
            edge="TOP",
            max_distance=5.0,
            weight=10.0,
        ),
    ]
