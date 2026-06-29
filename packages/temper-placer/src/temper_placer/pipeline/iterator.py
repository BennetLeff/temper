"""PlaceRouteIterator orchestrator class.

Part of temper-1d78.2
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jax import Array

    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


@dataclass
class IterationResult:
    """Result of a single placement-routing iteration."""
    iteration: int
    completion_rate: float
    is_feasible: bool
    elapsed_time: float
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaceRouteResult:
    """Final result of the place-route iteration loop."""
    converged: bool
    iterations: int
    final_positions: Array
    iteration_history: list[IterationResult] = field(default_factory=list)
    final_metrics: dict[str, Any] = field(default_factory=dict)


class PlaceRouteIterator:
    """Orchestrates the iterative loop between placement and routing.

    This class manages multiple iterations of:
    1. Routing the current placement.
    2. Analyzing routing failures.
    3. Updating placement based on feedback.
    4. Checking for convergence or completion.
    """

    def __init__(
        self,
        netlist: Netlist,
        board: Board,
        router: Any,
        placement_update_fn: Callable[[Array, Any], Array] | None = None,
        max_iterations: int = 10,
        target_completion: float = 1.0,
        min_improvement: float = 0.001,
    ):
        """Initialize the iterator.

        Args:
            netlist: The PCB netlist.
            board: The PCB board definition.
            router: An object with a .route(positions) method.
            placement_update_fn: Optional function to adjust positions based on routing feedback.
            max_iterations: Maximum number of iterations to run.
            target_completion: Completion rate (0.0 to 1.0) to stop at.
            min_improvement: Minimum improvement in completion rate to continue.
        """
        self.netlist = netlist
        self.board = board
        self.router = router
        self.placement_update_fn = placement_update_fn
        self.max_iterations = max_iterations
        self.target_completion = target_completion
        self.min_improvement = min_improvement

    def run(self, initial_positions: Array) -> PlaceRouteResult:
        """Execute the iterative place-route loop.

        Args:
            initial_positions: The starting positions for the components.

        Returns:
            A PlaceRouteResult containing the final state and history.
        """
        current_positions = initial_positions
        history = []
        best_completion = -1.0
        best_positions = initial_positions

        for i in range(self.max_iterations):
            start_time = time.time()
            iteration_idx = i + 1

            # 1. Route
            routing_result = self.router.route(current_positions)

            completion = getattr(routing_result, "completion_rate", 0.0)
            is_feasible = routing_result.is_feasible()

            # Record iteration
            metrics = {
                "completion": completion,
                "is_feasible": is_feasible,
                "nets_failed": getattr(routing_result, "nets_failed", 0)
            }
            # Merge any additional metrics from routing result
            if hasattr(routing_result, "metrics") and isinstance(routing_result.metrics, dict):
                metrics.update(routing_result.metrics)

            iter_result = IterationResult(
                iteration=iteration_idx,
                completion_rate=completion,
                is_feasible=is_feasible,
                elapsed_time=time.time() - start_time,
                metrics=metrics
            )
            history.append(iter_result)

            # Track best
            if completion > best_completion:
                best_completion = completion
                best_positions = current_positions

            # Check termination
            if is_feasible or completion >= self.target_completion:
                return PlaceRouteResult(
                    converged=True,
                    iterations=iteration_idx,
                    final_positions=current_positions,
                    iteration_history=history,
                    final_metrics=iter_result.metrics
                )

            # Check for stagnation
            if i > 0 and self.min_improvement >= 0:
                improvement = completion - history[-2].completion_rate
                if improvement < self.min_improvement:
                    return PlaceRouteResult(
                        converged=False,
                        iterations=iteration_idx,
                        final_positions=best_positions,
                        iteration_history=history,
                        final_metrics=iter_result.metrics
                    )

            # 2. Update placement if possible
            if i < self.max_iterations - 1 and self.placement_update_fn:
                current_positions = self.placement_update_fn(current_positions, routing_result)
            elif not self.placement_update_fn:
                # If no update function, we can't iterate
                break

        return PlaceRouteResult(
            converged=False,
            iterations=len(history),
            final_positions=best_positions,
            iteration_history=history,
            final_metrics=history[-1].metrics if history else {}
        )
