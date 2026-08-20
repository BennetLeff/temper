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


def test_no_loop_success_writes_output(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_propagates_seed(runner: CliRunner, tmp_path: Path) -> None:
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
        result = runner.invoke(cli_main, _base_args(out) + ["--seed", "42"])

    assert result.exit_code == 0
    mock_solve.assert_called_once()
    assert mock_solve.call_args.kwargs["seed"] == 42


def test_no_loop_stale_banner_removed(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_infeasible_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_infeasible_surfaces_unsat_core(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_infeasible_writes_unsat_json(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_solver_exception(runner: CliRunner, tmp_path: Path) -> None:
    """Solver exception -> click.ClickException, non-zero exit."""
    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        side_effect=RuntimeError("OR-Tools solver timed out"),
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code != 0
    assert "CP-SAT solve failed" in result.output


def test_no_loop_round_trip_oracle_runs_and_passes(
    runner: CliRunner, tmp_path: Path
) -> None:
    """The post-write round-trip oracle (plan 2026-08-02-009 U3) runs on a
    successful --no-loop write and reports PASS."""
    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0)},
        rotations={"R1": 1},
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

    assert result.exit_code == 0, f"CLI failed:\n{result.output}"
    assert "Round-trip oracle: round-trip PASS" in result.output


def test_no_loop_round_trip_oracle_is_given_file_frame_positions(
    runner: CliRunner, tmp_path: Path
) -> None:
    """The oracle must be handed the model positions in FILE coordinates.

    ``--no-loop`` solves against ``parse_kicad_pcb(..., normalize=True)``
    output, so ``cp_result.positions`` is origin-relative, and the write
    adds ``board.origin`` back (``write_placements_to_pcb(board_origin=)``)
    to land in the template's absolute frame. ``check_placement_roundtrip``
    re-parses that written FILE (KTD4) and its ``positions`` argument is
    documented as being "in the same coordinate frame the writer wrote
    (file coordinates)" -- so it must be given the origin-corrected
    positions, not the raw normalized ones.

    Handing it the raw normalized dict made it report a
    ``board.origin``-sized ``footprint_anchor`` mismatch for every
    component and ``pad_position`` mismatch for every pad, on any board
    whose Edge.Cuts origin is not (0, 0) -- i.e. every real board.
    Measured on ``pcb/temper.kicad_pcb`` (origin (8, 20) mm): 689
    mismatches (168 ``footprint_anchor`` + 521 ``pad_position``), every
    single ``pad_position`` displaced by exactly (8.0, 20.0).

    The second half of this test is the anti-vacuity half: it feeds the
    same written file the raw normalized frame and asserts the oracle
    really does reject it, so a future regression cannot make the first
    half pass by making the oracle blind instead of by keeping the frame
    right.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.validation import placement_roundtrip as pr

    origin = parse_kicad_pcb(MINIMAL_PCB).board.origin
    assert (float(origin[0]), float(origin[1])) != (0.0, 0.0), (
        "fixture must have a non-(0,0) Edge.Cuts origin or this test is "
        f"vacuous -- got {origin!r}"
    )

    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0)},
        rotations={"R1": 1},
        placed_refs=["R1"],
        solve_time_ms=10.0,
        objective_value=0.0,
    )

    real_check = pr.check_placement_roundtrip
    captured: dict = {}

    def spy(path, positions, rotations=None, components=None, **kwargs):
        captured["path"] = Path(path)
        captured["positions"] = dict(positions)
        captured["rotations"] = dict(rotations or {})
        captured["components"] = list(components or [])
        result = real_check(path, positions, rotations, components, **kwargs)
        captured["result"] = result
        return result

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ), mock.patch.object(pr, "check_placement_roundtrip", spy):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code == 0, f"CLI failed:\n{result.output}"
    assert captured, "the round-trip oracle was never called"
    assert captured["positions"] == {
        "R1": (10.0 + origin[0], 20.0 + origin[1])
    }, (
        "the oracle must be given board.origin-corrected (file-frame) "
        f"positions -- got {captured['positions']!r} for a solve at "
        f"(10.0, 20.0) on a board with origin {origin!r}"
    )
    assert captured["result"].passed, captured["result"].summary

    # Anti-vacuity: the pre-fix argument (the raw normalized frame) really
    # is rejected by this same oracle on this same written file.
    stale = real_check(
        captured["path"],
        {"R1": (10.0, 20.0)},
        captured["rotations"],
        captured["components"],
    )
    assert not stale.passed, (
        "the oracle must reject normalized-frame positions against an "
        "absolute-frame file; if it does not, the check above proves nothing"
    )
    assert {m.kind for m in stale.mismatches} == {
        "footprint_anchor",
        "pad_position",
    }
    for m in stale.mismatches:
        if m.kind != "pad_position":
            continue
        assert (
            round(m.actual[0] - m.expected[0], 6),
            round(m.actual[1] - m.expected[1], 6),
        ) == (float(origin[0]), float(origin[1])), (
            f"expected every pad displaced by exactly board.origin, got {m}"
        )


def test_no_loop_round_trip_mismatch_fails_command(
    runner: CliRunner, tmp_path: Path
) -> None:
    """A round-trip oracle mismatch after the write fails the command at
    the write site -- a dropped or mis-signed rotation must not ship."""
    from temper_placer.validation.placement_roundtrip import (
        RoundTripMismatch,
        RoundTripResult,
    )

    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0)},
        rotations={"R1": 1},
        placed_refs=["R1"],
        solve_time_ms=10.0,
        objective_value=0.0,
    )
    failing = RoundTripResult(
        mismatches=[RoundTripMismatch(ref="R1", kind="footprint_angle")],
        checked_components=1,
        checked_pads=2,
    )

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=mock_result,
    ), mock.patch(
        "temper_placer.validation.placement_roundtrip.check_placement_roundtrip",
        return_value=failing,
    ):
        result = runner.invoke(cli_main, _base_args(out))

    assert result.exit_code != 0
    assert "Round-trip oracle FAILED after write" in result.output


def test_no_loop_missing_pcb(runner: CliRunner, tmp_path: Path) -> None:
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


def test_no_loop_model_invalid_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
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


# -------- warm-start ----------------------------------------------------------


def test_no_loop_warm_start_flag_registered(
    runner: CliRunner,
) -> None:
    """--warm-start flag appears in help output."""
    result = runner.invoke(cli_main, ["optimize", "--help"])
    assert "--warm-start" in result.output


def test_no_loop_warm_start_passes_hints(runner: CliRunner, tmp_path: Path) -> None:
    """--warm-start flag is accepted by the CLI (pipeline runs are tested at E2E level)."""
    mock_result = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0)},
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
        result = runner.invoke(cli_main, _base_args(out) + ["--warm-start"])

    assert result.exit_code == 0
    mock_solve.assert_called_once()
    # hint_positions kwarg is always passed — may be None if
    # the deterministic pipeline produces no placements for small test boards
    assert "hint_positions" in mock_solve.call_args.kwargs
