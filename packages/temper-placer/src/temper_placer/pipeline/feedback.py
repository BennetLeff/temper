"""
Placement-routing feedback loop implementation (temper-l65.2).

This module implements the bidirectional feedback between placement and routing
phases. When routing fails, it converts failures into placement adjustments
and enables re-optimization with updated constraints.

Feedback Flow:
1. Routing verifier detects failure (congestion, no path, etc.)
2. Diagnostics identify blocking elements and locations
3. FeedbackGenerator creates placement adjustment hints
4. AdjustmentApplier converts adjustments to soft constraints
5. Geometric optimizer re-runs with new constraints
6. Repeat until feasible or max iterations

Example usage:
    >>> from temper_placer.pipeline.feedback import run_feedback_loop
    >>> from temper_placer.routing import RoutingReport
    >>>
    >>> def my_router(adjustments):
    ...     # Re-run routing with adjustments applied
    ...     return new_routing_report
    >>>
    >>> result = run_feedback_loop(
    ...     initial_report=routing_report,
    ...     routing_function=my_router,
    ... )
    >>> if result.converged:
    ...     print("Routing feasible after", result.iterations, "iterations")
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from temper_placer.routing.diagnostics import (
    FailureType,
    RoutingDiagnostic,
    RoutingReport,
    compute_clear_direction,
)


class AdjustmentType(Enum):
    """Types of placement adjustments.

    Used to categorize feedback from router to placer.
    """

    MOVE = "move"  # Move component in a direction
    ROTATE = "rotate"  # Rotate component
    SPREAD = "spread"  # Spread components apart
    SWAP = "swap"  # Swap two component positions


@dataclass
class FeedbackAdjustment:
    """Placement adjustment generated from routing feedback.

    Provides actionable hints from the router to the placer for
    the placement ↔ routing feedback loop.

    Attributes:
        component: Component reference to adjust
        adjustment_type: Type of adjustment to make
        direction: (dx, dy) direction for MOVE, or None
        magnitude: Distance/angle to adjust
        reason: Human-readable explanation
        priority: 0.0-1.0 priority (higher = more important)
        source_diagnostic: Original diagnostic that triggered this
    """

    component: str
    adjustment_type: AdjustmentType
    direction: tuple[float, float] | None
    magnitude: float
    reason: str
    priority: float
    source_diagnostic: RoutingDiagnostic | None


@dataclass
class FeedbackLoopConfig:
    """Configuration for the feedback loop.

    Attributes:
        max_iterations: Maximum number of placement-routing iterations
        max_adjustments_per_iteration: Max adjustments to apply each iteration
        refinement_epochs: Epochs for refinement optimization runs
    """

    max_iterations: int = 5
    max_adjustments_per_iteration: int = 3
    refinement_epochs: int = 2000


@dataclass
class FeedbackLoopResult:
    """Result of running the feedback loop.

    Attributes:
        converged: True if routing became feasible
        iterations: Number of iterations executed
        final_routing_report: Last routing report
        adjustments_applied: All adjustments applied across iterations
        history: Per-iteration tracking info
    """

    converged: bool
    iterations: int
    final_routing_report: RoutingReport | None
    adjustments_applied: list[FeedbackAdjustment]
    history: list[dict[str, Any]]


class FeedbackGenerator:
    """Converts routing failures to placement adjustments.

    Analyzes routing diagnostics and generates actionable placement
    adjustments that may resolve routing issues.
    """

    def __init__(self):
        """Initialize the feedback generator."""
        pass

    def generate(self, routing_report: RoutingReport) -> list[FeedbackAdjustment]:
        """Generate placement adjustments from routing failures.

        Args:
            routing_report: Routing report with diagnostics.

        Returns:
            List of FeedbackAdjustment sorted by priority (highest first).
        """
        if routing_report.feasible:
            return []

        adjustments = []

        for diagnostic in routing_report.diagnostics:
            adj = self._diagnostic_to_adjustment(diagnostic)
            if adj is not None:
                adjustments.append(adj)

        # Sort by priority (highest first)
        adjustments.sort(key=lambda a: -a.priority)

        return adjustments

    def _diagnostic_to_adjustment(self, diagnostic: RoutingDiagnostic) -> FeedbackAdjustment | None:
        """Convert a single diagnostic to a placement adjustment.

        Args:
            diagnostic: The routing diagnostic to convert.

        Returns:
            FeedbackAdjustment or None if no adjustment possible.
        """
        if diagnostic.failure_type == FailureType.NO_PATH:
            return self._handle_no_path(diagnostic)
        elif diagnostic.failure_type == FailureType.CONGESTION:
            return self._handle_congestion(diagnostic)
        elif diagnostic.failure_type == FailureType.LAYER_CONFLICT:
            # Layer conflicts cannot be fixed by placement adjustment
            return None
        elif diagnostic.failure_type == FailureType.CLEARANCE:
            return self._handle_clearance(diagnostic)
        elif diagnostic.failure_type == FailureType.VIA_COUNT:
            return self._handle_via_count(diagnostic)

        return None

    def _handle_no_path(self, diagnostic: RoutingDiagnostic) -> FeedbackAdjustment | None:
        """Handle NO_PATH failure - move blocking component.

        Args:
            diagnostic: NO_PATH diagnostic.

        Returns:
            MOVE adjustment for the blocking component.
        """
        if not diagnostic.blocking_elements:
            return None

        # Target the first blocking element
        blocker = diagnostic.blocking_elements[0]

        # Compute direction to move - perpendicular to blocked path
        # Use the diagnostic location as a reference point
        loc = diagnostic.location
        # Default direction: move up and to the right
        direction = (1.0, 1.0)

        # If we have blocking info, try to compute smarter direction
        if len(diagnostic.blocking_elements) >= 1:
            # Simple heuristic: move away from the diagnostic location
            # In a real implementation, we'd use path endpoints
            direction = compute_clear_direction(
                blocker_pos=loc,
                path_start=(loc[0] - 5.0, loc[1]),
                path_end=(loc[0] + 5.0, loc[1]),
            )

        return FeedbackAdjustment(
            component=blocker,
            adjustment_type=AdjustmentType.MOVE,
            direction=direction,
            magnitude=3.0,  # mm - default move distance
            reason=f"Clear path for {diagnostic.net}",
            priority=1.0,  # High priority for NO_PATH
            source_diagnostic=diagnostic,
        )

    def _handle_congestion(self, diagnostic: RoutingDiagnostic) -> FeedbackAdjustment | None:
        """Handle CONGESTION failure - spread components.

        Args:
            diagnostic: CONGESTION diagnostic.

        Returns:
            SPREAD adjustment for congested area.
        """
        if not diagnostic.blocking_elements:
            return None

        # Target first component in the congested area
        target = diagnostic.blocking_elements[0]

        return FeedbackAdjustment(
            component=target,
            adjustment_type=AdjustmentType.SPREAD,
            direction=None,  # Spread doesn't have a specific direction
            magnitude=5.0,  # mm - spread radius
            reason=f"Reduce congestion at ({diagnostic.location[0]:.1f}, {diagnostic.location[1]:.1f})",
            priority=0.7,  # Medium priority for congestion
            source_diagnostic=diagnostic,
        )

    def _handle_clearance(self, diagnostic: RoutingDiagnostic) -> FeedbackAdjustment | None:
        """Handle CLEARANCE failure - increase separation.

        Args:
            diagnostic: CLEARANCE diagnostic.

        Returns:
            MOVE or SPREAD adjustment.
        """
        if not diagnostic.blocking_elements:
            return None

        target = diagnostic.blocking_elements[0]

        return FeedbackAdjustment(
            component=target,
            adjustment_type=AdjustmentType.MOVE,
            direction=(1.0, 0.0),  # Simple: move right
            magnitude=2.0,  # mm
            reason=f"Increase clearance for {diagnostic.net}",
            priority=0.8,
            source_diagnostic=diagnostic,
        )

    def _handle_via_count(self, diagnostic: RoutingDiagnostic) -> FeedbackAdjustment | None:
        """Handle VIA_COUNT failure - try rotation.

        Args:
            diagnostic: VIA_COUNT diagnostic.

        Returns:
            ROTATE adjustment to try alternate pin access.
        """
        if not diagnostic.blocking_elements:
            return None

        target = diagnostic.blocking_elements[0]

        return FeedbackAdjustment(
            component=target,
            adjustment_type=AdjustmentType.ROTATE,
            direction=None,
            magnitude=90.0,  # degrees
            reason=f"Try alternate orientation to reduce vias for {diagnostic.net}",
            priority=0.4,  # Lower priority
            source_diagnostic=diagnostic,
        )


class AdjustmentApplier:
    """Converts placement adjustments to soft constraints.

    Takes FeedbackAdjustments and creates soft constraints that
    can be added to the constraint set for re-optimization.
    """

    def __init__(self, max_adjustments: int = 3):
        """Initialize the applier.

        Args:
            max_adjustments: Maximum adjustments to apply per iteration.
        """
        self.max_adjustments = max_adjustments

    def apply(self, adjustments: list[FeedbackAdjustment]) -> list[dict[str, Any]]:
        """Convert adjustments to soft constraints.

        Args:
            adjustments: List of adjustments to convert.

        Returns:
            List of constraint dicts for the optimizer.
        """
        if not adjustments:
            return []

        # Limit number of adjustments
        limited = adjustments[: self.max_adjustments]

        constraints = []
        for adj in limited:
            constraint = self._adjustment_to_constraint(adj)
            if constraint is not None:
                constraints.append(constraint)

        return constraints

    def _adjustment_to_constraint(self, adjustment: FeedbackAdjustment) -> dict[str, Any] | None:
        """Convert a single adjustment to a constraint dict.

        Args:
            adjustment: The adjustment to convert.

        Returns:
            Constraint dict or None.
        """
        if adjustment.adjustment_type == AdjustmentType.MOVE:
            return {
                "type": "attraction",
                "scope": [adjustment.component],
                "direction": adjustment.direction,
                "magnitude": adjustment.magnitude,
                "tier": "SOFT",  # Feedback constraints are soft
                "because": adjustment.reason,
            }
        elif adjustment.adjustment_type == AdjustmentType.SPREAD:
            return {
                "type": "separation",
                "scope": [adjustment.component],
                "min_distance": adjustment.magnitude,
                "tier": "SOFT",
                "because": adjustment.reason,
            }
        elif adjustment.adjustment_type == AdjustmentType.ROTATE:
            return {
                "type": "rotation_hint",
                "scope": [adjustment.component],
                "preferred_angle": adjustment.magnitude,
                "tier": "SOFT",
                "because": adjustment.reason,
            }
        elif adjustment.adjustment_type == AdjustmentType.SWAP:
            return {
                "type": "swap_suggestion",
                "scope": [adjustment.component],
                "tier": "SOFT",
                "because": adjustment.reason,
            }

        return None


def run_feedback_loop(
    initial_report: RoutingReport,
    routing_function: Callable[[list[FeedbackAdjustment]], RoutingReport],
    config: FeedbackLoopConfig | None = None,
    on_iteration: Callable[[int, RoutingReport, list[FeedbackAdjustment]], None] | None = None,
) -> FeedbackLoopResult:
    """Run the placement-routing feedback loop.

    Iteratively generates placement adjustments from routing failures
    and re-runs routing until feasible or max iterations reached.

    Args:
        initial_report: Initial routing report to start from.
        routing_function: Function that takes adjustments and returns
            a new RoutingReport after re-routing.
        config: Configuration for the loop (optional).
        on_iteration: Callback called each iteration (optional).

    Returns:
        FeedbackLoopResult with convergence status and history.
    """
    if config is None:
        config = FeedbackLoopConfig()

    generator = FeedbackGenerator()
    applier = AdjustmentApplier(max_adjustments=config.max_adjustments_per_iteration)

    all_adjustments: list[FeedbackAdjustment] = []
    history: list[dict[str, Any]] = []
    current_report = initial_report

    # Check if already feasible
    if current_report.feasible:
        return FeedbackLoopResult(
            converged=True,
            iterations=0,
            final_routing_report=current_report,
            adjustments_applied=all_adjustments,
            history=history,
        )

    for iteration in range(config.max_iterations):
        # Generate adjustments from current failures
        adjustments = generator.generate(current_report)

        # Call callback
        if on_iteration is not None:
            on_iteration(iteration, current_report, adjustments)

        # Track history
        history.append(
            {
                "iteration": iteration,
                "feasible": current_report.feasible,
                "completion_rate": current_report.completion_rate,
                "num_adjustments": len(adjustments),
                "failed_nets": len(current_report.failed_nets),
            }
        )

        # If no adjustments possible, stop early
        if not adjustments:
            return FeedbackLoopResult(
                converged=False,
                iterations=iteration,
                final_routing_report=current_report,
                adjustments_applied=all_adjustments,
                history=history,
            )

        # Apply adjustments (converts to constraints)
        applier.apply(adjustments)

        # Track applied adjustments
        limited_adjustments = adjustments[: config.max_adjustments_per_iteration]
        all_adjustments.extend(limited_adjustments)

        # Re-run routing with adjustments
        current_report = routing_function(limited_adjustments)

        # Check if now feasible
        if current_report.feasible:
            # Add final history entry
            history.append(
                {
                    "iteration": iteration + 1,
                    "feasible": True,
                    "completion_rate": current_report.completion_rate,
                    "num_adjustments": 0,
                    "failed_nets": 0,
                }
            )
            return FeedbackLoopResult(
                converged=True,
                iterations=iteration + 1,
                final_routing_report=current_report,
                adjustments_applied=all_adjustments,
                history=history,
            )

    # Max iterations reached
    return FeedbackLoopResult(
        converged=False,
        iterations=config.max_iterations,
        final_routing_report=current_report,
        adjustments_applied=all_adjustments,
        history=history,
    )
