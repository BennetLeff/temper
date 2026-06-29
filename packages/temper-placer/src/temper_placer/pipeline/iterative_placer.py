"""
Iterative placement with routing feedback.

Implements the outer loop that adjusts placement based on routing failures.

Part of temper-gzur.2
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.router_v6.adapter import MazeRouter
from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.congestion_heatmap import CongestionHeatmap

if TYPE_CHECKING:
    from jax import Array



@dataclass
class IterationResult:
    """Result of one place-route iteration."""
    iteration: int
    completion_rate: float
    nets_routed: int
    nets_failed: int
    total_congestion: float
    hotspot_count: int
    placement_changed: bool
    routability_score_mean: float = 0.0
    unsat_core_size: int = 0
    solver_status: str = "unknown"


@dataclass
class PlaceRouteResult:
    """Final result of iterative place-and-route."""
    iterations: int
    final_completion: float
    converged: bool
    positions: Array
    routing_results: dict[str, RoutePath]
    heatmap: CongestionHeatmap | None
    iteration_history: list[IterationResult]
    routability_history: list[float] = field(default_factory=list)


def iterative_place_and_route(
    router_factory: Callable[[Array], MazeRouter],
    route_fn: Callable[[MazeRouter, Array], dict[str, RoutePath]],
    initial_positions: Array,
    placement_update_fn: Callable[[Array, CongestionHeatmap], Array] | None = None,
    max_iterations: int = 10,
    target_completion: float = 0.95,
    convergence_threshold: float = 0.01,
) -> PlaceRouteResult:
    """Iteratively refine placement based on routing feedback.

    Loop:
    1. Route with current placement
    2. Build congestion heatmap from failures
    3. Adjust placement to avoid congestion
    4. Repeat until target completion or convergence

    Args:
        router_factory: Creates router from positions
        route_fn: Routes all nets, returns results
        initial_positions: Starting component positions
        placement_update_fn: Optional function to adjust positions based on heatmap
        max_iterations: Maximum iterations before stopping
        target_completion: Stop if this completion achieved
        convergence_threshold: Stop if completion improvement below this

    Returns:
        PlaceRouteResult with final state
    """
    positions = initial_positions
    history: list[IterationResult] = []
    last_completion = 0.0
    best_positions = positions
    best_completion = 0.0
    best_results: dict[str, RoutePath] = {}
    final_heatmap: CongestionHeatmap | None = None

    for i in range(max_iterations):
        # Route with current placement
        router = router_factory(positions)
        results = route_fn(router, positions)

        # Calculate metrics
        success_count = sum(1 for r in results.values() if r.success)
        total_count = len(results)
        completion = success_count / total_count if total_count > 0 else 1.0

        # Build heatmap
        heatmap = CongestionHeatmap.from_router(router)
        hotspots = heatmap.get_hotspots(threshold=0.3)

        # Track best result
        if completion > best_completion:
            best_completion = completion
            best_positions = positions
            best_results = results
            final_heatmap = heatmap

        # Record iteration
        result = IterationResult(
            iteration=i + 1,
            completion_rate=completion,
            nets_routed=success_count,
            nets_failed=total_count - success_count,
            total_congestion=heatmap.get_total_congestion(),
            hotspot_count=len(hotspots),
            placement_changed=i > 0,
        )
        history.append(result)

        # Check termination conditions
        if completion >= target_completion:
            return PlaceRouteResult(
                iterations=i + 1,
                final_completion=completion,
                converged=True,
                positions=positions,
                routing_results=results,
                heatmap=heatmap,
                iteration_history=history,
            )

        # Check convergence (no improvement)
        improvement = completion - last_completion
        if i > 0 and abs(improvement) < convergence_threshold:
            # Not improving, return best
            return PlaceRouteResult(
                iterations=i + 1,
                final_completion=best_completion,
                converged=True,
                positions=best_positions,
                routing_results=best_results,
                heatmap=final_heatmap,
                iteration_history=history,
            )

        last_completion = completion

        # Update placement if we have an update function
        if placement_update_fn is not None:
            new_positions = placement_update_fn(positions, heatmap)
            positions = new_positions

    # Max iterations reached
    return PlaceRouteResult(
        iterations=max_iterations,
        final_completion=best_completion,
        converged=False,
        positions=best_positions,
        routing_results=best_results,
        heatmap=final_heatmap,
        iteration_history=history,
    )


def simple_congestion_repel(
    positions: Array,
    heatmap: CongestionHeatmap,
    repel_strength: float = 0.5,
) -> Array:
    """Simple placement update: move components away from congestion.

    For each component, compute gradient of congestion and move slightly away.

    Args:
        positions: Current positions (N, 2)
        heatmap: Congestion heatmap
        repel_strength: How far to move (mm)

    Returns:
        Updated positions
    """
    import jax.numpy as jnp

    new_positions = []

    for i in range(len(positions)):
        x, y = float(positions[i, 0]), float(positions[i, 1])

        # Sample congestion gradient (finite difference)
        dx = 0.5  # sample offset in mm
        cong_center = heatmap.get_congestion_at(x, y)
        cong_right = heatmap.get_congestion_at(x + dx, y)
        cong_up = heatmap.get_congestion_at(x, y + dx)

        # Gradient points toward higher congestion
        grad_x = (cong_right - cong_center) / dx
        grad_y = (cong_up - cong_center) / dx

        # Move opposite to gradient (away from congestion)
        new_x = x - repel_strength * grad_x
        new_y = y - repel_strength * grad_y

        new_positions.append([new_x, new_y])

    return jnp.array(new_positions)
