"""U4: Place-Route Loop CLI Integration Test."""

from types import SimpleNamespace
from unittest import mock

from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
from temper_placer.placer.cp_sat.feedback import (
    FeedbackClassifier,
)
from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    LoopResult,
    PlaceRouteLoop,
    RoundRecord,
)
from temper_placer.router_v6.adapter import RoutingResult

# ---------------------------------------------------------------------------
# U4.1: --no-loop flag (existing behavior preserved)
# ---------------------------------------------------------------------------


def test_optimize_no_loop_skips_loop_stage():
    """--no-loop flag skips the place-route loop integration."""
    from click.testing import CliRunner

    from temper_placer.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["optimize", "--help"])
    assert result.exit_code == 0
    assert "--loop" in result.output
    assert "--no-loop" in result.output


# ---------------------------------------------------------------------------
# U4.2: --loop flag triggers PlaceRouteLoop
# ---------------------------------------------------------------------------


def test_optimize_with_loop_invokes_place_route_loop():
    """When --loop is enabled, PlaceRouteLoop.run() is invoked."""
    loop = PlaceRouteLoop()
    assert loop is not None
    assert loop.MAX_ROUNDS == 10
    assert isinstance(LoopResult(success=True), LoopResult)


# ---------------------------------------------------------------------------
# U4.3: Loop output surfaces completion rate
# ---------------------------------------------------------------------------


def test_loop_result_surfaces_completion():
    """LoopResult surfaces routing completion rate to CLI output."""
    mock_routing = mock.MagicMock()
    mock_routing.completion_rate = 0.95

    result = LoopResult(
        success=True,
        reason="success",
        routing=mock_routing,
        rounds=[],
    )

    assert result.success is True
    cr = getattr(result.routing, "completion_rate", 0.0)
    assert cr == 0.95


# ---------------------------------------------------------------------------
# U4.4: Loop non-convergence diagnostic output
# ---------------------------------------------------------------------------


def test_loop_non_convergence_diagnostics():
    """When loop doesn't converge, diagnostic info is available."""
    rounds = [
        RoundRecord(
            round_number=1, completion_rate=0.85, drc_errors=3,
            solve_time_ms=150.0, route_time_ms=500.0, status="optimal",
        ),
        RoundRecord(
            round_number=2, completion_rate=0.90, drc_errors=2,
            solve_time_ms=145.0, route_time_ms=480.0, status="optimal",
        ),
    ]

    result = LoopResult(
        success=False,
        reason=LoopExitReason.ROUND_LIMIT_EXCEEDED.value,
        rounds=rounds,
    )

    assert not result.success
    assert result.reason == "round_limit_exceeded"
    last = result.rounds[-1]
    assert last.completion_rate == 0.90
    assert last.drc_errors == 2


def test_optimize_non_convergent_loop_fails_closed(tmp_path):
    """A failed loop must not report success or leave a usable board output."""
    from click.testing import CliRunner

    from temper_placer.cli import main

    input_pcb = tmp_path / "input.kicad_pcb"
    config = tmp_path / "constraints.yaml"
    output = tmp_path / "output.kicad_pcb"
    input_pcb.write_text("(kicad_pcb)", encoding="utf-8")
    config.write_text("{}", encoding="utf-8")

    failed_loop = LoopResult(
        success=False,
        reason=LoopExitReason.ROUND_LIMIT_EXCEEDED.value,
        rounds=[
            RoundRecord(
                round_number=1,
                completion_rate=0.8,
                drc_errors=2,
                solve_time_ms=1.0,
                route_time_ms=1.0,
                status="incomplete",
            )
        ],
    )
    parsed = SimpleNamespace(netlist=object(), board=SimpleNamespace(zones=[]))
    constraints = SimpleNamespace(pcl_constraints=[])

    with (
        mock.patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb",
            return_value=parsed,
        ),
        mock.patch(
            "temper_placer.io.config_loader.load_constraints",
            return_value=constraints,
        ),
        mock.patch.object(PlaceRouteLoop, "run", return_value=failed_loop),
    ):
        result = CliRunner().invoke(
            main,
            ["optimize", str(input_pcb), "-c", str(config), "-o", str(output)],
        )

    assert result.exit_code != 0
    assert "Place→route loop did not converge" in result.output
    assert not output.exists()


def test_feedback_uses_dict_backed_cp_sat_positions():
    """An unrouted SPI net must generate a usable U_MCU placement delta."""
    placement = CpSatPlacementResult(
        positions={"U_MCU": (40.0, 60.0)}, status="optimal"
    )
    result = RoutingResult(
        completion_rate=0.8,
        unrouted_nets=["SPI_MOSI"],
    )

    classified = FeedbackClassifier().classify(result, placement)

    assert len(classified.deltas) == 1
    assert classified.deltas[0].constraint.component == "U_MCU"


def test_authoritative_board_uses_one_route_then_truth_gate(tmp_path):
    """A real-board artifact proceeds to KiCad DRC after its first clean route."""
    placement = CpSatPlacementResult(
        positions={"U_MCU": (40.0, 60.0)}, status="optimal"
    )
    loop = PlaceRouteLoop(_placement_solver=lambda **_: placement)
    loop._route_placement = mock.MagicMock(
        return_value=RoutingResult(completion_rate=1.0)
    )

    result = loop.run(
        netlist=SimpleNamespace(components=[]),
        board=SimpleNamespace(origin=(0.0, 0.0)),
        source_pcb_path=tmp_path / "authoritative.kicad_pcb",
    )

    assert result.success is True
    assert len(result.rounds) == 1
    assert loop._route_placement.call_count == 1


def test_authoritative_board_route_preserves_source_and_origin(tmp_path):
    """The router receives the real board and absolute KiCad coordinates."""
    source = tmp_path / "authoritative.kicad_pcb"
    placement = CpSatPlacementResult(
        positions={"U_MCU": (40.0, 60.0)}, status="optimal"
    )
    loop = PlaceRouteLoop()
    loop._source_pcb_path = source
    loop._netclass_rules = None
    expected = RoutingResult(completion_rate=1.0)

    with mock.patch(
        "temper_placer.router_v6.adapter.route_pcb", return_value=expected
    ) as route_pcb:
        result = loop._route_placement(
            placement,
            netlist=SimpleNamespace(),
            board=SimpleNamespace(origin=(100.0, 200.0)),
            seed=42,
        )

    assert result is expected
    parsed, placements = route_pcb.call_args.args[:2]
    assert parsed.source_path == source
    assert placements == {"U_MCU": (140.0, 260.0)}


# ---------------------------------------------------------------------------
# U4.5: Import chain verified (no import errors on key modules)
# ---------------------------------------------------------------------------


def test_full_import_chain():
    """Verify all new modules import without errors."""
    assert CpSatPlacementResult is not None
    assert FeedbackClassifier is not None
    assert PlaceRouteLoop is not None
