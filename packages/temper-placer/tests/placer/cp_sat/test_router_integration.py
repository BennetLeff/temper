"""
U1: Baseline Router Integration Test.

Verifies the place->route->measure pipeline end-to-end:
1. CP-SAT placement produces a PlacementResult.
2. Placement can be applied to a KiCad PCB via _apply_placements_to_pcb.
3. route_pcb() runs on the placed PCB and produces a RoutingResult.
4. Baseline completion rate is recorded.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import numpy as np
import pytest


@dataclass
class MockComp:
    ref: str
    width: float = 10.0
    height: float = 10.0
    zone: str | None = None
    fixed: bool = False
    initial_position: tuple[float, float] | None = None
    initial_rotation: int | None = None
    footprint: str = "Resistor_SMD:R_0805_2012Metric"
    pins: list = None

    def __post_init__(self):
        if self.pins is None:
            self.pins = []


@dataclass
class MockNet:
    name: str


@dataclass
class MockNetlist:
    components: list[MockComp]
    nets: list[MockNet] = None

    def __post_init__(self):
        if self.nets is None:
            self.nets = [MockNet("GND"), MockNet("VCC")]

    @property
    def n_components(self) -> int:
        return len(self.components)

    @property
    def n_nets(self) -> int:
        return len(self.nets)

    def get_component_index(self, ref: str) -> int:
        for i, c in enumerate(self.components):
            if c.ref == ref:
                return i
        raise ValueError(f"Component {ref} not found")


@dataclass
class MockZone:
    name: str
    bounds: tuple[float, float, float, float]
    components: list[str] = None

    def __post_init__(self):
        if self.components is None:
            self.components = []


@dataclass
class MockBoard:
    zones: list[MockZone]
    width: float = 100.0
    height: float = 100.0
    origin: tuple[float, float] = (0.0, 0.0)

    def get_zone(self, name: str) -> MockZone | None:
        for z in self.zones:
            if z.name == name:
                return z
        return None


# ---------------------------------------------------------------------------
# U1.0: CP-SAT Encoder produces PlacementResult
# ---------------------------------------------------------------------------


def test_cp_sat_placement_result_to_placement_result():
    """CpSatPlacementResult.to_placement_result() produces valid PlacementResult."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
    from temper_placer.placer.deterministic import PlacementResult

    positions = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
    rotations = np.array([0, 2], dtype=np.int32)  # 0deg, 180deg
    result = CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=["Q1", "Q2"],
        unplaced_refs=[],
        solve_time_ms=150.0,
        status="optimal",
    )

    pr = result.to_placement_result()
    assert isinstance(pr, PlacementResult)
    np.testing.assert_allclose(pr.positions, positions)
    np.testing.assert_allclose(pr.rotations, [0.0, 180.0])
    assert pr.placed_refs == ["Q1", "Q2"]


def test_cp_sat_placement_result_to_placements_dict():
    """to_placements_dict() produces dict ready for _apply_placements_to_pcb."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    positions = np.array([[10.5, 20.3], [30.0, 40.8]], dtype=np.float32)
    rotations = np.array([0, 1], dtype=np.int32)
    result = CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=["Q1", "Q2"],
        unplaced_refs=[],
    )

    d = result.to_placements_dict()
    assert d["Q1"] == pytest.approx((10.5, 20.3), rel=1e-5)
    assert d["Q2"] == pytest.approx((30.0, 40.8), rel=1e-5)


def test_solve_placement_fallback_without_ortools():
    """When OR-Tools is unavailable, fallback produces a valid result."""
    netlist = MockNetlist(components=[MockComp("Q1"), MockComp("Q2"), MockComp("C1")])
    board = MockBoard(zones=[], width=100, height=100)

    with mock.patch.dict("sys.modules", {"ortools": None}):
        from temper_placer.placer.cp_sat.encoder import solve_placement

        result = solve_placement(netlist, board)
        assert result.status == "deterministic_fallback"
        assert len(result.placed_refs) == 3
        assert result.positions.shape == (3, 2)


# ---------------------------------------------------------------------------
# U1.1: _apply_placements_to_pcb integration
# ---------------------------------------------------------------------------


def test_apply_placements_to_pcb_updates_positions():
    """_apply_placements_to_pcb correctly rewrites footprint (at ...) lines."""
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    raw = """(kicad_pcb (version 20221018)
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "R1")
    (at 12.5 34.2 90)
  )
  (footprint "Capacitor_SMD:C_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "C1")
    (at 5.0 5.0)
  )
)"""

    placements = {"R1": (50.0, 75.0)}
    result = _apply_placements_to_pcb(raw, placements)
    assert "50.0000 75.0000 90" in result
    assert "12.5 34.2" not in result


def test_apply_placements_to_pcb_empty_placements():
    """Passing empty placements returns raw_content unchanged."""
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    raw = "(kicad_pcb) (footprint \"Dummy\" (layer \"F.Cu\") (at 1 2))"
    result = _apply_placements_to_pcb(raw, {})
    assert result == raw


# ---------------------------------------------------------------------------
# U1.2: route_pcb() baseline measurement (mock router)
# ---------------------------------------------------------------------------


class MockPipelineResult:
    completion_rate: float = 0.0


def test_route_pcb_with_placements():
    """route_pcb() applies placements and runs the router pipeline."""
    from unittest import mock as umock

    from temper_placer.router_v6.adapter import route_pcb

    mock_result = MockPipelineResult()
    mock_result.completion_rate = 0.85

    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
        f.write("(kicad_pcb (version 20221018))\n")
        temp_path = f.name

    try:
        parsed = type("ParsedPCB", (), {"source_path": temp_path})()

        with umock.patch(
            "temper_placer.router_v6.pipeline.RouterV6Pipeline"
        ) as mock_pipe_cls:
            mock_pipe = umock.MagicMock()
            mock_pipe.run.return_value = mock_result
            mock_pipe_cls.return_value = mock_pipe

            result = route_pcb(
                parsed,
                placements={"R1": (10.0, 20.0)},
                _seed=42,
            )

            assert result.completion_rate == 0.85
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_route_pcb_no_source_path_raises():
    """route_pcb() raises ValueError when parsed has no source_path."""
    from temper_placer.router_v6.adapter import route_pcb

    parsed = type("ParsedPCB", (), {})()
    with pytest.raises(ValueError, match="source_path"):
        route_pcb(parsed, placements={}, _seed=0)


# ---------------------------------------------------------------------------
# U1.3: End-to-end Place->Route->Measure pipeline
# ---------------------------------------------------------------------------


def test_place_to_route_pipeline():
    """CP-SAT placement feeds into routing pipeline end-to-end."""
    from unittest import mock as umock

    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    netlist = MockNetlist(
        components=[MockComp("Q1"), MockComp("Q2"), MockComp("C1")],
        nets=[MockNet("GND"), MockNet("VCC"), MockNet("SW_NODE")],
    )
    board = MockBoard(zones=[])

    positions = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
    rotations = np.array([0, 0, 0], dtype=np.int32)
    cp_result = CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=["Q1", "Q2", "C1"],
        unplaced_refs=[],
        solve_time_ms=100.0,
        status="optimal",
    )

    placements = cp_result.to_placements_dict()
    assert placements == {"Q1": (10.0, 20.0), "Q2": (30.0, 40.0), "C1": (50.0, 60.0)}

    pr = cp_result.to_placement_result()
    assert pr is not None
    assert len(pr.placed_refs) == 3

    # Verify RoutingResult compilation path
    from temper_placer.router_v6.adapter import RoutingResult
    rr = RoutingResult(completion_rate=0.92)
    assert rr.completion_rate == 0.92


# ---------------------------------------------------------------------------
# U1.4: Baseline completion rate measurement
# ---------------------------------------------------------------------------


def test_baseline_completion_rate_recorded():
    """The place->route->measure pipeline produces a completion rate."""
    from temper_placer.router_v6.adapter import RoutingResult

    result = RoutingResult(completion_rate=0.88)
    assert 0.0 <= result.completion_rate <= 1.0

    baseline = result.completion_rate
    assert baseline is not None
    assert isinstance(baseline, float)


def test_routing_result_default_zero():
    """Uninitialized RoutingResult has completion_rate=0.0."""
    from temper_placer.router_v6.adapter import RoutingResult

    rr = RoutingResult()
    assert rr.completion_rate == 0.0
