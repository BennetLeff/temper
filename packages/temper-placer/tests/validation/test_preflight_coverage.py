"""Tests for validation.preflight module — PreflightResult."""
from temper_placer.validation.preflight import (
    PreflightIssue,
    PreflightResult,
    PreflightSeverity,
)


class TestPreflightResult:
    """Tests for PreflightResult properties and merge."""

    def test_defaults(self):
        r = PreflightResult(passed=True)
        assert r.passed is True
        assert r.issues == []
        assert r.error_count == 0
        assert r.warning_count == 0
        assert r.info_count == 0

    def test_error_count(self):
        r = PreflightResult(
            passed=False,
            issues=[
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="err"),
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E2", message="err2"),
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="warn"),
                PreflightIssue(severity=PreflightSeverity.INFO, code="I1", message="info"),
            ],
        )
        assert r.error_count == 2
        assert r.warning_count == 1
        assert r.info_count == 1

    def test_warning_count(self):
        r = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="w"),
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W2", message="w2"),
            ],
        )
        assert r.warning_count == 2
        assert r.error_count == 0
        assert r.info_count == 0

    def test_info_count(self):
        r = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.INFO, code="I1", message="info"),
                PreflightIssue(severity=PreflightSeverity.INFO, code="I2", message="info2"),
                PreflightIssue(severity=PreflightSeverity.INFO, code="I3", message="info3"),
            ],
        )
        assert r.info_count == 3
        assert r.error_count == 0

    def test_merge(self):
        r1 = PreflightResult(
            passed=True,
            issues=[PreflightIssue(severity=PreflightSeverity.INFO, code="I1", message="m1")],
        )
        r2 = PreflightResult(
            passed=False,
            issues=[PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="m2")],
        )
        merged = r1.merge(r2)
        assert merged.passed is False  # AND of passed flags
        assert len(merged.issues) == 2
        assert merged.error_count == 1
        assert merged.info_count == 1

    def test_merge_both_passed(self):
        r1 = PreflightResult(passed=True, issues=[])
        r2 = PreflightResult(passed=True, issues=[])
        merged = r1.merge(r2)
        assert merged.passed is True
