"""
Loop area loss function for minimizing critical current loop areas.

This loss targets EMI-critical current loops such as gate drive loops,
bootstrap charging loops, and power switching loops. Smaller loop areas
reduce radiated EMI and improve signal integrity.

NOTE: This implementation computes the polygon area formed by pin positions
using the shoelace formula. This is an approximation since actual current
paths follow PCB traces, not straight lines between pins. For more accurate
estimates, consider:
1. Adding a routing factor (e.g., 1.2-1.5x) to account for trace routing
2. Using Manhattan distance estimates for rectilinear routing
3. Post-layout verification with actual trace lengths

The implementation uses pre-computed padded arrays for JAX JIT compatibility,
avoiding Python loops that would cause recompilation on every call.
"""

from __future__ import annotations

from typing import List, Tuple

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.polygon import polygon_area
from temper_placer.losses.base import LoopConstraint, LossContext, LossFunction, LossResult


class LoopAreaLoss(LossFunction):
    """
    Penalize large current loop areas for EMI-critical paths.

    For each defined loop constraint, computes the polygon area formed by
    the loop's pin positions and penalizes areas exceeding the maximum.
    Uses the shoelace formula for differentiable polygon area computation.

    Critical loops for the Temper induction cooker:
    - Gate drive high-side: UCC21550 -> Q1 gate -> Q1 source
    - Gate drive low-side: UCC21550 -> Q2 gate -> Q2 source
    - Bootstrap charging: Bootstrap diode -> bootstrap cap -> HO return
    - Buck converter: LMR51430 SW -> inductor -> output cap

    This implementation is fully JAX-compatible and uses pre-computed arrays
    from LossContext for efficient vectorized computation without Python loops.

    Attributes:
        area_penalty_scale: Scale factor for area penalty.
        routing_factor: Multiplier to estimate actual loop area from polygon
            area (default 1.0). Set to 1.2-1.5 for Manhattan routing estimate.
    """

    def __init__(
        self,
        area_penalty_scale: float = 0.01,
        routing_factor: float = 1.0,
    ):
        """
        Initialize LoopAreaLoss.

        Args:
            area_penalty_scale: Scale factor for area violations.
                Smaller values reduce the impact since areas can be large.
            routing_factor: Multiplier for estimated actual loop area.
                Set > 1.0 to account for non-straight trace routing.
        """
        self.area_penalty_scale = area_penalty_scale
        self.routing_factor = routing_factor

    @property
    def name(self) -> str:
        return "loop_area"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total loop area penalty using vectorized operations.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with pre-computed loop arrays.

        Returns:
            LossResult with sum of loop area penalties.
        """
        # Check for empty loop constraints
        if context.loop_pin_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Get pre-computed arrays from context
        # loop_pin_indices: (L, Q) - component indices for each loop's pins
        # loop_pin_offsets: (L, Q, 2) - pin offsets from component center
        # loop_pin_mask: (L, Q) - True for valid pins, False for padding
        # loop_max_areas: (L,) - maximum allowed area per loop
        # loop_weights: (L,) - weight per loop

        # Get component positions for all pins: (L, Q, 2)
        pin_comp_positions = positions[context.loop_pin_indices]

        # Compute rotation angles from soft one-hot: (N,)
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
        comp_angles = jnp.sum(rotations * angles[None, :], axis=1)  # (N,)

        # Get angles for each pin's component: (L, Q)
        pin_angles = comp_angles[context.loop_pin_indices]

        # Rotate pin offsets: (L, Q, 2)
        cos_a = jnp.cos(pin_angles)  # (L, Q)
        sin_a = jnp.sin(pin_angles)  # (L, Q)

        px = context.loop_pin_offsets[:, :, 0]  # (L, Q)
        py = context.loop_pin_offsets[:, :, 1]  # (L, Q)

        rx = px * cos_a - py * sin_a  # (L, Q)
        ry = px * sin_a + py * cos_a  # (L, Q)

        rotated_offsets = jnp.stack([rx, ry], axis=-1)  # (L, Q, 2)

        # Compute absolute pin positions: (L, Q, 2)
        pin_positions = pin_comp_positions + rotated_offsets

        # Compute loop areas and penalties
        total_penalty, breakdown = self._compute_loop_penalties_vectorized(
            pin_positions,
            context.loop_pin_mask,
            context.loop_max_areas,
            context.loop_weights,
            context.loop_constraints,
        )

        return LossResult(value=total_penalty, breakdown=breakdown)

    def _compute_loop_penalties_vectorized(
        self,
        pin_positions: Array,
        mask: Array,
        max_areas: Array,
        weights: Array,
        loop_constraints: List[LoopConstraint],
    ) -> Tuple[Array, dict]:
        """
        Compute loop area penalties for all loops in parallel.

        Args:
            pin_positions: (L, Q, 2) pin positions for all loops.
            mask: (L, Q) boolean mask for valid pins.
            max_areas: (L,) maximum allowed areas.
            weights: (L,) weights per loop.
            loop_constraints: List of constraints (for breakdown names).

        Returns:
            total_penalty: Scalar total penalty.
            breakdown: Dict mapping loop name to area value.
        """
        # Count valid pins per loop: (L,)
        valid_pin_counts = jnp.sum(mask, axis=1)

        # Compute area for each loop using shoelace formula
        # Need at least 3 pins to form a polygon
        areas = jax.vmap(self._compute_single_loop_area)(pin_positions, mask)

        # Apply routing factor estimate
        estimated_areas = areas * self.routing_factor

        # Compute violations: penalize areas exceeding max
        violations = jax.nn.relu(estimated_areas - max_areas)

        # Apply weights and scale
        penalties = weights * violations**2 * self.area_penalty_scale

        # Zero out penalties for loops with < 3 valid pins
        penalties = jnp.where(valid_pin_counts >= 3, penalties, 0.0)

        total_penalty = jnp.sum(penalties)

        # Build breakdown dict
        breakdown = {}
        for i, loop in enumerate(loop_constraints):
            breakdown[loop.name] = areas[i]

        return total_penalty, breakdown

    def _compute_single_loop_area(
        self,
        vertices: Array,
        mask: Array,
    ) -> Array:
        """
        Compute polygon area for a single loop using shoelace formula.

        The shoelace formula computes the signed area of a polygon:
        area = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|

        This is differentiable with respect to vertex positions.

        For masked vertices (padding), we set them to the centroid of valid
        vertices so they don't contribute to the area.

        Args:
            vertices: (Q, 2) array of polygon vertices.
            mask: (Q,) boolean mask for valid vertices.

        Returns:
            Absolute area of the polygon.
        """
        # Compute centroid of valid vertices
        valid_count = jnp.sum(mask)
        masked_vertices = jnp.where(mask[:, None], vertices, 0.0)
        centroid = jnp.sum(masked_vertices, axis=0) / jnp.maximum(valid_count, 1.0)

        # Replace invalid vertices with centroid (they won't contribute to area)
        vertices_clean = jnp.where(mask[:, None], vertices, centroid[None, :])

        # Shoelace formula
        vertices_next = jnp.roll(vertices_clean, -1, axis=0)
        cross = (
            vertices_clean[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices_clean[:, 1]
        )

        # Only sum valid contributions
        cross_masked = jnp.where(mask, cross, 0.0)
        signed_area = jnp.sum(cross_masked) / 2.0

        return jnp.abs(signed_area)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Loop area is a performance objective - introduced after feasibility.

        Returns full weight after 40% of training.
        """
        progress = epoch / max(total_epochs, 1)
        if progress < 0.4:
            return 0.0
        elif progress < 0.6:
            # Ramp up
            return (progress - 0.4) / 0.2
        return 1.0


def compute_loop_area_penalty(
    pin_positions: Array,
    max_area: float,
    scale: float = 0.01,
) -> Array:
    """
    Standalone function to compute loop area penalty.

    Args:
        pin_positions: (M, 2) positions of pins forming the loop.
        max_area: Maximum allowed area (mm²).
        scale: Penalty scale factor.

    Returns:
        Scalar penalty value.
    """
    if pin_positions.shape[0] < 3:
        return jnp.array(0.0)

    # Shoelace formula
    vertices_next = jnp.roll(pin_positions, -1, axis=0)
    cross = pin_positions[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * pin_positions[:, 1]
    area = jnp.abs(jnp.sum(cross) / 2.0)

    # Penalty for exceeding max
    violation = jax.nn.relu(area - max_area)
    return scale * violation**2


def create_temper_loop_constraints() -> List[LoopConstraint]:
    """
    Create loop constraints for the Temper induction cooker.

    These are the critical EMI loops that must be minimized:
    - Gate drive loops (high-side and low-side)
    - Bootstrap charging loop
    - Buck converter switching loop

    Returns:
        List of LoopConstraint for Temper-specific requirements.
    """
    # Note: Actual pin names depend on component assignments in schematic
    # These are placeholders based on typical half-bridge topology

    return [
        LoopConstraint(
            name="gate_drive_high",
            pins=(
                ("U_GATE_DRIVER", "HO"),  # Gate driver high-side output
                ("Q1", "G"),  # IGBT gate
                ("Q1", "E"),  # IGBT emitter
                ("U_GATE_DRIVER", "HS"),  # Gate driver high-side source
            ),
            max_area=50.0,  # mm²
            weight=2.0,  # Critical for switching speed
        ),
        LoopConstraint(
            name="gate_drive_low",
            pins=(
                ("U_GATE_DRIVER", "LO"),  # Gate driver low-side output
                ("Q2", "G"),  # IGBT gate
                ("Q2", "E"),  # IGBT emitter
                ("U_GATE_DRIVER", "VSS"),  # Gate driver ground
            ),
            max_area=50.0,
            weight=2.0,
        ),
        LoopConstraint(
            name="bootstrap",
            pins=(
                ("D_BOOT", "K"),  # Bootstrap diode cathode
                ("C_BOOT", "1"),  # Bootstrap cap
                ("C_BOOT", "2"),
                ("U_GATE_DRIVER", "VB"),  # Bootstrap supply
            ),
            max_area=100.0,  # Less critical
            weight=1.0,
        ),
        LoopConstraint(
            name="buck_switch",
            pins=(
                ("U_BUCK", "SW"),  # Buck converter switch node
                ("L_BUCK", "1"),  # Buck inductor
                ("L_BUCK", "2"),
                ("C_OUT", "1"),  # Output capacitor
            ),
            max_area=80.0,
            weight=1.5,
        ),
    ]
