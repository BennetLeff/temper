"""
Component spacing loss function for enforcing minimum distances between specific components.

This loss enforces edge-to-edge spacing constraints between component pairs as specified
in the configuration. Unlike ClearanceLoss which operates on net classes, this loss
targets specific component references (e.g., "D2" and "C_BUS1").

Primary use case: Preventing overlaps and ensuring HV clearances in power sections.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class ComponentSpacingLoss(LossFunction):
    """
    Penalize component pairs that violate minimum spacing requirements.

    Enforces distance constraints between specific components identified by reference.
    Uses proper axis-aligned box-to-box distance calculation accounting for rotation.

    This is critical for preventing overlaps in densely packed power sections where
    large components (e.g., bridge rectifiers) can interfere with nearby capacitors.

    Attributes:
        use_rotated_bounds: Whether to account for component rotation.
    """

    def __init__(self, use_rotated_bounds: bool = True):
        """
        Initialize ComponentSpacingLoss.

        Args:
            use_rotated_bounds: Whether to use rotation-aware bounds.
        """
        self.use_rotated_bounds = use_rotated_bounds

    @property
    def name(self) -> str:
        return "component_spacing"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute total component spacing violation penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with component_spacing_rules and component_name_to_index.

        Returns:
            LossResult with sum of spacing violation penalties.
        """
        # Get rotation-aware bounds if enabled
        bounds = context.bounds  # (N, 2)
        if self.use_rotated_bounds:
            widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)
        else:
            widths = bounds[:, 0]
            heights = bounds[:, 1]

        total_penalty = jnp.array(0.0)
        breakdown = {}

        # Apply spacing rules from context
        if not context.component_spacing_rules:
            return LossResult(value=total_penalty, breakdown=breakdown)

        for rule in context.component_spacing_rules:
            # Get component indices
            idx_a = context.component_name_to_index.get(rule.component_a)
            idx_b = context.component_name_to_index.get(rule.component_b)

            # Skip if components not found (might be missing in this netlist)
            if idx_a is None or idx_b is None:
                continue

            # Get positions and bounds
            pos_a = positions[idx_a]  # (2,)
            pos_b = positions[idx_b]  # (2,)
            half_w_a = widths[idx_a] / 2.0
            half_h_a = heights[idx_a] / 2.0
            half_w_b = widths[idx_b] / 2.0
            half_h_b = heights[idx_b] / 2.0

            # Compute edge-to-edge distance
            edge_dist = self._compute_box_box_distance(
                pos_a, half_w_a, half_h_a,
                pos_b, half_w_b, half_h_b
            )

            # Compute violation: positive when too close
            violation = jax.nn.relu(rule.min_separation_mm - edge_dist)

            # Apply rule weight and square the violation
            rule_penalty = rule.weight * (violation ** 2)
            total_penalty = total_penalty + rule_penalty

            # Track breakdown
            breakdown[f"{rule.component_a}_{rule.component_b}"] = rule_penalty

        return LossResult(value=total_penalty, breakdown=breakdown)

    def _compute_box_box_distance(
        self,
        pos_a: Array,
        half_w_a: Array,
        half_h_a: Array,
        pos_b: Array,
        half_w_b: Array,
        half_h_b: Array,
    ) -> Array:
        """
        Compute axis-aligned box-to-box distance between two components.

        For two axis-aligned boxes, the edge-to-edge distance is:
        - If separated: sqrt(dx^2 + dy^2) where dx, dy are edge separations
        - If overlapping in one dimension: the separation in the other dimension
        - If overlapping in both dimensions: negative (overlap)

        Args:
            pos_a: (2,) center position of first component
            half_w_a: half-width of first component
            half_h_a: half-height of first component
            pos_b: (2,) center position of second component
            half_w_b: half-width of second component
            half_h_b: half-height of second component

        Returns:
            Scalar edge-to-edge distance (negative = overlap)
        """
        # Position differences
        diff = pos_a - pos_b  # (2,)

        # Absolute position differences
        abs_dx = jnp.abs(diff[0])
        abs_dy = jnp.abs(diff[1])

        # Combined half-dimensions
        combined_half_w = half_w_a + half_w_b
        combined_half_h = half_h_a + half_h_b

        # Separation in x and y (negative = overlap in that dimension)
        sep_x = abs_dx - combined_half_w
        sep_y = abs_dy - combined_half_h

        # Box-to-box distance:
        # - Both sep positive: Euclidean distance to corner: sqrt(sep_x^2 + sep_y^2)
        # - One sep positive: that separation (boxes are separated along that axis)
        # - Both sep negative: max(sep_x, sep_y) which is negative (overlap)

        # Case 1: Both separated (sep_x > 0 and sep_y > 0) -> corner distance
        corner_dist = jnp.sqrt(jnp.maximum(sep_x, 0.0) ** 2 + jnp.maximum(sep_y, 0.0) ** 2 + 1e-8)

        # Use conditional logic to determine the correct distance
        both_positive = (sep_x > 0) & (sep_y > 0)
        only_x_positive = (sep_x > 0) & (sep_y <= 0)
        only_y_positive = (sep_x <= 0) & (sep_y > 0)

        edge_dist = jnp.where(
            both_positive,
            corner_dist,
            jnp.where(
                only_x_positive,
                sep_x,
                jnp.where(
                    only_y_positive,
                    sep_y,
                    jnp.maximum(sep_x, sep_y),  # Both negative (overlap)
                ),
            ),
        )

        return edge_dist

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Component spacing is introduced after initial spread phase.

        Returns full weight after 20% of training.
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        result = jnp.where(progress < 0.2, 0.5, 1.0)
        return result  # type: ignore
