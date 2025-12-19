"""
Clearance loss function for enforcing minimum distances between component classes.

This loss enforces safety-critical clearances between high-voltage and low-voltage
components as specified in the PCB design rules. For the Temper induction cooker,
this includes the 10mm reinforced isolation clearance required between HV and LV sections.

The implementation uses:
1. Pre-computed net class indices for JAX JIT compatibility
2. Proper axis-aligned box-to-box distance (not circular approximation)
3. Rotation-aware bounding boxes
"""

from __future__ import annotations

from typing import List, Tuple

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import ClearanceRule, LossContext, LossFunction, LossResult


class ClearanceLoss(LossFunction):
    """
    Penalize component pairs that violate minimum clearance requirements.

    Enforces distance constraints between components of different net classes.
    The primary use case is HV-to-LV clearance (10mm for reinforced isolation),
    but supports arbitrary net class pairs with configurable clearances.

    This is a critical safety constraint that must be satisfied.

    This implementation:
    - Uses pre-computed net class indices for JAX compatibility
    - Uses proper axis-aligned box-to-box distance (not circular approximation)
    - Accounts for component rotation when computing bounds

    Attributes:
        default_hv_lv_clearance: Default HV-LV clearance (mm) if no rules specified.
        use_rotated_bounds: Whether to account for component rotation.
    """

    def __init__(
        self,
        default_hv_lv_clearance: float = 10.0,
        use_rotated_bounds: bool = True,
    ):
        """
        Initialize ClearanceLoss.

        Args:
            default_hv_lv_clearance: Default HV-LV clearance in mm.
            use_rotated_bounds: Whether to use rotation-aware bounds.
        """
        self.default_hv_lv_clearance = default_hv_lv_clearance
        self.use_rotated_bounds = use_rotated_bounds

    @property
    def name(self) -> str:
        return "clearance"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute total clearance violation penalty.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with HV/LV indices and clearance rules.

        Returns:
            LossResult with sum of clearance violation penalties.
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

        # Apply clearance rules from context
        if context.clearance_rules:
            for rule in context.clearance_rules:
                rule_penalty = self._compute_rule_penalty_vectorized(
                    positions, widths, heights, context, rule
                )
                total_penalty = total_penalty + rule_penalty
                breakdown[f"{rule.net_class_a}_{rule.net_class_b}"] = rule_penalty
        else:
            # Use default HV-LV clearance
            hv_lv_penalty = self._compute_hv_lv_penalty(positions, widths, heights, context)
            total_penalty = hv_lv_penalty
            breakdown["hv_lv"] = hv_lv_penalty

        return LossResult(value=total_penalty, breakdown=breakdown)

    def _compute_hv_lv_penalty(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        context: LossContext,
    ) -> Array:
        """
        Compute penalty for HV-LV clearance violations using pre-computed indices.

        Uses proper axis-aligned box-to-box distance instead of circular approximation.
        """
        hv_indices = context.hv_indices
        lv_indices = context.lv_indices

        if len(hv_indices) == 0 or len(lv_indices) == 0:
            return jnp.array(0.0)

        # Get positions and half-dimensions for HV and LV components
        hv_positions = positions[hv_indices]  # (H, 2)
        lv_positions = positions[lv_indices]  # (L, 2)

        hv_half_w = widths[hv_indices] / 2.0  # (H,)
        hv_half_h = heights[hv_indices] / 2.0  # (H,)
        lv_half_w = widths[lv_indices] / 2.0  # (L,)
        lv_half_h = heights[lv_indices] / 2.0  # (L,)

        # Compute pairwise box-to-box distances
        edge_dist = self._compute_box_box_distances(
            hv_positions,
            hv_half_w,
            hv_half_h,
            lv_positions,
            lv_half_w,
            lv_half_h,
        )  # (H, L)

        # Compute violations: positive when too close
        violations = jax.nn.relu(self.default_hv_lv_clearance - edge_dist)

        # Sum squared violations
        return jnp.sum(violations**2)

    def _compute_rule_penalty_vectorized(
        self,
        positions: Array,
        widths: Array,
        heights: Array,
        context: LossContext,
        rule: ClearanceRule,
    ) -> Array:
        """
        Compute penalty for a specific clearance rule using pre-computed indices.

        Uses proper axis-aligned box-to-box distance.
        """
        # Get indices for each net class from pre-computed arrays
        indices_a = context.net_class_indices.get(rule.net_class_a)
        indices_b = context.net_class_indices.get(rule.net_class_b)

        if indices_a is None or indices_b is None:
            return jnp.array(0.0)
        if len(indices_a) == 0 or len(indices_b) == 0:
            return jnp.array(0.0)

        # Get positions and half-dimensions
        pos_a = positions[indices_a]  # (A, 2)
        pos_b = positions[indices_b]  # (B, 2)

        half_w_a = widths[indices_a] / 2.0  # (A,)
        half_h_a = heights[indices_a] / 2.0  # (A,)
        half_w_b = widths[indices_b] / 2.0  # (B,)
        half_h_b = heights[indices_b] / 2.0  # (B,)

        # Compute pairwise box-to-box distances
        edge_dist = self._compute_box_box_distances(
            pos_a,
            half_w_a,
            half_h_a,
            pos_b,
            half_w_b,
            half_h_b,
        )  # (A, B)

        # Handle case where net classes are the same (avoid double counting)
        if rule.net_class_a == rule.net_class_b:
            # Use upper triangle mask
            n = len(indices_a)
            mask = jnp.triu(jnp.ones((n, n), dtype=jnp.bool_), k=1)
            edge_dist = jnp.where(mask, edge_dist, jnp.inf)

        # Compute violations
        violations = jax.nn.relu(rule.min_clearance - edge_dist)

        # Apply rule weight
        return rule.weight * jnp.sum(violations**2)

    def _compute_box_box_distances(
        self,
        pos_a: Array,
        half_w_a: Array,
        half_h_a: Array,
        pos_b: Array,
        half_w_b: Array,
        half_h_b: Array,
    ) -> Array:
        """
        Compute axis-aligned box-to-box distances between two sets of components.

        For two axis-aligned boxes, the edge-to-edge distance is:
        - If separated: sqrt(dx^2 + dy^2) where dx, dy are edge separations
        - If overlapping in one dimension: the separation in the other dimension
        - If overlapping in both dimensions: negative (overlap)

        Args:
            pos_a: (A, 2) center positions of first group
            half_w_a: (A,) half-widths of first group
            half_h_a: (A,) half-heights of first group
            pos_b: (B, 2) center positions of second group
            half_w_b: (B,) half-widths of second group
            half_h_b: (B,) half-heights of second group

        Returns:
            (A, B) edge-to-edge distances (negative = overlap)
        """
        # Position differences: (A, B, 2)
        diff = pos_a[:, None, :] - pos_b[None, :, :]

        # Absolute position differences
        abs_dx = jnp.abs(diff[:, :, 0])  # (A, B)
        abs_dy = jnp.abs(diff[:, :, 1])  # (A, B)

        # Combined half-dimensions for each pair
        combined_half_w = half_w_a[:, None] + half_w_b[None, :]  # (A, B)
        combined_half_h = half_h_a[:, None] + half_h_b[None, :]  # (A, B)

        # Separation in x and y (negative = overlap in that dimension)
        sep_x = abs_dx - combined_half_w  # (A, B)
        sep_y = abs_dy - combined_half_h  # (A, B)

        # Box-to-box distance:
        # - Both sep positive: Euclidean distance to corner: sqrt(sep_x^2 + sep_y^2)
        # - One sep positive: that separation (boxes are separated along that axis)
        # - Both sep negative: max(sep_x, sep_y) which is negative (overlap)

        # Case 1: Both separated (sep_x > 0 and sep_y > 0) -> corner distance
        corner_dist = jnp.sqrt(jnp.maximum(sep_x, 0.0) ** 2 + jnp.maximum(sep_y, 0.0) ** 2 + 1e-8)

        # Case 2: Separated only in x or y -> edge distance (the positive sep)
        # Case 3: Overlapping -> max of (negative) separations

        # Use the fact that:
        # - If both sep > 0: corner distance
        # - If sep_x > 0, sep_y <= 0: sep_x (edge-to-edge in x)
        # - If sep_x <= 0, sep_y > 0: sep_y (edge-to-edge in y)
        # - If both sep <= 0: max(sep_x, sep_y) (overlap, negative)

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
        Clearance is introduced after initial spread phase.

        Returns full weight after 20% of training.
        """
        # Use jnp.maximum instead of Python max() for JAX compatibility
        progress = epoch / jnp.maximum(total_epochs, 1)
        # Use jnp.where instead of if/else for JAX compatibility
        # We need to cast back to float/scalar context for type checker happiness
        # though JAX will handle the array/scalar interoperability
        result = jnp.where(progress < 0.2, 0.5, 1.0)
        return result  # type: ignore


def compute_clearance_penalty(
    positions_a: Array,
    positions_b: Array,
    min_clearance: float,
    half_w_a: Array | None = None,
    half_h_a: Array | None = None,
    half_w_b: Array | None = None,
    half_h_b: Array | None = None,
) -> Array:
    """
    Standalone function to compute clearance penalty between two groups.

    Uses proper box-to-box distance when dimensions are provided.

    Args:
        positions_a: (A, 2) positions of first group.
        positions_b: (B, 2) positions of second group.
        min_clearance: Minimum required clearance (mm).
        half_w_a: Optional (A,) half-widths of first group.
        half_h_a: Optional (A,) half-heights of first group.
        half_w_b: Optional (B,) half-widths of second group.
        half_h_b: Optional (B,) half-heights of second group.

    Returns:
        Scalar clearance penalty value.
    """
    # Default to point-to-point if no dimensions provided
    if half_w_a is None:
        half_w_a = jnp.zeros(len(positions_a))
    if half_h_a is None:
        half_h_a = jnp.zeros(len(positions_a))
    if half_w_b is None:
        half_w_b = jnp.zeros(len(positions_b))
    if half_h_b is None:
        half_h_b = jnp.zeros(len(positions_b))

    # Position differences
    diff = positions_a[:, None, :] - positions_b[None, :, :]
    abs_dx = jnp.abs(diff[:, :, 0])
    abs_dy = jnp.abs(diff[:, :, 1])

    # Combined half-dimensions
    combined_half_w = half_w_a[:, None] + half_w_b[None, :]
    combined_half_h = half_h_a[:, None] + half_h_b[None, :]

    # Separations
    sep_x = abs_dx - combined_half_w
    sep_y = abs_dy - combined_half_h

    # Compute edge distance
    both_positive = (sep_x > 0) & (sep_y > 0)
    corner_dist = jnp.sqrt(jnp.maximum(sep_x, 0.0) ** 2 + jnp.maximum(sep_y, 0.0) ** 2 + 1e-8)

    edge_dist = jnp.where(both_positive, corner_dist, jnp.maximum(sep_x, sep_y))

    # Violations
    violations = jax.nn.relu(min_clearance - edge_dist)

    return jnp.sum(violations**2)
