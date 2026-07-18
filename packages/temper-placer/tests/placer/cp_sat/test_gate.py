"""Unit tests for the two-tier acceptance gate.

VERIFIED 2026-07-18: AcceptanceGate.inner_gate()/truth_gate()/accept()
were refactored to operate on real Placement/BaseConstraint domain
objects (via PlacementAuditor) and to return AuditReport/DrcResult
directly, rather than the GateResult-wrapping, raw-violations-list API
these tests originally assumed. AcceptanceGate has zero production
callers (grepped across src/) -- the tests below are rewritten against
the current real implementation rather than the abandoned earlier
design. GateResult itself is unchanged and still tested by
TestGateResult below, but note it is no longer actually returned by any
AcceptanceGate method -- it's an orphaned type describing a two-tier
contract the current accept() (which returns a plain
tuple[bool, AuditReport, DrcResult | None]) doesn't fulfill. See
docs/solutions/logic-errors/
acceptance-gate-tests-stale-after-real-domain-object-refactor.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.audit import Placement
from temper_placer.placer.cp_sat.gate import AcceptanceGate, GateResult


def _make_placement(**overrides: object) -> Placement:
    """Build a minimal Placement with defaults overridden (mirrors test_audit.py)."""
    positions: dict[str, tuple[float, float]] = overrides.get(
        "positions", {"A": (5.0, 5.0), "B": (15.0, 5.0)}
    )
    sizes: dict[str, tuple[float, float]] = overrides.get(
        "sizes", {"A": (2.0, 2.0), "B": (2.0, 2.0)}
    )
    return Placement(
        positions_mm=positions,
        sizes_mm=sizes,
        rotations={ref: 0 for ref in positions},
        board_w_mm=20.0,
        board_h_mm=20.0,
    )


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


_SEPARATED_KWARGS = dict(
    tier=ConstraintTier.HARD,
    because="Safety isolation requirement for high voltage paths",
)


class TestInnerGate:
    def test_passes_with_no_violations(self):
        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (12.0, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=3.0, **_SEPARATED_KWARGS)
        result = gate.inner_gate(placement, [c])
        assert result.all_pass is True
        assert result.violations == []

    def test_fails_with_violations(self):
        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (5.6, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=5.0, **_SEPARATED_KWARGS)
        result = gate.inner_gate(placement, [c])
        assert result.all_pass is False
        assert len(result.violations) == 1

    def test_truth_not_run_by_inner_gate(self):
        """inner_gate() must never call DRC -- that's the truth gate's job."""
        gate = AcceptanceGate()
        placement = _make_placement()
        with mock.patch(f"{DRC_MODULE}.run_drc") as mock_run_drc:
            gate.inner_gate(placement, [])
            mock_run_drc.assert_not_called()


# gate.py does `from temper_placer.validation.drc_runner import run_drc`,
# binding its own local name at import time -- patching must target where
# the name is looked up (gate.py's namespace), not where run_drc is
# originally defined, or the mock silently has no effect and the test
# hits the real kicad-cli.
DRC_MODULE = "temper_placer.placer.cp_sat.gate"


class TestTruthGate:
    def test_truth_gate_not_run_for_passing_inner(self):
        """Calling inner_gate() alone must not touch DRC at all."""
        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (12.0, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=3.0, **_SEPARATED_KWARGS)
        with mock.patch(f"{DRC_MODULE}.run_drc") as mock_run_drc:
            result = gate.inner_gate(placement, [c])
            assert result.all_pass is True
            mock_run_drc.assert_not_called()

    def test_truth_gate_returns_synthetic_error_for_missing_pcb(self):
        """A nonexistent PCB path returns a synthetic error result without
        ever reaching run_drc() -- truth_gate() checks path.exists() first."""
        gate = AcceptanceGate()

        with mock.patch(f"{DRC_MODULE}.run_drc") as mock_run_drc:
            result = gate.truth_gate(Path("/nonexistent.kicad_pcb"))
            mock_run_drc.assert_not_called()
            assert result.error_count >= 1
            assert len(result.errors) > 0

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_accepts_when_no_errors(self, mock_run_drc, tmp_path):
        mock_run_drc.return_value = _FakeDrcResult(errors=[], warnings=[])
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        gate = AcceptanceGate()
        result = gate.truth_gate(pcb_path)
        assert result.error_count == 0

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_rejects_when_errors_present(self, mock_run_drc, tmp_path):
        mock_run_drc.return_value = _FakeDrcResult(
            error_count=1,
            errors=[_FakeDrcError(message="Clearance violation")],
        )
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        gate = AcceptanceGate()
        result = gate.truth_gate(pcb_path)
        assert result.error_count == 1
        assert len(result.errors) == 1

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_passes_when_only_warnings(self, mock_run_drc, tmp_path):
        mock_run_drc.return_value = _FakeDrcResult(
            warning_count=2,
            warnings=[_FakeDrcError(severity="warning") for _ in range(2)],
        )
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        gate = AcceptanceGate()
        result = gate.truth_gate(pcb_path)
        assert result.error_count == 0
        assert len(result.warnings) == 2


class TestAcceptFlow:
    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_full_accept_flow_passes(self, mock_run_drc, tmp_path):
        mock_run_drc.return_value = _FakeDrcResult(errors=[], warnings=[])
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (12.0, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=3.0, **_SEPARATED_KWARGS)
        accepted, audit_report, drc_result = gate.accept(placement, [c], pcb_path=pcb_path)
        assert audit_report.all_pass is True
        assert drc_result.error_count == 0
        assert accepted is True

    def test_full_accept_flow_stops_at_inner_fail(self, tmp_path):
        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (5.6, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=5.0, **_SEPARATED_KWARGS)
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        with mock.patch(f"{DRC_MODULE}.run_drc") as mock_run_drc:
            accepted, audit_report, drc_result = gate.accept(placement, [c], pcb_path=pcb_path)
            mock_run_drc.assert_not_called()
        assert audit_report.all_pass is False
        assert drc_result is None
        assert accepted is False

    @mock.patch(f"{DRC_MODULE}.run_drc")
    def test_disagreement_signal_surfaced(self, mock_run_drc, tmp_path):
        """AE5: audit passes but DRC fails -- the two-tier gap this design exists to catch."""
        mock_run_drc.return_value = _FakeDrcResult(
            error_count=1,
            errors=[_FakeDrcError(message="5.8mm clearance with 6.0mm rule")],
        )
        pcb_path = tmp_path / "fake.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        gate = AcceptanceGate()
        placement = _make_placement(positions={"A": (5.0, 5.0), "B": (12.0, 5.0)})
        c = SeparatedConstraint("A", "B", min_distance_mm=3.0, **_SEPARATED_KWARGS)
        accepted, audit_report, drc_result = gate.accept(placement, [c], pcb_path=pcb_path)
        assert audit_report.all_pass is True
        assert drc_result.error_count == 1
        assert accepted is False
