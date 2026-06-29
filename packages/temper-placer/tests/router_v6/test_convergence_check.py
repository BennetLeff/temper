"""
Tests for Router V6 Feedback F.5: Check Convergence

Part of temper-o52r
"""

import pytest

from temper_placer.router_v6.apply_suggestions import AdjustmentResult, AppliedAdjustment
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.convergence_check import (
    ConvergenceMetrics,
    check_convergence,
    should_continue_iteration,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def test_convergence_high_success_rate():
    """Test convergence with high routing success rate."""
    # 95% success rate (19/20 nets)
    routes = {}
    for i in range(19):
        path = RoutePath(f"NET{i}", [(0, 0), (10, 10)], "F.Cu", 14.14)
        routes[f"NET{i}"] = CompiledRoute(f"NET{i}", path, 0.127, [], None)

    results = RoutingResults(compiled_routes=routes, failed_nets=["NET19"])

    metrics = check_convergence(1, results)

    assert metrics.has_converged
    assert "success rate" in metrics.convergence_reason.lower()


def test_convergence_minimal_movement():
    """Test convergence with minimal component movement."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=["NET2"])

    # Very small movement
    adj = AppliedAdjustment("U1", (0, 0), (0.5, 0), (0.3, 0), 0.5)
    adjustment = AdjustmentResult(adjustments=[adj])

    metrics = check_convergence(1, results, adjustment, movement_threshold=1.0)

    assert metrics.has_converged
    assert "movement" in metrics.convergence_reason.lower()


def test_convergence_max_iterations():
    """Test convergence when max iterations reached."""
    results = RoutingResults(compiled_routes={}, failed_nets=["NET1", "NET2"])

    metrics = check_convergence(10, results, max_iterations=10)

    assert metrics.has_converged
    assert "maximum iterations" in metrics.convergence_reason.lower()


def test_not_converged():
    """Test when convergence not yet achieved."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=["NET2", "NET3"])

    # Large movement
    adj = AppliedAdjustment("U1", (0, 0), (10, 0), (5, 0), 0.5)
    adjustment = AdjustmentResult(adjustments=[adj])

    metrics = check_convergence(3, results, adjustment, max_iterations=10)

    assert not metrics.has_converged
    assert "Continuing iteration" in metrics.convergence_reason


def test_convergence_metrics_dataclass():
    """Test ConvergenceMetrics dataclass."""
    metrics = ConvergenceMetrics(
        iteration=5,
        routing_success_rate=0.85,
        total_movement=2.5,
        failed_net_count=3,
        has_converged=False,
        convergence_reason="Continuing iteration",
    )

    assert metrics.iteration == 5
    assert metrics.routing_success_rate == 0.85
    assert metrics.failed_net_count == 3
    assert not metrics.has_converged


def test_should_continue_iteration():
    """Test should_continue_iteration helper."""
    converged_metrics = ConvergenceMetrics(5, 0.95, 0.5, 1, True, "Converged")
    not_converged_metrics = ConvergenceMetrics(5, 0.80, 5.0, 5, False, "Continuing")

    assert not should_continue_iteration(converged_metrics)
    assert should_continue_iteration(not_converged_metrics)


def test_custom_thresholds():
    """Test convergence with custom thresholds."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=["NET2"]  # 50% success
    )

    # Should not converge with high threshold
    metrics_high = check_convergence(
        1, results,
        success_rate_threshold=0.99
    )
    assert not metrics_high.has_converged

    # Should converge with low threshold
    metrics_low = check_convergence(
        1, results,
        success_rate_threshold=0.40
    )
    assert metrics_low.has_converged


def test_success_rate_calculation():
    """Test accurate success rate calculation."""
    routes = {f"NET{i}": CompiledRoute(
        f"NET{i}",
        RoutePath(f"NET{i}", [(0, 0), (10, 10)], "F.Cu", 14.14),
        0.127, [], None
    ) for i in range(7)}

    results = RoutingResults(
        compiled_routes=routes,
        failed_nets=["NET7", "NET8", "NET9"]  # 7 success, 3 failed = 70%
    )

    metrics = check_convergence(1, results)

    assert metrics.routing_success_rate == pytest.approx(0.7)
    assert metrics.failed_net_count == 3
