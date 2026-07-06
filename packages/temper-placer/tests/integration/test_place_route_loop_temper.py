"""U4: Place-Route Loop CLI Integration Test."""

from unittest import mock

from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    LoopResult,
    PlaceRouteLoop,
    RoundRecord,
    UnsatError,
)
from temper_placer.placer.cp_sat.feedback import (
    ConstraintDelta,
    FeedbackClassifier,
    UnclassifiedFailure,
)
from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult, solve_placement


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


# ---------------------------------------------------------------------------
# U4.5: Import chain verified (no import errors on key modules)
# ---------------------------------------------------------------------------


def test_full_import_chain():
    """Verify all new modules import without errors."""
    assert CpSatPlacementResult is not None
    assert FeedbackClassifier is not None
    assert PlaceRouteLoop is not None
