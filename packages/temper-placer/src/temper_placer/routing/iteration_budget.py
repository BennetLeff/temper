"""
Adaptive A* iteration budget calculation for PCB routing.

This module provides congestion-aware iteration limits for the A* pathfinding
algorithm used in PCB routing. The iteration budget adapts based on:
1. Route distance (Manhattan distance)
2. Congestion level (LOW/MEDIUM/HIGH/EXTREME)
3. Number of available layers
4. Distance-based exponential scaling

Design principles:
- Pure functions (no side effects)
- Immutable data structures (frozen dataclasses)
- Strong typing (no Any types)
- Deterministic calculations

Formula:
    budget = distance * base * congestion_factor * layer_factor * distance_factor * 1.2
    Clamped to [5k, 1M]

Example:
    >>> context = RoutingContext(
    ...     net_name="+5V",
    ...     start=(0.0, 0.0),
    ...     end=(50.0, 30.0),
    ...     allowed_layers=(0, 1, 2, 3),
    ...     net_class="PowerTrace"
    ... )
    >>> budget = IterationBudget.calculate(context, CongestionLevel.HIGH)
    >>> print(f"Budget: {budget.max_iterations}, Reason: {budget.reason}")
    Budget: 95400, Reason: dist=80.0mm, congestion=HIGH, layers=4, budget=95400
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class CongestionLevel(Enum):
    """Congestion levels for routing areas.

    - LOW: Open routing area (<30% occupied)
    - MEDIUM: Some obstacles (30-60% occupied)
    - HIGH: Dense area (60-80% occupied)
    - EXTREME: Very constrained (>80% occupied, near fine-pitch IC)
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

    def get_factor(self) -> float:
        """Get congestion factor for iteration budget calculation.

        Returns:
            Multiplier for iteration budget:
            - LOW: 1.0x
            - MEDIUM: 2.0x
            - HIGH: 4.0x
            - EXTREME: 8.0x
        """
        return {
            CongestionLevel.LOW: 1.0,
            CongestionLevel.MEDIUM: 2.0,
            CongestionLevel.HIGH: 4.0,
            CongestionLevel.EXTREME: 8.0,
        }[self]


@dataclass(frozen=True)
class RoutingContext:
    """Immutable context for a single routing segment.

    Attributes:
        net_name: Name of the net being routed
        start: Start point (x, y) in mm
        end: End point (x, y) in mm
        allowed_layers: Tuple of allowed layer indices (0-based)
        net_class: Net class name (e.g., "Signal", "PowerTrace", "Ground")
    """

    net_name: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    allowed_layers: Tuple[int, ...]
    net_class: str

    def manhattan_distance(self) -> float:
        """Calculate Manhattan distance between start and end points.

        Returns:
            Distance in mm (|dx| + |dy|)
        """
        dx = abs(self.end[0] - self.start[0])
        dy = abs(self.end[1] - self.start[1])
        return dx + dy

    def layer_count(self) -> int:
        """Get number of allowed layers.

        Returns:
            Number of layers available for routing
        """
        return len(self.allowed_layers)


@dataclass(frozen=True)
class IterationBudget:
    """Immutable result of iteration budget calculation.

    Attributes:
        max_iterations: Maximum A* iterations allowed
        reason: Human-readable explanation of calculation
        congestion_factor: Multiplier for congestion level (1.0-8.0)
        distance_factor: Multiplier for long routes (1.0-1.5)
        layer_factor: Multiplier for multi-layer routing (1.0-2.5)
    """

    max_iterations: int
    reason: str
    congestion_factor: float
    distance_factor: float
    layer_factor: float

    @staticmethod
    def calculate(
        context: RoutingContext, congestion: CongestionLevel, base_iterations_per_cell: int = 100
    ) -> "IterationBudget":
        """Calculate adaptive iteration budget for A* pathfinding.

        This is a pure function - given the same inputs, always returns
        the same output. No side effects.

        Args:
            context: Immutable routing context
            congestion: Congestion level at route start/end
            base_iterations_per_cell: Base iterations per mm of distance
                (default: 100, gives ~10k for 10mm route in open area)

        Returns:
            Immutable IterationBudget with calculated limits

        Formula:
            1. Base budget = distance_mm * base_iterations_per_cell
            2. Congestion factor: LOW=1.0, MEDIUM=2.0, HIGH=4.0, EXTREME=8.0
            3. Layer factor: 1 layer=1.0, 2 layers=1.5, 3 layers=2.0, 4+ layers=2.5
            4. Distance factor: <100mm=1.0, >=100mm=1.5 (exponential growth)
            5. Safety margin: 1.2x
            6. Clamp to [5,000, 1,000,000]

        Examples:
            >>> # Short route, open area
            >>> ctx = RoutingContext("USB_D+", (0,0), (10,0), (0,1), "Signal")
            >>> budget = IterationBudget.calculate(ctx, CongestionLevel.LOW)
            >>> budget.max_iterations
            5000  # Clamped to minimum

            >>> # Long route, high congestion, multi-layer
            >>> ctx = RoutingContext("+5V", (0,0), (100,50), (0,1,2,3), "PowerTrace")
            >>> budget = IterationBudget.calculate(ctx, CongestionLevel.HIGH)
            >>> budget.max_iterations
            270000  # 150mm * 100 * 4.0 * 2.5 * 1.5 * 1.2
        """
        distance = context.manhattan_distance()
        layer_count = context.layer_count()

        # Congestion factor (1.0 - 8.0x)
        congestion_factor = congestion.get_factor()

        # Layer factor (1.0 - 2.5x)
        if layer_count == 1:
            layer_factor = 1.0
        elif layer_count == 2:
            layer_factor = 1.5
        elif layer_count == 3:
            layer_factor = 2.0
        else:  # 4+ layers
            layer_factor = 2.5

        # Distance factor (1.0 or 1.5x for long routes)
        # Long routes (>100mm) need exponential scaling due to search space growth
        distance_factor = 1.5 if distance >= 100.0 else 1.0

        # Calculate budget with safety margin
        base_budget = distance * base_iterations_per_cell
        safety_margin = 1.2
        budget = base_budget * congestion_factor * layer_factor * distance_factor * safety_margin

        # Clamp to reasonable limits
        MIN_ITERATIONS = 5_000
        MAX_ITERATIONS = 1_000_000
        clamped_budget = int(max(MIN_ITERATIONS, min(MAX_ITERATIONS, budget)))

        # Generate human-readable reason
        reason = (
            f"dist={distance:.1f}mm, "
            f"congestion={congestion.value}, "
            f"layers={layer_count}, "
            f"budget={clamped_budget}"
        )

        return IterationBudget(
            max_iterations=clamped_budget,
            reason=reason,
            congestion_factor=congestion_factor,
            distance_factor=distance_factor,
            layer_factor=layer_factor,
        )


# ============================================================================
# Pure Helper Functions
# ============================================================================


def estimate_iterations_for_route(
    start: Tuple[float, float],
    end: Tuple[float, float],
    layer_count: int,
    congestion: CongestionLevel,
    net_class: str = "Signal",
) -> int:
    """Convenience function to estimate iterations for a route.

    Args:
        start: Start point (x, y) in mm
        end: End point (x, y) in mm
        layer_count: Number of available layers
        congestion: Congestion level
        net_class: Net class name

    Returns:
        Estimated max iterations
    """
    context = RoutingContext(
        net_name="estimate",
        start=start,
        end=end,
        allowed_layers=tuple(range(layer_count)),
        net_class=net_class,
    )
    budget = IterationBudget.calculate(context, congestion)
    return budget.max_iterations


def get_congestion_scaling_factors() -> dict:
    """Get all congestion scaling factors for reference.

    Returns:
        Dictionary mapping CongestionLevel to scaling factor
    """
    return {level: level.get_factor() for level in CongestionLevel}
