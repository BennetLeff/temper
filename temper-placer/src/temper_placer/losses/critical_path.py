"""
Critical path length loss function for PCB placement.

This module implements a loss function that penalizes critical signal paths
that exceed maximum length constraints. Critical paths include:
- Gate drive signals (fast edges, inductance-sensitive)
- High-speed digital signals (SPI, I2C clocks)
- Analog sensing signals (susceptible to noise pickup)

The loss uses Manhattan distance as a routing estimate, which is a reasonable
approximation for PCB routing since traces typically follow rectilinear paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


# Priority type for type safety
Priority = Literal["critical", "high", "normal"]


@dataclass(frozen=True)
class CriticalPath:
    """
    Defines a critical signal path with maximum length constraint.

    Attributes:
        name: Human-readable name for the path (e.g., "gate_drive_high").
        from_ref: Source component reference (e.g., "U_GATE").
        to_ref: Destination component reference (e.g., "Q1").
        max_length_mm: Maximum allowed path length in mm.
        priority: Priority level affecting penalty weight.
            - "critical": Weight 10.0 (gate drive, power loops)
            - "high": Weight 5.0 (high-speed signals)
            - "normal": Weight 1.0 (general signals)
    """

    name: str
    from_ref: str
    to_ref: str
    max_length_mm: float
    priority: Priority = "normal"

    @property
    def weight(self) -> float:
        """Get weight multiplier based on priority."""
        weights = {"critical": 10.0, "high": 5.0, "normal": 1.0}
        return weights.get(self.priority, 1.0)


class CriticalPathLengthLoss(LossFunction):
    """
    Penalize critical paths that exceed maximum length constraints.

    This loss function enforces length constraints on signal paths where
    length matters for signal integrity, EMI, or timing. Uses Manhattan
    distance as a routing estimate.

    The penalty is quadratic in the excess length:
        penalty = weight * (length - max_length)² if length > max_length else 0

    Attributes:
        critical_paths: List of CriticalPath constraints to enforce.

    Example:
        >>> paths = [
        ...     CriticalPath("gate_high", "U_GATE", "Q1", max_length_mm=15.0, priority="critical"),
        ...     CriticalPath("spi_clk", "U_MCU", "U_FLASH", max_length_mm=50.0, priority="high"),
        ... ]
        >>> loss = CriticalPathLengthLoss(critical_paths=paths)
        >>> result = loss(positions, rotations, context)
    """

    def __init__(self, critical_paths: List[CriticalPath]):
        """
        Initialize CriticalPathLengthLoss.

        Args:
            critical_paths: List of critical path constraints.
        """
        self.critical_paths = critical_paths

    @property
    def name(self) -> str:
        return "critical_path_length"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total penalty for critical paths exceeding max length.

        Args:
            positions: (N, 2) component center positions in mm.
            rotations: (N, 4) soft one-hot rotation indicators (unused).
            context: LossContext with netlist for component index lookup.

        Returns:
            LossResult with total penalty value.
        """
        if not self.critical_paths:
            return LossResult(value=jnp.array(0.0))

        total_penalty = jnp.array(0.0)

        for path in self.critical_paths:
            # Get component indices
            try:
                from_idx = context.get_component_index(path.from_ref)
                to_idx = context.get_component_index(path.to_ref)
            except (KeyError, ValueError):
                # Component not found - skip this path
                continue

            # Get positions
            pos_from = positions[from_idx]
            pos_to = positions[to_idx]

            # Compute Manhattan distance as routing estimate
            length = jnp.abs(pos_from[0] - pos_to[0]) + jnp.abs(pos_from[1] - pos_to[1])

            # Compute penalty for excess length (quadratic)
            excess = jnp.maximum(0.0, length - path.max_length_mm)
            penalty = path.weight * excess**2

            total_penalty = total_penalty + penalty

        return LossResult(value=total_penalty)


def compute_critical_path_penalty(
    positions: Array,
    from_idx: int,
    to_idx: int,
    max_length_mm: float,
    weight: float = 1.0,
) -> Array:
    """
    Compute penalty for a single critical path.

    Standalone function for use outside the loss class.

    Args:
        positions: (N, 2) component positions.
        from_idx: Index of source component.
        to_idx: Index of destination component.
        max_length_mm: Maximum allowed length.
        weight: Penalty weight multiplier.

    Returns:
        Scalar penalty value.
    """
    pos_from = positions[from_idx]
    pos_to = positions[to_idx]

    # Manhattan distance
    length = jnp.abs(pos_from[0] - pos_to[0]) + jnp.abs(pos_from[1] - pos_to[1])

    # Quadratic penalty for excess
    excess = jnp.maximum(0.0, length - max_length_mm)
    return weight * excess**2


def create_temper_critical_paths() -> List[CriticalPath]:
    """
    Create default critical path constraints for Temper induction cooker.

    Returns:
        List of CriticalPath constraints for Temper board.
    """
    return [
        # Gate drive paths - must be short for fast switching and low inductance
        CriticalPath(
            name="gate_drive_high",
            from_ref="U_GATE",
            to_ref="Q1",
            max_length_mm=15.0,
            priority="critical",
        ),
        CriticalPath(
            name="gate_drive_low",
            from_ref="U_GATE",
            to_ref="Q2",
            max_length_mm=15.0,
            priority="critical",
        ),
        # SPI signals - moderate length requirement
        CriticalPath(
            name="spi_to_temp",
            from_ref="U_MCU",
            to_ref="U_TEMP",
            max_length_mm=50.0,
            priority="high",
        ),
        # Current sense path - analog, noise-sensitive
        CriticalPath(
            name="current_sense",
            from_ref="R_SENSE",
            to_ref="U_MCU",
            max_length_mm=30.0,
            priority="high",
        ),
    ]
