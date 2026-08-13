"""Coverage-paydown wave 18: router_v6 power/capacity geometry, zone emission,
scorecard/validation helpers, io provenance/reference loader, deterministic
bottleneck loader, and the pipeline visualization/preflight components.

Targets allowlist entries that are pure functions, dataclass methods, or
cheaply-constructed observers reachable from ``tests/core/`` without a solver
or a live DRC backend.  Every target is exercised directly so the CI-exact
coverage run records non-zero line coverage and the entry becomes removable.

Do NOT edit ``.coverage-allowlist`` here -- the orchestrator applies the
removals after CI-exact verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from temper_placer.core.board import Board, Via
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.deterministic.bottleneck_map import BottleneckMap, load_bottleneck_map
from temper_placer.deterministic.state import BoardState
from temper_placer.io.provenance import Provenance, compute_provenance, embed_provenance
from temper_placer.io.reference_loader import (
    ReferenceDesign,
    filter_components,
    list_reference_designs,
    load_reference_pcb,
    netlist_to_placement_state,
)
from temper_placer.pipeline.preflight import (
    PreflightCheck,
    PreflightChecker,
    PreflightReport,
    PreflightResult,
)
from temper_placer.pipeline.terminal_dashboard import (
    TerminalDashboardObserver,
    create_terminal_dashboard,
)
from temper_placer.pipeline.visualization import (
    ProgressCallback,
    RichDashboard,
    TerminalProgress,
    create_progress_display,
)
from temper_placer.regression.physics_oracle import PhysicsOracleResult
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, SkeletonGraph
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.corridor import extract_corridor_mask
from temper_placer.router_v6.layer_capacity import (
    LayerCapacity,
    LayerCapacityStage,
    calculate_layer_capacity,
    validate_layer_capacity,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.power_plane import (
    CopperPour,
    PowerPlaneGeometry,
    generate_ground_pour,
    generate_power_planes,
    generate_power_pours,
    generate_thermal_vias,
)
from temper_placer.router_v6.zone_emission import (
    ZoneDefinition,
    compute_zone_for_net,
    compute_zones_for_net,
    emit_zone_s_expr,
)
from temper_placer.validation.helps_battery import BatteryVerdict, decide_verdict
from temper_placer.validation.metrics import compute_metrics
from temper_placer.validation.scorecard import (
    GateMargin,
    IndependenceViolationError,
    MarginScorecard,
    build_scorecard,
    score_placement_via_oracle,
)
from temper_placer.validation.spice_templates import (
    check_thresholds,
    compute_spice_penalty,
    get_available_templates,
    get_template_parameters,
    load_template,
)
from temper_placer.validation.trace_analyzer import (
    calculate_actual_loop_area,
    calculate_actual_trace_length,
    calculate_min_hv_lv_clearance,
    validate_emi_traces,
    validate_signal_integrity,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _make_board(width: float = 100.0, height: float = 100.0) -> Board:
    return Board(width=width, height=height, origin=(0.0, 0.0))


def _make_component(ref: str, bounds: tuple[float, float] = (3.0, 3.0)) -> Component:
    comp = Component(ref=ref, footprint="0603", bounds=bounds)
    comp.initial_position = (10.0, 10.0)
    return comp


# ---------------------------------------------------------------------------
# router_v6/power_plane
# ---------------------------------------------------------------------------


class TestPowerPlane:
    def test_copper_pour_geometry(self):
        pour = CopperPour(
            net="GND",
            layer="In1.Cu",
            bounds=(0.0, 0.0, 100.0, 50.0),
        )
        assert pour.width == pytest.approx(100.0)
        assert pour.height == pytest.approx(50.0)
        assert pour.area == pytest.approx(5000.0)
        assert pour.is_ground is False

    def test_power_plane_geometry_via_count(self):
        vias = [Via(position=(0.0, 0.0), drill=0.3, width=0.6) for _ in range(9)]
        ground = CopperPour(net="GND", layer="In1.Cu", bounds=(0, 0, 10, 10), is_ground=True)
        geom = PowerPlaneGeometry(ground_pour=ground, power_pours=[], thermal_vias=vias)
        assert geom.via_count == 9
        assert geom.ground_pour.is_ground is True

    def test_generate_ground_pour(self):
        board = _make_board(100.0, 50.0)
        pour = generate_ground_pour(board)
        assert pour.net == "GND"
        assert pour.layer == "In1.Cu"
        assert pour.width == pytest.approx(100.0)
        assert pour.height == pytest.approx(50.0)
        assert pour.is_ground is True
        assert len(pour.polygon) == 4

    def test_generate_power_pours_strips(self):
        board = _make_board(100.0, 50.0)
        pours = generate_power_pours(board, domains=["+3V3", "+5V"], isolation_gap_mm=1.0)
        assert [p.net for p in pours] == ["+3V3", "+5V"]
        assert [p.layer for p in pours] == ["In2.Cu", "In2.Cu"]
        # two strips plus a 1.0mm gap must tile the full 100mm width
        total = sum(p.width for p in pours) + 1.0
        assert total == pytest.approx(100.0)

    def test_generate_power_pours_empty(self):
        board = _make_board()
        assert generate_power_pours(board, domains=[]) == []

    def test_generate_thermal_vias_only_igbts(self):
        board = _make_board()
        igbt = Component(ref="Q1", footprint="TO247", bounds=(15.0, 20.0))
        igbt.initial_position = (50.0, 50.0)
        other = Component(ref="R1", footprint="0603", bounds=(3.0, 3.0))
        other.initial_position = (10.0, 10.0)
        vias = generate_thermal_vias(board, [igbt, other], count=4)
        assert len(vias) == 4
        assert all(isinstance(v, Via) for v in vias)
        assert all(v.net == "DC_BUS+" for v in vias)

    def test_generate_thermal_vias_rejects_bad_diameters(self):
        board = _make_board()
        with pytest.raises(ValueError):
            generate_thermal_vias(board, [], diameter_mm=0.2, drill_mm=0.3)

    def test_generate_power_planes(self):
        board = _make_board()
        igbt = Component(ref="Q2", footprint="TO247", bounds=(15.0, 20.0))
        igbt.initial_position = (40.0, 40.0)
        geom = generate_power_planes(board, [igbt], thermal_via_count=4)
        assert geom.ground_pour.net == "GND"
        assert len(geom.power_pours) == 3
        assert geom.via_count == 4


# ---------------------------------------------------------------------------
# router_v6/layer_capacity
# ---------------------------------------------------------------------------


class TestLayerCapacity:
    def test_utilization_and_available_ratio(self):
        lc = LayerCapacity(
            layer_name="F.Cu",
            total_cells=100,
            free_cells=80,
            blocked_cells=20,
            min_channel_width=0.5,
            avg_channel_width=1.0,
            estimated_traces=10,
        )
        assert lc.utilization_ratio == pytest.approx(0.2)
        assert lc.available_ratio == pytest.approx(0.8)

    def test_ratio_zero_division(self):
        lc = LayerCapacity(
            layer_name="F.Cu",
            total_cells=0,
            free_cells=0,
            blocked_cells=0,
            min_channel_width=0.5,
            avg_channel_width=1.0,
            estimated_traces=0,
        )
        assert lc.utilization_ratio == 0.0
        assert lc.available_ratio == 0.0

    def test_calculate_layer_capacity(self):
        grid = OccupancyGrid(
            layer_name="F.Cu",
            grid=np.zeros((4, 4), dtype=np.int8),
            origin=(0.0, 0.0),
            cell_size=1.0,
            width_cells=4,
            height_cells=4,
        )
        widths = ChannelWidths(
            layer_name="F.Cu",
            node_widths={},
            edge_widths={},
            min_width=0.5,
            max_width=2.0,
            avg_width=1.0,
        )
        cap = calculate_layer_capacity(grid, widths)
        assert cap.layer_name == "F.Cu"
        assert cap.total_cells == 16
        assert cap.free_cells == 16
        assert cap.estimated_traces >= 1

    def test_validate_layer_capacity_clean(self):
        lc = LayerCapacity(
            layer_name="F.Cu",
            total_cells=100,
            free_cells=80,
            blocked_cells=20,
            min_channel_width=0.5,
            avg_channel_width=1.0,
            estimated_traces=10,
        )
        assert validate_layer_capacity(BoardState(layer_capacities={"F.Cu": lc})) == []

    def test_validate_layer_capacity_missing(self):
        failures = validate_layer_capacity(BoardState(layer_capacities=None))
        assert len(failures) == 1
        assert failures[0].field == "layer_capacities"

    def test_validate_layer_capacity_invariant_breach(self):
        lc = LayerCapacity(
            layer_name="F.Cu",
            total_cells=10,
            free_cells=50,
            blocked_cells=5,
            min_channel_width=0.5,
            avg_channel_width=1.0,
            estimated_traces=-1,
        )
        failures = validate_layer_capacity(BoardState(layer_capacities={"F.Cu": lc}))
        assert len(failures) == 2

    def test_layer_capacity_stage_name(self):
        assert LayerCapacityStage().name == "LayerCapacity"

    def test_layer_capacity_stage_run(self):
        dr = SimpleNamespace(default_trace_width_mm=0.2, default_clearance_mm=0.15)
        pcb = SimpleNamespace(design_rules=dr)
        grid = OccupancyGrid(
            layer_name="F.Cu",
            grid=np.zeros((4, 4), dtype=np.int8),
            origin=(0.0, 0.0),
            cell_size=1.0,
            width_cells=4,
            height_cells=4,
        )
        widths = ChannelWidths(
            layer_name="F.Cu",
            node_widths={},
            edge_widths={},
            min_width=0.5,
            max_width=2.0,
            avg_width=1.0,
        )
        state = BoardState(
            _parsed_pcb=pcb,
            occupancy_grids={"F.Cu": grid},
            channel_widths={"F.Cu": widths},
        )
        out = LayerCapacityStage().run(state)
        assert "F.Cu" in out.layer_capacities
        assert out.layer_capacities["F.Cu"].total_cells == 16


# ---------------------------------------------------------------------------
# router_v6/zone_emission
# ---------------------------------------------------------------------------


class TestZoneEmission:
    def test_compute_zone_for_net_single(self):
        zone = compute_zone_for_net("HV", 5, [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])
        assert zone.net_name == "HV"
        assert zone.net_number == 5
        assert zone.layer == "F.Cu"
        assert len(zone.points) >= 3

    def test_compute_zones_for_net_no_cluster(self):
        zones = compute_zones_for_net(
            "HV", 5, [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], cluster=False
        )
        assert len(zones) == 1
        assert isinstance(zones[0], ZoneDefinition)

    def test_compute_zones_for_net_empty_raises(self):
        with pytest.raises(ValueError):
            compute_zones_for_net("HV", 5, [])

    def test_emit_zone_s_expr(self):
        zone = ZoneDefinition(
            net_name="GND",
            net_number=1,
            layer="In1.Cu",
            points=((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
        )
        expr = emit_zone_s_expr(zone)
        assert expr.strip().startswith("(zone ")
        assert '"GND"' in expr


# ---------------------------------------------------------------------------
# router_v6/corridor
# ---------------------------------------------------------------------------


class TestCorridor:
    def test_extract_corridor_mask(self):
        mask = extract_corridor_mask([(0, 0)], coarse_factor=4, buffer_cells=0, fine_rows=8, fine_cols=8)
        assert mask.shape == (8, 8)
        assert mask.dtype == np.bool_
        assert mask.sum() == 16  # 4x4 block for one coarse cell

    def test_extract_corridor_mask_buffer_clamps(self):
        mask = extract_corridor_mask([(0, 0)], coarse_factor=4, buffer_cells=2, fine_rows=8, fine_cols=8)
        # buffer expands but clamps at fine-grid bounds
        assert mask.shape == (8, 8)
        assert 16 <= mask.sum() <= 36


# ---------------------------------------------------------------------------
# router_v6/channel_skeleton
# ---------------------------------------------------------------------------


class TestChannelSkeletonProperties:
    def test_counts_and_connectivity(self):
        g = SkeletonGraph()
        g.add_node((0.0, 0.0), pos=(0.0, 0.0))
        g.add_node((10.0, 0.0), pos=(10.0, 0.0))
        g.add_edge((0.0, 0.0), (10.0, 0.0), weight=10.0)
        skeleton = ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=10.0)
        assert skeleton.node_count == 2
        assert skeleton.edge_count == 1
        assert skeleton.is_connected is True

    def test_empty_skeleton(self):
        skeleton = ChannelSkeleton(graph=SkeletonGraph(), layer_name="F.Cu", total_length=0.0)
        assert skeleton.node_count == 0
        assert skeleton.edge_count == 0
        assert skeleton.is_connected is True


# ---------------------------------------------------------------------------
# validation/scorecard
# ---------------------------------------------------------------------------


class TestScorecard:
    def test_gate_margin_alias(self):
        gm = GateMargin(gate_name="thermal", value=3.2, unit="mm")
        assert gm.margin == pytest.approx(3.2)
        assert gm.value == pytest.approx(3.2)

    def test_from_oracle_result(self):
        result = PhysicsOracleResult(
            board_id="board-1",
            passed=True,
            quality_report={
                "thermal_score": 0.9,
                "hv_lv_clearance_score": 0.95,
                "loop_area_score": 0.5,
                "compactness_score": 0.8,
            },
        )
        scorecard = MarginScorecard.from_oracle_result(result, scorer_id="oracle-v1")
        assert scorecard.board_id == "board-1"
        assert scorecard.scorer_id == "oracle-v1"
        assert [m.gate_name for m in scorecard.margins] == [
            "thermal",
            "hv_lv_clearance",
            "loop_area",
            "compactness",
        ]

    def test_scorable_margins_filters_defaults(self):
        result = PhysicsOracleResult(
            board_id="board-1",
            passed=True,
            quality_report={
                "thermal_score": 1.0,  # default pass-through -> not scorable
                "compactness_score": 0.7,
            },
        )
        scorecard = MarginScorecard.from_oracle_result(result, scorer_id="oracle-v1")
        scorable = scorecard.scorable_margins()
        assert [m.gate_name for m in scorable] == ["compactness"]

    def test_margin_for(self):
        result = PhysicsOracleResult(
            board_id="b", passed=True, quality_report={"compactness_score": 0.7}
        )
        scorecard = MarginScorecard.from_oracle_result(result, scorer_id="o")
        assert scorecard.margin_for("compactness").gate_name == "compactness"
        assert scorecard.margin_for("nope") is None

    def test_build_scorecard(self):
        def scorer(_placement, _board, _netlist):
            return PhysicsOracleResult(
                board_id="mock", passed=True, quality_report={"compactness_score": 0.6}
            )

        scorecard = build_scorecard(None, None, None, scorer=scorer, scorer_id="phys", field_id="field")
        assert scorecard.board_id == "mock"
        assert scorecard.scorer_id == "phys"

    def test_build_scorecard_independence_guard(self):
        def scorer(_placement, _board, _netlist):
            return PhysicsOracleResult(board_id="mock", passed=True)

        with pytest.raises(IndependenceViolationError):
            build_scorecard(None, None, None, scorer=scorer, scorer_id="same", field_id="same")

    def test_score_placement_via_oracle(self):
        board = _make_board()
        c1 = _make_component("U1")
        c2 = _make_component("U2")
        c2.initial_position = (50.0, 50.0)
        netlist = Netlist(components=[c1, c2], nets=[])
        state = PlacementState(
            positions=np.array([[10.0, 10.0], [50.0, 50.0]], dtype=np.float32),
            rotation_logits=np.zeros((2, 4), dtype=np.float32),
        )
        scorecard = score_placement_via_oracle(state, board, netlist, field_id="thermal_field_v2")
        assert scorecard.scorer_id == "physics_oracle"
        assert [m.gate_name for m in scorecard.margins] == [
            "thermal",
            "hv_lv_clearance",
            "loop_area",
            "compactness",
        ]


# ---------------------------------------------------------------------------
# validation/spice_templates
# ---------------------------------------------------------------------------


class TestSpiceTemplates:
    def test_get_available_templates(self):
        templates = get_available_templates()
        assert isinstance(templates, list)
        assert "gate_drive" in templates

    def test_load_template(self):
        content = load_template("gate_drive")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_template_missing(self):
        with pytest.raises(FileNotFoundError):
            load_template("does_not_exist")

    def test_get_template_parameters(self):
        params = get_template_parameters("gate_drive")
        assert "GATE_LOOP_INDUCTANCE" in params
        assert "GATE_RESISTANCE" in params

    def test_check_thresholds_pass(self):
        results = check_thresholds("gate_drive", {"v_overshoot_pct": 10.0})
        assert results["v_overshoot_pct"]["passed"] is True

    def test_check_thresholds_fail_and_missing(self):
        results = check_thresholds("gate_drive", {"v_overshoot_pct": 25.0})
        assert results["v_overshoot_pct"]["passed"] is False
        assert results["v_overshoot_pct"]["limit_type"] == "max"
        # missing measurement
        assert results["t_rise"]["passed"] is False
        assert results["t_rise"]["error"] == "Measurement not found"

    def test_compute_spice_penalty_zero(self):
        clean = {
            "gate_drive": {
                "v_overshoot_pct": 10.0,
                "v_undershoot_pct": 2.0,
                "t_rise": 50e-9,
                "t_fall": 50e-9,
                "v_ring_pp": 1.0,
            }
        }
        assert compute_spice_penalty(clean) == 0.0

    def test_compute_spice_penalty_missing_measurement(self):
        # Missing measurements contribute a 0.1 soft penalty each.
        penalty = compute_spice_penalty({"gate_drive": {"v_overshoot_pct": 10.0}})
        assert penalty == pytest.approx(0.4)

    def test_compute_spice_penalty_positive(self):
        penalty = compute_spice_penalty({"gate_drive": {"v_overshoot_pct": 40.0}})
        assert penalty > 0.0


# ---------------------------------------------------------------------------
# validation/helps_battery
# ---------------------------------------------------------------------------


class TestDecideVerdict:
    def _args(self, **overrides):
        args = dict(
            margin_gain=0.4,
            beats_cheap_by=0.3,
            n_actual_physics=10,
            n_actual_cheap=10,
            n_required=5,
            divergence_detected=True,
            budget_exceeded=False,
            pass_bar_x=0.1,
            pass_bar_y=0.1,
        )
        args.update(overrides)
        return args

    def test_keep(self):
        verdict, detail = decide_verdict(**self._args())
        assert verdict == BatteryVerdict.KEEP
        assert "KEEP" in detail

    def test_kill(self):
        verdict, detail = decide_verdict(**self._args(margin_gain=0.0))
        assert verdict == BatteryVerdict.KILL
        assert "KILL" in detail

    def test_budget_exceeded(self):
        verdict, _ = decide_verdict(**self._args(budget_exceeded=True))
        assert verdict == BatteryVerdict.INCONCLUSIVE

    def test_no_divergence(self):
        verdict, _ = decide_verdict(**self._args(divergence_detected=False))
        assert verdict == BatteryVerdict.INCONCLUSIVE

    def test_insufficient_perturbations(self):
        verdict, _ = decide_verdict(**self._args(n_actual_physics=2, n_actual_cheap=2))
        assert verdict == BatteryVerdict.INCONCLUSIVE


# ---------------------------------------------------------------------------
# validation/trace_analyzer
# ---------------------------------------------------------------------------


class TestTraceAnalyzer:
    def test_calculate_actual_trace_length(self):
        board = _make_board()
        board.traces = [
            SimpleNamespace(net="N1", start=(0.0, 0.0), end=(10.0, 0.0)),
            SimpleNamespace(net="N1", start=(10.0, 0.0), end=(10.0, 10.0)),
            SimpleNamespace(net="N2", start=(0.0, 0.0), end=(100.0, 0.0)),
        ]
        assert calculate_actual_trace_length(board, "N1") == pytest.approx(20.0)

    def test_calculate_actual_loop_area(self):
        board = _make_board()
        board.traces = [
            SimpleNamespace(net="L1", start=(0.0, 0.0), end=(10.0, 0.0)),
            SimpleNamespace(net="L1", start=(10.0, 0.0), end=(10.0, 10.0)),
            SimpleNamespace(net="L1", start=(10.0, 10.0), end=(0.0, 10.0)),
            SimpleNamespace(net="L1", start=(0.0, 10.0), end=(0.0, 0.0)),
        ]
        assert calculate_actual_loop_area(board, ["L1"]) == pytest.approx(100.0)

    def test_calculate_actual_loop_area_degenerate(self):
        board = _make_board()
        board.traces = [SimpleNamespace(net="L1", start=(0.0, 0.0), end=(1.0, 0.0))]
        assert calculate_actual_loop_area(board, ["L1"]) == 0.0

    def test_calculate_min_hv_lv_clearance(self):
        board = _make_board()
        board.traces = [
            SimpleNamespace(net="HV", start=(0.0, 0.0), end=(10.0, 0.0)),
            SimpleNamespace(net="LV", start=(0.0, 20.0), end=(10.0, 20.0)),
        ]
        clearance = calculate_min_hv_lv_clearance(board, {"HV": "HighVoltage", "LV": "Signal"})
        assert clearance == pytest.approx(20.0)

    def test_validate_signal_integrity(self):
        board = _make_board()
        board.traces = [SimpleNamespace(net="CLK", start=(0.0, 0.0), end=(5.0, 0.0))]
        spec = SimpleNamespace(max_length_mm={"CLK": 100.0})
        results = validate_signal_integrity(board, spec)
        assert results["CLK_length"] == pytest.approx(5.0)

    def test_validate_emi_traces(self):
        assert validate_emi_traces(_make_board(), SimpleNamespace()) == {}


# ---------------------------------------------------------------------------
# validation/metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_compute_metrics(self):
        c1 = _make_component("U1", bounds=(3.0, 3.0))
        c1.pins = [Pin("1", "1", (1.0, 1.0), net="N1"), Pin("2", "2", (-1.0, -1.0), net="N1")]
        c2 = _make_component("U2", bounds=(3.0, 3.0))
        c2.initial_position = (50.0, 50.0)
        c2.pins = [Pin("1", "1", (1.0, 1.0), net="N1"), Pin("2", "2", (-1.0, -1.0), net="N1")]
        netlist = Netlist(
            components=[c1, c2],
            nets=[Net("N1", [("U1", "1"), ("U1", "2"), ("U2", "1"), ("U2", "2")])],
        )
        board = _make_board()
        state = PlacementState(
            positions=np.array([[10.0, 10.0], [50.0, 50.0]], dtype=np.float32),
            rotation_logits=np.zeros((2, 4), dtype=np.float32),
        )
        metrics = compute_metrics(state, netlist, board)
        assert metrics.overlap_count == 0
        assert metrics.boundary_violations == 0
        assert metrics.total_wirelength > 0.0
        assert metrics.is_valid is True


# ---------------------------------------------------------------------------
# io/reference_loader
# ---------------------------------------------------------------------------


class TestReferenceLoader:
    def test_netlist_to_placement_state(self):
        comp = Component(ref="U1", footprint="0603", bounds=(1.0, 1.0))
        comp.initial_position = (5.0, 5.0)
        comp.initial_rotation_quadrant = 1
        netlist = Netlist(components=[comp], nets=[Net("N1", [("U1", "1")])])
        state = netlist_to_placement_state(netlist, _make_board())
        assert state.positions.shape == (1, 2)
        assert state.positions[0].tolist() == pytest.approx([5.0, 5.0])
        assert state.rotation_logits.shape == (1, 4)
        assert state.rotation_logits[0, 1] == 10.0

    def test_netlist_to_placement_state_default_center(self):
        comp = Component(ref="U1", footprint="0603", bounds=(1.0, 1.0))
        netlist = Netlist(components=[comp], nets=[])
        state = netlist_to_placement_state(netlist, _make_board(100.0, 50.0))
        assert state.positions[0].tolist() == pytest.approx([50.0, 25.0])

    def test_list_reference_designs(self, tmp_path):
        (tmp_path / "simple.kicad_pcb").write_text("(kicad_pcb\n (footprint x)\n")
        (tmp_path / "complex.kicad_pcb").write_text("(kicad_pcb\n" + " (footprint x)\n" * 30)
        designs = list_reference_designs(tmp_path)
        assert len(designs) == 2
        assert designs[0]["name"] == "simple"
        assert designs[0]["complexity"] == "simple"
        assert designs[1]["complexity"] == "medium"

    def test_load_reference_pcb(self):
        design = load_reference_pcb(FIXTURES / "pitchfork.kicad_pcb")
        assert design.name == "pitchfork"
        assert design.netlist is not None
        assert design.board is not None
        assert isinstance(design.state, PlacementState)

    def test_load_reference_pcb_missing(self):
        with pytest.raises(FileNotFoundError):
            load_reference_pcb(FIXTURES / "no_such_board.kicad_pcb")

    def test_filter_components(self):
        design = load_reference_pcb(FIXTURES / "pitchfork.kicad_pcb")
        refs = {c.ref for c in design.netlist.components}
        keep = set(list(refs)[:2])
        filtered = filter_components(design, refs=keep)
        assert {c.ref for c in filtered.netlist.components} == keep
        assert filtered.name.endswith("_filtered")
        assert filtered.state.positions.shape[0] == len(keep)

    def test_filter_components_by_footprint(self):
        design = load_reference_pcb(FIXTURES / "pitchfork.kicad_pcb")
        first_fp = design.netlist.components[0].footprint
        filtered = filter_components(design, footprint_pattern=first_fp)
        assert filtered.netlist.components[0].footprint == first_fp


# ---------------------------------------------------------------------------
# io/provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_compute_provenance(self, tmp_path):
        board_file = tmp_path / "in.kicad_pcb"
        board_file.write_text("board-bytes")
        net_file = tmp_path / "net.net"
        net_file.write_text("net-bytes")
        prov = compute_provenance(board_file, net_file)
        assert isinstance(prov, Provenance)
        assert len(prov.board_sha256) == 64
        assert len(prov.netlist_sha256) == 64
        assert prov.config_sha256 is None
        assert "board=" in prov.as_comment()

    def test_compute_provenance_with_config(self, tmp_path):
        board_file = tmp_path / "in.kicad_pcb"
        board_file.write_text("b")
        net_file = tmp_path / "net.net"
        net_file.write_text("n")
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text("c")
        prov = compute_provenance(board_file, net_file, cfg_file)
        assert prov.config_sha256 is not None
        assert "config=" in prov.as_comment()

    def test_embed_provenance(self):
        from kiutils.board import Board as KiBoard

        board = KiBoard()
        prov = Provenance(
            board_sha256="a" * 64,
            netlist_sha256="b" * 64,
            config_sha256=None,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        embed_provenance(board, prov)
        assert board.titleBlock is not None
        assert "provenance:" in board.titleBlock.comments[9]


# ---------------------------------------------------------------------------
# deterministic/bottleneck_map
# ---------------------------------------------------------------------------


class TestBottleneckMapLoader:
    def test_load_from_state_attribute(self):
        bm = BottleneckMap(
            cell_size_mm=1.0, width=2, height=2, origin_xy=(0.0, 0.0), scores=(0.1, 0.2, 0.3, 0.4)
        )
        state = SimpleNamespace(bottleneck_analysis=bm)
        assert load_bottleneck_map(state) is bm

    def test_load_from_sidecar(self, tmp_path):
        sidecar = tmp_path / "placement.channels.json"
        sidecar.write_text(
            json.dumps(
                {
                    "cell_size_mm": 1.0,
                    "width": 2,
                    "height": 2,
                    "origin_xy": [0.0, 0.0],
                    "scores": [0.1, 0.2, 0.3, 0.4],
                }
            )
        )
        state = SimpleNamespace(bottleneck_analysis=None)
        bm = load_bottleneck_map(state, sidecar)
        assert bm is not None
        assert bm.width == 2
        assert bm.scores == (0.1, 0.2, 0.3, 0.4)

    def test_load_none(self):
        state = SimpleNamespace(bottleneck_analysis=None)
        assert load_bottleneck_map(state) is None


# ---------------------------------------------------------------------------
# pipeline/visualization
# ---------------------------------------------------------------------------


class TestProgressCallback:
    def test_base_noop_methods(self):
        cb = ProgressCallback()
        assert cb.on_phase_start("p", None) is None
        assert cb.on_phase_complete("p", None) is None
        assert cb.on_iteration(1, None) is None
        assert cb.on_epoch(1, 0.5) is None


class TestTerminalProgress:
    def test_phase_and_iteration(self, capsys):
        tp = TerminalProgress(total_phases=4)
        tp.on_phase_start("init", None)
        tp.on_phase_complete("init", None)
        tp.on_iteration(1, None)
        tp.on_epoch(0, 0.5)  # epoch 0 % 100 == 0 -> prints
        out = capsys.readouterr().out
        assert "Phase 1/4" in out
        assert "Iteration 1" in out

    def test_epoch_skips_non_interval(self, capsys):
        tp = TerminalProgress(epoch_interval=100)
        tp.on_epoch(1, 0.5)  # 1 % 100 != 0 -> no print
        assert capsys.readouterr().out == ""


class TestRichDashboard:
    def test_create_layout(self):
        dash = RichDashboard()
        layout = dash.create_layout()
        assert dash._layout is layout
        assert layout["header"].name == "header"
        assert layout["body"].name == "body"
        assert layout["footer"].name == "footer"

    def test_update_header(self):
        dash = RichDashboard()
        panel = dash.update_header("optimize", 3)
        assert "optimize" in panel.renderable
        assert "Iteration: 3" in panel.renderable

    def test_update_metrics(self):
        dash = RichDashboard()
        dash.metrics = {"loss": 0.123, "epoch": 5}
        table = dash.update_metrics()
        assert table.title == "Metrics"
        assert table.row_count == 2

    def test_update_loss_chart_empty(self):
        assert RichDashboard().update_loss_chart() == "No data"

    def test_update_loss_chart(self):
        dash = RichDashboard()
        dash.losses = [1.0, 0.5, 0.25]
        chart = dash.update_loss_chart()
        assert "Loss:" in chart

    def test_epoch_callback(self):
        dash = RichDashboard()
        dash.on_epoch(1, 0.4)
        assert dash.losses == [0.4]
        assert dash.metrics["epoch"] == 1
        assert dash.metrics["loss"] == 0.4

    def test_phase_and_iteration_callbacks(self, capsys):
        dash = RichDashboard()
        dash.on_phase_start("init", None)
        dash.on_phase_complete("init", None)
        dash.on_iteration(2, None)
        assert dash.current_phase == "init"
        assert dash.iteration == 2


class TestCreateProgressDisplay:
    def test_terminal_default(self):
        assert isinstance(create_progress_display(), TerminalProgress)

    def test_rich(self):
        assert isinstance(create_progress_display("rich"), RichDashboard)

    def test_unknown_falls_back_to_terminal(self):
        assert isinstance(create_progress_display("bogus"), TerminalProgress)


# ---------------------------------------------------------------------------
# pipeline/terminal_dashboard
# ---------------------------------------------------------------------------


class TestTerminalDashboardObserver:
    def test_stage_lifecycle(self):
        obs = TerminalDashboardObserver(stage_order=["geometric", "route"])
        obs.on_stage_start("geometric", 0, {})
        assert obs._current_stage == "geometric"
        assert obs._stage_status["geometric"] == obs.STATUS_ACTIVE
        obs.on_stage_complete("geometric", 1.5, {})
        assert obs._stage_status["geometric"] == obs.STATUS_DONE
        assert obs._stage_durations["geometric"] == 1.5
        obs.on_stage_skip("route", "no-op")
        assert obs._stage_status["route"] == obs.STATUS_SKIP
        obs.on_stage_error("route", ValueError("boom"))
        assert obs._stage_status["route"] == obs.STATUS_ERROR

    def test_feedback_and_pipeline_complete(self):
        obs = TerminalDashboardObserver(stage_order=["geometric"])
        obs.on_feedback_triggered("c", "a", "b", 1)
        assert obs._feedback_count == 1
        obs.on_pipeline_complete(True, 42.0, {"geometric": 5.0})
        assert obs._pipeline_success is True
        assert obs._total_duration == 42.0

    def test_epoch_trims_history(self):
        obs = TerminalDashboardObserver(stage_order=["geometric"])
        for i in range(250):
            obs.on_epoch("geometric", i, float(i))
        assert len(obs._losses) == 200
        assert len(obs._loss_epochs) == 200

    def test_update_noop_when_not_live(self):
        obs = TerminalDashboardObserver(stage_order=["geometric"])
        assert obs.update() is None  # guard branch executes without a Live

    def test_create_terminal_dashboard(self):
        obs = create_terminal_dashboard(["a", "b"])
        assert isinstance(obs, TerminalDashboardObserver)
        assert obs.stage_order == ["a", "b"]


# ---------------------------------------------------------------------------
# pipeline/preflight
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_report_passed_property(self):
        report = PreflightReport(checks=[], overall=PreflightResult.PASS, total_time_ms=1.0)
        assert report.passed is True
        failing = PreflightReport(checks=[], overall=PreflightResult.FAIL, total_time_ms=1.0)
        assert failing.passed is False

    def test_report_summary(self):
        report = PreflightReport(
            checks=[
                PreflightCheck("Layer Count", PreflightResult.PASS, "4-layer stackup verified"),
                PreflightCheck("Zone Capacity", PreflightResult.WARN, "some warning"),
            ],
            overall=PreflightResult.WARN,
            total_time_ms=3.5,
        )
        summary = report.summary()
        assert "Preflight Checks:" in summary
        assert "Layer Count" in summary
        assert "WARN" in summary
        assert "Overall: WARN" in summary

    def test_preflight_checker_run(self):
        c1 = _make_component("U1")
        c2 = _make_component("U2")
        netlist = Netlist(components=[c1, c2], nets=[])
        board = _make_board()
        report = PreflightChecker().run(board, netlist, None, None)
        assert isinstance(report, PreflightReport)
        assert len(report.checks) >= 10
        assert report.passed is True
