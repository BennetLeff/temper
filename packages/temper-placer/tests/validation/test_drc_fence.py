"""Tests for the minimum-viable DRC fence (U1: 3-state DRC status).

R1 (3-state) / R6 (replace default-to-100%) are exercised here.  U2
(posture) and U3 (schema) / U4 (cache) tests live alongside these
because the fence is one object with three orthogonal properties, but
the U1 contract is the load-bearing one: ``DrcStatus`` is the typed
enum that the rest of the fence composes on.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.regression.closure_test import ClosureResult, ClosureTest
from temper_placer.regression.measure_closure import measure_closure
from temper_placer.validation.drc_runner import (
    DrcError,
    DrcResult,
    DrcRunnerError,
    DrcStatus,
    DrcWarning,
    run_drc,
)


class TestDrcStatusEnum:
    """The 3-state enum is the load-bearing type for the fence."""

    def test_three_members(self) -> None:
        """DrcStatus must have exactly PASS / FAIL / UNVERIFIED."""
        members = {m.name for m in DrcStatus}
        assert members == {"PASS", "FAIL", "UNVERIFIED"}

    def test_values_are_stringly_distinct(self) -> None:
        """Each member has a unique string value (used in JSON output)."""
        values = {m.value for m in DrcStatus}
        assert len(values) == 3
        assert "PASS" in values
        assert "FAIL" in values
        assert "UNVERIFIED" in values


class TestDrcResultDefaultStatus:
    """The default status must be UNVERIFIED, never PASS."""

    def test_default_is_unverified(self) -> None:
        """An uninitialized DrcResult must not look like a PASS."""
        result = DrcResult(error_count=0, warning_count=0)
        assert result.drc_status == DrcStatus.UNVERIFIED

    def test_default_with_zero_errors_is_still_unverified(self) -> None:
        """``error_count=0`` alone does not imply PASS — the dataclass
        default is UNVERIFIED, and only ``_parse_drc_json`` ever
        promotes to PASS / FAIL.  This is the property that closes
        the false-PASS path: you cannot construct a clean-looking
        DrcResult without explicitly setting the status.
        """
        result = DrcResult(error_count=0, warning_count=0)
        assert result.error_count == 0
        assert result.drc_status == DrcStatus.UNVERIFIED


class TestParseDrcJsonDerivesStatus:
    """``_parse_drc_json`` is the only place that promotes UNVERIFIED→PASS/FAIL."""

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_clean_board_yields_pass(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No errors, no warnings → drc_status == PASS."""
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "clean.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [],
                    "unconnected_items": [],
                    "schematic_parity": [],
                    "ignored_checks": [],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.PASS
        assert result.error_count == 0

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_warnings_only_yields_pass(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Warnings (no errors) → drc_status == PASS — warnings are
        non-blocking, only errors are gating.
        """
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "warn.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "silk_over_pads",
                            "severity": "warning",
                            "description": "Silkscreen over pad",
                            "pos": {"x": 0.0, "y": 0.0},
                            "items": [{"reference": "R1"}],
                        }
                    ],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.PASS
        assert result.error_count == 0
        assert result.warning_count == 1

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_errors_yield_fail(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Any error-severity violation → drc_status == FAIL."""
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "dirty.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "clearance",
                            "severity": "error",
                            "description": "Clearance violation",
                            "pos": {"x": 1.0, "y": 2.0},
                            "items": [{"reference": "U1"}, {"reference": "U2"}],
                        }
                    ],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.FAIL
        assert result.error_count == 1

    @patch("temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=False)
    def test_missing_kicad_cli_raises_drc_runner_error(
        self, mock_avail: MagicMock, tmp_path: Path
    ) -> None:
        """With no kicad-cli, run_drc raises — no DrcResult is produced
        (U1 only; U2 introduces the posture=REPORT path that returns
        UNVERIFIED instead of raising).
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        with pytest.raises(DrcRunnerError):
            run_drc(pcb)


class TestClosureResultDrcStatus:
    """``ClosureResult`` must surface ``drc_status`` from the runner."""

    def test_closure_result_has_drc_status_field(self) -> None:
        """The field exists with default None (legacy / not-yet-run)."""
        r = ClosureResult(passed=True, board_id="temper")
        assert hasattr(r, "drc_status")
        assert r.drc_status is None

    def test_closure_result_drc_status_round_trip(self) -> None:
        """The field accepts a DrcStatus enum value."""
        r = ClosureResult(
            passed=True, board_id="temper", drc_status=DrcStatus.PASS
        )
        assert r.drc_status == DrcStatus.PASS
        r2 = ClosureResult(
            passed=False, board_id="temper", drc_status=DrcStatus.UNVERIFIED
        )
        assert r2.drc_status == DrcStatus.UNVERIFIED


class TestMeasureClosureStatusMapping:
    """The match-statement in ``measure_closure`` is the false-PASS fix.

    The pre-U1 bug was: ``if stages_exercised >= 4 and drc_errors == 0:
    100.0``.  This made a missing measurement (kicad-cli unavailable,
    ``drc_errors == 0`` because the exception was swallowed) look like
    a perfect PASS.  The U1 contract is that an UNVERIFIED measurement
    is ``None`` — distinct from 100.0 — so the SM2 gate fails loudly.
    """

    def _build_closure_result(
        self,
        *,
        drc_status: DrcStatus | None,
        drc_errors: int = 0,
        stages_exercised: int = 4,
    ) -> ClosureResult:
        return ClosureResult(
            passed=drc_status == DrcStatus.PASS,
            board_id="temper",
            benders_iterations=1,
            benders_cuts=0,
            router_completion_pct=100.0,
            drc_errors=drc_errors,
            drc_warnings=0,
            drc_status=drc_status,
            stages_exercised=stages_exercised,
        )

    def test_unverified_yields_none_not_100(self) -> None:
        """The pre-U1 false-PASS: this is the bug fix."""
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.UNVERIFIED, stages_exercised=4
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] is None
        assert payload["drc_status"] == "UNVERIFIED"
        # The pre-U1 bug would have produced 100.0 here.

    def test_pass_yields_100(self) -> None:
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.PASS, stages_exercised=4
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 100.0
        assert payload["drc_status"] == "PASS"

    def test_fail_yields_penalty_formula(self) -> None:
        """A FAIL is a measured result, not a default.  The penalty
        is ``max(0, 100 - 10*errors)`` — the same formula as the
        pre-U1 code, but reached only when a real measurement exists.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.FAIL,
                drc_errors=3,
                stages_exercised=4,
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 70.0
        assert payload["drc_status"] == "FAIL"

    def test_fail_with_zero_errors_is_100(self) -> None:
        """Defensive: ``DrcStatus.FAIL`` with 0 errors is a degenerate
        case (the parser would normally produce PASS).  The penalty
        formula produces 100.0, which is correct.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.FAIL,
                drc_errors=0,
                stages_exercised=4,
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 100.0

    def test_none_drc_status_falls_through_to_zero(self) -> None:
        """Legacy / pre-U1 callers that set ``drc_status=None`` map to
        ``0.0`` — the same as ``stages_exercised < 4``.  This is the
        only path where the result is a numeric zero rather than a
        typed-null or a real measurement.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=None, stages_exercised=2
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 0.0
        assert payload["drc_status"] is None


class TestFalsePassBugRegression:
    """Regression: the pre-U1 default-to-100% line must not exist."""

    def test_measure_closure_does_not_hard_code_100(self, tmp_path: Path) -> None:
        """The literal pattern ``drc_clearance_pass_pct = 100.0`` must
        not appear in ``measure_closure.py`` — the only way to get
        100.0 is via the ``match DrcStatus.PASS`` arm.  This is a
        guard against re-introducing the false-PASS bug.
        """
        from temper_placer.regression import measure_closure

        src = Path(measure_closure.__file__).read_text()
        assert "drc_clearance_pass_pct = 100.0" not in src, (
            "The pre-U1 false-PASS bug has been re-introduced: "
            "drc_clearance_pass_pct is hard-coded to 100.0. The 3-state "
            "DrcStatus match statement is the only path that should "
            "produce 100.0, and only for a measured PASS."
        )
