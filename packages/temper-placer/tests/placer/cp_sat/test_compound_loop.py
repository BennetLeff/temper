"""U2: Compound Place-Route Loop — Gate Registry + all_gates_green Tests.

Covers:
- Gate registry initialization and default gates
- all_gates_green truth table (CLEAN / VIOLATIONS / UNMEASURED)
- Gate-driven convergence in run()
- Backward compatibility when gates=[] (classifier path preserved)
- Gate check exceptions → UNMEASURED
- _collect_deltas_from_gates and _build_board_state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest import mock

import pytest

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)
from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    PlaceRouteLoop,
    UnsatError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cp_result(refs=("Q1", "Q2", "C_BUS1"), status="optimal"):
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    positions = {r: (float(i * 20 + 10), float(i * 20 + 20)) for i, r in enumerate(refs)}
    rotations = {r: 0 for r in refs}
    return CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        status=status,
        solve_time_ms=50.0,
    )


# ---------------------------------------------------------------------------
# Test gates — controllable for truth-table testing
# ---------------------------------------------------------------------------


class AlwaysCleanGate(Gate):
    stage = GateStage.ROUTING
    name = "always_clean"

    def check(self, state: BoardState) -> GateResult:
        return GateResult(GateStatus.CLEAN)


class AlwaysViolationsGate(Gate):
    stage = GateStage.ROUTING
    name = "always_violations"

    def check(self, state: BoardState) -> GateResult:
        v = Violation(type=ViolationType.CLEARANCE, description="test violation")
        return GateResult(GateStatus.VIOLATIONS, violations=(v,))

    def to_delta(self, violation: Violation):
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta

        return ConstraintDelta(
            constraint=object(), reason="test delta", priority=1,
        )


class AlwaysUnmeasuredGate(Gate):
    stage = GateStage.ROUTING
    name = "always_unmeasured"

    def check(self, state: BoardState) -> GateResult:
        return GateResult(
            GateStatus.UNMEASURED,
            error_message="kicad-cli exit 3",
        )


class RaisesGate(Gate):
    stage = GateStage.ROUTING
    name = "raises_gate"

    def check(self, state: BoardState) -> GateResult:
        raise RuntimeError("simulated crash")


# ---------------------------------------------------------------------------
# U2.1: Gate registry + all_gates_green truth table
# ---------------------------------------------------------------------------


class TestAllGatesGreen:
    def test_empty_registry_trivially_green(self):
        """With no gates, all_gates_green returns True (vacuously)."""
        loop = PlaceRouteLoop(gates=[])
        state = BoardState()
        assert loop.all_gates_green(state) is True
        assert loop._gate_results == {}

    def test_all_clean_is_green(self):
        """Registry with all-CLEAN gates → True."""
        loop = PlaceRouteLoop(gates=[AlwaysCleanGate(), AlwaysCleanGate()])
        state = BoardState()
        assert loop.all_gates_green(state) is True

    def test_one_violations_not_green(self):
        """One VIOLATIONS gate blocks convergence."""
        loop = PlaceRouteLoop(
            gates=[AlwaysCleanGate(), AlwaysViolationsGate()],
        )
        state = BoardState()
        assert loop.all_gates_green(state) is False

    def test_one_unmeasured_not_green(self):
        """One UNMEASURED gate blocks convergence — core invariant."""
        loop = PlaceRouteLoop(
            gates=[AlwaysCleanGate(), AlwaysUnmeasuredGate()],
        )
        state = BoardState()
        assert loop.all_gates_green(state) is False
        assert loop._gate_results["always_unmeasured"].status is GateStatus.UNMEASURED

    def test_unmeasured_never_green_even_with_empty_violations(self):
        """Architectural heart: UNMEASURED with zero violations ≠ CLEAN."""
        loop = PlaceRouteLoop(gates=[AlwaysUnmeasuredGate()])
        state = BoardState()
        assert loop.all_gates_green(state) is False
        result = loop._gate_results["always_unmeasured"]
        assert result.status is GateStatus.UNMEASURED
        assert result.violations == ()

    def test_mixed_unmeasured_and_violations(self):
        """Both non-CLEAN statuses → False."""
        loop = PlaceRouteLoop(
            gates=[AlwaysUnmeasuredGate(), AlwaysViolationsGate()],
        )
        state = BoardState()
        assert loop.all_gates_green(state) is False

    def test_gate_check_exception_becomes_unmeasured(self):
        """A gate that raises during check() is caught and logged as UNMEASURED."""
        loop = PlaceRouteLoop(gates=[RaisesGate()])
        state = BoardState()
        assert loop.all_gates_green(state) is False
        result = loop._gate_results["raises_gate"]
        assert result.status is GateStatus.UNMEASURED
        assert "simulated crash" in result.error_message

    def test_results_stored_per_gate_name(self):
        """_gate_results maps gate.name → result."""
        loop = PlaceRouteLoop(
            gates=[AlwaysCleanGate(), AlwaysUnmeasuredGate()],
        )
        loop.all_gates_green(BoardState())
        assert "always_clean" in loop._gate_results
        assert "always_unmeasured" in loop._gate_results
        assert loop._gate_results["always_clean"].status is GateStatus.CLEAN


# ---------------------------------------------------------------------------
# U2.2: _build_board_state
# ---------------------------------------------------------------------------


class TestBuildBoardState:
    def test_builds_with_placement_and_routing(self):
        """_build_board_state assembles a BoardState from pipeline objects."""
        loop = PlaceRouteLoop()
        fake_placement = object()
        fake_routing = object()
        fake_netlist = object()
        fake_board = object()

        state = loop._build_board_state(
            fake_placement, fake_routing, fake_netlist, fake_board,
        )
        assert state.placement is fake_placement
        assert state.routing is fake_routing
        assert state.netlist is fake_netlist
        assert state.board is fake_board

    def test_builds_with_none_routing(self):
        """BoardState handles routing=None gracefully."""
        loop = PlaceRouteLoop()
        state = loop._build_board_state(
            object(), None, object(), object(),
        )
        assert state.routing is None
        assert state.routed_pcb_path is None


# ---------------------------------------------------------------------------
# U2.3: _collect_deltas_from_gates
# ---------------------------------------------------------------------------


class TestCollectDeltasFromGates:
    def test_clean_gates_produce_no_deltas(self):
        """CLEAN gates contribute no deltas."""
        loop = PlaceRouteLoop(gates=[AlwaysCleanGate()])
        loop.all_gates_green(BoardState())
        deltas = loop._collect_deltas_from_gates()
        assert deltas == []

    def test_violations_gate_produces_deltas(self):
        """VIOLATIONS gate's to_delta is called and deltas collected."""
        loop = PlaceRouteLoop(gates=[AlwaysViolationsGate()])
        loop.all_gates_green(BoardState())
        deltas = loop._collect_deltas_from_gates()
        assert len(deltas) == 1
        assert deltas[0].reason == "test delta"

    def test_unmeasured_gate_produces_no_deltas(self):
        """UNMEASURED has no violations → no deltas."""
        loop = PlaceRouteLoop(gates=[AlwaysUnmeasuredGate()])
        loop.all_gates_green(BoardState())
        deltas = loop._collect_deltas_from_gates()
        assert deltas == []


# ---------------------------------------------------------------------------
# U2.4: _gates_for_stage
# ---------------------------------------------------------------------------


class PlacementGate(Gate):
    stage = GateStage.PLACEMENT
    name = "placement_gate"

    def check(self, state: BoardState) -> GateResult:
        return GateResult(GateStatus.CLEAN)


class TestGatesForStage:
    def test_filters_by_stage(self):
        """_gates_for_stage returns only gates of the requested stage."""
        gates = [PlacementGate(), AlwaysCleanGate(), AlwaysUnmeasuredGate()]
        loop = PlaceRouteLoop(gates=gates)
        placement_gates = loop._gates_for_stage(gates, GateStage.PLACEMENT)
        routing_gates = loop._gates_for_stage(gates, GateStage.ROUTING)

        assert len(placement_gates) == 1
        assert placement_gates[0].name == "placement_gate"
        assert len(routing_gates) == 2


# ---------------------------------------------------------------------------
# U2.5: Gate-driven convergence in run()
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


class TestGateDrivenConvergence:
    def test_all_green_converges_to_success(self, basic_netlist, basic_board):
        """When all gates are green for STABILITY_ROUNDS, loop returns SUCCESS."""
        loop = PlaceRouteLoop(gates=[AlwaysCleanGate()])

        with mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement"
        ) as mock_solve, mock.patch.object(
            loop, "_route_placement"
        ) as mock_route, mock.patch.object(
            loop, "_solve_phase2"
        ) as mock_phase2, mock.patch.object(
            loop, "_detect_oscillation", return_value=False,
        ), mock.patch.object(
            loop, "_are_named_gates_clean", return_value=True,
        ):
            cp_result = _make_cp_result()

            mock_solve.return_value = cp_result
            mock_route.return_value = MockRoutingResult(completion_rate=1.0, drc_errors=0)
            mock_phase2.return_value = cp_result

            result = loop.run(basic_netlist, basic_board, seed=42)
            assert result.success is True
            assert result.reason == LoopExitReason.SUCCESS.value
            assert len(result.rounds) >= 2  # STABILITY_ROUNDS

    def test_violations_inject_deltas_and_continue(self, basic_netlist, basic_board):
        """VIOLATIONS gate → deltas injected → loop continues."""
        loop = PlaceRouteLoop(gates=[AlwaysViolationsGate()])

        with mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement"
        ) as mock_solve, mock.patch.object(
            loop, "_route_placement"
        ) as mock_route, mock.patch.object(
            loop, "_solve_with_delta"
        ) as mock_solve_delta, mock.patch.object(
            loop, "_detect_oscillation", return_value=False,
        ):
            cp_result = _make_cp_result()

            mock_solve.return_value = cp_result
            mock_route.return_value = MockRoutingResult(completion_rate=0.5)
            mock_solve_delta.return_value = cp_result

            # Violations every round → never converges → hits round limit
            result = loop.run(basic_netlist, basic_board, seed=42)
            assert result.success is False
            assert result.reason == LoopExitReason.ROUND_LIMIT_EXCEEDED.value
            assert len(result.rounds) == PlaceRouteLoop.MAX_ROUNDS

    def test_gate_deltas_unsat_exits(self, basic_netlist, basic_board):
        """When all gate deltas are UNSAT, loop exits with ALL_FEEDBACK_UNSAT."""
        loop = PlaceRouteLoop(gates=[AlwaysViolationsGate()])

        with mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement"
        ) as mock_solve, mock.patch.object(
            loop, "_route_placement"
        ) as mock_route, mock.patch.object(
            loop, "_solve_with_delta"
        ) as mock_solve_delta, mock.patch.object(
            loop, "_detect_oscillation", return_value=False,
        ):
            cp_result = _make_cp_result()

            mock_solve.return_value = cp_result
            mock_route.return_value = MockRoutingResult(completion_rate=0.5)
            mock_solve_delta.side_effect = UnsatError(deltas=[], message="unsat")

            result = loop.run(basic_netlist, basic_board, seed=42)
            assert result.success is False
            assert result.reason == LoopExitReason.ALL_FEEDBACK_UNSAT.value
            assert result.unsat_core is not None
            assert "gate_results" in result.unsat_core

    def test_unmeasured_blocks_convergence(self, basic_netlist, basic_board):
        """UNMEASURED gate blocks convergence; loop exits with GATE_UNMEASURED."""
        loop = PlaceRouteLoop(gates=[AlwaysUnmeasuredGate()])

        with mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement"
        ) as mock_solve, mock.patch.object(
            loop, "_route_placement"
        ) as mock_route, mock.patch.object(
            loop, "_detect_oscillation", return_value=False,
        ):
            cp_result = _make_cp_result()

            mock_solve.return_value = cp_result
            mock_route.return_value = MockRoutingResult(completion_rate=1.0, drc_errors=0)

            result = loop.run(basic_netlist, basic_board, seed=42)
            assert result.success is False
            assert result.reason == LoopExitReason.GATE_UNMEASURED.value


# ---------------------------------------------------------------------------
# U2.6: Backward compatibility — empty gates preserves old path
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_empty_gates_preserves_classifier_path(self, basic_netlist, basic_board):
        """When gates=[], the old classifier-driven convergence is used."""
        loop = PlaceRouteLoop(gates=[])

        with mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement"
        ) as mock_solve, mock.patch.object(
            loop, "_route_placement"
        ) as mock_route, mock.patch.object(
            loop, "_detect_oscillation", return_value=False,
        ):
            cp_result = _make_cp_result()

            mock_solve.return_value = cp_result
            mock_route.return_value = MockRoutingResult(completion_rate=1.0, drc_errors=0)

            result = loop.run(basic_netlist, basic_board, seed=42)
            # With empty gates, the old completion_rate>=1.0 && drc_errors==0
            # convergence check fires (needs STABILITY_ROUNDS of green)
            assert result.success is True
            assert result.reason == LoopExitReason.SUCCESS.value


# ---------------------------------------------------------------------------
# U2.7: Default registry contains DrcGate + RoutingGate
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    def test_default_constructor_registers_two_gates(self):
        """PlaceRouteLoop() with no args creates DrcGate + RoutingGate."""
        loop = PlaceRouteLoop()
        assert len(loop.gates) == 2
        names = {g.name for g in loop.gates}
        assert names == {"drc", "routing"}
        stages = {g.stage for g in loop.gates}
        assert GateStage.PLACEMENT in stages
        assert GateStage.ROUTING in stages

    def test_explicit_gates_override_default(self):
        """Passing gates= overrides the default registry."""
        loop = PlaceRouteLoop(gates=[AlwaysCleanGate()])
        assert len(loop.gates) == 1
        assert loop.gates[0].name == "always_clean"
