"""Integration tests for temper-placer optimize --no-loop.

Proves that --no-loop correctly calls solve_placement(), writes output on
success, and exits non-zero on infeasible.  All solver calls are mocked so
no real CP-SAT solver runs during testing.
"""

import json
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from temper_placer.cli import main as cli_main
from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

# -------- fixtures -----------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _base_args(
    output_board: Path,
) -> list[str]:
    return [
        "optimize",
        str(MINIMAL_PCB),
        "-c",
        str(MINIMAL_CONSTRAINTS),
        "-o",
        str(output_board),
        "--no-loop",
    ]


# -------- happy path ---------------------------------------------------------


def test_no_loop_success_writes_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Feasible solve writes updated .kicad_pcb to --output."""
    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0), "R2": (30.0, 40.0)},
        rotations={"R1": 1, "R2": 0},
        placed_refs=["R1", "R2"],
        solve_time_ms=42.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ) as mock_solve:
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code == 0, f"CLI failed:\n{result.output}"
    mock_solve.assert_called_once()
    assert out.exists(), f"Output file not written:\n{result.output}"


def test_no_loop_propagates_seed(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--seed flag is forwarded to solve_placement(seed=...)."""
    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (5.0, 5.0)},
        rotations={"R1": 0},
        placed_refs=["R1"],
        solve_time_ms=10.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ) as mock_solve:
        result = runner.invoke(
            cli_main, _base_args(out) + ["--seed", "42"]
        )

    assert result.exit_code == 0
    mock_solve.assert_called_once()
    assert mock_solve.call_args.kwargs["seed"] == 42


def test_no_loop_stale_banner_removed(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Stale "Full CP-SAT pipeline integration is in progress" is gone."""
    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (5.0, 5.0)},
        rotations={"R1": 0},
        placed_refs=["R1"],
        solve_time_ms=10.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert "in progress" not in result.output.lower()
    assert "temper pipeline" not in result.output.lower()


# -------- infeasible path ----------------------------------------------------


def test_no_loop_infeasible_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Infeasible solve exits 1, writes no output file."""
    mock_result = CpSatPlacementResult(
        status="infeasible",
        positions={},
        rotations={},
        placed_refs=[],
        unsat_core=[{"name": "loop_area_hb", "because": ""}],
        solve_time_ms=500.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code != 0, f"Expected non-zero exit, got 0:\n{result.output}"
    assert not out.exists(), f"Output file should not exist:\n{result.output}"


def test_no_loop_infeasible_surfaces_unsat_core(
    runner: CliRunner, tmp_path: Path
) -> None:
    """UNSAT core text appears in stderr/stdout on infeasible solve."""
    mock_result = CpSatPlacementResult(
        status="infeasible",
        positions={},
        rotations={},
        placed_refs=[],
        unsat_core=[{"name": "loop_area_hb", "because": "coil area exceeds limit"}],
        solve_time_ms=500.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert "loop_area_hb" in result.output


def test_no_loop_infeasible_writes_unsat_json(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--unsat-report writes JSON on infeasible solve."""
    mock_result = CpSatPlacementResult(
        status="infeasible",
        positions={},
        rotations={},
        placed_refs=[],
        unsat_core=[{"name": "loop_area_hb", "because": "coil area exceeds limit"}],
        solve_time_ms=500.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    report = tmp_path / "unsat.json"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ):
        result = runner.invoke(
            cli_main,
            _base_args(out) + ["--unsat-report", str(report)],
        )

    assert result.exit_code != 0
    assert not out.exists()
    assert report.exists()
    data = json.loads(report.read_text())
    assert "loop_area_hb" in json.dumps(data)


# -------- error paths --------------------------------------------------------


def test_no_loop_solver_exception(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Solver exception -> click.ClickException, non-zero exit."""
    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        side_effect=RuntimeError("OR-Tools solver timed out"),
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code != 0
    assert "CP-SAT solve failed" in result.output


def test_no_loop_missing_pcb(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Missing input PCB -> non-zero exit with clear message."""
    out = tmp_path / "placed.kicad_pcb"
    result = runner.invoke(
        cli_main,
        [
            "optimize",
            str(tmp_path / "nonexistent.kicad_pcb"),
            "-c",
            str(MINIMAL_CONSTRAINTS),
            "-o",
            str(out),
            "--no-loop",
        ],
    )

    assert result.exit_code != 0


def test_no_loop_model_invalid_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    """model_invalid status exits non-zero."""
    mock_result = CpSatPlacementResult(
        status="model_invalid",
        positions={},
        rotations={},
        placed_refs=[],
        unsat_core=[{"name": "board_size", "because": ""}],
        solve_time_ms=10.0,
        objective_value=0.0,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code != 0
    assert not out.exists()
