"""Tests for ngspice simulation runner."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.spice.corner_results import CornerResult
from tools.spice.sim_runner import (
    _apply_params,
    _parse_output,
    check_ngspice_available,
    run_simulation,
)

NGSPICE_AVAILABLE = check_ngspice_available()


MINIMAL_CONVERGED_CIR = """\
* Minimal converged netlist for testing
.options reltol=1e-3
.options abstol=1e-9

V1 1 0 DC 10
R1 1 0 1k

.control
op
print v(1)
quit
.endc

.end
"""


MINIMAL_BROKEN_CIR = """\
* Deliberately broken netlist
V1 1 0 DC 10
V2 1 0 DC 5

.control
op
quit
.endc

.end
"""


@pytest.fixture
def converged_cir(tmp_path: Path) -> str:
    p = tmp_path / "converged.cir"
    p.write_text(MINIMAL_CONVERGED_CIR)
    return str(p)


@pytest.fixture
def broken_cir(tmp_path: Path) -> str:
    p = tmp_path / "broken.cir"
    p.write_text(MINIMAL_BROKEN_CIR)
    return str(p)


class TestApplyParams:
    def test_no_params_unchanged(self) -> None:
        netlist = ".param VDC=320\nR1 1 0 1k\n"
        result = _apply_params(netlist, None, None)
        assert result == netlist

    def test_overrides_existing_param(self) -> None:
        netlist = ".param VDC=320\nR1 1 0 1k\n"
        result = _apply_params(netlist, {"VDC": 400.0}, None)
        assert "VDC=400.0" in result

    def test_adds_temp_when_none_present(self) -> None:
        netlist = ".param VDC=320\n.options reltol=1e-3\n"
        result = _apply_params(netlist, None, 125.0)
        assert ".temp 125.0" in result


@pytest.mark.skipif(not NGSPICE_AVAILABLE, reason="ngspice not installed")
class TestSimRunnerIntegration:
    def test_converged_returns_result(self, converged_cir: str) -> None:
        result = run_simulation(converged_cir)
        assert isinstance(result, CornerResult)
        assert not result.convergence_error

    def test_broken_flags_error(self, broken_cir: str) -> None:
        result = run_simulation(broken_cir)
        assert result.convergence_error

    def test_non_existent_file(self) -> None:
        result = run_simulation("/nonexistent/foo.cir")
        assert result.convergence_error


class TestParseOutput:
    def test_convergence_error_detected(self) -> None:
        result = _parse_output(
            "",
            "tran simulation(s) aborted: convergence failure",
            None,
            None,
        )
        assert result.convergence_error

    def test_no_error_clean_output(self) -> None:
        stdout = "Measurement: v_ge_hs_max\nv_ge_hs_max = 1.850000e+01\n"
        result = _parse_output(stdout, "", None, None)
        assert not result.convergence_error
        assert result.Vge_peak == pytest.approx(18.5)

    def test_null_metrics_default(self) -> None:
        result = _parse_output("", "Everything OK", None, None)
        assert not result.convergence_error
        assert result.Vge_peak is None
        assert result.Vce_peak is None

    def test_extracts_tank_rms(self) -> None:
        stdout = "Measurement: i_tank_rms\ni_tank_rms = 1.500000e+01\n"
        result = _parse_output(stdout, "", None, None)
        assert result.tank_current_rms == pytest.approx(15.0)
