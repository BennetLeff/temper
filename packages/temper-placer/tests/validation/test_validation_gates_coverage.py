"""Tests for validation.validation_gates module."""

from temper_placer.validation.validation_gates import (
    GateResult,
    GateStatus,
    ValidationGatesResult,
)


class TestGateResult:
    """Tests for GateResult."""

    def test_passed_true(self):
        gr = GateResult(gate_name="test", status=GateStatus.PASS)
        assert gr.passed is True

    def test_passed_false(self):
        gr = GateResult(gate_name="test", status=GateStatus.FAIL)
        assert gr.passed is False

    def test_passed_skip(self):
        gr = GateResult(gate_name="test", status=GateStatus.SKIP)
        assert gr.passed is False

    def test_create_with_all_fields(self):
        gr = GateResult(
            gate_name="placement_complete",
            status=GateStatus.FAIL,
            message="Overlaps found",
            required_metrics=["overlap_count", "boundary_violations"],
            failed_metrics={"overlap_count": 3.0},
            elapsed_ms=15.0,
        )
        assert gr.gate_name == "placement_complete"
        assert gr.message == "Overlaps found"
        assert gr.required_metrics == ["overlap_count", "boundary_violations"]
        assert gr.failed_metrics == {"overlap_count": 3.0}
        assert gr.elapsed_ms == 15.0


class TestValidationGatesResult:
    """Tests for ValidationGatesResult."""

    def test_all_passed_true(self):
        result = ValidationGatesResult(
            placement_complete=GateResult(gate_name="pc", status=GateStatus.PASS),
            routing_complete=GateResult(gate_name="rc", status=GateStatus.PASS),
            production_ready=GateResult(gate_name="pr", status=GateStatus.PASS),
            validated=GateResult(gate_name="v", status=GateStatus.PASS),
        )
        assert result.all_passed is True

    def test_all_passed_one_fail(self):
        result = ValidationGatesResult(
            placement_complete=GateResult(gate_name="pc", status=GateStatus.PASS),
            routing_complete=GateResult(gate_name="rc", status=GateStatus.FAIL),
            production_ready=GateResult(gate_name="pr", status=GateStatus.PASS),
            validated=GateResult(gate_name="v", status=GateStatus.PASS),
        )
        assert result.all_passed is False

    def test_all_passed_one_none(self):
        """A None gate means not run, should fail-closed."""
        result = ValidationGatesResult(
            placement_complete=GateResult(gate_name="pc", status=GateStatus.PASS),
            routing_complete=GateResult(gate_name="rc", status=GateStatus.PASS),
            production_ready=None,
            validated=GateResult(gate_name="v", status=GateStatus.PASS),
        )
        assert result.all_passed is False

    def test_all_passed_all_none(self):
        """All-None means nothing run, should fail."""
        result = ValidationGatesResult()
        assert result.all_passed is False

    def test_summary(self):
        result = ValidationGatesResult(
            placement_complete=GateResult(gate_name="pc", status=GateStatus.PASS),
            routing_complete=GateResult(gate_name="rc", status=GateStatus.FAIL,
                                        message="Not routed"),
            production_ready=None,
            validated=GateResult(gate_name="v", status=GateStatus.PASS),
        )
        s = result.summary()
        assert "Validation Gates" in s


class TestGateStatus:
    """Enum smoke tests."""

    def test_values(self):
        assert GateStatus.PASS.value == "pass"
        assert GateStatus.FAIL.value == "fail"
        assert GateStatus.SKIP.value == "skip"
        assert GateStatus.PENDING.value == "pending"
