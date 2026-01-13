"""
Router V6 Feedback F.6: Iteration Control

Orchestrates the complete feedback loop between routing and placement.
Part of temper-dml9 (Feedback Loop & Co-Optimization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.apply_suggestions import (
    apply_suggestions_with_damping,
    update_component_positions,
)
from temper_placer.router_v6.congestion_analysis import identify_congested_regions
from temper_placer.router_v6.convergence_check import check_convergence
from temper_placer.router_v6.placement_suggestions import generate_placement_suggestions
from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class IterationHistory:
    """History of a single feedback iteration."""

    iteration: int
    routing_success_rate: float
    failed_net_count: int
    congested_region_count: int
    suggestion_count: int
    total_movement: float
    converged: bool


@dataclass
class FeedbackLoopResult:
    """Result of complete feedback loop execution."""

    final_positions: dict[str, tuple[float, float]]
    history: list[IterationHistory]
    final_routing_results: RoutingResults
    converged: bool
    total_iterations: int

    @property
    def final_success_rate(self) -> float:
        """Final routing success rate."""
        if self.history:
            return self.history[-1].routing_success_rate
        return 0.0


def run_feedback_loop(
    initial_positions: dict[str, tuple[float, float]],
    routing_function,  # Callable that takes positions and returns RoutingResults
    board_width: float,
    board_height: float,
    max_iterations: int = 10,
    damping_factor: float = 0.5,
) -> FeedbackLoopResult:
    """
    Run complete feedback loop between routing and placement.

    Iteratively:
    1. Route with current positions
    2. Identify congested regions
    3. Generate placement suggestions
    4. Apply suggestions with damping
    5. Check convergence
    6. Repeat until converged or max iterations

    Args:
        initial_positions: Starting component positions
        routing_function: Function that routes given positions
        board_width: Board width (mm)
        board_height: Board height (mm)
        max_iterations: Maximum iterations
        damping_factor: Damping factor for suggestions

    Returns:
        FeedbackLoopResult with complete history

    Example:
        >>> def mock_router(positions):
        ...     from temper_placer.router_v6.routing_results import RoutingResults
        ...     return RoutingResults(compiled_routes={}, failed_nets=[])
        >>> positions = {"U1": (10.0, 10.0)}
        >>> result = run_feedback_loop(positions, mock_router, 100, 100, max_iterations=3)
        >>> result.total_iterations >= 1
        True
    """
    current_positions = initial_positions.copy()
    history = []

    for iteration in range(1, max_iterations + 1):
        # Step 1: Route with current positions
        routing_results = routing_function(current_positions)

        # Step 2: Identify congested regions
        congestion_map = identify_congested_regions(
            routing_results,
            board_width,
            board_height,
        )

        # Step 3: Generate placement suggestions
        suggestions = generate_placement_suggestions(
            congestion_map,
            current_positions,
        )

        # Step 4: Apply suggestions with damping
        adjustment_result = apply_suggestions_with_damping(
            suggestions,
            current_positions,
            damping_factor=damping_factor,
        )

        # Step 5: Check convergence
        convergence = check_convergence(
            iteration,
            routing_results,
            adjustment_result,
            max_iterations=max_iterations,
        )

        # Record history
        history.append(IterationHistory(
            iteration=iteration,
            routing_success_rate=convergence.routing_success_rate,
            failed_net_count=convergence.failed_net_count,
            congested_region_count=congestion_map.congested_region_count,
            suggestion_count=suggestions.suggestion_count,
            total_movement=convergence.total_movement,
            converged=convergence.has_converged,
        ))

        # Check if converged
        if convergence.has_converged:
            break

        # Step 6: Update positions for next iteration
        current_positions = update_component_positions(
            current_positions,
            adjustment_result,
        )

    return FeedbackLoopResult(
        final_positions=current_positions,
        history=history,
        final_routing_results=routing_results,
        converged=history[-1].converged if history else False,
        total_iterations=len(history),
    )
