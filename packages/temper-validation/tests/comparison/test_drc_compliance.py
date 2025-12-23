"""Tests for DRC compliance scoring module."""

import pytest
from dataclasses import dataclass
from typing import NamedTuple

# Import real data structures from implementation
from temper_validation.comparison.drc_compliance import (
    ViolationSeverity,
    DRCViolation,
    DRCResult,
    DRCComplianceResult,
)


def create_test_violation(
    violation_id: str,
    severity: ViolationSeverity,
    description: str = "Test violation",
    component: str | None = None,
) -> DRCViolation:
    """Helper to create test violation."""
    return DRCViolation(
        violation_id=violation_id, severity=severity, description=description, component=component
    )


def test_drc_score_calculation():
    """Calculate DRC score from violations (error=-20, warning=-5)."""
    # Setup: 1 error, 2 warnings
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR, "Clearance violation"),
        create_test_violation("V002", ViolationSeverity.WARNING, "Text off grid"),
        create_test_violation("V003", ViolationSeverity.WARNING, "Track too close to edge"),
    ]

    # Expected: 100 - (1 * 20) - (2 * 5) = 70
    expected_score = 70.0

    # This will FAIL until we implement calculate_drc_score
    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    assert score == expected_score, f"Expected score {expected_score}, got {score}"


def test_drc_verdict_threshold():
    """Verdict PASS if score >= 80, FAIL otherwise."""
    from temper_validation.comparison.drc_compliance import get_drc_verdict

    # Case 1: score = 85 (should PASS)
    score_1 = 85.0
    verdict_1 = get_drc_verdict(score_1)
    assert verdict_1 == "PASS", f"Score 85 should PASS, got {verdict_1}"

    # Case 2: score = 75 (should FAIL)
    score_2 = 75.0
    verdict_2 = get_drc_verdict(score_2)
    assert verdict_2 == "FAIL", f"Score 75 should FAIL, got {verdict_2}"

    # Case 3: score = 80 (edge case, should PASS)
    score_3 = 80.0
    verdict_3 = get_drc_verdict(score_3)
    assert verdict_3 == "PASS", f"Score 80 (edge) should PASS, got {verdict_3}"


def test_drc_violation_categorization():
    """Classify violations as error vs warning."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR),
        create_test_violation("V002", ViolationSeverity.WARNING),
        create_test_violation("V003", ViolationSeverity.ERROR),
        create_test_violation("V004", ViolationSeverity.WARNING),
        create_test_violation("V005", ViolationSeverity.WARNING),
    ]

    # This will FAIL until we implement categorize_violations
    from temper_validation.comparison.drc_compliance import categorize_violations

    critical_count, warning_count = categorize_violations(violations)

    assert critical_count == 2, f"Expected 2 critical violations, got {critical_count}"
    assert warning_count == 3, f"Expected 3 warning violations, got {warning_count}"


def test_empty_violations_score_100():
    """No violations should result in perfect score."""
    violations = []

    # Expected: 100 - (0 * 20) - (0 * 5) = 100
    expected_score = 100.0

    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    assert score == expected_score, f"Expected perfect score {expected_score}, got {score}"


def test_drc_compliance_result_structure():
    """DRC compliance result contains all required fields."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR),
        create_test_violation("V002", ViolationSeverity.WARNING),
    ]

    from temper_validation.comparison.drc_compliance import evaluate_drc_compliance

    result = evaluate_drc_compliance(violations)

    # Check all required fields
    assert hasattr(result, "score"), "Result should have 'score' field"
    assert hasattr(result, "max_score"), "Result should have 'max_score' field"
    assert hasattr(result, "critical_violations"), "Result should have 'critical_violations' field"
    assert hasattr(result, "warning_violations"), "Result should have 'warning_violations' field"
    assert hasattr(result, "verdict"), "Result should have 'verdict' field"

    # Check types
    assert isinstance(result.score, float), "score should be float"
    assert isinstance(result.max_score, float), "max_score should be float"
    assert isinstance(result.critical_violations, int), "critical_violations should be int"
    assert isinstance(result.warning_violations, int), "warning_violations should be int"
    assert isinstance(result.verdict, str), "verdict should be str"

    # Check reasonable values
    assert 0.0 <= result.score <= 100.0, "score should be between 0 and 100"
    assert result.max_score == 100.0, "max_score should be 100"
    assert result.critical_violations >= 0, "critical_violations should be non-negative"
    assert result.warning_violations >= 0, "warning_violations should be non-negative"
    assert result.verdict in ["PASS", "FAIL"], "verdict should be PASS or FAIL"


def test_kicad_drc_integration():
    """Run KiCad DRC and parse output (integration test)."""
    from unittest.mock import patch, MagicMock

    # Mock KiCad DRC subprocess call
    mock_drc_output = """
** Drc report for board: /tmp/test.kicad_pcb
** Created on 2024-12-23 13:00:00

** 1 error(s)
** 2 warning(s)

Erreur: Clearance violation (20mil < 25mil)
    @ (10.0, 20.0) on Net1

Warning: Text off grid
    @ (15.5, 10.3) on silkscreen

Warning: Track too close to edge
    @ (5.0, 2.0) on Edge.Cuts

** End of report
"""

    with patch("temper_validation.comparison.drc_compliance.subprocess.run") as mock_run:
        mock_process = MagicMock()
        mock_process.stdout = mock_drc_output
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        from temper_validation.comparison.drc_compliance import run_kicad_drc

        result = run_kicad_drc("/tmp/test.kicad_pcb", "/path/to/kicad")

        # Verify DRC was called
        mock_run.assert_called_once()

        # Verify basic structure
        assert isinstance(result, DRCResult), "Should return DRCResult"
        assert isinstance(result.violations, list), "violations should be a list"

        # Verify violations were parsed (mock has 1 error + 2 warnings)
        assert len(result.violations) == 3, f"Expected 3 violations, got {len(result.violations)}"

        # Verify run_time was recorded
        assert result.run_time_seconds > 0, "run_time_seconds should be positive"


def test_multiple_critical_violations():
    """Handle multiple critical violations correctly."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR, "Clearance"),
        create_test_violation("V002", ViolationSeverity.ERROR, "Short circuit"),
        create_test_violation("V003", ViolationSeverity.ERROR, "Unrouted net"),
        create_test_violation("V004", ViolationSeverity.WARNING, "Text placement"),
    ]

    from temper_validation.comparison.drc_compliance import evaluate_drc_compliance

    result = evaluate_drc_compliance(violations)

    # Score: 100 - (3 * 20) - (1 * 5) = 35
    assert result.score == 35.0, f"Expected score 35.0, got {result.score}"

    # Should FAIL with only 35 points
    assert result.verdict == "FAIL", f"Score {result.score} should FAIL, got {result.verdict}"

    assert result.critical_violations == 3, (
        f"Expected 3 critical violations, got {result.critical_violations}"
    )

    assert result.warning_violations == 1, (
        f"Expected 1 warning violation, got {result.warning_violations}"
    )


def test_score_never_negative():
    """DRC score should be clamped at 0 (never negative)."""
    # Create many violations to drive score below 0
    violations = [
        create_test_violation(f"V{i:03d}", ViolationSeverity.ERROR)
        for i in range(10)  # 10 * 20 = -200 points
    ]

    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    # Should be clamped at 0, not negative
    assert score == 0.0, f"Score should be clamped at 0.0, got {score}"


def test_drc_score_calculation():
    """Calculate DRC score from violations (error=-20, warning=-5)."""
    # Setup: 1 error, 2 warnings
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR, "Clearance violation"),
        create_test_violation("V002", ViolationSeverity.WARNING, "Text off grid"),
        create_test_violation("V003", ViolationSeverity.WARNING, "Track too close to edge"),
    ]

    # Expected: 100 - (1 * 20) - (2 * 5) = 70
    expected_score = 70.0

    # This will FAIL until we implement calculate_drc_score
    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    assert score == expected_score, f"Expected score {expected_score}, got {score}"


def test_drc_verdict_threshold():
    """Verdict PASS if score >= 80, FAIL otherwise."""
    from temper_validation.comparison.drc_compliance import get_drc_verdict

    # Case 1: score = 85 (should PASS)
    score_1 = 85.0
    verdict_1 = get_drc_verdict(score_1)
    assert verdict_1 == "PASS", f"Score 85 should PASS, got {verdict_1}"

    # Case 2: score = 75 (should FAIL)
    score_2 = 75.0
    verdict_2 = get_drc_verdict(score_2)
    assert verdict_2 == "FAIL", f"Score 75 should FAIL, got {verdict_2}"

    # Case 3: score = 80 (edge case, should PASS)
    score_3 = 80.0
    verdict_3 = get_drc_verdict(score_3)
    assert verdict_3 == "PASS", f"Score 80 (edge) should PASS, got {verdict_3}"


def test_drc_violation_categorization():
    """Classify violations as error vs warning."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR),
        create_test_violation("V002", ViolationSeverity.WARNING),
        create_test_violation("V003", ViolationSeverity.ERROR),
        create_test_violation("V004", ViolationSeverity.WARNING),
        create_test_violation("V005", ViolationSeverity.WARNING),
    ]

    # This will FAIL until we implement categorize_violations
    from temper_validation.comparison.drc_compliance import categorize_violations

    critical_count, warning_count = categorize_violations(violations)

    assert critical_count == 2, f"Expected 2 critical violations, got {critical_count}"
    assert warning_count == 3, f"Expected 3 warning violations, got {warning_count}"


def test_empty_violations_score_100():
    """No violations should result in perfect score."""
    violations = []

    # Expected: 100 - (0 * 20) - (0 * 5) = 100
    expected_score = 100.0

    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    assert score == expected_score, f"Expected perfect score {expected_score}, got {score}"


def test_drc_compliance_result_structure():
    """DRC compliance result contains all required fields."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR),
        create_test_violation("V002", ViolationSeverity.WARNING),
    ]

    from temper_validation.comparison.drc_compliance import evaluate_drc_compliance

    result = evaluate_drc_compliance(violations)

    # Check all required fields
    assert hasattr(result, "score"), "Result should have 'score' field"
    assert hasattr(result, "max_score"), "Result should have 'max_score' field"
    assert hasattr(result, "critical_violations"), "Result should have 'critical_violations' field"
    assert hasattr(result, "warning_violations"), "Result should have 'warning_violations' field"
    assert hasattr(result, "verdict"), "Result should have 'verdict' field"

    # Check types
    assert isinstance(result.score, float), "score should be float"
    assert isinstance(result.max_score, float), "max_score should be float"
    assert isinstance(result.critical_violations, int), "critical_violations should be int"
    assert isinstance(result.warning_violations, int), "warning_violations should be int"
    assert isinstance(result.verdict, str), "verdict should be str"

    # Check reasonable values
    assert 0.0 <= result.score <= 100.0, "score should be between 0 and 100"
    assert result.max_score == 100.0, "max_score should be 100"
    assert result.critical_violations >= 0, "critical_violations should be non-negative"
    assert result.warning_violations >= 0, "warning_violations should be non-negative"
    assert result.verdict in ["PASS", "FAIL"], "verdict should be PASS or FAIL"


def test_kicad_drc_integration():
    """Run KiCad DRC and parse output (integration test)."""
    from unittest.mock import patch, MagicMock

    # Mock KiCad DRC subprocess call
    mock_drc_output = """
** Drc report for board: /tmp/test.kicad_pcb
** Created on 2024-12-23 13:00:00

** 1 error(s)
** 2 warning(s)

Erreur: Clearance violation (20mil < 25mil)
    @ (10.0, 20.0) on Net1

Warning: Text off grid
    @ (15.5, 10.3) on silkscreen

Warning: Track too close to edge
    @ (5.0, 2.0) on Edge.Cuts

** End of report
"""

    with patch("temper_validation.comparison.drc_compliance.subprocess.run") as mock_run:
        mock_process = MagicMock()
        mock_process.stdout = mock_drc_output
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        from temper_validation.comparison.drc_compliance import run_kicad_drc

        result = run_kicad_drc("/tmp/test.kicad_pcb", "/path/to/kicad")

        # Verify DRC was called
        mock_run.assert_called_once()

        # Verify basic structure
        assert isinstance(result, DRCResult), "Should return DRCResult"
        assert isinstance(result.violations, list), "violations should be a list"

        # Verify violations were parsed (mock has 1 error + 2 warnings)
        assert len(result.violations) == 3, f"Expected 3 violations, got {len(result.violations)}"

        # Verify run_time was recorded
        assert result.run_time_seconds > 0, "run_time_seconds should be positive"


def test_multiple_critical_violations():
    """Handle multiple critical violations correctly."""
    violations = [
        create_test_violation("V001", ViolationSeverity.ERROR, "Clearance"),
        create_test_violation("V002", ViolationSeverity.ERROR, "Short circuit"),
        create_test_violation("V003", ViolationSeverity.ERROR, "Unrouted net"),
        create_test_violation("V004", ViolationSeverity.WARNING, "Text placement"),
    ]

    from temper_validation.comparison.drc_compliance import evaluate_drc_compliance

    result = evaluate_drc_compliance(violations)

    # Score: 100 - (3 * 20) - (1 * 5) = 35
    assert result.score == 35.0, f"Expected score 35.0, got {result.score}"

    # Should FAIL with only 35 points
    assert result.verdict == "FAIL", f"Score {result.score} should FAIL, got {result.verdict}"

    assert result.critical_violations == 3, (
        f"Expected 3 critical violations, got {result.critical_violations}"
    )

    assert result.warning_violations == 1, (
        f"Expected 1 warning violation, got {result.warning_violations}"
    )


def test_score_never_negative():
    """DRC score should be clamped at 0 (never negative)."""
    # Create many violations to drive score below 0
    violations = [
        create_test_violation(f"V{i:03d}", ViolationSeverity.ERROR)
        for i in range(10)  # 10 * 20 = -200 points
    ]

    from temper_validation.comparison.drc_compliance import calculate_drc_score

    score = calculate_drc_score(violations)

    # Should be clamped at 0, not negative
    assert score == 0.0, f"Score should be clamped at 0.0, got {score}"
