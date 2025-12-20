"""Tests for severity module."""


from temper_drc.core.severity import Severity


class TestSeverity:
    """Test Severity enum."""

    def test_severity_weights(self):
        """Verify severity weights are correct."""
        assert Severity.INFO.weight == 0.0
        assert Severity.WARNING.weight == 1.0
        assert Severity.ERROR.weight == 10.0
        assert Severity.CRITICAL.weight == 100.0

    def test_is_failure(self):
        """Test is_failure property."""
        assert not Severity.INFO.is_failure
        assert not Severity.WARNING.is_failure
        assert Severity.ERROR.is_failure
        assert Severity.CRITICAL.is_failure

    def test_severity_comparison(self):
        """Test severity ordering."""
        assert Severity.INFO < Severity.WARNING
        assert Severity.WARNING < Severity.ERROR
        assert Severity.ERROR < Severity.CRITICAL
        assert Severity.INFO <= Severity.INFO
        assert not Severity.ERROR < Severity.WARNING
