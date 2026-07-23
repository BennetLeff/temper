"""Integration tests for UNSAT report surfacing in the CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from temper_placer.cli import optimize as optimize_command
from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.unsat import UnsatConstraint, UnsatReport


def _fake_result_with_unsat(unsat_report: UnsatReport | None):
    """Build a mock result object that may carry an unsat_report attr."""
    result = mock.MagicMock()
    result.unsat_report = unsat_report
    result.final_loss = 0.0
    result.best_loss = 0.0
    result.total_epochs = 100
    result.converged = True
    result.elapsed_seconds = 1.0
    result.history = []
    return result


def _make_sample_report() -> UnsatReport:
    c1 = UnsatConstraint(
        name="loop_area 'commutation'",
        constraint_type=ConstraintType.LOOP_AREA,
        because=(
            "IGBT overvoltage destruction above 635 mm2 at 1 A/ns di/dt and 80%-derated V_CE=960 V"
        ),
        assumption_literal=1,
    )
    c2 = UnsatConstraint(
        name="separated 'Q1_Q2'",
        constraint_type=ConstraintType.SEPARATED,
        because="IEC 60335-1 reinforced isolation",
        assumption_literal=2,
    )
    return UnsatReport(
        sufficient_core=[c1, c2],
        minimal_core=[c1, c2],
        is_minimal=True,
    )


class TestUnsatReportFlag:
    """Verify --unsat-report flag is registered on the optimize command."""

    def test_flag_registered(self):
        """The --unsat-report option is available on the optimize command."""
        runner = CliRunner()
        result = runner.invoke(optimize_command, ["--help"])
        assert result.exit_code == 0
        assert "--unsat-report" in result.output


class TestMaybeSurfaceUnsat:
    """Test the _maybe_surface_unsat helper."""

    def test_does_nothing_when_no_unsat(self):
        """When result has no unsat_report attr, function is a no-op."""
        from temper_placer.cli import _maybe_surface_unsat

        result = mock.MagicMock(spec=[])
        _maybe_surface_unsat(result, None)
        # Should not raise; should just return silently.

    def test_does_nothing_when_unsat_is_none(self):
        from temper_placer.cli import _maybe_surface_unsat

        result = _fake_result_with_unsat(None)
        _maybe_surface_unsat(result, None)
        # Should not raise.

    def test_surfaces_panel_to_stderr_without_json(self):
        """When unsat_report is present, Rich panel prints to console."""
        from temper_placer.cli import _maybe_surface_unsat

        report = _make_sample_report()
        result = _fake_result_with_unsat(report)

        _maybe_surface_unsat(result, None)
        # If no exception, panel was formatted and printed.
        # Verified by the surface unit tests (U2).

    def test_writes_json_when_path_provided(self):
        """When --unsat-report path is given, JSON is written."""
        from temper_placer.cli import _maybe_surface_unsat

        report = _make_sample_report()
        result = _fake_result_with_unsat(report)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            json_path = Path(f.name)

        try:
            _maybe_surface_unsat(result, json_path)
            assert json_path.exists()
            with open(json_path) as f:
                data = json.load(f)
            assert data["report_type"] == "unsat"
            assert len(data["minimal_core"]) == 2
        finally:
            json_path.unlink(missing_ok=True)

    def test_json_contains_because_from_report(self):
        """JSON output carries the because text from the PCL spec."""
        from temper_placer.cli import _maybe_surface_unsat

        report = _make_sample_report()
        result = _fake_result_with_unsat(report)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            json_path = Path(f.name)

        try:
            _maybe_surface_unsat(result, json_path)
            with open(json_path) as f:
                data = json.load(f)
            because_texts = [c["because"] for c in data["minimal_core"]]
            assert any("IGBT overvoltage" in t for t in because_texts)
        finally:
            json_path.unlink(missing_ok=True)
