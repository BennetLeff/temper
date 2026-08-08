"""Tests for preflight module."""

from temper_placer.pipeline.preflight import (
    PreflightCheck,
    PreflightReport,
    PreflightResult,
)


def test_preflight_report_passed_true():
    """PreflightReport with PASS overall returns passed=True."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.PASS,
        total_time_ms=10.0,
    )
    assert report.passed is True


def test_preflight_report_passed_warn():
    """PreflightReport with WARN overall returns passed=True (not FAIL)."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.WARN,
        total_time_ms=10.0,
    )
    assert report.passed is True


def test_preflight_report_passed_false():
    """PreflightReport with FAIL overall returns passed=False."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.FAIL,
        total_time_ms=10.0,
    )
    assert report.passed is False


def test_preflight_report_summary():
    """summary() returns a multi-line string with check results."""
    checks = [
        PreflightCheck(
            name="Layer Count",
            result=PreflightResult.PASS,
            message="4-layer stackup verified",
        ),
        PreflightCheck(
            name="Component Area",
            result=PreflightResult.WARN,
            message="Fill ratio 75.0%",
        ),
        PreflightCheck(
            name="Constraint Satisfiability",
            result=PreflightResult.FAIL,
            message="Found 2 issues",
        ),
    ]
    report = PreflightReport(
        checks=checks,
        overall=PreflightResult.FAIL,
        total_time_ms=42.0,
    )
    summary = report.summary()
    assert "Preflight Checks:" in summary
    assert "[OK]" in summary
    assert "[WARN]" in summary
    assert "[FAIL]" in summary
    assert "Layer Count" in summary
    assert "Component Area" in summary
    assert "Constraint Satisfiability" in summary
    assert "Overall: FAIL" in summary
    assert "42.0ms" in summary
