"""CLI optimize validator_input wiring tests (issue #617 second half).

Proves that the optimize command arms the REQ-SAFE-01 validator post-solve
audit -- constructing ``validator_input`` from the production real-board
loader -- in BOTH the --no-loop solve_placement call and the default
PlaceRouteLoop path, and that it logs the documented skip (never crashes,
never half-wires) when the audit inputs are unavailable.

The loader itself is covered by the fixture-bound integration tests
(``tests/requirements/safety/test_clearance.py``); these tests assert the
CLI boundary contract. Solver calls are mocked so no real CP-SAT solve runs.
"""

import re
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from temper_placer.cli import main as cli_main

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"
REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def _norm(text: str) -> str:
    """Collapse whitespace -- the rich console wraps long log lines at word
    boundaries, so multi-word assertions must not depend on line breaks."""
    return re.sub(r"\s+", " ", text)


def _require_real_board() -> None:
    """Skip when the real board inputs are unavailable (fresh checkout
    without ``make netlist``) -- same skip contract as the safety suite."""
    if not REAL_PCB.is_file():
        pytest.skip("pcb/temper.kicad_pcb not present")
    if not (REPO_ROOT / "elec" / "build" / "default.net").is_file():
        pytest.skip("elec/build/default.net not present (run `make netlist`)")
    if not (REPO_ROOT / "elec" / "domain_manifest.yaml").is_file():
        pytest.skip("elec/domain_manifest.yaml not present")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _no_loop_args(output_board: Path) -> list[str]:
    return [
        "optimize",
        str(REAL_PCB),
        "-c",
        str(MINIMAL_CONSTRAINTS),
        "-o",
        str(output_board),
        "--no-loop",
    ]


def _loop_args(output_board: Path) -> list[str]:
    return [
        "optimize",
        str(REAL_PCB),
        "-c",
        str(MINIMAL_CONSTRAINTS),
        "-o",
        str(output_board),
    ]


def _infeasible_result():
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    return CpSatPlacementResult(
        status="infeasible",
        positions={},
        rotations={},
        placed_refs=[],
        unsat_core=[{"name": "board_size", "because": ""}],
        solve_time_ms=10.0,
        objective_value=0.0,
    )


# -------- --no-loop path -----------------------------------------------------


def test_no_loop_arms_validator_input_on_real_board(
    runner: CliRunner, tmp_path: Path
) -> None:
    """With the real board + manifest + netlist present, the --no-loop solve
    receives validator_input carrying BOTH keys and a non-empty placement --
    never a half-wired dict (which would raise ValueError inside
    solve_placement on the missing key)."""
    _require_real_board()
    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=_infeasible_result(),
    ) as mock_solve:
        result = runner.invoke(cli_main, _no_loop_args(out))

    assert "REQ-SAFE-01 validator audit armed" in result.output
    kwargs = mock_solve.call_args.kwargs
    assert "validator_input" in kwargs, "solve_placement must receive validator_input"
    v_input = kwargs["validator_input"]
    assert set(v_input) == {"placement", "voltage_domains"}
    assert v_input["placement"]["components"], "placement must be non-empty"
    assert v_input["voltage_domains"]


def test_no_loop_skips_audit_when_loader_unavailable(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Loader raising RealBoardUnavailable -> logged skip, solve called
    WITHOUT validator_input (byte-identical to pre-wiring)."""
    from temper_placer.io.real_board import RealBoardUnavailable

    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=_infeasible_result(),
    ) as mock_solve, mock.patch(
        "temper_placer.io.real_board.load_real_board_placement",
        side_effect=RealBoardUnavailable("PCB not found: /nonexistent"),
    ):
        result = runner.invoke(cli_main, _no_loop_args(out))

    assert "REQ-SAFE-01 validator post-solve audit SKIPPED" in _norm(result.output)
    # The documented skip: validator_input stays None (== absent in the
    # encoder), never a half-wired dict.
    assert mock_solve.call_args.kwargs.get("validator_input") is None


def test_no_loop_skips_audit_when_placement_empty(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Board with zero domain-classified components -> logged skip (the
    validator would vacuous-pass), no validator_input."""
    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=_infeasible_result(),
    ) as mock_solve, mock.patch(
        "temper_placer.io.real_board.load_real_board_placement",
        return_value=({"components": [], "nets": {}}, {}, {}),
    ):
        result = runner.invoke(cli_main, _no_loop_args(out))

    assert "zero domain-classified components" in _norm(result.output)
    assert mock_solve.call_args.kwargs.get("validator_input") is None


def test_no_loop_prints_audit_buckets(runner: CliRunner, tmp_path: Path) -> None:
    """When the solve carries a validator_audit result, the CLI surfaces the
    buckets (hard/intra/coverage-gap + geometry trust)."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    audit = mock.Mock()
    audit.hard_failures = []
    audit.intra_footprint = []
    audit.coverage_gaps = []
    audit.geometry_trusted = True
    result_obj = CpSatPlacementResult(
        status="optimal",
        positions={"R1": (10.0, 20.0)},
        rotations={"R1": 0},
        placed_refs=["R1"],
        solve_time_ms=10.0,
        objective_value=0.0,
        validator_audit=audit,
    )
    out = tmp_path / "placed.kicad_pcb"
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement",
        return_value=result_obj,
    ):
        result = runner.invoke(cli_main, _no_loop_args(out))

    assert "REQ-SAFE-01 validator post-solve audit: 0 hard" in result.output
    assert "geometry_trusted=True" in result.output


# -------- loop path (default) -----------------------------------------------


def test_loop_forwards_validator_input(runner: CliRunner, tmp_path: Path) -> None:
    """The default place-route loop path forwards validator_input into
    PlaceRouteLoop.run (which hands it to every solve_placement round)."""
    _require_real_board()

    class _FakeRouting:
        completion_rate = 1.0
        routed_pcb_content = None
        drc_errors = 0

    class _FakeLoopResult:
        success = True
        rounds = []
        routing = _FakeRouting()
        placement = None
        reason = ""
        unmeasured_gates = {}

    captured: dict = {}

    def _fake_run(**kwargs) -> _FakeLoopResult:
        captured.update(kwargs)
        return _FakeLoopResult()

    with mock.patch(
        "temper_placer.placer.cp_sat.loop.PlaceRouteLoop",
    ) as mock_loop:
        mock_loop.return_value.run.side_effect = _fake_run
        out = tmp_path / "placed.kicad_pcb"
        result = runner.invoke(cli_main, _loop_args(out))

    assert result.exit_code == 0, f"CLI failed:\n{result.output}"
    assert "REQ-SAFE-01 validator audit armed" in result.output
    assert "validator_input" in captured
    assert set(captured["validator_input"]) == {"placement", "voltage_domains"}
    assert captured["validator_input"]["placement"]["components"]
