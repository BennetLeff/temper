"""Tests for validation.scorecard module."""

from temper_placer.validation.scorecard import (
    GateMargin,
    IndependenceViolationError,
    _assert_independent,
)


class TestGateMargin:
    """Tests for GateMargin."""

    def test_create(self):
        gm = GateMargin(
            gate_name="thermal_headroom",
            value=15.0,
            unit="C",
            raw_score=0.85,
        )
        assert gm.gate_name == "thermal_headroom"
        assert gm.value == 15.0
        assert gm.unit == "C"
        assert gm.raw_score == 0.85
        assert gm.is_scorable is True

    def test_margin_alias(self):
        gm = GateMargin(gate_name="test", value=42.0, unit="mm")
        assert gm.margin == 42.0

    def test_defaults(self):
        gm = GateMargin(gate_name="test", value=0.0, unit="")
        assert gm.raw_score == 0.0
        assert gm.is_scorable is True


class TestIndependenceGuard:
    """Tests for the independence assertion."""

    def test_different_ids_pass(self):
        _assert_independent("field_solver_A", "scorer_B")

    def test_same_ids_raise(self):
        import pytest
        with pytest.raises(IndependenceViolationError, match="Independence violation"):
            _assert_independent("solver_X", "solver_X")
