"""
Boundary loss function for keeping components within board outline.

This loss penalizes components that extends beyond the board boundaries
or intrude into keepout zones (mounting holes, restricted areas).
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array
from typing import Any

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class BoundaryLoss(LossFunction):
    """
    Penalize components outside board boundaries or in keepout zones.

    For each component, checks if any part of its bounding box extends
    beyond the board edges. Also penalizes components that overlap with
    mounting hole keepout zones.

    This is a hard constraint that should have high weight.

    Attributes:
        edge_margin: Minimum distance from board edge (mm).
        margin_ramp: If > 0, fraction of epochs over which to ramp from 0 to edge_margin.
        keepout_penalty_scale: Scale factor for keepout violations.
        use_rotated_bounds: Whether to account for component rotation.
    """

    def __init__(
        self,
        edge_margin: float = 0.5,
        margin_ramp: float = 0.3,
        keepout_penalty_scale: float = 1.0,
        use_rotated_bounds: bool = True,
        inflation_ramp: float = 0.0,
    ):
        """
        Initialize BoundaryLoss.

        Args:
            edge_margin: Minimum clearance from board edges (mm).
            margin_ramp: Fraction of epochs over which to ramp margin.
            keepout_penalty_scale: Scale factor for keepout violations.
            use_rotated_bounds: Whether to use rotation-aware bounds.
            inflation_ramp: Fraction of epochs over which to ramp component size.
        """
        self.edge_margin = edge_margin
        self.margin_ramp = margin_ramp
        self.keepout_penalty_scale = keepout_penalty_scale
        self.use_rotated_bounds = use_rotated_bounds
        self.inflation_ramp = inflation_ramp

    @property
    def name(self) -> str:
        return "boundary"

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
        Compute total boundary violation penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with board and component bounds.

        Returns:
            LossResult with sum of boundary violation penalties.
        """
        n = positions.shape[0]
        if n == 0:
            return LossResult(
                value=jnp.array(0.0),
                breakdown={
                    "edge_violation": jnp.array(0.0),
                    "keepout_violation": jnp.array(0.0),
                    "per_component": jnp.array([]),
                }
            )

        bounds = context.bounds  # (N, 2)
        board = context.board
        centrality = context.centrality if hasattr(context, "centrality") else None

        # Apply soft-body inflation ramp
        if self.inflation_ramp > 0:
            ramp_end = self.inflation_ramp * total_epochs
            progress = jnp.clip(epoch / jnp.maximum(ramp_end, 1.0), 0.0, 1.0)
            multiplier = 0.05 + 0.95 * (progress**2)
            bounds = bounds * multiplier

        # Compute dynamic margin
        current_margin = self.edge_margin
        if self.margin_ramp > 0:
            progress = jnp.clip(epoch / jnp.maximum(self.margin_ramp * total_epochs, 1.0), 0.0, 1.0)
            current_margin = self.edge_margin * progress

        # Get effective bounds after rotation
        if self.use_rotated_bounds:
            widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)
        else:
            widths = bounds[:, 0]
            heights = bounds[:, 1]

        # Compute edge violations
        edge_violations = self._compute_edge_violations(
            positions, widths, heights, board, current_margin, centrality
        )
        edge_penalty = jnp.sum(edge_violations)

        # Compute keepout violations
        keepout_violations = self._compute_keepout_violations(
            positions, widths, heights, board, centrality
        )
        keepout_penalty = jnp.sum(keepout_violations)

        total = edge_penalty + self.keepout_penalty_scale * keepout_penalty

        return LossResult(
            value=total,
            breakdown={
                "edge_violation": edge_penalty,
                "keepout_violation": keepout_penalty,
                "per_component": edge_violations
                + self.keepout_penalty_scale * keepout_violations,
            },
        )

    def _compute_edge_violations(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        board,
        margin: float,
        centrality: Array | None = None,
    ) -> Array:
        """
        Compute penalty for components extending beyond board edges.
        """
        # Board bounds
        board_bounds = board.get_bounds_array()  # [x_min, y_min, x_max, y_max]
        x_min, y_min, x_max, y_max = board_bounds
        n = positions.shape[0]

        # Component half-dimensions
        half_w = widths / 2.0
        half_h = heights / 2.0

        # Component edge positions (accounting for margin)
        comp_left = positions[:, 0] - half_w
        comp_right = positions[:, 0] + half_w
        comp_bottom = positions[:, 1] - half_h
        comp_top = positions[:, 1] + half_h

        # Violations
        left_violation = jax.nn.relu((x_min + margin) - comp_left)
        right_violation = jax.nn.relu(comp_right - (x_max - margin))
        bottom_violation = jax.nn.relu((y_min + margin) - comp_bottom)
        top_violation = jax.nn.relu(comp_top - (y_max - margin))

        violations = 10.0 * (left_violation + right_violation + bottom_violation + top_violation)
        violations += left_violation**2 + right_violation**2 + bottom_violation**2 + top_violation**2

        if centrality is not None and centrality.size > 0:
            violations = violations * (centrality * n)

        return violations

    def _compute_keepout_violations(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        board,
        centrality: Array | None = None,
    ) -> Array:
        """
        Compute penalty for components overlapping keepout zones.
        """
        n = positions.shape[0]
        total_violations = jnp.zeros(n)

        half_w = widths / 2.0
        half_h = heights / 2.0

        for hole in board.mounting_holes:
            hx, hy = hole.position
            keepout_r = hole.keepout_radius

            closest_x = jnp.clip(hx, positions[:, 0] - half_w, positions[:, 0] + half_w)
            closest_y = jnp.clip(hy, positions[:, 1] - half_h, positions[:, 1] + half_h)

            dist_x = hx - closest_x
            dist_y = hy - closest_y
            dist_to_circle_center = jnp.sqrt(dist_x**2 + dist_y**2 + 1e-8)

            edge_dist = dist_to_circle_center - keepout_r
            violation = jax.nn.relu(-edge_dist)
            total_violations = total_violations + violation**2

        # Check rectangular keepout regions if present
        if hasattr(board, 'keepout_regions'):
            for keepout in board.keepout_regions:
                kx_min, ky_min, kx_max, ky_max = keepout
                kw = kx_max - kx_min
                kh = ky_max - ky_min
                kcx = (kx_min + kx_max) / 2.0
                kcy = (ky_min + ky_max) / 2.0

                dx = jnp.abs(positions[:, 0] - kcx)
                dy = jnp.abs(positions[:, 1] - kcy)

                combined_half_w = half_w + kw / 2.0
                combined_half_h = half_h + kh / 2.0

                sep_x = dx - combined_half_w
                sep_y = dy - combined_half_h

                signed_dist = jnp.maximum(sep_x, sep_y)
                violation = jax.nn.relu(-signed_dist)
                total_violations = total_violations + violation**2

        if centrality is not None and centrality.size > 0:
            total_violations = total_violations * (centrality * n)

        return total_violations

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Boundary is a hard constraint - full weight throughout training.
        We ramp up weight in the final 25% of training to ensure convergence.
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        # Ramp from 1.0 to 10.0 between 75% and 100% of epochs
        return jnp.where(progress < 0.75, 1.0, 1.0 + 9.0 * (progress - 0.75) * 4.0)


def compute_boundary_penalty(
    positions: Array,
    widths: Array,
    heights: Array,
    board_bounds: Array,
    margin: float = 0.5,
) -> Array:
    """
    Standalone function to compute boundary penalty.
    """
    x_min, y_min, x_max, y_max = board_bounds

    half_w = widths / 2.0
    half_h = heights / 2.0

    comp_left = positions[:, 0] - half_w
    comp_right = positions[:, 0] + half_w
    comp_bottom = positions[:, 1] - half_h
    comp_top = positions[:, 1] + half_h

    left_violation = jax.nn.relu((x_min + margin) - comp_left)
    right_violation = jax.nn.relu(comp_right - (x_max - margin))
    bottom_violation = jax.nn.relu((y_min + margin) - comp_bottom)
    top_violation = jax.nn.relu(comp_top - (y_max - margin))

    violations = left_violation**2 + right_violation**2 + bottom_violation**2 + top_violation**2

    return jnp.sum(violations)