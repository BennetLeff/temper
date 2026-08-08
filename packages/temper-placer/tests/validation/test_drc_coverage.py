"""Tests for validation.drc module (contract types)."""

from temper_placer.validation.drc import (
    DRCResult,
    DRCViolation,
    DRCSeverity,
    DRCViolationType,
)


class TestDRCSeverity:
    """Enum smoke tests."""

    def test_values(self):
        assert DRCSeverity.ERROR.value == "error"
        assert DRCSeverity.WARNING.value == "warning"


class TestDRCViolationType:
    """Enum smoke tests."""

    def test_has_clearance(self):
        assert DRCViolationType.CLEARANCE.value == "clearance"

    def test_has_unconnected(self):
        assert DRCViolationType.UNCONNECTED_ITEMS.value == "unconnected_items"


class TestDRCResult:
    """Tests for DRCResult contract type."""

    def test_default_construction(self):
        r = DRCResult(success=True)
        assert r.violations == []
        assert r.success is True

    def test_total_violations(self):
        r = DRCResult(success=True, error_count=3, warning_count=2)
        assert r.total_violations == 5

    def test_summary(self):
        r = DRCResult(success=True)
        s = r.summary()
        assert isinstance(s, str)

    def test_has_errors(self):
        r = DRCResult(success=True, error_count=0)
        assert r.has_errors is False

    def test_has_errors_with_errors(self):
        r = DRCResult(success=False, error_count=2)
        assert r.has_errors is True


class TestDRCViolation:
    """Tests for DRCViolation contract type."""

    def test_to_dict(self):
        v = DRCViolation(
            severity=DRCSeverity.ERROR,
            code="CLEARANCE_001",
            message="Clearance violation",
            violation_type=DRCViolationType.CLEARANCE,
        )
        d = v.to_dict()
        assert isinstance(d, dict)

