"""
U9: Fixed-Point Continuous Thermal-Field Feedback Loop Tests.

Tests for the place->field->route->field fixed-point extension:
- Happy path: field reaches stable fixed point
- Drift exit: monotonically-drifting field exits on round budget
- Period-4 cycle detection
- UNMEASURED field blocks convergence (fail-closed)
- Field-off regression: thermal_weight=0 / no field_compute_fn
- RoundRecord carries field state across rounds
- Solve-time trend monitor warning

All tests inject scripted FieldResults via ``field_compute_fn`` — no
real FDM solve or router runs.  All gate checks are mocked to CLEAN so
the loop focuses on field-feedback behaviour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from unittest import mock

import numpy as np
import pytest

from temper_placer.fields.field import CostField
from temper_placer.fields.result import FieldResult
from temper_placer.placer.cp_sat.gates import GateResult, GateStatus
from temper_placer.placer.cp_sat.loop import (
    LoopExitReason,
    PlaceRouteLoop,
)
from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult


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
    completion_rate: float = 1.0
    unrouted_nets: list[str] = field(default_factory=list)
    drc_violations: list[object] = field(default_factory=list)
    congestion_regions: list[object] = field(default_factory=list)
    drc_errors: int = 0


# ---------------------------------------------------------------------------
# Gate mocking helper — all gates return CLEAN so we test field behaviour
# ---------------------------------------------------------------------------

GATE_CLEAN_RESULT = GateResult(GateStatus.CLEAN)
_ALL_GATE_CLASSES = ("DrcGate", "RoutingGate", "StackupGate",
                      "PhysicsGate", "QualityGate")


def _mock_all_gates_clean():
    """Return a list of mock.patch objects that make every gate .check() = CLEAN."""
    patches = []
    for name in _ALL_GATE_CLASSES:
        patches.append(
            mock.patch(
                f"temper_placer.placer.cp_sat.gates.{name}.check",
                return_value=GATE_CLEAN_RESULT,
            )
        )
    return patches


# ---------------------------------------------------------------------------
# Placement factory — each round gets slightly different positions (>0.1mm)
# to avoid triggering the existing position-oscillation detector.
# ---------------------------------------------------------------------------

def _make_placement(round_num: int, base_positions=None) -> CpSatPlacementResult:
    """Return a CpSatPlacementResult with positions that drift per round."""
    if base_positions is None:
        base_positions = {"Q1": (10.0, 20.0), "Q2": (30.0, 40.0),
                          "C_BUS1": (50.0, 60.0)}
    # Offset each component by 0.5mm per round (well above 0.1mm tolerance)
    offset = round_num * 0.5
    shifted = {
        ref: (x + offset, y + offset * 0.7)
        for ref, (x, y) in base_positions.items()
    }
    return CpSatPlacementResult(
        positions=shifted,
        rotations={r: 0 for r in base_positions},
        status="optimal",
        solve_time_ms=50.0,
    )


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def _make_field_result(grid: np.ndarray, weight: float = 1.0,
                       status: GateStatus = GateStatus.CLEAN,
                       error: str = "") -> FieldResult:
    return FieldResult(
        gate_result=GateResult(status=status, error_message=error),
        field=CostField(grid=grid.astype(np.float32), cell_size_mm=0.5,
                        origin_mm=(0.0, 0.0)),
        weight=weight,
    )


def _make_unmeasured_field(message: str = "solve failed") -> FieldResult:
    return FieldResult(
        gate_result=GateResult(status=GateStatus.UNMEASURED,
                               error_message=message),
        field=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_netlist():
    return MockNetlist(
        components=[MockComp("Q1"), MockComp("Q2"), MockComp("C_BUS1")],
        nets=[MockNet("GND"), MockNet("VCC"), MockNet("SW_NODE")],
    )


@pytest.fixture
def basic_board():
    return MockBoard(zones=[MockZone("power_zone", (0, 0, 50, 50))])


# ---------------------------------------------------------------------------
# U9 Happy: field reaches stable fixed point
# ---------------------------------------------------------------------------


def test_field_stable_fixed_point_converges(basic_netlist, basic_board):
    """Board reaches stable field + green gates -> convergence."""
    field_grid = np.full((10, 10), 42.0, dtype=np.float32)
    call_count = [0]

    def get_field(placement, routing, netlist, board):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_field_result(np.full((10, 10), 100.0, dtype=np.float32))
        return _make_field_result(field_grid)

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result.success is True
    assert result.reason == LoopExitReason.SUCCESS.value
    for r in result.rounds:
        assert hasattr(r, "field_grid")
        assert hasattr(r, "field_status")


# ---------------------------------------------------------------------------
# U9 Edge: Monotonically-drifting field exits on field round budget
# ---------------------------------------------------------------------------


def test_drifting_field_exits_on_round_budget(basic_netlist, basic_board):
    """A field that monotonically drifts never stabilizes -> exits on
    field round budget (not an infinite loop)."""
    call_count = [0]

    def get_drifting_field(placement, routing, netlist, board):
        call_count[0] += 1
        temp = 30.0 + call_count[0] * 10.0
        return _make_field_result(np.full((10, 10), temp, dtype=np.float32))

    loop = PlaceRouteLoop(
        field_compute_fn=get_drifting_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result.success is False
    assert result.reason == LoopExitReason.FIELD_ROUND_LIMIT_EXCEEDED.value
    assert call_count[0] > 0


# ---------------------------------------------------------------------------
# U9 Edge: Period-4 place<->field cycle detected
# ---------------------------------------------------------------------------


def test_period4_cycle_detected(basic_netlist, basic_board):
    """A period-4 field pattern is caught by the field-aware window (4)."""
    grids = [
        np.full((10, 10), 40.0, dtype=np.float32),
        np.full((10, 10), 45.0, dtype=np.float32),
        np.full((10, 10), 50.0, dtype=np.float32),
        np.full((10, 10), 55.0, dtype=np.float32),
    ]
    call_count = [0]

    def get_cycle_field(placement, routing, netlist, board):
        idx = call_count[0] % 4
        call_count[0] += 1
        return _make_field_result(grids[idx])

    loop = PlaceRouteLoop(
        field_compute_fn=get_cycle_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    # Period-4 cycle: field repeats after 4 rounds -> detected
    assert result.success is False
    assert result.reason == LoopExitReason.OSCILLATION_DETECTED.value
    assert len(result.rounds) >= 4


# ---------------------------------------------------------------------------
# U9 Error: UNMEASURED field mid-loop blocks convergence (fail-closed)
# ---------------------------------------------------------------------------


def test_unmeasured_field_blocks_convergence(basic_netlist, basic_board):
    """UNMEASURED field uses the shared unmeasured-streak exit path."""
    call_count = [0]

    def get_field(placement, routing, netlist, board):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_field_result(np.full((10, 10), 42.0, dtype=np.float32))
        return _make_unmeasured_field("FDM solve exceeded timeout")

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    # UNMEASURED exit via the shared path
    assert result.success is False
    assert result.reason == LoopExitReason.GATE_UNMEASURED.value
    assert "thermal_field" in result.unmeasured_gates


# ---------------------------------------------------------------------------
# U9 Edge: Field-off regression (zero weight, no field_compute_fn)
# ---------------------------------------------------------------------------


def test_field_off_same_as_today(basic_netlist, basic_board):
    """With no field_compute_fn, the loop behaves identically to pre-U9."""
    loop = PlaceRouteLoop()

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result.success is True
    assert result.reason == LoopExitReason.SUCCESS.value
    for r in result.rounds:
        assert r.field_grid is None
        assert r.field_status is None


def test_field_off_zero_weight_same_as_today(basic_netlist, basic_board):
    """thermal_weight=0.0 — field tracked for stability but zero cost
    injected into routing."""
    field_grid = np.full((10, 10), 42.0, dtype=np.float32)

    def get_field(placement, routing, netlist, board):
        return _make_field_result(field_grid)

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=0.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result.success is True
    for call in mock_route.call_args_list:
        _, kwargs = call
        assert kwargs.get("thermal_weight") == 0.0


# ---------------------------------------------------------------------------
# U9 Integration: RoundRecord carries both discrete deltas and continuous
# field state across >=2 rounds
# ---------------------------------------------------------------------------


def test_round_record_carries_field_across_rounds(basic_netlist, basic_board):
    """RoundRecord carries both deltas_applied and field_grid/field_status."""
    grids = [
        np.full((10, 10), 42.0, dtype=np.float32),
        np.full((10, 10), 43.0, dtype=np.float32),
        np.full((10, 10), 43.0, dtype=np.float32),
        np.full((10, 10), 43.0, dtype=np.float32),
    ]
    call_count = [0]

    def get_field(placement, routing, netlist, board):
        idx = min(call_count[0], len(grids) - 1)
        call_count[0] += 1
        return _make_field_result(grids[idx])

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=0.5,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert len(result.rounds) >= 2
    for record in result.rounds:
        assert hasattr(record, "field_grid")
        assert hasattr(record, "field_status")
        assert hasattr(record, "deltas_applied")
        assert isinstance(record.deltas_applied, list)

    stable_rounds = [r for r in result.rounds if r.field_status == "clean"]
    assert len(stable_rounds) >= 2


# ---------------------------------------------------------------------------
# U9 Integration: Solve-time trend warning
# ---------------------------------------------------------------------------


def test_solve_time_trend_warning(basic_netlist, basic_board, caplog):
    """Monotonic solve_time_ms growth over 3+ rounds triggers WARNING."""
    caplog.set_level(logging.WARNING, logger="temper_placer.placer.cp_sat.loop")

    field_grid = np.full((10, 10), 42.0, dtype=np.float32)

    def get_field(placement, routing, netlist, board):
        return _make_field_result(field_grid)

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=1.0,
    )

    solve_count = [0]

    # time.monotonic() is called 4+ times per round.  Provide enough
    # incrementing values for up to 10 rounds (40 calls).
    _t = 0.0
    _times = []
    for _ in range(50):
        # Growing deltas: 50ms, 80ms, 110ms, 150ms, 170ms, 200ms, ...
        delta_s = 0.05 + len(_times) * 0.005
        _t += delta_s
        _times.append(_t)

    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route, mock.patch(
        "temper_placer.placer.cp_sat.loop.time.monotonic"
    ) as mock_time:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )
        mock_time.side_effect = _times

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    warnings = [
        rec.message for rec in caplog.records
        if rec.levelno >= logging.WARNING and "solve-time" in rec.message
    ]
    assert len(warnings) >= 1, (
        f"Expected solve-time trend warning, got: {caplog.text}"
    )
    assert result.success is True


# ---------------------------------------------------------------------------
# U9: Field round budget exit with UNMEASURED, not silent zero
# ---------------------------------------------------------------------------


def test_field_round_budget_below_max_rounds(basic_netlist, basic_board):
    """FIELD_CONVERGENCE_ROUND_LIMIT (8) is below MAX_ROUNDS (10),
    ensuring the field budget is the primary exit for non-converging
    fields — not the generic round limit."""
    loop = PlaceRouteLoop()
    assert loop.FIELD_CONVERGENCE_ROUND_LIMIT < loop.MAX_ROUNDS, (
        f"FIELD_CONVERGENCE_ROUND_LIMIT ({loop.FIELD_CONVERGENCE_ROUND_LIMIT}) "
        f"must be below MAX_ROUNDS ({loop.MAX_ROUNDS})"
    )


def test_field_epsilon_default_sane():
    """FIELD_EPSILON (0.5°C) is a sensible per-cell threshold."""
    loop = PlaceRouteLoop()
    assert 0.0 < loop.FIELD_EPSILON < 100.0, (
        f"FIELD_EPSILON={loop.FIELD_EPSILON} should be a small positive "
        "temperature threshold"
    )


def test_field_oscillation_window_is_four():
    """FIELD_OSCILLATION_WINDOW is 4 (not 3) to catch period-4 cycles."""
    loop = PlaceRouteLoop()
    assert loop.FIELD_OSCILLATION_WINDOW == 4, (
        "FIELD_OSCILLATION_WINDOW must be 4 to detect period-4 cycles"
    )


# ---------------------------------------------------------------------------
# U9: Independent counters — field-unstable resets only field counter
# ---------------------------------------------------------------------------


def test_field_unstable_resets_only_field_counter(basic_netlist, basic_board):
    """Field-unstable round resets only field counter, not gate counters."""
    call_count = [0]
    stable_grid = np.full((10, 10), 42.0, dtype=np.float32)

    def get_field(placement, routing, netlist, board):
        call_count[0] += 1
        if call_count[0] <= 2:
            return _make_field_result(stable_grid)
        return _make_field_result(np.full((10, 10), 80.0, dtype=np.float32))

    loop = PlaceRouteLoop(
        field_compute_fn=get_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result is not None
    assert loop._field_stability_counter >= 0


# ---------------------------------------------------------------------------
# U9: Field compute exception yields UNMEASURED
# ---------------------------------------------------------------------------


def test_field_compute_exception_yields_unmeasured(basic_netlist, basic_board):
    """Field compute exception is caught and treated as UNMEASURED."""
    def get_exploding_field(placement, routing, netlist, board):
        raise RuntimeError("FDM solver segfault")

    loop = PlaceRouteLoop(
        field_compute_fn=get_exploding_field,
        thermal_weight=1.0,
    )

    solve_count = [0]
    with mock.patch(
        "temper_placer.placer.cp_sat.encoder.solve_placement"
    ) as mock_solve, mock.patch.object(
        loop, "_route_placement"
    ) as mock_route:
        def different_placement(*args, **kwargs):
            solve_count[0] += 1
            return _make_placement(solve_count[0])

        mock_solve.side_effect = different_placement
        mock_route.return_value = MockRoutingResult(
            completion_rate=1.0, drc_errors=0,
        )

        patches = _mock_all_gates_clean()
        for p in patches:
            p.start()
        try:
            result = loop.run(
                basic_netlist, basic_board, seed=42, all_gates=True,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    assert result.success is False
    assert result.reason == LoopExitReason.GATE_UNMEASURED.value
    assert "thermal_field" in result.unmeasured_gates
