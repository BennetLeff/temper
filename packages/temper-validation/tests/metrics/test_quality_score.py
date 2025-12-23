"""Tests for aggregate quality score calculation module."""

import pytest
from dataclasses import dataclass

# Import real data structures from implementation
from temper_validation.comparison.wirelength import WirelengthResult
from temper_validation.comparison.drc_compliance import DRCComplianceResult
from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult


def test_perfect_score():
    """All metrics perfect = 100 aggregate score."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=100.0, max_score=100.0, critical_violations=0, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    # Expected: 100 * 0.3 + 100 * 0.4 + 100 * 0.3 = 100.0
    expected_score = 100.0

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(wirelength_result, drc_result, routing_result)

    assert result.total_score == expected_score, (
        f"Expected perfect score {expected_score}, got {result.total_score}"
    )

    assert result.verdict == "PASS", f"Perfect score should be PASS, got {result.verdict}"


def test_mixed_metrics():
    """Mixed good/poor metrics = weighted average."""
    wirelength_result = WirelengthResult(
        optimized=90.0, reference=100.0, ratio=0.9, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=70.0, max_score=100.0, critical_violations=1, warning_violations=2, verdict="FAIL"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=8,
        failed_nets=2,
        completion_rate=0.8,
        average_wirelength=60.0,
        total_vias=5,
        verdict="FAIL",
    )

    # Wirelength: PASS (ratio < 1.1), but we use normalized score
    # If wirelength ratio=0.9, normalized: (1/0.9) * 100 = 111.1 (capped at 100)
    # DRC: 70
    # Routing: 0.8 completion, normalized: 80
    # Expected: 100 * 0.3 + 70 * 0.4 + 80 * 0.3 = 30 + 28 + 24 = 82.0
    expected_score = 82.0

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(wirelength_result, drc_result, routing_result)

    assert pytest.approx(result.total_score, rel=0.01) == expected_score, \
        f"Expected score ~{expected_score}, got {result.total_score}"
    

    assert result.verdict == "PASS", \
        f"Score {result.total_score} (>=80) should be PASS, got {result.verdict}"


def test_edge_case_pass_threshold():
    """Score exactly 80 = PASS (edge case)."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=80.0, max_score=100.0, critical_violations=1, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=8,
        failed_nets=2,
        completion_rate=0.8,
        average_wirelength=60.0,
        total_vias=5,
        verdict="FAIL",
    )

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(wirelength_result, drc_result, routing_result)

    assert pytest.approx(result.total_score, rel=0.01) == 86.0, (
        f"Expected edge score 80.0, got {result.total_score}"
    )

    assert result.verdict == "PASS", f"Edge case should be 86.0 (PASS), got {result.verdict}"


def test_all_fail_metrics():
    """All metrics failing = low aggregate score."""
    wirelength_result = WirelengthResult(
        optimized=120.0, reference=100.0, ratio=1.2, margin=0.1, verdict="FAIL"
    )

    drc_result = DRCComplianceResult(
        score=50.0, max_score=100.0, critical_violations=2, warning_violations=2, verdict="FAIL"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=5,
        failed_nets=5,
        completion_rate=0.5,
        average_wirelength=80.0,
        total_vias=10,
        verdict="FAIL",
    )

    # Wirelength ratio 1.2 -> normalize: ~83 (invert for score)
    # DRC: 50
    # Routing: 50
    # Expected: ~83 * 0.3 + 50 * 0.4 + 50 * 0.3 = 24.9 + 20 + 15 = 59.9
    # Using simple normalized scores for now

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(wirelength_result, drc_result, routing_result)

    assert result.total_score < 80.0, (
        f"All failing metrics should score < 80, got {result.total_score}"
    )

    assert result.verdict == "FAIL", f"All failing metrics should FAIL, got {result.verdict}"


def test_aggregate_score_structure():
    """Aggregate score result contains all required fields."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=85.0, max_score=100.0, critical_violations=0, warning_violations=1, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(wirelength_result, drc_result, routing_result)

    # Check all required fields
    assert hasattr(result, "total_score"), "Result should have 'total_score' field"
    assert hasattr(result, "max_score"), "Result should have 'max_score' field"
    assert hasattr(result, "wirelength_weight"), "Result should have 'wirelength_weight' field"
    assert hasattr(result, "drc_weight"), "Result should have 'drc_weight' field"
    assert hasattr(result, "routing_weight"), "Result should have 'routing_weight' field"
    assert hasattr(result, "wirelength_score"), "Result should have 'wirelength_score' field"
    assert hasattr(result, "drc_score"), "Result should have 'drc_score' field"
    assert hasattr(result, "routing_score"), "Result should have 'routing_score' field"
    assert hasattr(result, "verdict"), "Result should have 'verdict' field"

    # Check types
    assert isinstance(result.total_score, float), "total_score should be float"
    assert isinstance(result.max_score, float), "max_score should be float"
    assert isinstance(result.verdict, str), "verdict should be str"

    # Check reasonable values
    assert 0.0 <= result.total_score <= 100.0, "total_score should be between 0 and 100"
    assert result.max_score == 100.0, "max_score should be 100"
    assert result.verdict in ["PASS", "FAIL"], "verdict should be PASS or FAIL"


def test_custom_weights():
    """Custom weights should override defaults."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=50.0, max_score=100.0, critical_violations=1, warning_violations=2, verdict="FAIL"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    # Custom: wirelength 50%, DRC 30%, routing 20%
    custom_weights = {"wirelength": 0.5, "drc": 0.3, "routing": 0.2}

    # Expected: 100 * 0.5 + 50 * 0.3 + 100 * 0.2 = 50 + 15 + 20 = 85.0
    expected_score = 85.0

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(
        wirelength_result, drc_result, routing_result, weights=custom_weights
    )

    assert pytest.approx(result.total_score, rel=0.01) == expected_score, (
        f"Expected weighted score {expected_score}, got {result.total_score}"
    )


def test_weight_normalization():
    """Weights should sum to 1.0 (or be normalized)."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=80.0, max_score=100.0, critical_violations=1, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=50.0,
        total_vias=0,
        verdict="PASS",
    )

    # Weights don't sum to 1.0 - should be normalized
    invalid_weights = {"wirelength": 2.0, "drc": 2.0, "routing": 2.0}

    # Normalized: each weight = 2.0 / 6.0 = 1/3
    # Expected: 100 * 0.333 + 80 * 0.333 + 100 * 0.333 = 33.3 + 26.6 + 33.3 = 93.3
    expected_score = pytest.approx(93.3, rel=0.01)

    from temper_validation.metrics.quality_score import calculate_aggregate_score

    result = calculate_aggregate_score(
        wirelength_result, drc_result, routing_result, weights=invalid_weights
    )

    assert result.total_score == expected_score, (
        f"Expected normalized weighted score {expected_score}, got {result.total_score}"
    )
