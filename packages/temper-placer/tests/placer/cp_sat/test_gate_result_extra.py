"""Tests for uncovered acceptance-gate methods.

Covers GateResult.accepted and GateResult.disagreement_signal from gate.py.
"""

from temper_placer.placer.cp_sat.gate import GateResult


class TestGateResult:
    """Test GateResult dataclass from gate.py (two-tier acceptance)."""

    def test_accepted_when_both_pass(self):
        result = GateResult(inner_passed=True, truth_passed=True)
        assert result.accepted is True

    def test_not_accepted_when_inner_fails(self):
        result = GateResult(inner_passed=False, truth_passed=True)
        assert result.accepted is False

    def test_not_accepted_when_truth_fails(self):
        result = GateResult(inner_passed=True, truth_passed=False)
        assert result.accepted is False

    def test_not_accepted_when_truth_not_run(self):
        result = GateResult(inner_passed=True, truth_passed=None)
        assert result.accepted is False

    def test_disagreement_signal_true(self):
        result = GateResult(inner_passed=True, truth_passed=False)
        assert result.disagreement_signal is True

    def test_disagreement_signal_false_when_both_pass(self):
        result = GateResult(inner_passed=True, truth_passed=True)
        assert result.disagreement_signal is False

    def test_disagreement_signal_false_when_inner_fails(self):
        result = GateResult(inner_passed=False, truth_passed=False)
        assert result.disagreement_signal is False

    def test_disagreement_signal_false_when_truth_none(self):
        result = GateResult(inner_passed=True, truth_passed=None)
        assert result.disagreement_signal is False
