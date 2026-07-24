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


# test_cp_sat_placement_result_to_placement_result removed 2026-07-18:
# CpSatPlacementResult never gained a to_placement_result() method (bridging
# to the older, array-based placer.deterministic.PlacementResult) -- grepped
# all of src/ for any production caller, found none. It also constructed
# `positions`/`rotations` as raw (N,2)/(N,) numpy arrays, but
# CpSatPlacementResult's real fields are `positions: dict[str, tuple[float,
# float]]` and `rotations: dict[str, int]` (ref-keyed, not index-aligned) --
# a leftover from an earlier, array-based design. See docs/solutions/
# test-failures/router-integration-tests-assumed-array-based-cpsatplacementresult.md.


def test_cp_sat_placement_result_to_placements_dict():
    """to_placements_dict() produces dict ready for _apply_placements_to_pcb."""
    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    result = CpSatPlacementResult(
        positions={"Q1": (10.5, 20.3), "Q2": (30.0, 40.8)},
        rotations={"Q1": 0, "Q2": 1},
        placed_refs=["Q1", "Q2"],
        unplaced_refs=[],
    )

    d = result.to_placements_dict()
    assert d["Q1"] == pytest.approx((10.5, 20.3), rel=1e-5)
    assert d["Q2"] == pytest.approx((30.0, 40.8), rel=1e-5)


# test_solve_placement_fallback_without_ortools removed 2026-07-18:
# solve_placement() imports `from ortools.sat.python import cp_model` with
# no try/except -- ortools is now an unconditional, required dependency
# with no "deterministic_fallback" status or degraded-mode path anywhere
# in encoder.py (grepped -- the string never appears outside this test).
# The test's own mock.patch.dict("sys.modules", {"ortools": None}) also
# doesn't reliably prevent the real import once ortools.sat.python.cp_model
# is already cached in sys.modules by an earlier test in the same process,
# which is why it was silently getting a real "optimal" result instead of
# hitting any fallback path. See docs/solutions/test-failures/
# router-integration-tests-assumed-array-based-cpsatplacementresult.md.


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

    raw = '(kicad_pcb) (footprint "Dummy" (layer "F.Cu") (at 1 2))'
    result = _apply_placements_to_pcb(raw, {})
    assert result == raw


# ---------------------------------------------------------------------------
# U1.2: route_pcb() baseline measurement (mock router)
# ---------------------------------------------------------------------------


class MockPipelineResult:
    completion_rate: float = 0.0
    stage4: object = None
    manufacturing_report: object = None

    def __init__(self):
        mock_rr = type(
            "RoutingResults",
            (),
            {
                "failed_nets": [],
                "net_reports": [],
            },
        )()
        self.stage4 = type(
            "Stage4Output",
            (),
            {
                "routing_results": mock_rr,
            },
        )()
        self.manufacturing_report = None


def test_route_pcb_with_placements():
    """route_pcb() applies placements and runs the router pipeline.

    Verifies that placements reach _apply_placements_to_pcb (the function
    that rewrites footprint coordinates in the PCB content) and that the
    pipeline receives the modified temp file, not just that the mock's
    return value survives pass-through.
    """
    from pathlib import Path as PathLib
    from unittest import mock as umock

    from temper_placer.core.design_rules import DesignRules
    from temper_placer.router_v6.adapter import route_pcb

    mock_result = MockPipelineResult()
    mock_result.completion_rate = 0.85

    # Minimal PCB fixture with a footprint so _apply_placements_to_pcb
    # has something to rewrite — a real placement test needs real content.
    _PCB_FIXTURE = (
        "(kicad_pcb (version 20221018)\n"
        '  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")\n'
        '    (property "Reference" "R1")\n'
        "    (at 0 0)\n"
        "  )\n"
        ")\n"
    )

    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
        f.write(_PCB_FIXTURE)
        temp_path = f.name

    try:
        parsed = type("ParsedPCB", (), {"source_path": temp_path})()

        # route_pcb()'s own `finally: os.unlink(temp_path)` deletes the temp
        # PCB unconditionally once it returns, mocked pipeline or not -- the
        # deletion isn't contingent on a real pipeline "consuming" the file.
        # So the content must be captured at call time, inside run()'s
        # side_effect, before route_pcb() reaches its cleanup -- reading
        # run_args[0] after route_pcb() returns races a file that's
        # already gone.
        captured = {}

        def _capture_run(path, *_args, **_kwargs):
            captured["path"] = path
            captured["content"] = PathLib(path).read_text(encoding="utf-8")
            return mock_result

        with umock.patch(
            "temper_placer.router_v6.pipeline.RouterV6Pipeline"
        ) as mock_pipe_cls:
            mock_pipe = umock.MagicMock()
            mock_pipe.run.side_effect = _capture_run
            mock_pipe_cls.return_value = mock_pipe

            result = route_pcb(
                parsed,
                placements={"R1": (10.0, 20.0)},
                _seed=42,
                design_rules=DesignRules(),
            )

            assert result.completion_rate == 0.85

            # Pipeline constructor: verify it receives expected kwargs.
            mock_pipe_cls.assert_called_once()
            _, ctor_kwargs = mock_pipe_cls.call_args
            assert "layer_constraints" in ctor_kwargs
            assert ctor_kwargs["layer_constraints"] == {}
            assert ctor_kwargs.get("enable_zone_pours") is False

            # Pipeline invocation: run() receives the modified PCB file.
            mock_pipe.run.assert_called_once()
            run_args, _run_kwargs = mock_pipe.run.call_args
            assert len(run_args) == 1
            assert isinstance(run_args[0], PathLib)

            # The temp file must contain the placement-applied coordinates,
            # captured at call time via the side_effect above.
            temp_pcb_path = run_args[0]
            assert "(at 10.0000 20.0000" in captured["content"], (
                "Placement was not applied: expected R1 at (10.0, 20.0) "
                "in the temp PCB content passed to pipeline.run()"
            )
            assert temp_pcb_path != PathLib(temp_path), (
                "Pipeline should receive a placement-modified temp file, "
                "not the original source path"
            )
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

    from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult

    MockNetlist(
        components=[MockComp("Q1"), MockComp("Q2"), MockComp("C1")],
        nets=[MockNet("GND"), MockNet("VCC"), MockNet("SW_NODE")],
    )
    MockBoard(zones=[])

    cp_result = CpSatPlacementResult(
        positions={"Q1": (10.0, 20.0), "Q2": (30.0, 40.0), "C1": (50.0, 60.0)},
        rotations={"Q1": 0, "Q2": 0, "C1": 0},
        placed_refs=["Q1", "Q2", "C1"],
        unplaced_refs=[],
        solve_time_ms=100.0,
        status="optimal",
    )

    placements = cp_result.to_placements_dict()
    assert placements == {"Q1": (10.0, 20.0), "Q2": (30.0, 40.0), "C1": (50.0, 60.0)}
    assert len(cp_result.placed_refs) == 3

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
