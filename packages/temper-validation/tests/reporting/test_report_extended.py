"""Tests for report generator module - Additional coverage."""

import pytest
from dataclasses import dataclass
from pathlib import Path
import tempfile
import os

# Import real data structures from implementation
from temper_validation.comparison.wirelength import WirelengthResult
from temper_validation.comparison.drc_compliance import DRCComplianceResult
from temper_validation.comparison.routing_feasibility import RoutingFeasibilityResult
from temper_validation.metrics.quality_score import AggregateScoreResult


def test_custom_report_config():
    """Custom report configuration should be applied."""
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

    aggregate_result = AggregateScoreResult(
        total_score=90.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=85.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import ReportConfig

    config = ReportConfig(
        title="Custom Validation Report", author="Validation System", show_timestamp=False
    )

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
            config=config,
        )

        with open(report_path, "r") as f:
            content = f.read()

        assert config.title in content, "Report should contain custom title"
        assert config.author in content, "Report should contain custom author"
        assert "Generated:" not in content, (
            "Report should not contain timestamp (show_timestamp=False)"
        )

        os.unlink(report_path)


def test_score_boundary_conditions():
    """Test edge cases for scoring thresholds."""
    from temper_validation.metrics.quality_score import (
        normalize_wirelength_ratio,
        normalize_routing_completion,
        get_drc_verdict,
        get_routing_verdict,
    )

    # Test wirelength normalization boundaries
    assert normalize_wirelength_ratio(0.5) == 100.0, "50% better should cap at 100"
    assert normalize_wirelength_ratio(1.0) == 100.0, "Perfect ratio should be 100"
    assert normalize_wirelength_ratio(1.1) == pytest.approx(90.9, rel=0.01), (
        "10% worse should be ~90.9"
    )

    # Test routing completion boundaries
    assert normalize_routing_completion(0.95) == 95.0, "95% completion should be 95.0 score"
    assert normalize_routing_completion(1.0) == 100.0, "100% completion should be 100.0 score"
    assert normalize_routing_completion(0.0) == 0.0, "0% completion should be 0.0 score"

    # Test DRC verdict thresholds
    assert get_drc_verdict(80.0) == "PASS", "80.0 should be PASS (edge case)"
    assert get_drc_verdict(79.9) == "FAIL", "79.9 should be FAIL (edge case)"
    assert get_drc_verdict(81.0) == "PASS", "81.0 should be PASS"

    # Test routing verdict thresholds
    assert get_routing_verdict(0.95) == "PASS", "95% should be PASS (edge case)"
    assert get_routing_verdict(0.949) == "FAIL", "94.9% should be FAIL (edge case)"
    assert get_routing_verdict(1.0) == "PASS", "100% should be PASS"


def test_weight_normalization_edge_cases():
    """Test weight normalization edge cases."""
    from temper_validation.metrics.quality_score import normalize_weights

    # Test normalization with zero weights
    wl, drc, rt = normalize_weights(0.0, 0.0, 0.0)
    assert wl == 0.3333333333333333, "Zero weights should default to equal distribution"

    # Test normalization with single non-zero weight
    wl, drc, rt = normalize_weights(1.0, 0.0, 0.0)
    assert wl == 1.0 and drc == 0.0 and rt == 0.0, "Single weight should get full value"

    # Test normalization that sums to > 1.0
    wl, drc, rt = normalize_weights(2.0, 2.0, 2.0)
    assert pytest.approx(wl + drc + rt, rel=0.01) == 1.0, "Weights should normalize to sum to 1.0"
    assert wl == pytest.approx(0.3333, rel=0.01), "Equal weights should be ~0.3333"


def test_markdown_report_all_verdict_pass():
    """Markdown report with all PASS verdicts should highlight success."""
    wirelength_result = WirelengthResult(
        optimized=95.0, reference=100.0, ratio=0.95, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=90.0, max_score=100.0, critical_violations=0, warning_violations=0, verdict="PASS"
    )

    routing_result = RoutingFeasibilityResult(
        total_nets=10,
        routed_nets=10,
        failed_nets=0,
        completion_rate=1.0,
        average_wirelength=45.0,
        total_vias=0,
        verdict="PASS",
    )

    aggregate_result = AggregateScoreResult(
        total_score=95.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=90.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Count PASS occurrences
        pass_count = content.count("**PASS**")
        fail_count = content.count("**FAIL**")

        assert pass_count >= 4, f"Should have 4+ PASS verdicts, got {pass_count}"
        assert fail_count == 0, f"Should have 0 FAIL verdicts, got {fail_count}"

        os.unlink(report_path)


def test_markdown_report_all_verdict_fail():
    """Markdown report with all FAIL verdicts should highlight failures."""
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

    aggregate_result = AggregateScoreResult(
        total_score=60.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=83.3,
        drc_score=50.0,
        routing_score=50.0,
        verdict="FAIL",
    )

    from temper_validation.reporting.report import generate_markdown_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
        report_path = Path(f.name)
        generate_markdown_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Count FAIL occurrences
        fail_count = content.count("**FAIL**")
        pass_count = content.count("**PASS**")

        assert fail_count >= 4, f"Should have 4+ FAIL verdicts, got {fail_count}"

        os.unlink(report_path)


def test_html_report_complete_document():
    """HTML report should be complete and well-formed."""
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=95.0, max_score=100.0, critical_violations=0, warning_violations=1, verdict="PASS"
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

    aggregate_result = AggregateScoreResult(
        total_score=95.0,
        max_score=100.0,
        wirelength_weight=0.3,
        drc_weight=0.4,
        routing_weight=0.3,
        wirelength_score=100.0,
        drc_score=95.0,
        routing_score=100.0,
        verdict="PASS",
    )

    from temper_validation.reporting.report import generate_html_report

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        report_path = Path(f.name)
        generate_html_report(
            report_path=report_path,
            optimized_path="optimized.kicad_pcb",
            reference_path="reference.kicad_pcb",
            wirelength_result=wirelength_result,
            drc_result=drc_result,
            routing_result=routing_result,
            aggregate_result=aggregate_result,
        )

        with open(report_path, "r") as f:
            content = f.read()

        # Check for required HTML elements
        assert "<!doctype" in content.lower(), "Should have DOCTYPE declaration"
        assert "<html" in content.lower(), "Should have html element"
        assert "</html>" in content.lower(), "Should have closing html tag"
        assert "<head>" in content.lower(), "Should have head section"
        assert "</head>" in content.lower(), "Should close head section"
        assert "<body>" in content.lower(), "Should have body section"
        assert "</body>" in content.lower(), "Should close body section"
        assert "<style>" in content.lower(), "Should have embedded CSS"
        assert "</style>" in content.lower(), "Should close style tag"

        os.unlink(report_path)


def test_score_calculation_with_extreme_ratios():
    """Test quality score calculation with extreme wirelength ratios."""
    from temper_validation.metrics.quality_score import calculate_aggregate_score

    # Perfect case
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

    # Create mock RoutingResult for aggregate calculation
    class MockRoutingResult:
        pass

    mock_routing_result = MockRoutingResult()
    mock_routing_result.__dict__.update(
        {
            "total_nets": 10,
            "routed_nets": 10,
            "failed_nets": 0,
            "completion_rate": 1.0,
            "average_wirelength": 50.0,
            "total_vias": 0,
            "verdict": "PASS",
        }
    )

    result = calculate_aggregate_score(wirelength_result, drc_result, mock_routing_result)

    assert result.total_score == 100.0, "All perfect should give 100.0 score"
    assert result.verdict == "PASS", "Perfect score should PASS"

    # All failure case
    wirelength_result_bad = WirelengthResult(
        optimized=200.0, reference=100.0, ratio=2.0, margin=0.1, verdict="FAIL"
    )

    drc_result_bad = DRCComplianceResult(
        score=40.0, max_score=100.0, critical_violations=3, warning_violations=4, verdict="FAIL"
    )

    result_bad = calculate_aggregate_score(
        wirelength_result_bad, drc_result_bad, mock_routing_result
    )

    assert result_bad.total_score < 70.0, "All bad should give low score (<70)"
    assert result_bad.verdict == "FAIL", "Low score should FAIL"


def test_drc_score_with_violation_thresholds():
    """Test DRC score calculation at key thresholds."""
    from temper_validation.comparison.drc_compliance import (
        calculate_drc_score,
        DRCViolation,
        ViolationSeverity,
    )

    # Test score calculation at key points
    test_cases = [
        # (errors, warnings, expected_score)
        (0, 0, 100.0),  # Perfect
        (1, 0, 80.0),  # 1 error (80)
        (0, 4, 80.0),  # 4 warnings (80)
        (2, 0, 60.0),  # 2 errors
        (1, 2, 70.0),  # 1 error + 2 warnings
        (5, 0, 0.0),  # 5 errors = 100, clamped at 0
        (0, 20, 0.0),  # 20 warnings = 100, clamped at 0
    ]

    for errors, warnings, expected_score in test_cases:
        violations = []
        for _ in range(errors):
            violations.append(
                DRCViolation(
                    violation_id="V001",
                    severity=ViolationSeverity.ERROR,
                    description="Critical violation",
                )
            )
        for _ in range(warnings):
            violations.append(
                DRCViolation(
                    violation_id="V002",
                    severity=ViolationSeverity.WARNING,
                    description="Warning violation",
                )
            )

        score = calculate_drc_score(violations)
        assert score == expected_score, (
            f"Expected {expected_score} for {errors} errors, {warnings} warnings, got {score}"
        )


def test_aggregate_score_with_custom_weights():
    """Test aggregate score with non-standard weights."""
    from temper_validation.metrics.quality_score import calculate_aggregate_score

    # Create perfect results
    wirelength_result = WirelengthResult(
        optimized=100.0, reference=100.0, ratio=1.0, margin=0.1, verdict="PASS"
    )

    drc_result = DRCComplianceResult(
        score=100.0, max_score=100.0, critical_violations=0, warning_violations=0, verdict="PASS"
    )

    # Mock routing result
    class MockRoutingResult:
        pass

    mock_routing_result = MockRoutingResult()
    mock_routing_result.__dict__.update(
        {
            "total_nets": 10,
            "routed_nets": 10,
            "failed_nets": 0,
            "completion_rate": 1.0,
            "average_wirelength": 50.0,
            "total_vias": 0,
            "verdict": "PASS",
        }
    )

    # Test with custom weights (wirelength 50%, DRC 30%, routing 20%)
    custom_weights = {"wirelength": 0.5, "drc": 0.3, "routing": 0.2}

    result = calculate_aggregate_score(
        wirelength_result, drc_result, mock_routing_result, weights=custom_weights
    )

    # Expected: 100 * 0.5 + 100 * 0.3 + 100 * 0.2 = 50 + 30 + 20 = 100
    assert pytest.approx(result.total_score, rel=0.01) == 100.0, (
        f"Custom weights should give 100.0, got {result.total_score}"
    )
    assert result.wirelength_weight == 0.5, (
        f"Wirelength weight should be 0.5, got {result.wirelength_weight}"
    )
    assert result.drc_weight == 0.3, f"DRC weight should be 0.3, got {result.drc_weight}"
    assert result.routing_weight == 0.2, (
        f"Routing weight should be 0.2, got {result.routing_weight}"
    )
