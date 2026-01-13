"""
Router V6 Feedback F.5: Check Convergence

Checks if feedback loop has converged and should terminate.
Part of temper-o52r (Feedback Loop & Co-Optimization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.apply_suggestions import AdjustmentResult
from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class ConvergenceMetrics:
    """Metrics for convergence analysis."""

    iteration: int
    routing_success_rate: float  # 0.0-1.0
    total_movement: float  # mm
    failed_net_count: int
    has_converged: bool
    convergence_reason: str


def check_convergence(
    iteration: int,
    routing_results: RoutingResults,
    adjustment_result: AdjustmentResult | None = None,
    max_iterations: int = 10,
    success_rate_threshold: float = 0.95,
    movement_threshold: float = 1.0,  # mm
) -> ConvergenceMetrics:
    """
    Check if feedback loop has converged.

    Convergence is achieved when:
    1. Routing success rate is high enough, OR
    2. Component movement is minimal, OR
    3. Maximum iterations reached

    Args:
        iteration: Current iteration number
        routing_results: Latest routing results
        adjustment_result: Latest adjustment result (if any)
        max_iterations: Maximum allowed iterations
        success_rate_threshold: Minimum success rate for convergence
        movement_threshold: Maximum movement for convergence (mm)

    Returns:
        ConvergenceMetrics with convergence status

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> metrics = check_convergence(1, results)
        >>> isinstance(metrics.has_converged, bool)
        True
    """
    # Calculate routing success rate
    total_nets = routing_results.success_count + routing_results.failure_count
    success_rate = routing_results.success_count / total_nets if total_nets > 0 else 0.0

    # Get total movement
    total_movement = adjustment_result.total_movement if adjustment_result else 0.0

    # Check convergence conditions
    has_converged = False
    reason = ""

    # Condition 1: High success rate
    if success_rate >= success_rate_threshold:
        has_converged = True
        reason = f"High routing success rate: {success_rate:.1%}"

    # Condition 2: Minimal movement
    elif adjustment_result and total_movement < movement_threshold:
        has_converged = True
        reason = f"Minimal component movement: {total_movement:.2f}mm"

    # Condition 3: Max iterations
    elif iteration >= max_iterations:
        has_converged = True
        reason = f"Maximum iterations reached: {iteration}/{max_iterations}"

    # Still iterating
    else:
        reason = f"Continuing iteration {iteration}/{max_iterations}"

    return ConvergenceMetrics(
        iteration=iteration,
        routing_success_rate=success_rate,
        total_movement=total_movement,
        failed_net_count=routing_results.failure_count,
        has_converged=has_converged,
        convergence_reason=reason,
    )


def should_continue_iteration(metrics: ConvergenceMetrics) -> bool:
    """
    Determine if feedback loop should continue.

    Args:
        metrics: Convergence metrics

    Returns:
        True if should continue iterating
    """
    return not metrics.has_converged
