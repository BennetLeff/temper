"""Tests for routing feasibility detection module."""

import pytest
from dataclasses import dataclass
from typing import NamedTuple

# Import real data structures from implementation
from temper_validation.comparison.routing_feasibility import RoutingResult, RoutingFeasibilityResult


@dataclass
class Pin:
    """Pin for routing tests."""

    name: str
    position: tuple[float, float]
    layer: int = 0


@dataclass
class Net:
    """Net for routing tests."""

    name: str
    pins: list[Pin]


# Alias for compatibility with test code
RoutingAttempt = RoutingResult


def create_test_net(name: str, pin_positions: list[tuple[float, float]]) -> Net:
    """Helper to create test net."""
    pins = [Pin(f"{name}.pin{i}", pos, layer=0) for i, pos in enumerate(pin_positions)]
    return Net(name=name, pins=pins)


def test_all_nets_routed():
    """All nets successfully routed = 100% completion."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
        create_test_net("NET3", [(0, 10), (10, 0)]),
    ]

    # All nets successful
    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
        RoutingAttempt("NET2", True, 10.0, 0),
        RoutingAttempt("NET3", True, 20.0, 0),
    ]

    from temper_validation.comparison.routing_feasibility import calculate_routing_completion

    completion_rate = calculate_routing_completion(nets, attempts)

    # Should be 100%
    assert completion_rate == 1.0, f"Expected 100% completion (1.0), got {completion_rate}"


def test_no_nets_routed():
    """No nets successfully routed = 0% completion."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
    ]

    # All nets failed
    attempts = [
        RoutingAttempt("NET1", False, None, 0),
        RoutingAttempt("NET2", False, None, 0),
    ]

    from temper_validation.comparison.routing_feasibility import calculate_routing_completion

    completion_rate = calculate_routing_completion(nets, attempts)

    # Should be 0%
    assert completion_rate == 0.0, f"Expected 0% completion (0.0), got {completion_rate}"


def test_partial_routing():
    """Some nets routed, some failed = partial completion."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
        create_test_net("NET3", [(0, 10), (10, 0)]),
        create_test_net("NET4", [(2, 2), (8, 8)]),
    ]

    # 2 of 4 nets successful = 50%
    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
        RoutingAttempt("NET2", False, None, 0),
        RoutingAttempt("NET3", True, 20.0, 0),
        RoutingAttempt("NET4", False, None, 0),
    ]

    from temper_validation.comparison.routing_feasibility import calculate_routing_completion

    completion_rate = calculate_routing_completion(nets, attempts)

    # Should be 50% (2/4)
    assert completion_rate == 0.5, f"Expected 50% completion (0.5), got {completion_rate}"


def test_routing_verdict_threshold():
    """Verdict PASS if completion >= 95%, FAIL otherwise."""
    from temper_validation.comparison.routing_feasibility import get_routing_verdict

    # Case 1: 95% (should PASS - edge case)
    verdict_1 = get_routing_verdict(0.95)
    assert verdict_1 == "PASS", f"95% should PASS, got {verdict_1}"

    # Case 2: 96% (should PASS)
    verdict_2 = get_routing_verdict(0.96)
    assert verdict_2 == "PASS", f"96% should PASS, got {verdict_2}"

    # Case 3: 94% (should FAIL)
    verdict_3 = get_routing_verdict(0.94)
    assert verdict_3 == "FAIL", f"94% should FAIL, got {verdict_3}"

    # Case 4: 100% (should PASS)
    verdict_4 = get_routing_verdict(1.0)
    assert verdict_4 == "PASS", f"100% should PASS, got {verdict_4}"

    # Case 5: 80% (should FAIL)
    verdict_5 = get_routing_verdict(0.80)
    assert verdict_5 == "FAIL", f"80% should FAIL, got {verdict_5}"


def test_routing_feasibility_result_structure():
    """Routing feasibility result contains all required fields."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
    ]

    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
        RoutingAttempt("NET2", True, 10.0, 0),
    ]

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # Check all required fields
    assert hasattr(result, "total_nets"), "Result should have 'total_nets' field"
    assert hasattr(result, "routed_nets"), "Result should have 'routed_nets' field"
    assert hasattr(result, "failed_nets"), "Result should have 'failed_nets' field"
    assert hasattr(result, "completion_rate"), "Result should have 'completion_rate' field"
    assert hasattr(result, "average_wirelength"), "Result should have 'average_wirelength' field"
    assert hasattr(result, "total_vias"), "Result should have 'total_vias' field"
    assert hasattr(result, "verdict"), "Result should have 'verdict' field"

    # Check types
    assert isinstance(result.total_nets, int), "total_nets should be int"
    assert isinstance(result.routed_nets, int), "routed_nets should be int"
    assert isinstance(result.failed_nets, int), "failed_nets should be int"
    assert isinstance(result.completion_rate, float), "completion_rate should be float"
    assert isinstance(result.average_wirelength, float), "average_wirelength should be float"
    assert isinstance(result.total_vias, int), "total_vias should be int"
    assert isinstance(result.verdict, str), "verdict should be str"

    # Check reasonable values
    assert result.total_nets == 2, "Should have 2 total nets"
    assert result.routed_nets == 2, "Should have 2 routed nets"
    assert result.failed_nets == 0, "Should have 0 failed nets"
    assert result.completion_rate == 1.0, "Should have 100% completion"
    assert result.average_wirelength == 15.0, "Should have avg wirelength 15.0"
    assert result.total_vias == 0, "Should have 0 vias"
    assert result.verdict in ["PASS", "FAIL"], "verdict should be PASS or FAIL"


def test_average_wirelength_only_routed():
    """Average wirelength should only include successfully routed nets."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
        create_test_net("NET3", [(0, 10), (10, 0)]),
    ]

    # NET2 failed, should not contribute to avg
    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
        RoutingAttempt("NET2", False, None, 0),
        RoutingAttempt("NET3", True, 20.0, 0),
    ]

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # Average of NET1 (20) and NET3 (20) = 20.0
    assert result.average_wirelength == 20.0, (
        f"Expected avg wirelength 20.0, got {result.average_wirelength}"
    )

    # Should ignore failed nets
    assert result.total_nets == 3, "Should have 3 total nets"
    assert result.routed_nets == 2, "Should have 2 routed nets"
    assert result.failed_nets == 1, "Should have 1 failed net"


def test_via_counting():
    """Total vias should be summed across all successful routes."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
        create_test_net("NET3", [(0, 10), (10, 0)]),
    ]

    attempts = [
        RoutingAttempt("NET1", True, 20.0, 2),
        RoutingAttempt("NET2", True, 10.0, 1),
        RoutingAttempt("NET3", True, 20.0, 0),
    ]

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # 2 + 1 + 0 = 3 vias
    assert result.total_vias == 3, f"Expected 3 total vias, got {result.total_vias}"


def test_empty_nets():
    """Empty net list should handle gracefully."""
    nets = []
    attempts = []

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # All counts should be 0
    assert result.total_nets == 0, "Should have 0 total nets"
    assert result.routed_nets == 0, "Should have 0 routed nets"
    assert result.failed_nets == 0, "Should have 0 failed nets"

    # Completion rate undefined - treat as 100%
    assert result.completion_rate == 1.0, (
        f"Empty nets should be 100% complete, got {result.completion_rate}"
    )

    # Average wirelength undefined - treat as 0
    assert result.average_wirelength == 0.0, (
        f"Empty nets should have 0 avg wirelength, got {result.average_wirelength}"
    )

    # No vias
    assert result.total_vias == 0, "Should have 0 total vias"


def test_failed_net_no_wirelength():
    """Failed nets should not contribute to average wirelength."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
        create_test_net("NET3", [(0, 10), (10, 0)]),
    ]

    # Only NET1 succeeded
    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
        RoutingAttempt("NET2", False, None, 0),
        RoutingAttempt("NET3", False, None, 0),
    ]

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # Only NET1's wirelength (20) / 1 routed = 20.0
    assert result.average_wirelength == 20.0, (
        f"Expected avg wirelength 20.0, got {result.average_wirelength}"
    )

    # Completion: 1/3 = 33.33%
    assert result.completion_rate == pytest.approx(0.3333, rel=0.01), (
        f"Expected ~33.33% completion, got {result.completion_rate}"
    )

    # Should FAIL (< 95%)
    assert result.verdict == "FAIL", f"33% completion should FAIL, got {result.verdict}"


def test_missing_net_attempt():
    """If a net has no routing attempt, count as failed."""
    nets = [
        create_test_net("NET1", [(0, 0), (10, 10)]),
        create_test_net("NET2", [(5, 5), (15, 5)]),
    ]

    # NET2 missing from attempts
    attempts = [
        RoutingAttempt("NET1", True, 20.0, 0),
    ]

    from temper_validation.comparison.routing_feasibility import evaluate_routing_feasibility

    result = evaluate_routing_feasibility(nets, attempts)

    # NET2 counted as failed
    assert result.total_nets == 2, "Should have 2 total nets"
    assert result.routed_nets == 1, "Should have 1 routed net"
    assert result.failed_nets == 1, "Should have 1 failed net (missing)"
    assert result.completion_rate == 0.5, f"Expected 50% completion, got {result.completion_rate}"
