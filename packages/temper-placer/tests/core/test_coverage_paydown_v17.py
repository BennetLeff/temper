"""Coverage-paydown wave 17: router_v6 pure functions + adjacent pure helpers.

Targets allowlist entries across ``router_v6/`` (geometry, channel mapping,
net ordering, package detection, DFM reports, occupancy grid, DRC oracle,
connectivity) plus a few ``placer/cp_sat`` / ``deterministic`` dataclass
helpers.  Every target is a pure function or dataclass method reachable from
``tests/core/`` without a solver or a board file.

Do NOT edit ``.coverage-allowlist`` here -- the orchestrator applies the
removals after CI-exact verification.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import Polygon as ShapelyPolygon

from temper_placer.core.board import Board
from temper_placer.core.loop import LoopCollection
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.placer.cp_sat.feedback import FeedbackClassifier
from temper_placer.placer.cp_sat.unsat import UnsatConstraint, UnsatReport
from temper_placer.placer.cp_sat.unsat_surface import format_unsat_panel, write_unsat_json
from temper_placer.pcl.constraints import ConstraintType
from temper_placer.router_v6.acid_trap_detection import AcidTrapReport
from temper_placer.router_v6.annular_ring_check import AnnularRingReport
from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.astar_monitor import (
    InvariantViolation,
    MonitorState,
    astar_monitor,
    get_monitor_state,
)
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.bottleneck_geometry import is_hard_blocked
from temper_placer.router_v6.bundle_analyzer import BundleAnalyzer, BundleManifest
from temper_placer.router_v6.capacity_check import (
    build_capacity_demand_report,
    compute_capacity_demand_ratios,
)
from temper_placer.router_v6.channel_mapping import (
    ChannelMapping,
    ChannelPath,
    expand_channel_path_terminals,
    fallback_channel_path,
)
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    verify_clearance,
)
from temper_placer.router_v6.congestion_analysis import (
    CongestionSeverity,
    identify_congested_regions,
)
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    CopperZone,
    PadIdentity,
    verify_connectivity_by_net,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
)
from temper_placer.router_v6.constraints_drc_oracle import DRCOracle, Violation
from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    RotatedRect,
    closest_points_segment_segment,
    point_to_circle_distance,
    point_to_rotated_rect_distance,
    point_to_segment_distance,
    segment_to_rotated_rect_distance,
    segment_to_segment_distance,
)
from temper_placer.router_v6.constraints_spatial_index import Pad, Track, Via
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    LayerCopperBalance,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    CreepageViolation,
    verify_creepage,
)
from temper_placer.router_v6.dense_package_detection import (
    DensePackage,
    identify_dense_packages,
)
from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.router_v6.grid_converter import (
    GridCell,
    compute_path_length,
    count_vias_in_path,
    extract_vias,
    grid_to_world,
)
from temper_placer.router_v6.layer_assignment import (
    assign_layers,
    get_layer_for_net,
    layer_assignments_from_netclass,
)
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    format_manufacturing_report,
    generate_manufacturing_report,
)
from temper_placer.router_v6.neighbor_validity import (
    build_neighbor_validity_tensor_2d,
    is_valid_2d,
)
from temper_placer.router_v6.net_ordering import (
    NetClass,
    compute_bbox_area,
    compute_hpwl,
    get_loop_criticality,
    get_net_class_from_string,
    order_nets,
)
from temper_placer.router_v6.occupancy_grid import (
    OccupancyGrid,
    OccupancyGridStage,
    build_occupancy_grid,
    mark_path_blocked_3d,
)
from temper_placer.router_v6.path_simplify import (
    estimate_segment_count,
    is_collinear,
    simplify_path,
)
from temper_placer.router_v6.resource_bound import (
    demand_budget_summary,
    max_routable_nets,
    max_routable_nets_from_pcb,
)
from temper_placer.router_v6.routing_demand import RoutingDemand, estimate_routing_demand
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import (
    DesignRules,
    LayerInfo,
    ParsedPCB,
    StackupInfo,
)
from temper_placer.router_v6.teardrop_generation import (
    Teardrop,
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.thermal_relief import (
    ThermalRelief,
    ThermalReliefReport,
    add_thermal_relief,
)
from temper_placer.router_v6.topology_solver import SolverStatus, TopologicalSolution
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
    assign_trace_widths,
)
from temper_placer.router_v6.via_placement import ViaPlacement, Via as RouteVia, place_vias


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_component(ref: str = "U1", footprint: str = "0603") -> Component:
    comp = Component(ref=ref, footprint=footprint, bounds=(1.0, 1.0))
    comp.initial_position = (0.0, 0.0)
    return comp


def _make_netlist() -> Netlist:
    comp = _make_component("U1")
    comp.pins = [
        Pin("A", "1", (0.0, 0.0), net="N1"),
        Pin("B", "2", (5.0, 5.0), net="N1"),
    ]
    net = Net(name="N1", pins=[("U1", "1"), ("U1", "2")], net_class="Signal")
    return Netlist(components=[comp], nets=[net])


def _make_grid(size: int = 4) -> OccupancyGrid:
    grid = np.zeros((size, size), dtype=np.int8)
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=size,
        height_cells=size,
    )


# ---------------------------------------------------------------------------
# constraints_geometry
# ---------------------------------------------------------------------------


class TestConstraintsGeometry:
    def test_line_segment_length(self):
        seg = LineSegment(Point(0, 0), Point(3, 4))
        assert seg.length == 5.0

    def test_line_segment_direction(self):
        seg = LineSegment(Point(0, 0), Point(3, 4))
        direction = seg.direction
        assert np.allclose(direction, [0.6, 0.8])

    def test_line_segment_midpoint(self):
        seg = LineSegment(Point(0, 0), Point(2, 4))
        assert seg.midpoint() == Point(1.0, 2.0)

    def test_rotated_rect_corners(self):
        rect = RotatedRect(Point(0, 0), (2.0, 4.0), 0.0)
        corners = rect.corners
        assert len(corners) == 4
        assert Point(-1.0, -2.0) in corners
        assert Point(1.0, 2.0) in corners

    def test_rotated_rect_bounding_radius(self):
        rect = RotatedRect(Point(0, 0), (2.0, 4.0), 0.0)
        assert rect.bounding_radius == pytest.approx((1.0**2 + 2.0**2) ** 0.5)

    def test_point_to_segment_distance(self):
        dist = point_to_segment_distance(Point(0, 1), LineSegment(Point(0, 0), Point(1, 0)))
        assert dist == pytest.approx(1.0)

    def test_segment_to_segment_distance(self):
        s1 = LineSegment(Point(0, 0), Point(1, 0))
        s2 = LineSegment(Point(0, 2), Point(1, 2))
        assert segment_to_segment_distance(s1, s2) == pytest.approx(2.0)

    def test_closest_points_segment_segment(self):
        s1 = LineSegment(Point(0, 0), Point(1, 0))
        s2 = LineSegment(Point(0, 2), Point(1, 2))
        p1, p2 = closest_points_segment_segment(s1, s2)
        assert p1 == Point(0.0, 0.0)
        assert p2 == Point(0.0, 2.0)

    def test_point_to_circle_distance(self):
        assert point_to_circle_distance(Point(5, 0), Point(0, 0), 3.0) == pytest.approx(2.0)
        assert point_to_circle_distance(Point(2, 0), Point(0, 0), 3.0) == pytest.approx(-1.0)

    def test_point_to_rotated_rect_distance(self):
        rect = RotatedRect(Point(0, 0), (2.0, 2.0), 0.0)
        assert point_to_rotated_rect_distance(Point(3, 0), rect) == pytest.approx(2.0)
        assert point_to_rotated_rect_distance(Point(0, 0), rect) < 0

    def test_segment_to_rotated_rect_distance(self):
        rect = RotatedRect(Point(0, 0), (2.0, 2.0), 0.0)
        seg = LineSegment(Point(3, -1), Point(3, 1))
        assert segment_to_rotated_rect_distance(seg, rect) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# grid_converter
# ---------------------------------------------------------------------------


class TestGridConverter:
    def test_grid_to_world(self):
        assert grid_to_world(GridCell(10, 20, 0), (0, 0), 0.5) == (5.25, 10.25)

    def test_extract_vias(self):
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1), GridCell(2, 0, 1)]
        assert extract_vias(cells) == [2]

    def test_compute_path_length(self):
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        assert compute_path_length(cells, cell_size=0.5) == pytest.approx(1.0)

    def test_count_vias_in_path(self):
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 1), GridCell(2, 0, 1), GridCell(3, 0, 0)]
        assert count_vias_in_path(cells) == 2


# ---------------------------------------------------------------------------
# path_simplify
# ---------------------------------------------------------------------------


class TestPathSimplify:
    def test_is_collinear_horizontal(self):
        assert is_collinear(GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0))

    def test_is_collinear_corner(self):
        assert not is_collinear(GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0))

    def test_simplify_path_straight(self):
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        simplified = simplify_path(cells)
        assert simplified == [GridCell(0, 0, 0), GridCell(2, 0, 0)]

    def test_estimate_segment_count(self):
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]
        assert estimate_segment_count(cells) == 2


# ---------------------------------------------------------------------------
# channel_widths / channel_mapping
# ---------------------------------------------------------------------------


class TestChannelWidths:
    def test_bottleneck_width(self):
        cw = ChannelWidths("F.Cu", {(0.0, 0.0): 0.5}, {}, 0.5, 0.9, 0.7)
        assert cw.bottleneck_width == 0.5

    def test_get_node_width(self):
        cw = ChannelWidths("F.Cu", {(0.0, 0.0): 0.5}, {}, 0.5, 0.5, 0.5)
        assert cw.get_node_width((0.0, 0.0)) == 0.5
        assert cw.get_node_width((9.0, 9.0)) == 0.0


class TestChannelMapping:
    def test_mapped_net_count_and_get_path(self):
        cm = ChannelMapping({"A": ChannelPath("A", ["c1"], [(0, 0)], 1.0)})
        assert cm.mapped_net_count == 1
        assert cm.get_path("A") is not None
        assert cm.get_path("B") is None

    def test_expand_channel_path_terminals_two_pad(self):
        path = ChannelPath("X", [], [], 0.0)
        expanded = expand_channel_path_terminals(path, [(0, 0), (1, 1)])
        assert len(expanded.waypoints) == 2

    def test_expand_channel_path_terminals_noop(self):
        path = ChannelPath("X", ["c1"], [(0, 0)], 1.0)
        assert expand_channel_path_terminals(path, []) is path

    def test_fallback_channel_path(self):
        path = fallback_channel_path("GND", [(0, 0), (1, 1)])
        assert path.net_name == "GND"
        assert path.channel_sequence == []


# ---------------------------------------------------------------------------
# net_ordering
# ---------------------------------------------------------------------------


class TestNetOrdering:
    def test_get_net_class_from_string(self):
        assert get_net_class_from_string("HighVoltage") == NetClass.HIGH_VOLTAGE
        assert get_net_class_from_string("unknown") == NetClass.SIGNAL

    def test_compute_hpwl_and_bbox(self):
        netlist = _make_netlist()
        # single pin set on this net resolves to two pins at (0,0),(5,5)
        assert compute_hpwl("N1", netlist) == pytest.approx(10.0)
        assert compute_bbox_area("N1", netlist) == pytest.approx(25.0)

    def test_compute_hpwl_missing_net(self):
        netlist = _make_netlist()
        assert compute_hpwl("NOPE", netlist) == 0.0
        assert compute_bbox_area("NOPE", netlist) == 0.0

    def test_get_loop_criticality(self):
        netlist = _make_netlist()
        assert get_loop_criticality("N1", LoopCollection([])) == 3  # low/none

    def test_order_nets_empty(self):
        assert order_nets(Netlist(components=[], nets=[]), LoopCollection([])) == []

    def test_order_nets(self):
        netlist = _make_netlist()
        assert order_nets(netlist, LoopCollection([])) == ["N1"]


# ---------------------------------------------------------------------------
# dense_package_detection / diff_pair_inference
# ---------------------------------------------------------------------------


class TestDensePackageDetection:
    def test_is_bga_and_qfn(self):
        comp = _make_component("U1", "QFN-48_0.4mm")
        qfn = DensePackage(comp, 48, 0.4, "QFN", True)
        assert qfn.is_qfn
        assert not qfn.is_bga
        bga = DensePackage(comp, 48, 0.4, "BGA", True)
        assert bga.is_bga
        assert not bga.is_qfn

    def test_identify_dense_packages(self):
        comp = _make_component("U1", "QFN-48_0.4mm")
        comp.pins = [Pin(f"p{i}", str(i), (0.0, 0.0)) for i in range(20)]
        dense = identify_dense_packages([comp])
        assert len(dense) == 1
        assert dense[0].requires_escape

    def test_identify_dense_packages_skips_low_pin_count(self):
        comp = _make_component("U1", "0603")
        comp.pins = [Pin("1", "1", (0.0, 0.0))]
        assert identify_dense_packages([comp]) == []


class TestDiffPairInference:
    def test_positive_negative_net(self):
        pair = DiffPair("USB", "USB_D+", "USB_D-")
        assert pair.positive_net == "USB_D+"
        assert pair.negative_net == "USB_D-"

    def test_diff_pair_validation(self):
        with pytest.raises(ValueError):
            DiffPair("X", "SAME", "SAME")

    def test_infer_differential_pairs(self):
        pairs = infer_differential_pairs(["USB_DP", "USB_DN", "GND", "3V3"])
        assert len(pairs) == 1
        assert pairs[0].p_net == "USB_DP"
        assert pairs[0].n_net == "USB_DN"


# ---------------------------------------------------------------------------
# layer_assignment
# ---------------------------------------------------------------------------


class TestLayerAssignment:
    def test_assign_layers(self):
        netlist = Netlist(
            components=[],
            nets=[
                Net(name="DC_BUS_P", pins=[], net_class="HV"),
                Net(name="GND", pins=[], net_class="GND"),
                Net(name="SIG", pins=[], net_class="Signal"),
            ],
        )
        assignments = assign_layers(netlist)
        assert set(assignments) == {"DC_BUS_P", "GND", "SIG"}
        # HV nets get L1_TOP per DEFAULT_LAYER_CONSTRAINTS-equivalent Rust kernel
        assert assignments["DC_BUS_P"].primary_layer.value == 1

    def test_get_layer_for_net_power_rail(self):
        assert get_layer_for_net("+3V3", None) == "In2.Cu"
        assert get_layer_for_net("SIG", None) == "B.Cu"

    def test_layer_assignments_from_netclass(self):
        dr = DesignRules()
        assignments = layer_assignments_from_netclass(dr, ["GND", "SIG"])
        assert set(assignments) == {"GND", "SIG"}


# ---------------------------------------------------------------------------
# copper_balance / thermal_relief / teardrop
# ---------------------------------------------------------------------------


class TestCopperBalance:
    def test_layer_needs_balancing(self):
        assert LayerCopperBalance("F.Cu", 10.0, 20.0, False).needs_balancing
        assert not LayerCopperBalance("F.Cu", 10.0, 50.0, True).needs_balancing

    def test_balanced_unbalanced_counts(self):
        report = CopperBalanceReport(
            layer_balances=[
                LayerCopperBalance("F.Cu", 10.0, 50.0, True),
                LayerCopperBalance("In1.Cu", 10.0, 10.0, False),
            ],
            total_area_mm2=100.0,
        )
        assert report.balanced_layer_count == 1
        assert report.unbalanced_layer_count == 1

    def test_analyze_copper_balance_empty(self):
        report = analyze_copper_balance(RoutingResults({}, []), 100, 100)
        assert report.balanced_layer_count == 0
        assert report.unbalanced_layer_count == 4


class TestThermalRelief:
    def test_relief_count_and_spokes(self):
        report = ThermalReliefReport(
            thermal_reliefs=[ThermalRelief("GND", (0, 0), 4, 0.254, 0.254)]
        )
        assert report.relief_count == 1
        assert report.total_spokes == 4

    def test_add_thermal_relief_empty(self):
        report = add_thermal_relief(RoutingResults({}, []))
        assert report.relief_count == 0

    def test_add_thermal_relief_validation(self):
        with pytest.raises(ValueError):
            add_thermal_relief(RoutingResults({}, []), spoke_width=0.0)


class TestTeardropGeneration:
    def test_teardrop_counts(self):
        report = TeardropReport(
            teardrops=[
                Teardrop("N1", (0, 0), "via", 0.3, 0.6, "F.Cu"),
                Teardrop("N1", (1, 0), "pad", 0.3, 0.6, "F.Cu"),
            ]
        )
        assert report.teardrop_count == 2
        assert report.via_teardrop_count == 1
        assert report.pad_teardrop_count == 1

    def test_insert_teardrops_empty(self):
        report = insert_teardrops(RoutingResults({}, []))
        assert report.teardrop_count == 0

    def test_insert_teardrops_clamps_ratio(self):
        report = insert_teardrops(RoutingResults({}, []), teardrop_length_ratio=5.0)
        assert report.teardrop_count == 0


# ---------------------------------------------------------------------------
# trace_width_assignment / via_placement
# ---------------------------------------------------------------------------


class TestTraceWidthAssignment:
    def test_assignment_count_and_get_width(self):
        ta = TraceWidthAssignment({"A": TraceWidth("A", 0.2, "default")})
        assert ta.assignment_count == 1
        assert ta.get_width("A") == 0.2
        assert ta.get_width("X") is None

    def test_assign_trace_widths(self):
        pf = PathfindingResult(routed_paths={}, failed_nets=[])
        pf.routed_paths["N1"] = RoutePath3D("N1", [(0, 0, "F.Cu")], [], 0.0)
        ta = assign_trace_widths(pf)
        assert ta.assignment_count == 1
        assert ta.get_width("N1") == 0.127


class TestViaPlacement:
    def test_via_count_and_get_vias_for_net(self):
        vp = ViaPlacement(
            vias=[RouteVia((1.0, 1.0), "F.Cu", "B.Cu", 0.6, 0.3, "N1")]
        )
        assert vp.via_count == 1
        assert len(vp.get_vias_for_net("N1")) == 1
        assert vp.get_vias_for_net("X") == []

    def test_place_vias_3d(self):
        pf = PathfindingResult(routed_paths={}, failed_nets=[])
        pf.routed_paths["N1"] = RoutePath3D(
            "N1", [(0, 0, "F.Cu"), (1, 1, "F.Cu"), (2, 2, "B.Cu")], [(1, 1)], 2.0
        )
        vp = place_vias(pf)
        assert vp.via_count == 1
        via = vp.get_vias_for_net("N1")[0]
        assert via.from_layer == "F.Cu"
        assert via.to_layer == "B.Cu"


# ---------------------------------------------------------------------------
# resource_bound / neighbor_validity / bundle_analyzer
# ---------------------------------------------------------------------------


class TestResourceBound:
    def test_max_routable_nets(self):
        grid = _make_grid(4)
        bboxes = {"A": (0.0, 0.0, 2.0, 2.0), "B": (1.0, 1.0, 3.0, 3.0)}
        result = max_routable_nets(grid, bboxes, 0.2)
        assert result == 2

    def test_max_routable_nets_empty(self):
        assert max_routable_nets(_make_grid(4), {}, 0.2) == 0

    def test_max_routable_nets_from_pcb(self):
        grid = _make_grid(4)
        netlist = _make_netlist()
        comp = netlist.components[0]
        pcb = ParsedPCB(
            components=[comp],
            nets=netlist.nets,
            zones=[],
            board=Board(width=100, height=100),
            design_rules=DesignRules(),
            stackup=StackupInfo([LayerInfo(0, "F.Cu", "signal", 35)], 1.6, 1),
            source_path=None,
        )
        result = max_routable_nets_from_pcb(grid, pcb, 0.2)
        assert isinstance(result, int)

    def test_demand_budget_summary(self):
        grid = _make_grid(4)
        bboxes = {"A": (0.0, 0.0, 2.0, 2.0)}
        summary = demand_budget_summary(grid, bboxes, 0.2)
        assert summary["total_nets"] == 1
        assert "max_routable" in summary


class TestNeighborValidity:
    def test_build_tensor_and_is_valid(self):
        grid = _make_grid(4)
        tensor = build_neighbor_validity_tensor_2d(grid)
        assert tensor.shape == (4, 4, 8)
        # interior cell moving E on a fully-free grid is valid
        assert is_valid_2d(tensor, 1, 1, 0)
        # out-of-bounds reads return False
        assert not is_valid_2d(tensor, -1, 1, 0)
        assert not is_valid_2d(tensor, 10, 10, 0)

    def test_build_tensor_with_corridor_mask(self):
        grid = _make_grid(4)
        mask = np.zeros((4, 4), dtype=bool)
        mask[0:2, 0:2] = True
        tensor = build_neighbor_validity_tensor_2d(grid, corridor_mask=mask)
        assert tensor.shape == (4, 4, 8)


class TestBundleAnalyzer:
    def test_manifest_properties(self):
        manifest = BundleManifest()
        manifest.bundle_id_for_net = {0: 1, 1: 1}
        assert manifest.bundle_count == 0
        assert manifest.is_bundled(0)
        assert not manifest.is_bundled(5)

    def test_analyze_empty(self):
        assert BundleAnalyzer([], {}).analyze().bundle_count == 0

    def test_analyze_two_nets_no_geometry(self):
        # Two nets with empty footprints overlap trivially (Jaccard of empty
        # covers is 1.0 > 0.5), so they bundle into a single class.
        nets = [
            Net(name="A", pins=[], net_class="Signal"),
            Net(name="B", pins=[], net_class="Signal"),
        ]
        manifest = BundleAnalyzer(nets, {}).analyze()
        assert manifest.bundle_count == 1
        assert manifest.is_bundled(0) and manifest.is_bundled(1)


# ---------------------------------------------------------------------------
# astar_monitor
# ---------------------------------------------------------------------------


class TestAstarMonitor:
    def test_record_pop_monotonic_ok(self):
        state = MonitorState()
        state.record_pop((0, 0), 1.0)
        state.record_pop((1, 1), 2.0)
        assert state.violations == []

    def test_record_pop_monotonic_violation(self):
        state = MonitorState()
        state.record_pop((0, 0), 2.0)
        state.record_pop((1, 1), 1.0)
        assert any(v.invariant == "f_cost_monotonicity" for v in state.violations)

    def test_validate_cost_lower_bound(self):
        state = MonitorState()
        path = [(0, 0), (1, 0)]
        g_score = {(1, 0): 1.0}
        came_from = {(1, 0): (0, 0)}
        state.validate_cost_lower_bound(path, g_score, came_from)
        assert state.violations == []

    def test_validate_cost_lower_bound_mismatch(self):
        state = MonitorState()
        path = [(0, 0), (1, 0)]
        g_score = {(1, 0): 999.0}
        came_from = {(1, 0): (0, 0)}
        state.validate_cost_lower_bound(path, g_score, came_from)
        assert any(v.invariant == "cost_lower_bound" for v in state.violations)

    def test_validate_path_completeness(self):
        state = MonitorState()
        state.validate_path_completeness([(0, 0), (1, 0)], (0, 0), (1, 0))
        assert state.violations == []

    def test_validate_path_completeness_violation(self):
        state = MonitorState()
        state.validate_path_completeness([(0, 0), (2, 0)], (0, 0), (1, 0))
        assert any(v.invariant == "path_completeness" for v in state.violations)

    def test_get_monitor_state_inactive(self):
        assert get_monitor_state() is None

    def test_astar_monitor_context_manager(self):
        with astar_monitor() as state:
            assert isinstance(state, MonitorState)
            assert get_monitor_state() is state
        assert get_monitor_state() is None


# ---------------------------------------------------------------------------
# topology_solver / stage0_data
# ---------------------------------------------------------------------------


class TestTopologySolver:
    def test_get_value_and_is_satisfiable(self):
        sol = TopologicalSolution(SolverStatus.SATISFIABLE, {"x1": True}, 1.0)
        assert sol.is_satisfiable
        assert sol.get_value("x1") is True
        assert sol.get_value("nope") is None
        unsat = TopologicalSolution(SolverStatus.UNSATISFIABLE, {}, 1.0)
        assert not unsat.is_satisfiable


class TestStage0Data:
    def _stackup(self) -> StackupInfo:
        return StackupInfo(
            [
                LayerInfo(0, "F.Cu", "signal", 35),
                LayerInfo(1, "In1.Cu", "plane", 35, plane_net="GND"),
                LayerInfo(2, "In2.Cu", "plane", 35, plane_net="+15V"),
                LayerInfo(3, "B.Cu", "signal", 35),
            ],
            1.6,
            4,
        )

    def test_signal_and_plane_layers(self):
        stackup = self._stackup()
        assert stackup.signal_layers == [0, 3]
        assert stackup.plane_layers == {1: "GND", 2: "+15V"}

    def test_get_reference_plane(self):
        stackup = self._stackup()
        assert stackup.get_reference_plane(0) == 1
        assert stackup.get_reference_plane(3) == 2
        empty = StackupInfo([LayerInfo(0, "F.Cu", "signal", 35)], 1.6, 1)
        assert empty.get_reference_plane(0) is None

    def test_design_rules_get_rules_for_net(self):
        dr = DesignRules()
        rules = dr.get_rules_for_net("ANY")
        assert rules.name == "Default"
        assert rules.clearance_mm == 0.2

    def test_parsed_pcb_validate_placement(self):
        comp = _make_component("U1")
        comp.initial_position = (10.0, 10.0)
        pcb = ParsedPCB(
            components=[comp],
            nets=[Net(name="A", pins=[])],
            zones=[],
            board=Board(width=100, height=100),
            design_rules=DesignRules(),
            stackup=self._stackup(),
            source_path=None,
        )
        assert pcb.validate_placement() == []


# ---------------------------------------------------------------------------
# manufacturing_report
# ---------------------------------------------------------------------------


def _make_manufacturing_report() -> ManufacturingReport:
    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=0)
    teardrops = TeardropReport(
        teardrops=[Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")]
    )
    thermal = ThermalReliefReport(
        thermal_reliefs=[ThermalRelief("GND", (0, 0), 4, 0.254, 0.254)]
    )
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=100.0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)
    return generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )


class TestManufacturingReport:
    def test_generate_and_properties(self):
        report = _make_manufacturing_report()
        assert report.is_manufacturability_ok
        assert report.total_violations == 0
        assert report.critical_violations == 0

    def test_generate_rejects_none(self):
        acid = AcidTrapReport(acid_traps=[])
        with pytest.raises(TypeError):
            generate_manufacturing_report(
                acid, None, None, None, None, None, None
            )

    def test_format_manufacturing_report(self):
        text = format_manufacturing_report(_make_manufacturing_report())
        assert "MANUFACTURING DRC REPORT" in text
        assert "PASS" in text


# ---------------------------------------------------------------------------
# routing_demand / capacity_check
# ---------------------------------------------------------------------------


class TestRoutingDemand:
    def test_routing_complexity(self):
        rd = RoutingDemand(10, 8, 20, 6, 2, 1, 2.0, 4)
        assert 0.0 <= rd.routing_complexity <= 1.0

    def test_estimate_routing_demand(self):
        netlist = _make_netlist()
        pcb = ParsedPCB(
            components=netlist.components,
            nets=netlist.nets,
            zones=[],
            board=Board(width=100, height=100),
            design_rules=DesignRules(),
            stackup=StackupInfo([LayerInfo(0, "F.Cu", "signal", 35)], 1.6, 1),
            source_path=None,
        )
        demand = estimate_routing_demand(pcb)
        assert demand.total_nets == 1
        assert demand.total_pins == 2


class TestCapacityCheck:
    def _stage2_output(self) -> object:
        class _Stage2Output:
            def __init__(self):
                area = ShapelyPolygon([(0, 0), (20, 0), (20, 20), (0, 20)])
                self.routing_spaces = {
                    "F.Cu": RoutingSpace("F.Cu", area, 400.0, 0.0, 400.0)
                }

        return _Stage2Output()

    def _pcb(self) -> ParsedPCB:
        comp = _make_component("U1")
        comp.pins = [Pin("A", "1", (1.0, 1.0), net="N1"), Pin("B", "2", (5.0, 5.0), net="N1")]
        return ParsedPCB(
            components=[comp],
            nets=[Net(name="N1", pins=[("U1", "1"), ("U1", "2")])],
            zones=[],
            board=Board(width=100, height=100),
            design_rules=DesignRules(),
            stackup=StackupInfo([LayerInfo(0, "F.Cu", "signal", 35)], 1.6, 1),
            source_path=None,
        )

    def test_compute_capacity_demand_ratios(self):
        ratios = compute_capacity_demand_ratios(self._stage2_output(), self._pcb())
        assert "N1" in ratios
        assert ratios["N1"] > 0

    def test_build_capacity_demand_report(self):
        report = build_capacity_demand_report(self._stage2_output(), self._pcb())
        assert report.ratios["N1"] > 1.0
        assert "N1" in report.safe_nets


# ---------------------------------------------------------------------------
# clearance_check / creepage_check
# ---------------------------------------------------------------------------


class TestClearanceCheck:
    def test_violation_deficiency(self):
        violation = ClearanceViolation("A", "B", (0, 0), 0.05, 0.2, "F.Cu")
        assert violation.deficiency == pytest.approx(0.15)

    def test_verify_clearance_empty(self):
        report = verify_clearance(RoutingResults({}, []))
        assert report.violation_count == 0

    def test_verify_clearance_bad_backend(self):
        with pytest.raises(ValueError):
            verify_clearance(RoutingResults({}, []), backend="bogus")


class TestCreepageCheck:
    def test_violation_deficiency(self):
        violation = CreepageViolation("HV", "LV", (0, 0), 1.0, 3.0)
        assert violation.deficiency == pytest.approx(2.0)

    def test_verify_creepage_empty(self):
        report = verify_creepage(RoutingResults({}, []))
        assert report.violation_count == 0

    def test_verify_creepage_bad_default(self):
        with pytest.raises(ValueError):
            verify_creepage(RoutingResults({}, []), default_creepage=float("nan"))


# ---------------------------------------------------------------------------
# connectivity
# ---------------------------------------------------------------------------


class TestConnectivity:
    def _pads(self):
        pid1 = PadIdentity("U1", "1", "N1", 0.0, 0.0, (0,))
        pid2 = PadIdentity("U1", "2", "N1", 10.0, 0.0, (0,))
        return [
            CopperPad(pid1, Point(0, 0), "circle", (1.0, 1.0)),
            CopperPad(pid2, Point(10, 0), "circle", (1.0, 1.0)),
        ]

    def test_verify_net_connectivity_routed(self):
        tracks = [CopperTrack(Point(0, 0), Point(10, 0), 0, 0.2, "N1")]
        result = verify_net_connectivity(self._pads(), tracks, [])
        assert result.disposition.value == "routed"
        assert result.connected_pad_count == 2

    def test_verify_net_connectivity_disconnected(self):
        result = verify_net_connectivity(self._pads(), [], [])
        assert result.disposition.value == "incomplete"

    def test_verify_net_connectivity_with_zone(self):
        zone = CopperZone(ShapelyPolygon([(-1, -1), (11, -1), (11, 1), (-1, 1)]), 0, "N1")
        result = verify_net_connectivity(self._pads(), [], [], [zone])
        assert result.disposition.value == "routed"

    def test_verify_connectivity_by_net(self):
        tracks = [CopperTrack(Point(0, 0), Point(10, 0), 0, 0.2, "N1")]
        by_net = verify_connectivity_by_net(self._pads(), tracks, [], [])
        assert set(by_net) == {"N1"}


# ---------------------------------------------------------------------------
# congestion_analysis
# ---------------------------------------------------------------------------


class TestCongestionAnalysis:
    def test_identify_congested_regions_empty(self):
        result = identify_congested_regions(RoutingResults({}, []), 100, 100)
        assert result.congested_region_count == 0
        assert result.critical_region_count == 0
        assert result.get_regions_by_severity(CongestionSeverity.HIGH) == []


# ---------------------------------------------------------------------------
# constraints_drc_oracle
# ---------------------------------------------------------------------------


class TestDrCOracle:
    def _oracle(self) -> DRCOracle:
        return DRCOracle(DesignRulesParser.create_default())

    def test_violation_severity(self):
        violation = Violation("x", "a", "b", "n1", "n2", 0.05, 0.2, Point(0, 0))
        assert violation.severity == pytest.approx(0.75)

    def test_can_place_via_empty(self):
        valid, reason = self._oracle().can_place_via((10.0, 10.0), 0.6, "N1")
        assert valid
        assert reason == ""

    def test_can_place_track_segment_empty(self):
        valid, reason = self._oracle().can_place_track_segment(
            (0.0, 0.0), (5.0, 5.0), 0, "N1", 0.2
        )
        assert valid

    def test_get_valid_via_sites(self):
        sites = self._oracle().get_valid_via_sites((10.0, 10.0), 0.5, "N1")
        assert isinstance(sites, list)
        assert (10.0, 10.0) in sites

    def test_add_clearance_credit(self):
        oracle = self._oracle()
        oracle.add_clearance_credit("U1", "1", "2", 0.1, 0.5, 1.0, (5.0, 5.0), "x")
        assert ("U1", "1", "2") in oracle.clearance_credits

    def test_add_clearance_credit_bad_axis(self):
        with pytest.raises(ValueError):
            self._oracle().add_clearance_credit("U1", "1", "2", 0.1, 0.5, 1.0, axis="z")

    def test_register_and_clear(self):
        oracle = self._oracle()
        pad = Pad(Point(5, 5), "circle", (1.0, 1.0), "N1", 0, id="U1-1")
        track = Track(Point(0, 0), Point(1, 1), 0.2, "N2", 0, id="t1")
        via = Via(Point(10, 10), 0.6, 0.3, "N3", id="v1")
        assert oracle.register_pad(pad) == "U1-1"
        assert oracle.register_track(track) == "t1"
        assert oracle.register_tracks([track]) == ["t1"]
        assert oracle.register_via(via) == "v1"
        assert oracle.register_vias([via]) == ["v1"]
        oracle.clear()
        assert oracle.validate_all() == []

    def test_get_effective_clearance_no_credit(self):
        oracle = self._oracle()
        pad = Pad(Point(5, 5), "circle", (1.0, 1.0), "N1", 0, id="U1-1")
        assert oracle.get_effective_clearance(pad, pad) is None
        assert oracle.get_pad_credit(pad) is None

    def test_validate_all_empty(self):
        assert self._oracle().validate_all() == []


# ---------------------------------------------------------------------------
# occupancy_grid
# ---------------------------------------------------------------------------


class TestOccupancyGrid:
    def test_dimensions(self):
        grid = _make_grid(4)
        assert grid.width_mm == 4.0
        assert grid.height_mm == 4.0

    def test_is_free_and_blocked(self):
        grid = _make_grid(4)
        assert grid.is_free(0, 0)
        assert not grid.is_blocked(0, 0)
        assert not grid.is_free(-1, 0)
        assert not grid.is_free(99, 99)

    def test_grid_to_world_roundtrip(self):
        grid = _make_grid(4)
        assert grid.world_to_grid(1.5, 2.5) == (1, 2)
        assert grid.grid_to_world(0, 0) == (0.5, 0.5)

    def test_cell_counts(self):
        grid = _make_grid(4)
        assert grid.free_cell_count == 16
        assert grid.blocked_cell_count == 0
        assert grid.occupancy_ratio == 0.0

    def test_mark_and_unmark(self):
        grid = _make_grid(4)
        grid.mark_path_blocked([(0.0, 0.0), (3.0, 3.0)], 0.2, 0.1, 7)
        assert grid.free_cell_count < 16
        assert 7 in grid.get_blocking_nets((0.0, 0.0), (3.0, 3.0))
        grid.mark_segment_blocked((0.0, 0.0), (1.0, 1.0), 0.2, 0.1, 7)
        grid.mark_via_blocked(2.0, 2.0, 0.6, 0.1, 7)
        grid.unmark_segment_blocked((0.0, 0.0), (1.0, 1.0), 0.2, 0.1, 7)
        grid.unmark_path([(0.0, 0.0), (3.0, 3.0)], 0.2, 0.1, 7)
        assert grid.free_cell_count == 16

    def test_downsample(self):
        grid = _make_grid(4)
        coarse = grid.downsample(2)
        assert coarse.width_cells == 2
        assert coarse.height_cells == 2
        assert coarse.cell_size == 2.0
        assert coarse.layer_name == "F.Cu_coarse"

    def test_mark_path_blocked_3d(self):
        grid = _make_grid(4)
        mark_path_blocked_3d(
            {"F.Cu": grid},
            [(0.0, 0.0, "F.Cu"), (2.0, 2.0, "F.Cu"), (3.0, 3.0, "B.Cu")],
            0.2,
            0.1,
            9,
        )
        # The B.Cu segment is ignored (no grid for it); the F.Cu segment marks.
        assert 9 in grid.get_blocking_nets((0.0, 0.0), (2.0, 2.0))

    def test_build_occupancy_grid(self):
        area = ShapelyPolygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        routing_space = RoutingSpace("F.Cu", area, 100.0, 0.0, 100.0)
        grid = build_occupancy_grid(routing_space, cell_size=1.0, margin=1.0)
        assert grid.width_cells > 0
        assert grid.height_cells > 0
        assert grid.free_cell_count > 0

    def test_occupancy_grid_stage_name(self):
        assert OccupancyGridStage().name == "OccupancyGrid"


# ---------------------------------------------------------------------------
# bottleneck_geometry
# ---------------------------------------------------------------------------


class TestBottleneckGeometry:
    def test_is_hard_blocked_free(self):
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(width_mm=10, height_mm=10, cell_size_mm=1.0, layer_count=2)
        assert not is_hard_blocked(grid, (0, 0, 0))

    def test_is_hard_blocked_out_of_bounds(self):
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(width_mm=10, height_mm=10, cell_size_mm=1.0, layer_count=2)
        assert is_hard_blocked(grid, (0, 999, 999))


# ---------------------------------------------------------------------------
# constraints_design_rules
# ---------------------------------------------------------------------------


class TestConstraintsDesignRules:
    def test_design_rules_parser_parse_bare(self):
        class _Bare:
            setup = None

        matrix = DesignRulesParser.parse(_Bare())
        assert isinstance(matrix, ClearanceMatrix)
        assert matrix.default_clearance > 0

    def test_clearance_matrix_parse_internal_board(self):
        board = Board(width=100, height=100)
        matrix = ClearanceMatrix.parse(board)
        assert isinstance(matrix, ClearanceMatrix)


# ---------------------------------------------------------------------------
# placer/cp_sat pure helpers
# ---------------------------------------------------------------------------


class TestUnsatHelpers:
    def _report(self) -> UnsatReport:
        core = [
            UnsatConstraint("c1", ConstraintType.SEPARATED, None, 1),
            UnsatConstraint("c2", ConstraintType.SEPARATED, "because text", 2),
        ]
        return UnsatReport(sufficient_core=core, minimal_core=core, is_minimal=True)

    def test_data_quality_gaps(self):
        report = self._report()
        gaps = report.data_quality_gaps
        assert len(gaps) == 1
        assert gaps[0]["constraint_name"] == "c1"

    def test_format_unsat_panel(self):
        text = format_unsat_panel(self._report())
        assert "c1" in text

    def test_write_unsat_json(self, tmp_path):
        target = tmp_path / "unsat.json"
        write_unsat_json(self._report(), target)
        assert target.exists()


class TestFeedbackClassifier:
    def test_classify_clean(self):
        classifier = FeedbackClassifier()
        result = classifier.classify(
            type("R", (), {"unrouted_nets": [], "drc_violations": [], "congestion_regions": [], "completion_rate": 1.0})(),
            type("P", (), {"placed_refs": [], "positions": {}})(),
        )
        assert result.deltas == []
        assert result.unclassified == []

    def test_classify_unrouted_noncritical(self):
        classifier = FeedbackClassifier()
        result = classifier.classify(
            type("R", (), {"unrouted_nets": ["SIG1"], "drc_violations": [], "congestion_regions": [], "completion_rate": 0.5})(),
            type("P", (), {"placed_refs": ["U1"], "positions": {"U1": (0.0, 0.0)}})(),
        )
        assert len(result.unclassified) == 1
        assert result.unclassified[0].nets == ["SIG1"]
