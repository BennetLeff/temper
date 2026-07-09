"""Unit tests for the two-tier acceptance gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

from temper_placer.placer.cp_sat.gate import AcceptanceGate, GateResult


@dataclass
class _FakeDrcError:
    rule: str = "clearance"
    severity: str = "error"
    location: tuple[float, float] = (0.0, 0.0)
    message: str = "test error"
    components: list[str] = field(default_factory=list)


@dataclass
class _FakeDrcResult:
    error_count: int = 0
    warning_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class TestGateResult:
    def test_accepted_when_both_pass(self):
        result = GateResult(inner_passed=True, truth_passed=True)
        assert result.accepted is True

    def test_not_accepted_when_truth_not_run(self):
        result = GateResult(inner_passed=True, truth_passed=None)
        assert result.accepted is False

    def test_not_accepted_when_inner_fails(self):
        result = GateResult(inner_passed=False, truth_passed=True)
        assert result.accepted is False

    def test_not_accepted_when_truth_fails(self):
        result = GateResult(inner_passed=True, truth_passed=False)
        assert result.accepted is False

    def test_disagreement_signal_when_inner_pass_truth_fail(self):
        result = GateResult(inner_passed=True, truth_passed=False)
        assert result.disagreement_signal is True

    def test_no_disagreement_when_both_pass(self):
        result = GateResult(inner_passed=True, truth_passed=True)
        assert result.disagreement_signal is False

    def test_no_disagreement_when_inner_fails(self):
        result = GateResult(inner_passed=False, truth_passed=False)
        assert result.disagreement_signal is False


class TestInnerGate:
    def test_passes_with_no_violations(self):
        gate = AcceptanceGate()
        result = gate.inner_gate(audit_violations=[])
        assert result.inner_passed is True
        assert result.audit_violations == []

    def test_fails_with_violations(self):
        gate = AcceptanceGate()
        result = gate.inner_gate(audit_violations=["clearance_violation"])
        assert result.inner_passed is False
        assert "clearance_violation" in result.audit_violations

    def test_truth_not_run_after_inner_only(self):
        gate = AcceptanceGate()
        result = gate.inner_gate(audit_violations=[])
        assert result.truth_passed is None


DRC_MODULE = "temper_placer.validation.drc_runner"


class TestTruthGate:
    def test_truth_gate_not_run_for_passing_inner(self):
        """Inner gate passes but truth gate not run → truth_passed is None."""
        gate = AcceptanceGate()
        result = gate.inner_gate(audit_violations=[])
        assert result.inner_passed is True
        assert result.truth_passed is None
        assert result.accepted is False

    def test_truth_gate_runs_when_kicad_cli_not_available(self):
        """When kicad-cli is not available, truth_gate returns truth_passed=False."""
        gate = AcceptanceGate()

        with mock.patch(
            f"{DRC_MODULE}.run_drc",
            side_effect=FileNotFoundError("PCB file not found"),
        ):
            result = gate.truth_gate(Path("/nonexistent.kicad_pcb"))
            assert result.truth_passed is False
            assert len(result.drc_errors) > 0

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_accepts_when_no_errors(self, mock_run_drc):
        mock_run_drc.return_value = _FakeDrcResult(errors=[], warnings=[])

        gate = AcceptanceGate()
        result = gate.truth_gate(Path("/fake/pcb.kicad_pcb"))
        assert result.truth_passed is True

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_rejects_when_errors_present(self, mock_run_drc):
        mock_run_drc.return_value = _FakeDrcResult(
            error_count=1,
            errors=[_FakeDrcError(message="Clearance violation")],
        )

        gate = AcceptanceGate()
        result = gate.truth_gate(Path("/fake/pcb.kicad_pcb"))
        assert result.truth_passed is False
        assert len(result.drc_errors) == 1

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_passes_when_only_warnings(self, mock_run_drc):
        mock_run_drc.return_value = _FakeDrcResult(
            warning_count=2,
            warnings=[_FakeDrcError(severity="warning") for _ in range(2)],
        )

        gate = AcceptanceGate()
        result = gate.truth_gate(Path("/fake/pcb.kicad_pcb"))
        assert result.truth_passed is True
        assert len(result.drc_warnings) == 2


class TestAcceptFlow:
    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_full_accept_flow_passes(self, mock_run_drc):
        mock_run_drc.return_value = _FakeDrcResult(errors=[], warnings=[])

        gate = AcceptanceGate()
        result = gate.accept(
            placement=None,
            constraints=None,
            pcb_path=Path("/fake/pcb.kicad_pcb"),
            audit_violations=[],
        )
        assert result.inner_passed is True
        assert result.truth_passed is True
        assert result.accepted is True

    def test_full_accept_flow_stops_at_inner_fail(self):
        gate = AcceptanceGate()
        result = gate.accept(
            placement=None,
            constraints=None,
            pcb_path=Path("/fake/pcb.kicad_pcb"),
            audit_violations=["overlap_violation"],
        )
        assert result.inner_passed is False
        assert result.truth_passed is None
        assert result.accepted is False

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_disagreement_signal_surfaced(self, mock_run_drc):
        """AE5: audit passes but DRC fails → signal surfaced."""
        mock_run_drc.return_value = _FakeDrcResult(
            error_count=1,
            errors=[_FakeDrcError(message="5.8mm clearance with 6.0mm rule")],
        )

        gate = AcceptanceGate()
        result = gate.accept(
            placement=None,
            constraints=None,
            pcb_path=Path("/fake/pcb.kicad_pcb"),
            audit_violations=[],
        )
        assert result.inner_passed is True
        assert result.truth_passed is False
        assert result.accepted is False
        assert result.disagreement_signal is True
