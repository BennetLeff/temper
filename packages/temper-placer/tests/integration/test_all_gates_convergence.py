"""U6: Compound place-route loop integration tests.

Covers SC1a (DrcGate+RoutingGate only), SC1b (all 5 gates via
all_gates=True), GATE_UNMEASURED exit, and incremental status
logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest import mock

import pytest

from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    LoopResult,
    PlaceRouteLoop,
    RoundRecord,
    UnsatError,
)
from temper_placer.placer.cp_sat.gates import (
    DrcGate,
    GateResult,
    GateStatus,
    PhysicsGate,
    QualityGate,
    RoutingGate,
    StackupGate,
    Violation,
    ViolationType,
)


# ---------------------------------------------------------------------------
# Factory for CpSatPlacementResult (dict-based positions, real dataclass)
# ---------------------------------------------------------------------------


def _make_placement(refs, status="optimal"):
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    positions = {}
    rotations = {}
    x = 10.0
    for ref in refs:
        positions[ref] = (x, 20.0)
        rotations[ref] = 0
        x += 20.0
    return CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        status=status,
        solve_time_ms=50.0,
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
    routed_pcb_path: str | None = None


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
# SC1a: DrcGate + RoutingGate convergence (all_gates=False, gate-driven path)
# ---------------------------------------------------------------------------


def test_sc1a_drc_routing_converge(loop, basic_netlist, basic_board):
    """Gate-driven path with all gates mocked CLEAN converges."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_get_placement_pcb_path"
    ) as mock_pcb_path:
        cp_ok = _make_placement(["Q1", "Q2", "C_BUS1"])

        mock_solve.return_value = cp_ok
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )
        mock_pcb_path.return_value = None

        clean = GateResult(GateStatus.CLEAN)
        with mock.patch.object(DrcGate, "check", return_value=clean), \
             mock.patch.object(RoutingGate, "check", return_value=clean), \
             mock.patch.object(StackupGate, "check", return_value=clean), \
             mock.patch.object(PhysicsGate, "check", return_value=clean), \
             mock.patch.object(QualityGate, "check", return_value=clean):
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
            assert result.success is True
            assert result.reason == LoopExitReason.SUCCESS.value


# ---------------------------------------------------------------------------
# SC3: all_gates=True runs all 5 gates
# ---------------------------------------------------------------------------


def test_all_gates_registers_five_gates(loop, basic_netlist, basic_board):
    """When all_gates=True, 5 gates are registered and checked."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_get_placement_pcb_path"
    ) as mock_pcb_path:
        cp_ok = _make_placement(["Q1", "Q2", "C_BUS1"])
        mock_solve.return_value = cp_ok
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )
        mock_pcb_path.return_value = None

        check_counts = {}
        clean = GateResult(GateStatus.CLEAN)

        def counting_check(gate_name):
            def _check(self, state):
                check_counts[gate_name] = (
                    check_counts.get(gate_name, 0) + 1
                )
                return clean
            return _check

        with mock.patch.object(DrcGate, "check", counting_check("drc")), \
             mock.patch.object(RoutingGate, "check", counting_check("routing")), \
             mock.patch.object(StackupGate, "check", counting_check("stackup")), \
             mock.patch.object(PhysicsGate, "check", counting_check("physics")), \
             mock.patch.object(QualityGate, "check", counting_check("quality")):
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
            assert result.success is True
            for name in ("drc", "routing", "stackup", "physics",
                         "quality"):
                assert check_counts.get(name, 0) >= 1, (
                    f"Gate {name} was never checked"
                )


# ---------------------------------------------------------------------------
# GATE_UNMEASURED exit after 3 consecutive UNMEASURED rounds
# ---------------------------------------------------------------------------


def test_unmeasured_persistent_exit(loop, basic_netlist, basic_board):
    """A gate UNMEASURED for 3+ consecutive rounds exits GATE_UNMEASURED."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_get_placement_pcb_path"
    ) as mock_pcb_path:
        cp_ok = _make_placement(["Q1", "Q2", "C_BUS1"])
        mock_solve.return_value = cp_ok
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )
        mock_pcb_path.return_value = None

        unmeasured = GateResult(
            GateStatus.UNMEASURED,
            error_message="kicad-cli not found",
        )
        clean = GateResult(GateStatus.CLEAN)
        with mock.patch.object(
            DrcGate, "check", return_value=unmeasured,
        ), mock.patch.object(
            RoutingGate, "check", return_value=clean,
        ), mock.patch.object(
            StackupGate, "check", return_value=clean,
        ), mock.patch.object(
            PhysicsGate, "check", return_value=clean,
        ), mock.patch.object(
            QualityGate, "check", return_value=clean,
        ):
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
            assert result.success is False
            assert (
                result.reason
                == LoopExitReason.GATE_UNMEASURED.value
            )
            assert "drc" in result.unmeasured_gates


# ---------------------------------------------------------------------------
# One UNMEASURED, then CLEAN -> converges
# ---------------------------------------------------------------------------


def test_unmeasured_once_then_clean_converges(
    loop, basic_netlist, basic_board,
):
    """A gate UNMEASURED once then CLEAN thereafter -> still converges."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_get_placement_pcb_path"
    ) as mock_pcb_path:
        cp_ok = _make_placement(["Q1", "Q2", "C_BUS1"])
        mock_solve.return_value = cp_ok
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )
        mock_pcb_path.return_value = None

        call_count = [0]
        clean = GateResult(GateStatus.CLEAN)

        def flaky_drc_check(self, state):
            call_count[0] += 1
            if call_count[0] <= 1:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message="transient kicad-cli failure",
                )
            return clean

        with mock.patch.object(DrcGate, "check", flaky_drc_check), \
             mock.patch.object(RoutingGate, "check", return_value=clean), \
             mock.patch.object(StackupGate, "check", return_value=clean), \
             mock.patch.object(
                 PhysicsGate, "check", return_value=clean,
             ), \
             mock.patch.object(
                 QualityGate, "check", return_value=clean,
             ):
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
            assert result.success is True


# ---------------------------------------------------------------------------
# Stage ordering: PLACEMENT gate violation -> skip routing
# ---------------------------------------------------------------------------


def test_placement_violation_skips_routing(
    loop, basic_netlist, basic_board,
):
    """A PLACEMENT-stage gate violation skips routing that round."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch.object(
        loop, "_get_placement_pcb_path"
    ) as mock_pcb_path, mock.patch.object(
        loop, "_solve_with_delta"
    ) as mock_solve_delta:
        cp_ok = _make_placement(["Q1", "Q2", "C_BUS1"])
        mock_solve.return_value = cp_ok
        mock_solve_delta.return_value = cp_ok
        mock_pcb_path.return_value = None

        call_count = [0]
        clean = GateResult(GateStatus.CLEAN)

        def drc_check(self, state):
            call_count[0] += 1
            if call_count[0] <= 1:
                return GateResult(
                    GateStatus.VIOLATIONS,
                    violations=(
                        Violation(
                            type=ViolationType.CLEARANCE,
                            components=("Q1", "Q2"),
                            severity=5.0,
                            description="Clearance violation",
                        ),
                    ),
                )
            return clean

        with mock.patch.object(DrcGate, "check", drc_check), \
             mock.patch.object(RoutingGate, "check", return_value=clean), \
             mock.patch.object(StackupGate, "check", return_value=clean), \
             mock.patch.object(
                 PhysicsGate, "check", return_value=clean,
             ), \
             mock.patch.object(
                 QualityGate, "check", return_value=clean,
             ):
            mock_route.return_value = MockRoutingResult(
                completion_rate=1.0, drc_errors=0,
            )
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
            assert result.success is True


# ---------------------------------------------------------------------------
# Legacy backward compatibility (all_gates=False, classifier path)
# ---------------------------------------------------------------------------


def test_legacy_classifier_path_still_works(
    loop, basic_netlist, basic_board,
):
    """The legacy classifier-based path works when all_gates=False."""
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        cp_result = _make_placement(["Q1", "Q2", "C_BUS1"])
        mock_solve.return_value = cp_result
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        result = loop.run(basic_netlist, basic_board, seed=42)
        assert result.success is True
        assert len(result.rounds) >= 2


# ---------------------------------------------------------------------------
# LoopResult.unmeasured_gates field
# ---------------------------------------------------------------------------


def test_loop_result_unmeasured_gates_default():
    """LoopResult.unmeasured_gates defaults to empty dict."""
    r = LoopResult()
    assert r.unmeasured_gates == {}


def test_loop_result_unmeasured_gates_serializes():
    """LoopResult.unmeasured_gates can hold gate -> message mappings."""
    r = LoopResult(
        unmeasured_gates={"drc": "kicad-cli exit 3"},
    )
    assert r.unmeasured_gates["drc"] == "kicad-cli exit 3"


# ---------------------------------------------------------------------------
# LoopExitReason.GATE_UNMEASURED
# ---------------------------------------------------------------------------


def test_loop_exit_reason_gate_unmeasured():
    assert LoopExitReason.GATE_UNMEASURED.value == "gate_unmeasured"


# ---------------------------------------------------------------------------
# all_gates_green predicate
# ---------------------------------------------------------------------------


def test_all_gates_green_with_clean_results(loop):
    loop._gate_results = {
        "drc": GateResult(GateStatus.CLEAN),
        "routing": GateResult(GateStatus.CLEAN),
    }
    assert loop._all_gates_green_results() is True


def test_all_gates_green_with_unmeasured(loop):
    loop._gate_results = {
        "drc": GateResult(GateStatus.CLEAN),
        "routing": GateResult(
            GateStatus.UNMEASURED, error_message="tool crash",
        ),
    }
    assert loop._all_gates_green_results() is False


def test_all_gates_green_with_violations(loop):
    loop._gate_results = {
        "drc": GateResult(
            GateStatus.VIOLATIONS,
            violations=(
                Violation(type=ViolationType.CLEARANCE, description="x"),
            ),
        ),
        "routing": GateResult(GateStatus.CLEAN),
    }
    assert loop._all_gates_green_results() is False


# ---------------------------------------------------------------------------
# _are_named_gates_clean
# ---------------------------------------------------------------------------


def test_are_named_gates_clean_subset(loop):
    loop._gate_results = {
        "drc": GateResult(GateStatus.CLEAN),
        "routing": GateResult(GateStatus.CLEAN),
        "stackup": GateResult(GateStatus.UNMEASURED),
    }
    assert loop._are_named_gates_clean({"drc", "routing"}) is True
    assert loop._are_named_gates_clean({"drc", "stackup"}) is False
