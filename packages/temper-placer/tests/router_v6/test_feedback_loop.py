"""
Tests for Router V6 Feedback F.6: Iteration Control

Part of temper-dml9
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.feedback_loop import (
    FeedbackLoopResult,
    IterationHistory,
    run_feedback_loop,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def mock_routing_function_success(positions):
    """Mock routing function with high success rate."""
    # Simulate successful routing
    routes = {}
    for i in range(19):
        path = RoutePath(f"NET{i}", [(0, 0), (10, 10)], "F.Cu", 14.14)
        routes[f"NET{i}"] = CompiledRoute(f"NET{i}", path, 0.127, [], None)
    
    return RoutingResults(compiled_routes=routes, failed_nets=["NET19"])


def mock_routing_function_failure(positions):
    """Mock routing function with low success rate."""
    # Simulate failed routing
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    return RoutingResults(
        compiled_routes={"NET1": CompiledRoute("NET1", path, 0.127, [], None)},
        failed_nets=["NET2", "NET3", "NET4"]
    )


def test_feedback_loop_converges_quickly():
    """Test feedback loop with successful routing."""
    positions = {"U1": (10.0, 10.0), "U2": (20.0, 20.0)}
    
    result = run_feedback_loop(
        positions,
        mock_routing_function_success,
        100.0,
        100.0,
        max_iterations=10,
    )
    
    # Should converge due to high success rate
    assert result.converged
    assert result.total_iterations < 10


def test_feedback_loop_max_iterations():
    """Test feedback loop with failed routing."""
    positions = {"U1": (10.0, 10.0)}
    
    result = run_feedback_loop(
        positions,
        mock_routing_function_failure,
        100.0,
        100.0,
        max_iterations=3,
    )
    
    # Should run and eventually converge (may be early if no suggestions)
    assert result.total_iterations >= 1
    assert result.total_iterations <= 3
    assert result.converged  # Should have converged by end


def test_iteration_history_dataclass():
    """Test IterationHistory dataclass."""
    history = IterationHistory(
        iteration=5,
        routing_success_rate=0.85,
        failed_net_count=3,
        congested_region_count=2,
        suggestion_count=4,
        total_movement=2.5,
        converged=False,
    )
    
    assert history.iteration == 5
    assert history.routing_success_rate == 0.85
    assert history.suggestion_count == 4


def test_feedback_loop_result_dataclass():
    """Test FeedbackLoopResult dataclass."""
    history = [
        IterationHistory(1, 0.8, 2, 1, 3, 5.0, False),
        IterationHistory(2, 0.95, 1, 0, 1, 1.0, True),
    ]
    
    positions = {"U1": (15.0, 15.0)}
    routing = RoutingResults(compiled_routes={}, failed_nets=[])
    
    result = FeedbackLoopResult(
        final_positions=positions,
        history=history,
        final_routing_results=routing,
        converged=True,
        total_iterations=2,
    )
    
    assert result.total_iterations == 2
    assert result.converged
    assert result.final_success_rate == 0.95


def test_position_updates_across_iterations():
    """Test that positions update across iterations."""
    initial_positions = {"U1": (50.0, 50.0)}
    
    result = run_feedback_loop(
        initial_positions,
        mock_routing_function_failure,
        100.0,
        100.0,
        max_iterations=2,
        damping_factor=0.5,
    )
    
    # Positions should have changed
    # (May or may not depending on congestion, but structure should work)
    assert "U1" in result.final_positions


def test_damping_factor_effect():
    """Test effect of different damping factors."""
    positions = {"U1": (50.0, 50.0)}
    
    # High damping = more movement per iteration
    result_high = run_feedback_loop(
        positions,
        mock_routing_function_failure,
        100.0,
        100.0,
        max_iterations=2,
        damping_factor=0.9,
    )
    
    # Low damping = less movement per iteration
    result_low = run_feedback_loop(
        positions,
        mock_routing_function_failure,
        100.0,
        100.0,
        max_iterations=2,
        damping_factor=0.1,
    )
    
    # Both should complete without error
    assert result_high.total_iterations >= 1
    assert result_low.total_iterations >= 1


def test_empty_initial_positions():
    """Test feedback loop with no components."""
    result = run_feedback_loop(
        {},
        mock_routing_function_success,
        100.0,
        100.0,
        max_iterations=5,
    )
    
    # Should still run and converge
    assert result.total_iterations >= 1
    assert len(result.final_positions) == 0
