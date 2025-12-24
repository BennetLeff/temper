"""
Loop area loss function for minimizing critical current loop areas.

This loss targets EMI-critical current loops such as gate drive loops,
bootstrap charging loops, and power switching loops. Smaller loop areas
reduce radiated EMI and improve signal integrity.

PIN ORDERING REQUIREMENT
========================

**IMPORTANT**: The shoelace formula used to compute polygon area requires pins
to be specified in order around the loop perimeter (either clockwise or
counter-clockwise). If pins are provided in arbitrary order, the computed
area will be INCORRECT and gradients will push components in the wrong direction.

**Correct ordering (CW or CCW around the loop):**

    Gate driver HO → IGBT gate → IGBT emitter → Gate driver HS

    This traces the physical current path around the loop.

**Incorrect ordering (arbitrary):**

    Gate driver HO → IGBT emitter → Gate driver HS → IGBT gate

    This creates a self-intersecting "figure-8" shape with wrong area.

**Why it matters for optimization:**

When pin ordering is wrong, the shoelace formula computes the signed area
of a self-intersecting polygon. This area may:
1. Be much smaller than the true loop area (underestimating EMI)
2. Have gradients that move components in unhelpful directions
3. Show "improvements" that actually make the physical loop larger

**Best practices:**
1. Trace the actual current flow path on your schematic
2. List pins in the order current flows through them
3. For power loops, start at the positive supply and follow to ground
4. Verify loop areas match hand calculations for simple rectangles

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

from typing import cast

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LoopConstraint, LossContext, LossFunction, LossResult


class LoopAreaLoss(LossFunction):
    """
    Penalize large current loop areas for EMI-critical paths.

    For each defined loop constraint, computes the polygon area formed by
    the loop's pin positions and penalizes areas exceeding the maximum.
    Uses the shoelace formula for differentiable polygon area computation.

    PIN ORDERING REQUIREMENT
    ------------------------

    **CRITICAL**: Pins MUST be specified in order around the loop perimeter
    (clockwise or counter-clockwise). The shoelace formula computes a signed
    area that only gives correct results for properly ordered vertices.

    **Example - Gate Drive Loop (CORRECT ordering):**

        pins=(
            ("U_DRIVER", "HO"),   # Step 1: Driver output
            ("Q1", "G"),          # Step 2: Current flows to IGBT gate
            ("Q1", "E"),          # Step 3: Returns from IGBT emitter
            ("U_DRIVER", "HS"),   # Step 4: Back to driver source
        )

        This traces the physical current path:
        HO → Gate → Emitter → HS → (back to HO)

    **Example - Same Loop (INCORRECT ordering):**

        pins=(
            ("U_DRIVER", "HO"),   # Driver output
            ("Q1", "E"),          # WRONG: Skips to emitter
            ("U_DRIVER", "HS"),   # WRONG: Back to driver
            ("Q1", "G"),          # WRONG: Then to gate
        )

        This creates a self-intersecting polygon with incorrect area!

    **Why ordering matters:**
    - Shoelace formula: area = 0.5 * |Σ(x_i*y_{i+1} - x_{i+1}*y_i)|
    - For a simple (non-self-intersecting) polygon, this gives true area
    - For self-intersecting polygons, it gives algebraic area (can be wrong)
    - Incorrect areas lead to incorrect gradients during optimization

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
        epoch: int = 0,
        total_epochs: int = 1,
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

        # Numerical stability guards: replace NaN/Inf with large finite value
        # This prevents a single component from crashing the entire optimization
        total_penalty = jnp.nan_to_num(total_penalty, nan=1e6, posinf=1e6, neginf=1e6)

        return LossResult(value=total_penalty, breakdown=breakdown)

    def trace(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> tuple[Array, Trace]:
        """Generate a natural language trace for critical loops."""
        from temper_placer.explainability.trace import Trace

        if context.loop_pin_indices.shape[0] == 0:
            return jnp.array(0.0), Trace.empty()

        result = self(positions, rotations, context, epoch, total_epochs)
        trace = Trace.empty()

        for loop in context.loop_constraints:
            area = result.breakdown.get(loop.name, 0.0)
            penalty = float(loop.weight * jnp.maximum(0, area - loop.max_area)**2 * self.area_penalty_scale)

            if penalty > 1e-4:
                trace = trace.add(
                    f"Loop:{loop.name}",
                    penalty,
                    loop.because or f"Critical current loop {loop.name} (area: {float(area):.1f}mm²)"
                )

        return result.value, trace


    def _compute_loop_penalties_vectorized(
        self,
        pin_positions: Array,
        mask: Array,
        max_areas: Array,
        weights: Array,
        loop_constraints: list[LoopConstraint],
    ) -> tuple[Array, dict]:
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
        # Guard against NaN/Inf in input vertices
        # This ensures that one bad component doesn't produce NaN gradients for all
        vertices = jnp.nan_to_num(vertices, nan=0.0, posinf=1e6, neginf=-1e6)

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
        progress = epoch / jnp.maximum(total_epochs, 1)

        # Use jnp.where to be JAX-compatible (avoid Python if/else on tracers)
        weight = jnp.where(
            progress < 0.4,
            0.0,
            jnp.where(
                progress < 0.6,
                (progress - 0.4) / 0.2,
                1.0
            )
        )
        return cast(float, weight)


def compute_loop_area_penalty(
    pin_positions: Array,
    max_area: float,
    scale: float = 0.01,
) -> Array:
    """
    Standalone function to compute loop area penalty.

    **PIN ORDERING REQUIREMENT**: pin_positions MUST be ordered around the
    loop perimeter (CW or CCW). Arbitrary ordering gives incorrect area!

    See LoopAreaLoss class docstring for detailed explanation and examples.

    Args:
        pin_positions: (M, 2) positions of pins forming the loop, in order
            around the loop perimeter (clockwise or counter-clockwise).
        max_area: Maximum allowed area (mm²).
        scale: Penalty scale factor.

    Returns:
        Scalar penalty value.

    Example:
        >>> # Rectangular loop with corners at (0,0), (10,0), (10,5), (0,5)
        >>> # CORRECT: ordered around perimeter
        >>> pins_correct = jnp.array([[0, 0], [10, 0], [10, 5], [0, 5]])
        >>> area = compute_loop_area_penalty(pins_correct, max_area=100.0)
        >>> # Area = 50 mm², no penalty since < 100
        >>>
        >>> # INCORRECT: arbitrary order creates figure-8
        >>> pins_wrong = jnp.array([[0, 0], [10, 5], [10, 0], [0, 5]])
        >>> # This gives wrong area and wrong gradient!
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


def create_temper_loop_constraints() -> list[LoopConstraint]:
    """
    Create loop constraints for the Temper induction cooker.

    These are the critical EMI loops that must be minimized:
    - Gate drive loops (high-side and low-side)
    - Bootstrap charging loop
    - Buck converter switching loop

    **PIN ORDERING**: Each constraint lists pins in the order that current
    flows around the loop. This is REQUIRED for correct area computation.
    Trace the current path on your schematic to verify ordering.

    **Example - High-side gate drive loop:**

        Gate driver HO pin
              ↓
        IGBT gate pin (current charges gate)
              ↓
        IGBT emitter pin (return path)
              ↓
        Gate driver HS pin (source reference)
              ↓
        (back to HO via driver internal)

    This forms a closed loop. The pins list traces this path.

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


def validate_loop_ordering(
    pin_positions: Array,
    loop_name: str = "unnamed",
) -> list[str]:
    """
    Validate that pin positions form a simple (non-self-intersecting) polygon.

    This is a heuristic check that can detect some common ordering errors.
    It compares the shoelace area to the convex hull area - if the shoelace
    area is much smaller, the polygon may be self-intersecting.

    **Note**: This is not a perfect check. Some self-intersecting polygons
    may pass, and some valid concave polygons may trigger warnings.
    Always verify loop ordering by tracing current flow on the schematic.

    Args:
        pin_positions: (M, 2) positions of pins in the specified order.
        loop_name: Name of the loop (for warning messages).

    Returns:
        List of warning messages (empty if no issues detected).

    Example:
        >>> pins = jnp.array([[0, 0], [10, 0], [10, 5], [0, 5]])
        >>> warnings = validate_loop_ordering(pins, "gate_drive")
        >>> if warnings:
        ...     print("\\n".join(warnings))
    """
    import numpy as np
    from scipy.spatial import ConvexHull

    warnings = []

    if pin_positions.shape[0] < 3:
        warnings.append(f"Loop '{loop_name}': Less than 3 pins, cannot form a polygon")
        return warnings

    # Convert to numpy for scipy
    points = np.array(pin_positions)

    # Compute shoelace area
    vertices_next = np.roll(points, -1, axis=0)
    cross = points[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * points[:, 1]
    shoelace_area = abs(np.sum(cross) / 2.0)

    # Compute convex hull area
    try:
        hull = ConvexHull(points)
        hull_area = hull.volume  # In 2D, "volume" is actually area
    except Exception:
        # Points may be collinear
        warnings.append(
            f"Loop '{loop_name}': Pins appear to be collinear (zero area). "
            "Check that pins form a 2D polygon, not a line."
        )
        return warnings

    # If shoelace area is much smaller than hull area, likely self-intersecting
    if hull_area > 0 and shoelace_area < hull_area * 0.5:
        warnings.append(
            f"Loop '{loop_name}': Computed area ({shoelace_area:.1f} mm²) is much smaller "
            f"than convex hull ({hull_area:.1f} mm²). This may indicate incorrect pin ordering "
            "resulting in a self-intersecting polygon. Verify pins are ordered around the "
            "loop perimeter by tracing current flow on the schematic."
        )

    # Check for very small area (might indicate nearly collinear points)
    if shoelace_area < 1.0:  # Less than 1 mm²
        warnings.append(
            f"Loop '{loop_name}': Very small area ({shoelace_area:.2f} mm²). "
            "This might be correct for tightly coupled components, or might indicate "
            "pins that are nearly collinear. Verify loop geometry."
        )

    return warnings
