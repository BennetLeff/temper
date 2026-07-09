"""
U3: PlaceRouteLoop Controller Tests.

Tests for the closed-loop place->route controller including:
- Clean placement exits after 1 round
- DRC violation injection and re-solve
- Closed-loop backtracking on UNSAT deltas
- All-feedback-UNSAT surface
- N=10 round limit
- Phase 2 polish after stability
- Oscillation detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest import mock

import numpy as np
import pytest

from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    LoopResult,
    PlaceRouteLoop,
    RoundRecord,
    UnsatError,
)

# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

@dataclass
class MockComp:
    ref: str
    width: float = 10.0
    height: float = 10.0
    footprint: str = "Resistor_SMD:R_0805_2012Metric"
    pins: list = field(default_factory=list)


@dataclass
class MockNet:
    name: str


@dataclass
class MockNetlist:
    components: list[MockComp]
    nets: list[MockNet] = field(default_factory=list)

    def __post_init__(self):
        if not self.nets:
            self.nets = [MockNet("GND"), MockNet("VCC")]

    @property
    def n_components(self) -> int:
        return len(self.components)

    @property
    def n_nets(self) -> int:
        return len(self.nets)


@dataclass
class MockZone:
    name: str
    bounds: tuple[float, float, float, float]
    components: list[str] = field(default_factory=list)


@dataclass
class MockBoard:
    zones: list[MockZone]
    width: float = 100.0
    height: float = 100.0


@dataclass
class MockRoutingResult:
    completion_rate: float = 0.5
    unrouted_nets: list[str] = field(default_factory=list)
    drc_violations: list[object] = field(default_factory=list)
    congestion_regions: list[object] = field(default_factory=list)
    drc_errors: int = 0


@pytest.fixture
def basic_netlist():
    return MockNetlist(
        components=[MockComp("Q1"), MockComp("Q2"), MockComp("C_BUS1")],
        nets=[MockNet("GND"), MockNet("VCC"), MockNet("SW_NODE")],
    )


@pytest.fixture
def basic_board():
    return MockBoard(zones=[MockZone("power_zone", (0, 0, 50, 50))])


@pytest.fixture
def loop():
    return PlaceRouteLoop()


# ---------------------------------------------------------------------------
# U3.0: Data types
# ---------------------------------------------------------------------------


def test_loop_result_defaults():
    """LoopResult has sensible defaults."""
    result = LoopResult()
    assert result.success is False
    assert result.rounds == []


def test_round_record():
    """RoundRecord stores per-round data."""
    record = RoundRecord(
        round_number=1,
        completion_rate=0.95,
        drc_errors=2,
        solve_time_ms=150.0,
        route_time_ms=500.0,
        status="optimal",
    )
    assert record.completion_rate == 0.95
    assert record.drc_errors == 2


def test_unsat_error():
    """UnsatError carries delta information."""
    delta = object()
    err = UnsatError(deltas=[delta], message="test")
    assert len(err.deltas) == 1
    assert err.deltas[0] is delta


# ---------------------------------------------------------------------------
# U3.1: Clean placement exits after 1 round (with 2 stability)
# ---------------------------------------------------------------------------


def test_clean_placement_exits_with_success(loop, basic_netlist, basic_board):
    """A placement that routes 100% immediately succeeds after 2 stability rounds."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        pos = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
        rot = np.array([0, 0, 0], dtype=np.int32)

        cp_result = CpSatPlacementResult(
            positions=pos,
            rotations=rot,
            placed_refs=["Q1", "Q2", "C_BUS1"],
            status="optimal",
            solve_time_ms=50.0,
        )

        mock_solve.return_value = cp_result
        mock_route.return_value = MockRoutingResult(completion_rate=1.0, drc_errors=0)

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is True
        assert len(result.rounds) >= 2  # At least 2 stable rounds needed


# ---------------------------------------------------------------------------
# U3.2: One clearance violation -> loop injects delta, re-solves -> success
# ---------------------------------------------------------------------------


def test_single_clearance_violation_converges(loop, basic_netlist, basic_board):
    """One clearance violation injects SeparatedConstraint and re-solves."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        pos = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
        rot = np.array([0, 0, 0], dtype=np.int32)

        cp_ok = CpSatPlacementResult(
            positions=pos, rotations=rot,
            placed_refs=["Q1", "Q2", "C_BUS1"],
            status="optimal", solve_time_ms=50.0,
        )

        # Round 1: DRC violations found
        # Round 2: Delta injected, resolve works -> clean
        mock_solve.return_value = cp_ok
        mock_route.side_effect = [
            MockRoutingResult(
                completion_rate=1.0, drc_errors=1,
                drc_violations=[type("V", (), {"comp_a": "Q1", "comp_b": "Q2", "required_mm": 6.0})()],
            ),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
        ]

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is True
        assert any(r.drc_errors == 1 for r in result.rounds)
        assert any(r.drc_errors == 0 for r in result.rounds)


# ---------------------------------------------------------------------------
# U3.3: Injected delta UNSAT -> backtrack to next signal
# ---------------------------------------------------------------------------


def test_closed_loop_backtracking(loop, basic_netlist, basic_board):
    """When one delta is UNSAT, loop tries the next-strongest signal."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_solve_with_delta"
    ) as mock_solve_delta:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        pos = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
        rot = np.array([0, 0, 0], dtype=np.int32)

        cp_ok = CpSatPlacementResult(
            positions=pos, rotations=rot,
            placed_refs=["Q1", "Q2", "C_BUS1"],
            status="optimal", solve_time_ms=50.0,
        )

        mock_solve.return_value = cp_ok

        # Round 1: has both clearance violation + congestion
        # -> classifier produces 2 deltas: clearance (prio=5) and congestion (prio=10)
        # First delta (clearance) UNSAT, second (congestion) works -> backtracking
        mock_route.side_effect = [
            MockRoutingResult(
                completion_rate=1.0, drc_errors=1,
                drc_violations=[type("V", (), {"comp_a": "Q1", "comp_b": "Q2", "required_mm": 6.0})()],
                congestion_regions=[
                    type("CR", (), {"comp_a": "Q1", "comp_b": "C_BUS1", "current_distance_mm": 2.0})()
                ],
            ),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
            MockRoutingResult(completion_rate=1.0, drc_errors=0),
        ]

        # First delta (clearance) UNSAT, second (congestion) works
        mock_solve_delta.side_effect = [
            UnsatError(deltas=[], message="clearance unsat"),
            cp_ok,  # congestion works
            cp_ok, cp_ok, cp_ok,
        ]

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is True


# ---------------------------------------------------------------------------
# U3.4: All deltas UNSAT -> exit with unsat_core
# ---------------------------------------------------------------------------


def test_all_feedback_unsat_exits(loop, basic_netlist, basic_board):
    """When all feedback deltas produce UNSAT, loop exits with diagnostic."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_solve_with_delta"
    ) as mock_solve_delta:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        pos = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
        rot = np.array([0, 0, 0], dtype=np.int32)
        cp_ok = CpSatPlacementResult(
            positions=pos, rotations=rot,
            placed_refs=["Q1", "Q2", "C_BUS1"],
            status="optimal", solve_time_ms=50.0,
        )

        mock_solve.return_value = cp_ok
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0,
            drc_errors=1,
            drc_violations=[type("V", (), {"comp_a": "Q1", "comp_b": "Q2", "required_mm": 6.0})()],
        )

        # All deltas UNSAT
        mock_solve_delta.side_effect = UnsatError(deltas=[], message="unsat")

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is False
        assert result.reason == LoopExitReason.ALL_FEEDBACK_UNSAT.value
        assert result.unsat_core is not None


# ---------------------------------------------------------------------------
# U3.5: N=10 rounds without convergence
# ---------------------------------------------------------------------------


def test_round_limit_exceeded(loop, basic_netlist, basic_board):
    """After 10 rounds without full success, loop exits with ROUND_LIMIT_EXCEEDED."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_solve_with_delta"
    ) as mock_solve_delta:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        # Return slightly different positions each round to avoid oscillation
        call_count = [0]
        def make_placement(*args, **kwargs):
            call_count[0] += 1
            x_offset = call_count[0] * 0.5
            pos = np.array(
                [[10.0 + x_offset, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32
            )
            rot = np.array([0, 0, 0], dtype=np.int32)
            return CpSatPlacementResult(
                positions=pos, rotations=rot,
                placed_refs=["Q1", "Q2", "C_BUS1"],
                status="optimal", solve_time_ms=50.0,
            )

        mock_solve.side_effect = make_placement
        mock_solve_delta.side_effect = make_placement
        # Always 85% completion with drc violations -> never converges
        mock_route.return_value = MockRoutingResult(
            completion_rate=0.85,
            drc_errors=2,
            drc_violations=[type("V", (), {"comp_a": "Q1", "comp_b": "Q2", "required_mm": 6.0})()],
        )

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is False
        assert result.reason == LoopExitReason.ROUND_LIMIT_EXCEEDED.value
        assert len(result.rounds) == PlaceRouteLoop.MAX_ROUNDS


# ---------------------------------------------------------------------------
# U3.6: Stability detection
# ---------------------------------------------------------------------------


def test_consecutive_stable_rounds(loop):
    """_consecutive_stable_rounds counts correctly."""
    rounds = [
        RoundRecord(1, completion_rate=1.0, drc_errors=0),
        RoundRecord(2, completion_rate=1.0, drc_errors=0),
        RoundRecord(3, completion_rate=0.9, drc_errors=1),
    ]
    assert loop._consecutive_stable_rounds(rounds) == 0  # Last round not stable

    rounds_stable = [
        RoundRecord(1, completion_rate=1.0, drc_errors=0),
        RoundRecord(2, completion_rate=1.0, drc_errors=0),
    ]
    assert loop._consecutive_stable_rounds(rounds_stable) == 2


# ---------------------------------------------------------------------------
# U3.7: Oscillation detection
# ---------------------------------------------------------------------------


def test_no_oscillation_with_few_rounds(loop):
    """Oscillation detection requires at least 3 rounds in history."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    pos = np.array([[10.0, 20.0]], dtype=np.float32)
    p = CpSatPlacementResult(positions=pos, rotations=np.array([0], dtype=np.int32), placed_refs=["Q1"])
    history = [p] * 2  # only 2 rounds
    assert loop._detect_oscillation(p, history) is False


def test_oscillation_detected_on_repeat(loop):
    """Same placement repeating triggers oscillation detection."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    pos = np.array([[10.0, 20.0]], dtype=np.float32)
    p1 = CpSatPlacementResult(positions=pos, rotations=np.array([0], dtype=np.int32), placed_refs=["Q1"])
    p2 = CpSatPlacementResult(positions=pos.copy(), rotations=np.array([0], dtype=np.int32), placed_refs=["Q1"])
    p3 = CpSatPlacementResult(positions=pos.copy(), rotations=np.array([0], dtype=np.int32), placed_refs=["Q1"])

    history = [p1, p2, p3]
    assert loop._detect_oscillation(p3, history) is True


# ---------------------------------------------------------------------------
# U3.8: UNSAT placement early exit
# ---------------------------------------------------------------------------


def test_infeasible_placement_exits_early(loop, basic_netlist, basic_board):
    """If initial placement is infeasible, loop returns with UNSAT core."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve:
        from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

        unsat_result = CpSatPlacementResult(
            positions=np.zeros((3, 2), dtype=np.float32),
            rotations=np.zeros(3, dtype=np.int32),
            placed_refs=[],
            unplaced_refs=["Q1", "Q2", "C_BUS1"],
            status="infeasible",
        )
        mock_solve.return_value = unsat_result

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is False
        assert result.reason == LoopExitReason.ALL_FEEDBACK_UNSAT.value
