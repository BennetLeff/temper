"""
Boundary loss function for keeping components within board outline.

This loss penalizes components that extend beyond the board boundaries
or intrude into keepout zones (mounting holes, restricted areas).
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

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
        keepout_penalty_scale: Scale factor for keepout violations.
        use_rotated_bounds: Whether to account for component rotation.
    """

    def __init__(
        self,
        edge_margin: float = 0.5,
        keepout_penalty_scale: float = 1.0,
        use_rotated_bounds: bool = True,
    ):
        """
        Initialize BoundaryLoss.

        Args:
            edge_margin: Minimum clearance from board edges (mm).
            keepout_penalty_scale: Scale factor for keepout violations.
            use_rotated_bounds: Whether to use rotation-aware bounds.
        """
        self.edge_margin = edge_margin
        self.keepout_penalty_scale = keepout_penalty_scale
        self.use_rotated_bounds = use_rotated_bounds

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
        bounds = context.bounds  # (N, 2)
        board = context.board
        centrality = context.centrality if hasattr(context, "centrality") else None

        # Get effective bounds after rotation
        if self.use_rotated_bounds:
            widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)
        else:
            widths = bounds[:, 0]
            heights = bounds[:, 1]

        # Compute edge violations
        edge_penalty = self._compute_edge_violations(positions, widths, heights, board, centrality)

        # Compute keepout violations
        keepout_penalty = self._compute_keepout_violations(
            positions, widths, heights, board, centrality
        )

        total = edge_penalty + self.keepout_penalty_scale * keepout_penalty

        return LossResult(
            value=total,
            breakdown={
                "edge_violation": edge_penalty,
                "keepout_violation": keepout_penalty,
            },
        )

    def _compute_edge_violations(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        board,
        centrality: Optional[Array] = None,
    ) -> Array:
        """
        Compute penalty for components extending beyond board edges.

        Uses signed distance from component edges to board edges.
        Positive penalty when any part of component is outside board.
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

        # Violations: how much each edge exceeds board boundary
        # Positive value means violation
        left_violation = jax.nn.relu((x_min + self.edge_margin) - comp_left)
        right_violation = jax.nn.relu(comp_right - (x_max - self.edge_margin))
        bottom_violation = jax.nn.relu((y_min + self.edge_margin) - comp_bottom)
        top_violation = jax.nn.relu(comp_top - (y_max - self.edge_margin))

        # Sum of squared violations for each component
        violations = (
            left_violation**2 + right_violation**2 + bottom_violation**2 + top_violation**2
        )

        # Apply centrality weighting if provided
        if centrality is not None and centrality.size > 0:
            # Scale by normalized centrality relative to average (sum=1, so avg=1/n)
            violations = violations * (centrality * n)

        return jnp.sum(violations)

    def _compute_keepout_violations(
        self,
        widths: Array,
        heights: Array,
        board,
        centrality: Optional[Array] = None,
    ) -> Array:
        """
        Compute penalty for components overlapping keepout zones.

        Checks mounting holes and rectangular keepout regions.
        Uses proper box-to-circle distance for mounting holes.
        """
        n = positions.shape[0]
        total_violations = jnp.zeros(n)

        # Component half-dimensions
        half_w = widths / 2.0
        half_h = heights / 2.0

        # Check mounting holes using proper box-circle distance
        for hole in board.mounting_holes:
            hx, hy = hole.position
            keepout_r = hole.keepout_radius

            # Closest point on box to circle center (clamped)
            dx = positions[:, 0] - hx
            dy = positions[:, 1] - hy

            # Clamp to box extent
            closest_x = jnp.clip(hx, positions[:, 0] - half_w, positions[:, 0] + half_w)
            closest_y = jnp.clip(hy, positions[:, 1] - half_h, positions[:, 1] + half_h)

            # Distance from closest point to circle center
            dist_x = hx - closest_x
            dist_y = hy - closest_y
            dist_to_circle_center = jnp.sqrt(dist_x**2 + dist_y**2 + 1e-8)

            # Distance from box edge to circle edge (negative = overlap)
            edge_dist = dist_to_circle_center - keepout_r

            # Violation: positive when overlapping
            violation = jax.nn.relu(-edge_dist)
            total_violations = total_violations + violation**2

        # Check rectangular keepout regions
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

        # Apply centrality weighting if provided
        if centrality is not None and centrality.size > 0:
            total_violations = total_violations * (centrality * n)

        return jnp.sum(total_violations)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Boundary is a hard constraint - full weight throughout training.
        """
        return 1.0


def compute_boundary_penalty(
    widths: Array,
    heights: Array,
    board_bounds: Array,
    margin: float = 0.5,
) -> Array:
    """
    Standalone function to compute boundary penalty.

    Args:
        positions: (N, 2) component positions.
        widths: (N,) component widths.
        heights: (N,) component heights.
        board_bounds: [x_min, y_min, x_max, y_max].
        margin: Edge margin.

    Returns:
        Scalar boundary penalty value.
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
