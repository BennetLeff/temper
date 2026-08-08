"""Tests for validation.base module."""

from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


class TestValidationResult:
    """Tests for ValidationResult methods and properties."""

    def test_default_counts(self):
        r = ValidationResult(valid=True)
        assert r.error_count == 0
        assert r.warning_count == 0
        assert r.critical_count == 0

    def test_error_count(self):
        r = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(severity=ValidationSeverity.ERROR, code="E001", message="test"),
                ValidationIssue(severity=ValidationSeverity.CRITICAL, code="C001", message="test"),
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W001", message="test"),
                ValidationIssue(severity=ValidationSeverity.INFO, code="I001", message="test"),
            ],
        )
        assert r.error_count == 2  # ERROR + CRITICAL
        assert r.warning_count == 1  # WARNING
        assert r.critical_count == 1  # CRITICAL only

    def test_critical_count_zero(self):
        r = ValidationResult(
            valid=True,
            issues=[
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W001", message="test"),
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W002", message="test"),
            ],
        )
        assert r.error_count == 0
        assert r.critical_count == 0
        assert r.warning_count == 2

    def test_merge(self):
        r1 = ValidationResult(
            valid=True,
            issues=[
                ValidationIssue(severity=ValidationSeverity.WARNING, code="W001", message="m1"),
            ],
            metrics={"a": 1.0},
            elapsed_ms=10.0,
            validator_name="val1",
        )
        r2 = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(severity=ValidationSeverity.ERROR, code="E001", message="m2"),
            ],
            metrics={"b": 2.0},
            elapsed_ms=20.0,
            validator_name="val2",
        )
        merged = r1.merge(r2)
        assert merged.valid is False  # AND of valid flags
        assert len(merged.issues) == 2
        assert merged.metrics == {"a": 1.0, "b": 2.0}
        assert merged.elapsed_ms == 30.0
        assert merged.validator_name == "val1+val2"

    def test_merge_both_valid(self):
        r1 = ValidationResult(valid=True, validator_name="v1")
        r2 = ValidationResult(valid=True, validator_name="v2")
        merged = r1.merge(r2)
        assert merged.valid is True

    def test_summary_pass(self):
        r = ValidationResult(valid=True, validator_name="test")
        s = r.summary()
        assert "PASS" in s

    def test_summary_fail(self):
        r = ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(severity=ValidationSeverity.CRITICAL, code="C001", message="fail"),
            ],
            validator_name="test",
        )
        s = r.summary()
        assert "FAIL" in s
        assert "1 critical" in s


class TestValidationIssue:
    """Smoke test for ValidationIssue."""

    def test_create(self):
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="OVERLAP_001",
            message="Components overlap",
            component_refs=["U1", "U2"],
            location=(10.0, 20.0),
            details={"overlap_mm": 0.5},
        )
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.code == "OVERLAP_001"
        assert issue.message == "Components overlap"
        assert issue.component_refs == ["U1", "U2"]
        assert issue.location == (10.0, 20.0)
        assert issue.details == {"overlap_mm": 0.5}


class TestValidationSeverity:
    """Enum smoke tests."""

    def test_values(self):
        severities = list(ValidationSeverity)
        assert ValidationSeverity.INFO in severities
        assert ValidationSeverity.WARNING in severities
        assert ValidationSeverity.ERROR in severities
        assert ValidationSeverity.CRITICAL in severities
