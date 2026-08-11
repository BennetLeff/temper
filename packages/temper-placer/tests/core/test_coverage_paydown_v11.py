"""Coverage paydown tests v11: router V6 dataclass properties, pure functions,
and io dataclass properties.

Exercises public functions in:
- router_v6/_check_report_base.py: BaseCheckReport (pass_rate, violation_count)
- router_v6/acid_trap_detection.py: AcidTrapReport (counts), detect_acid_traps
- router_v6/astar_core.py: RoutePath, RoutePath3D, in_bounds, octile_distance
- router_v6/astar_core_rust.py: RouteProfileStats.reset, get/reset_route_profile_stats
- router_v6/bottleneck_analysis.py: Bottleneck, BottleneckAnalysis (dataclass properties)
- router_v6/bottleneck_geometry.py: BottleneckGeometry.to_dict, grid_cell_size
- router_v6/annular_ring_check.py: AnnularRingViolation.deficiency
- router_v6/routing_results.py: RoutingResults (success_count, failure_count, etc.)
- router_v6/diagnostics.py: calculate_routing_score, aggregate_board_score, to_dict
- router_v6/verifier.py: parse_verification_level
- router_v6/connectivity.py: CopperPad, CopperTrack, NetConnectivity properties
- io/_write_types.py: WriteResult, StrippingResult, IsolationSlotResult has_warnings
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ===========================================================================
# router_v6/_check_report_base.py — BaseCheckReport mixin
# ===========================================================================


class TestBaseCheckReport:
    """Covers BaseCheckReport.violation_count and BaseCheckReport.pass_rate."""

    def test_violation_count_empty(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=[], total_checks=10)
        assert r.violation_count == 0

    def test_violation_count_with_entries(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=["a", "b", "c"], total_checks=10)
        assert r.violation_count == 3

    def test_pass_rate_perfect(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=[], total_checks=10)
        assert r.pass_rate == 100.0

    def test_pass_rate_half(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=["a", "b", "c", "d", "e"], total_checks=10)
        assert r.pass_rate == 50.0

    def test_pass_rate_zero_denominator(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=["a", "b", "c"], total_checks=0)
        assert r.pass_rate == 100.0

    def test_pass_rate_all_fail(self):
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        r = FakeReport(violations=["a"] * 10, total_checks=10)
        assert r.pass_rate == 0.0

    def test_pass_rate_with_more_violations_than_checks(self):
        """pass_rate should go negative and be handled by the formula
        yielding a negative float (violation_count > denominator)."""
        from dataclasses import dataclass

        from temper_placer.router_v6._check_report_base import BaseCheckReport

        @dataclass
        class FakeReport(BaseCheckReport):
            violations: list
            total_checks: int = 0

        # 15 violations for 10 checks → negative rate
        r = FakeReport(violations=["a"] * 15, total_checks=10)
        assert r.pass_rate == -50.0


# ===========================================================================
# router_v6/acid_trap_detection.py — AcidTrapReport counts + detect_acid_traps
# ===========================================================================


class TestAcidTrapReport:
    """Covers AcidTrapReport.trap_count, critical_count, medium_count, low_count."""

    def test_empty_report(self):
        from temper_placer.router_v6.acid_trap_detection import AcidTrapReport

        r = AcidTrapReport(acid_traps=[])
        assert r.trap_count == 0
        assert r.critical_count == 0
        assert r.medium_count == 0
        assert r.low_count == 0

    def test_all_severities(self):
        from temper_placer.router_v6.acid_trap_detection import AcidTrap, AcidTrapReport

        traps = [
            AcidTrap("N1", (0.0, 0.0), 30.0, "high"),
            AcidTrap("N1", (1.0, 0.0), 50.0, "medium"),
            AcidTrap("N2", (2.0, 0.0), 50.0, "medium"),
            AcidTrap("N3", (3.0, 0.0), 70.0, "low"),
            AcidTrap("N3", (4.0, 0.0), 80.0, "low"),
            AcidTrap("N3", (5.0, 0.0), 65.0, "low"),
        ]
        r = AcidTrapReport(acid_traps=traps)
        assert r.trap_count == 6
        assert r.critical_count == 1
        assert r.medium_count == 2
        assert r.low_count == 3

    def test_only_critical(self):
        from temper_placer.router_v6.acid_trap_detection import AcidTrap, AcidTrapReport

        traps = [
            AcidTrap("N1", (0.0, 0.0), 10.0, "high"),
            AcidTrap("N1", (1.0, 0.0), 20.0, "high"),
        ]
        r = AcidTrapReport(acid_traps=traps)
        assert r.trap_count == 2
        assert r.critical_count == 2
        assert r.medium_count == 0
        assert r.low_count == 0

    def test_errored_flag(self):
        from temper_placer.router_v6.acid_trap_detection import AcidTrapReport

        r = AcidTrapReport(acid_traps=[], errored=True)
        assert r.trap_count == 0
        assert r.critical_count == 0
        assert r.errored is True

    def test_detect_acid_traps_empty_routing_results(self):
        from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
        from temper_placer.router_v6.routing_results import RoutingResults

        results = RoutingResults(compiled_routes={}, failed_nets=[])
        report = detect_acid_traps(results)
        assert report.trap_count == 0

    def test_detect_acid_traps_nan_threshold(self):
        import math

        from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
        from temper_placer.router_v6.routing_results import RoutingResults

        results = RoutingResults(compiled_routes={}, failed_nets=[])
        report = detect_acid_traps(results, min_angle_threshold=math.nan)
        assert report.trap_count == 0

    def test_detect_acid_traps_clamped_threshold(self):
        """Threshold > 90 is clamped to 90 with a warning;
        empty results still produce zero traps."""
        from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
        from temper_placer.router_v6.routing_results import RoutingResults

        results = RoutingResults(compiled_routes={}, failed_nets=[])
        report = detect_acid_traps(results, min_angle_threshold=120.0)
        assert report.trap_count == 0


# ===========================================================================
# router_v6/astar_core.py — RoutePath, RoutePath3D, in_bounds, octile_distance
# ===========================================================================


class TestOctileDistance:
    """Covers octile_distance (pure math function)."""

    def test_same_point(self):
        from temper_placer.router_v6.astar_core import octile_distance

        assert octile_distance((0, 0), (0, 0)) == 0.0

    def test_cardinal(self):
        from temper_placer.router_v6.astar_core import octile_distance

        assert octile_distance((0, 0), (5, 0)) == 5.0

    def test_diagonal(self):
        from temper_placer.router_v6.astar_core import octile_distance

        d = octile_distance((0, 0), (3, 3))
        # max(3,3) + (sqrt2 - 1) * min(3,3) = 3 + 0.414... * 3 ≈ 4.2426...
        assert d > 4.2
        assert d < 4.3

    def test_rectangular(self):
        from temper_placer.router_v6.astar_core import octile_distance

        d = octile_distance((0, 0), (5, 2))
        expected = 5.0 + (1.4142135623730951 - 1.0) * 2.0
        assert abs(d - expected) < 1e-10

    def test_large_values(self):
        from temper_placer.router_v6.astar_core import octile_distance

        d = octile_distance((0, 0), (1000, 1000))
        assert d > 1414.0
        assert d < 1415.0


class TestInBounds:
    """Covers in_bounds."""

    def test_in_bounds_origin(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(0, 0, 10, 10) is True

    def test_in_bounds_corner(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(9, 9, 10, 10) is True

    def test_out_of_bounds_x(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(10, 0, 10, 10) is False

    def test_out_of_bounds_y(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(0, -1, 10, 10) is False

    def test_out_of_bounds_both(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(-1, -1, 10, 10) is False

    def test_zero_dims(self):
        from temper_placer.router_v6.astar_core import in_bounds

        assert in_bounds(0, 0, 0, 0) is False


class TestRoutePath:
    """Covers RoutePath.segment_count and RoutePath.success."""

    def test_segment_count_empty(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [], "F.Cu", 0.0)
        assert r.segment_count == 0

    def test_segment_count_single(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [(0.0, 0.0)], "F.Cu", 0.0)
        assert r.segment_count == 0

    def test_segment_count_two(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [(0.0, 0.0), (1.0, 0.0)], "F.Cu", 1.0)
        assert r.segment_count == 1

    def test_segment_count_three(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)], "F.Cu", 2.0)
        assert r.segment_count == 2

    def test_success_true(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [(0.0, 0.0), (1.0, 0.0)], "F.Cu", 1.0)
        assert r.success is True

    def test_success_false_empty(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [], "F.Cu", 0.0)
        assert r.success is False

    def test_success_false_single(self):
        from temper_placer.router_v6.astar_core import RoutePath

        r = RoutePath("N1", [(0.0, 0.0)], "F.Cu", 0.0)
        assert r.success is False


class TestRoutePath3D:
    """Covers RoutePath3D.segment_count and RoutePath3D.to_route_path."""

    def test_segment_count_empty(self):
        from temper_placer.router_v6.astar_core import RoutePath3D

        r = RoutePath3D("N1", [], [], 0.0)
        assert r.segment_count == 0

    def test_segment_count_two(self):
        from temper_placer.router_v6.astar_core import RoutePath3D

        r = RoutePath3D("N1", [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")], [], 1.0)
        assert r.segment_count == 1

    def test_to_route_path(self):
        from temper_placer.router_v6.astar_core import RoutePath3D

        r3d = RoutePath3D(
            "N1",
            [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (2.0, 0.0, "B.Cu")],
            [(1.0, 0.0)],
            2.0,
            via_count=1,
            forced_segment_count=0,
            failed_waypoint_indices=[2],
        )
        rp = r3d.to_route_path()
        assert rp.net_name == "N1"
        assert rp.coordinates == [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        assert rp.layer_name == "F.Cu"
        assert rp.path_length == 2.0
        assert rp.forced_segment_count == 0
        assert rp.failed_waypoint_indices == [2]

    def test_to_route_path_custom_layer(self):
        from temper_placer.router_v6.astar_core import RoutePath3D

        r3d = RoutePath3D("N2", [(0.0, 0.0, "In1.Cu"), (5.0, 0.0, "In2.Cu")], [], 5.0)
        rp = r3d.to_route_path(default_layer="In1.Cu")
        assert rp.layer_name == "In1.Cu"


# ===========================================================================
# router_v6/astar_core_rust.py — RouteProfileStats, get/reset stats
# ===========================================================================


class TestRouteProfileStats:
    """Covers RouteProfileStats.reset, get_route_profile_stats,
    reset_route_profile_stats."""

    def test_reset_zeros_all_fields(self):
        from temper_placer.router_v6.astar_core_rust import RouteProfileStats

        stats = RouteProfileStats(
            rust_time_ms=100.0,
            python_time_ms=50.0,
            astar_total_ms=200.0,
            dist_map_ms=30.0,
        )
        stats.reset()
        assert stats.rust_time_ms == 0.0
        assert stats.python_time_ms == 0.0
        assert stats.astar_total_ms == 0.0
        assert stats.dist_map_ms == 0.0

    def test_get_route_profile_stats_returns_instance(self):
        from temper_placer.router_v6.astar_core_rust import (
            RouteProfileStats,
            get_route_profile_stats,
        )

        stats = get_route_profile_stats()
        assert isinstance(stats, RouteProfileStats)

    def test_reset_route_profile_stats_zeros(self):
        from temper_placer.router_v6.astar_core_rust import (
            RouteProfileStats,
            get_route_profile_stats,
            reset_route_profile_stats,
        )

        # Mutate stats first
        stats = get_route_profile_stats()
        stats.rust_time_ms = 999.0
        assert get_route_profile_stats().rust_time_ms == 999.0

        # Reset
        reset_route_profile_stats()
        assert get_route_profile_stats().rust_time_ms == 0.0


# ===========================================================================
# router_v6/bottleneck_analysis.py — Bottleneck, BottleneckAnalysis
# ===========================================================================


class TestBottleneck:
    """Covers Bottleneck.is_critical and Bottleneck.margin."""

    def test_is_critical_true(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckSeverity,
        )

        bn = Bottleneck(
            layer_name="F.Cu",
            severity=BottleneckSeverity.CRITICAL,
            capacity=10,
            demand=50,
            utilization=5.0,
        )
        assert bn.is_critical is True

    def test_is_critical_false(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckSeverity,
        )

        bn = Bottleneck(
            layer_name="F.Cu",
            severity=BottleneckSeverity.HIGH,
            capacity=10,
            demand=20,
            utilization=2.0,
        )
        assert bn.is_critical is False

    def test_is_critical_none(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckSeverity,
        )

        bn = Bottleneck(
            layer_name="F.Cu",
            severity=BottleneckSeverity.NONE,
            capacity=100,
            demand=10,
            utilization=0.1,
        )
        assert bn.is_critical is False

    def test_margin_positive(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckSeverity,
        )

        bn = Bottleneck(
            layer_name="F.Cu",
            severity=BottleneckSeverity.LOW,
            capacity=100,
            demand=30,
            utilization=0.3,
        )
        assert bn.margin == 70.0

    def test_margin_negative(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckSeverity,
        )

        bn = Bottleneck(
            layer_name="F.Cu",
            severity=BottleneckSeverity.CRITICAL,
            capacity=10,
            demand=50,
            utilization=5.0,
        )
        assert bn.margin == -40.0


class TestBottleneckAnalysis:
    """Covers BottleneckAnalysis.has_critical_bottlenecks, worst_bottleneck."""

    def test_has_critical_bottlenecks_true(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckAnalysis,
            BottleneckSeverity,
        )

        ba = BottleneckAnalysis(
            bottlenecks=[
                Bottleneck("L1", BottleneckSeverity.LOW, 100, 20, 0.2),
                Bottleneck("L2", BottleneckSeverity.CRITICAL, 5, 50, 10.0),
            ],
            total_capacity=105,
            total_demand=70,
        )
        assert ba.has_critical_bottlenecks is True

    def test_has_critical_bottlenecks_false(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckAnalysis,
            BottleneckSeverity,
        )

        ba = BottleneckAnalysis(
            bottlenecks=[
                Bottleneck("L1", BottleneckSeverity.LOW, 100, 20, 0.2),
                Bottleneck("L2", BottleneckSeverity.HIGH, 20, 30, 1.5),
            ],
            total_capacity=120,
            total_demand=50,
        )
        assert ba.has_critical_bottlenecks is False

    def test_has_critical_bottlenecks_empty(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            BottleneckAnalysis,
        )

        ba = BottleneckAnalysis(
            bottlenecks=[],
            total_capacity=0,
            total_demand=0,
        )
        assert ba.has_critical_bottlenecks is False

    def test_worst_bottleneck_returns_max_utilization(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            Bottleneck,
            BottleneckAnalysis,
            BottleneckSeverity,
        )

        most_congested = Bottleneck("L3", BottleneckSeverity.CRITICAL, 10, 50, 5.0)
        ba = BottleneckAnalysis(
            bottlenecks=[
                Bottleneck("L1", BottleneckSeverity.LOW, 100, 20, 0.2),
                most_congested,
                Bottleneck("L2", BottleneckSeverity.HIGH, 30, 60, 2.0),
            ],
            total_capacity=140,
            total_demand=130,
        )
        assert ba.worst_bottleneck is most_congested

    def test_worst_bottleneck_empty(self):
        from temper_placer.router_v6.bottleneck_analysis import (
            BottleneckAnalysis,
        )

        ba = BottleneckAnalysis(bottlenecks=[], total_capacity=0, total_demand=0)
        assert ba.worst_bottleneck is None


# ===========================================================================
# router_v6/bottleneck_geometry.py — BottleneckGeometry.to_dict, grid_cell_size
# ===========================================================================


class TestBottleneckGeometry:
    """Covers BottleneckGeometry.to_dict."""

    def test_to_dict_ok(self):
        from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry

        bg = BottleneckGeometry(
            component_pair=("U1", "Q2"),
            pair_kind="component_component",
            positions_mm=((10.0, 20.0), (30.0, 40.0)),
            current_gap_mm=5.0,
            required_gap_mm=8.0,
            cut_size=3,
            cut_cells=((0, 5, 5), (0, 6, 5), (0, 5, 6)),
            message="U1 at (10.0, 20.0) and Q2 at (30.0, 40.0) create 5.0mm gap that needs 8.0mm",
            bottleneck_status="ok",
        )
        d = bg.to_dict()
        assert d["component_pair"] == ["U1", "Q2"]
        assert d["pair_kind"] == "component_component"
        assert d["positions_mm"] == [[10.0, 20.0], [30.0, 40.0]]
        assert d["current_gap_mm"] == 5.0
        assert d["required_gap_mm"] == 8.0
        assert d["cut_size"] == 3
        assert d["cut_cells"] == [[0, 5, 5], [0, 6, 5], [0, 5, 6]]
        assert d["message"] == "U1 at (10.0, 20.0) and Q2 at (30.0, 40.0) create 5.0mm gap that needs 8.0mm"
        assert d["bottleneck_status"] == "ok"

    def test_to_dict_aborted(self):
        from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry

        bg = BottleneckGeometry(
            component_pair=("U1", ""),
            pair_kind="component_component",
            positions_mm=((0.0, 0.0), (0.0, 0.0)),
            current_gap_mm=0.0,
            required_gap_mm=0.0,
            cut_size=0,
            cut_cells=(),
            message="N1: graph build failed",
            bottleneck_status="aborted_build_failure",
        )
        d = bg.to_dict()
        assert d["bottleneck_status"] == "aborted_build_failure"
        assert d["cut_cells"] == []


class TestGridCellSize:
    """Covers grid_cell_size."""

    def test_returns_cell_size_mm_from_object(self):
        from temper_placer.router_v6.bottleneck_geometry import grid_cell_size

        class FakeGrid:
            cell_size_mm = 2.5

        assert grid_cell_size(FakeGrid()) == 2.5

    def test_defaults_to_one(self):
        from temper_placer.router_v6.bottleneck_geometry import grid_cell_size

        class Stub:
            pass

        assert grid_cell_size(Stub()) == 1.0


# ===========================================================================
# router_v6/annular_ring_check.py — AnnularRingViolation.deficiency
# ===========================================================================


class TestAnnularRingViolation:
    """Covers AnnularRingViolation.deficiency."""

    def test_deficiency_positive(self):
        from temper_placer.router_v6.annular_ring_check import AnnularRingViolation

        v = AnnularRingViolation(
            net_name="N1",
            via_position=(10.0, 20.0),
            pad_diameter=0.6,
            drill_diameter=0.3,
            actual_ring_width=0.05,
            minimum_required=0.15,
        )
        assert v.deficiency == pytest.approx(0.10)

    def test_deficiency_zero(self):
        from temper_placer.router_v6.annular_ring_check import AnnularRingViolation

        v = AnnularRingViolation(
            net_name="N2",
            via_position=(0.0, 0.0),
            pad_diameter=1.0,
            drill_diameter=0.5,
            actual_ring_width=0.2,
            minimum_required=0.2,
        )
        assert v.deficiency == 0.0

    def test_deficiency_negative(self):
        """Ring is over-sized — deficiency is negative."""
        from temper_placer.router_v6.annular_ring_check import AnnularRingViolation

        v = AnnularRingViolation(
            net_name="N3",
            via_position=(0.0, 0.0),
            pad_diameter=2.0,
            drill_diameter=0.5,
            actual_ring_width=0.5,
            minimum_required=0.2,
        )
        assert v.deficiency == -0.30


# ===========================================================================
# router_v6/routing_results.py — RoutingResults properties
# ===========================================================================


class TestRoutingResults:
    """Covers RoutingResults.success_count, failure_count, total_route_length,
    get_route."""

    def test_success_count_from_compiled_routes(self):
        from temper_placer.router_v6.astar_core import RoutePath
        from temper_placer.router_v6.routing_results import (
            CompiledRoute,
            RoutingResults,
        )

        rr = RoutingResults(
            compiled_routes={
                "N1": CompiledRoute("N1", RoutePath("N1", [(0, 0), (1, 1)], "F.Cu", 1.0), 0.2, [], None),
                "N2": CompiledRoute("N2", RoutePath("N2", [(0, 0), (2, 2)], "F.Cu", 2.0), 0.2, [], None),
            },
            failed_nets=["N3"],
            plane_net_count=1,
        )
        assert rr.success_count == 3  # 2 compiled + 1 plane
        assert rr.failure_count == 1
        assert rr.get_route("N1") is not None
        assert rr.get_route("N99") is None

    def test_success_count_from_connectivity(self):
        from temper_placer.router_v6.connectivity import (
            ConnectivityComponent,
            NetConnectivity,
            NetDisposition,
            PadIdentity,
        )
        from temper_placer.router_v6.routing_results import RoutingResults

        rr = RoutingResults(
            compiled_routes={},
            failed_nets=[],
            connectivity={
                "N1": NetConnectivity(
                    net="N1",
                    disposition=NetDisposition.ROUTED,
                    connected_pad_count=2,
                    total_required_pad_count=2,
                    components=(),
                    unresolved_islands=(),
                ),
                "N2": NetConnectivity(
                    net="N2",
                    disposition=NetDisposition.PLANE_CONNECTED,
                    connected_pad_count=1,
                    total_required_pad_count=1,
                    components=(),
                    unresolved_islands=(),
                ),
                "N3": NetConnectivity(
                    net="N3",
                    disposition=NetDisposition.FAILED,
                    connected_pad_count=0,
                    total_required_pad_count=2,
                    components=(),
                    unresolved_islands=(),
                ),
            },
        )
        assert rr.success_count == 2  # ROUTED + PLANE_CONNECTED
        assert rr.failure_count == 1  # FAILED

    def test_total_route_length(self):
        from temper_placer.router_v6.astar_core import RoutePath
        from temper_placer.router_v6.routing_results import (
            CompiledRoute,
            RoutingResults,
        )

        rr = RoutingResults(
            compiled_routes={
                "N1": CompiledRoute("N1", RoutePath("N1", [(0, 0), (1, 1)], "F.Cu", 10.0), 0.2, [], None),
                "N2": CompiledRoute("N2", RoutePath("N2", [(0, 0), (2, 2)], "F.Cu", 5.5), 0.2, [], None),
            },
            failed_nets=[],
        )
        assert rr.total_route_length == 15.5

    def test_empty_results(self):
        from temper_placer.router_v6.routing_results import RoutingResults

        rr = RoutingResults(compiled_routes={}, failed_nets=[])
        assert rr.success_count == 0
        assert rr.failure_count == 0
        assert rr.total_route_length == 0.0
        assert rr.get_route("nonexistent") is None


# ===========================================================================
# router_v6/diagnostics.py — calculate_routing_score, aggregate_board_score, to_dict
# ===========================================================================


class TestCalculateRoutingScore:
    """Covers calculate_routing_score."""

    def test_perfect(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        assert calculate_routing_score(10, 10, 0) == 1.0

    def test_half(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        assert calculate_routing_score(5, 10, 0) == 0.5

    def test_drc_penalty(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        assert calculate_routing_score(10, 10, 3) == 0.7

    def test_zero_total_segments(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        assert calculate_routing_score(0, 0, 0) == 1.0

    def test_all_failed(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        assert calculate_routing_score(0, 10, 0) == 0.0

    def test_clamped_at_zero(self):
        from temper_placer.router_v6.diagnostics import calculate_routing_score

        # 0/10 = 0, - 10*0.1 = -1.0 -> clamped to 0.0
        assert calculate_routing_score(0, 10, 10) == 0.0


class TestAggregateBoardScore:
    """Covers aggregate_board_score."""

    def test_all_perfect(self):
        from temper_placer.router_v6.diagnostics import (
            FailureReason,
            NetRoutingReport,
            RoutingStatus,
            aggregate_board_score,
        )

        r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        r2 = NetRoutingReport("N2", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        assert aggregate_board_score([r1, r2]) == 1.0

    def test_one_failure_tanks(self):
        from temper_placer.router_v6.diagnostics import (
            NetRoutingReport,
            RoutingStatus,
            aggregate_board_score,
        )

        r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        r2 = NetRoutingReport("N2", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        r3 = NetRoutingReport("N3", RoutingStatus.FAILED, 0.0, 2, 0, 1)
        assert aggregate_board_score([r1, r2, r3]) == 0.0

    def test_empty(self):
        from temper_placer.router_v6.diagnostics import aggregate_board_score

        assert aggregate_board_score([]) == 0.0

    def test_mixed_scores(self):
        from temper_placer.router_v6.diagnostics import (
            NetRoutingReport,
            RoutingStatus,
            aggregate_board_score,
        )

        r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 0.5, 4, 2, 4)
        r2 = NetRoutingReport("N2", RoutingStatus.SUCCESS, 0.5, 4, 2, 4)
        # geometric mean of [0.5, 0.5] = 0.5
        assert aggregate_board_score([r1, r2]) == 0.5


class TestNetRoutingReportDict:
    """Covers NetRoutingReport.to_dict."""

    def test_to_dict_success(self):
        from temper_placer.router_v6.diagnostics import (
            NetRoutingReport,
            RoutingStatus,
        )

        r = NetRoutingReport(
            net_name="N1",
            status=RoutingStatus.SUCCESS,
            score=1.0,
            pins=2,
            routed_segments=1,
            total_segments=1,
            route_length_mm=12.5,
            direct_distance_mm=10.0,
            detour_ratio=1.25,
            drc_violations=0,
            layer=0,
            iterations_used=100,
            message="OK",
        )
        d = r.to_dict()
        assert d["net_name"] == "N1"
        assert d["status"] == "success"
        assert d["score"] == 1.0
        assert d["pins"] == 2
        assert d["route_length_mm"] == 12.5
        assert d["detour_ratio"] == 1.25
        assert d["bottleneck"] is None

    def test_to_dict_inf_detour(self):
        from temper_placer.router_v6.diagnostics import (
            NetRoutingReport,
            RoutingStatus,
        )

        r = NetRoutingReport("N1", RoutingStatus.FAILED, 0.0, 2, 0, 1)
        d = r.to_dict()
        assert d["detour_ratio"] is None  # inf → None

    def test_to_dict_with_failure_reason(self):
        from temper_placer.router_v6.diagnostics import (
            FailureReason,
            NetRoutingReport,
            RoutingStatus,
        )

        r = NetRoutingReport(
            "N1",
            RoutingStatus.FAILED,
            0.0,
            2,
            0,
            1,
            failure_reason=FailureReason.CHANNEL_CAPACITY,
        )
        d = r.to_dict()
        assert d["failure_reason"] == "channel_capacity"


class TestBoardRoutingReportDict:
    """Covers BoardRoutingReport.to_dict."""

    def test_to_dict(self):
        from temper_placer.router_v6.diagnostics import (
            BoardRoutingReport,
            NetRoutingReport,
            RoutingStatus,
        )

        nr = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
        br = BoardRoutingReport(
            board_name="test_board",
            net_reports=[nr],
            overall_score=1.0,
            auto_routed_count=1,
            flagged_count=0,
            failed_count=0,
            total_nets=1,
            completion_rate=1.0,
            total_route_length_mm=10.0,
            avg_detour_ratio=1.0,
            total_drc_violations=0,
            runtime_seconds=0.5,
        )
        d = br.to_dict()
        assert d["board_name"] == "test_board"
        assert len(d["net_reports"]) == 1
        assert d["overall_score"] == 1.0
        assert d["completion_rate"] == 1.0


# ===========================================================================
# router_v6/verifier.py — parse_verification_level
# ===========================================================================


class TestParseVerificationLevel:
    """Covers parse_verification_level."""

    def test_topological(self):
        from temper_placer.router_v6.verifier import (
            VerificationLevel,
            parse_verification_level,
        )

        assert parse_verification_level("topological") == VerificationLevel.TOPOLOGICAL
        assert parse_verification_level("TOPOLOGICAL") == VerificationLevel.TOPOLOGICAL
        assert parse_verification_level("Topological") == VerificationLevel.TOPOLOGICAL

    def test_geometric(self):
        from temper_placer.router_v6.verifier import (
            VerificationLevel,
            parse_verification_level,
        )

        assert parse_verification_level("geometric") == VerificationLevel.GEOMETRIC

    def test_maze(self):
        from temper_placer.router_v6.verifier import (
            VerificationLevel,
            parse_verification_level,
        )

        assert parse_verification_level("maze") == VerificationLevel.MAZE

    def test_invalid(self):
        import pytest

        from temper_placer.router_v6.verifier import parse_verification_level

        with pytest.raises(ValueError, match="Invalid verification level"):
            parse_verification_level("invalid_level")


# ===========================================================================
# router_v6/connectivity.py — CopperPad, CopperTrack, NetConnectivity
# ===========================================================================


class TestCopperPad:
    """Covers CopperPad.layers."""

    def test_layers(self):
        from temper_placer.router_v6.connectivity import (
            CopperPad,
            PadIdentity,
            Point,
        )

        pid = PadIdentity("U1", "1", "N1", 0.0, 0.0, (0, 1, 2))
        pad = CopperPad(identity=pid, center=Point(0.0, 0.0), shape="rect", size=(1.0, 1.0))
        assert pad.layers == frozenset({0, 1, 2})

    def test_layers_single(self):
        from temper_placer.router_v6.connectivity import (
            CopperPad,
            PadIdentity,
            Point,
        )

        pid = PadIdentity("U1", "1", "N1", 0.0, 0.0, (0,))
        pad = CopperPad(identity=pid, center=Point(0.0, 0.0), shape="rect", size=(1.0, 1.0))
        assert pad.layers == frozenset({0})


class TestCopperTrack:
    """Covers CopperTrack.segment."""

    def test_segment(self):
        from temper_placer.router_v6.connectivity import (
            CopperTrack,
            LineSegment,
            Point,
        )

        track = CopperTrack(start=Point(0.0, 0.0), end=Point(10.0, 20.0), layer=0)
        seg = track.segment
        assert isinstance(seg, LineSegment)
        assert seg.start.x == 0.0
        assert seg.start.y == 0.0
        assert seg.end.x == 10.0
        assert seg.end.y == 20.0


class TestNetConnectivity:
    """Covers NetConnectivity.connected_pad_ids."""

    def test_empty(self):
        from temper_placer.router_v6.connectivity import (
            ConnectivityComponent,
            NetConnectivity,
            NetDisposition,
        )

        nc = NetConnectivity(
            net="N1",
            disposition=NetDisposition.ROUTED,
            connected_pad_count=0,
            total_required_pad_count=0,
            components=(),
            unresolved_islands=(),
        )
        assert nc.connected_pad_ids == ()

    def test_with_pads(self):
        from temper_placer.router_v6.connectivity import (
            ConnectivityComponent,
            NetConnectivity,
            NetDisposition,
            PadIdentity,
        )

        pid1 = PadIdentity("U1", "1", "N1", 0.0, 0.0, (0,))
        pid2 = PadIdentity("U1", "2", "N1", 5.0, 0.0, (0,))
        comp = ConnectivityComponent(pads=(pid1, pid2))
        nc = NetConnectivity(
            net="N1",
            disposition=NetDisposition.ROUTED,
            connected_pad_count=2,
            total_required_pad_count=2,
            components=(comp,),
            unresolved_islands=(),
        )
        assert nc.connected_pad_ids == (pid1, pid2)


# ===========================================================================
# io/_write_types.py — WriteResult, StrippingResult, IsolationSlotResult
# ===========================================================================


class TestWriteResult:
    """Covers WriteResult.has_warnings."""

    def test_has_warnings_true(self):
        from temper_placer.io._write_types import WriteResult

        wr = WriteResult(
            output_path=Path("/tmp/test.pcb"),
            components_updated=5,
            components_skipped=2,
            warnings=["warning 1"],
        )
        assert wr.has_warnings is True

    def test_has_warnings_false(self):
        from temper_placer.io._write_types import WriteResult

        wr = WriteResult(
            output_path=Path("/tmp/test.pcb"),
            components_updated=5,
            components_skipped=0,
            warnings=[],
        )
        assert wr.has_warnings is False


class TestStrippingResult:
    """Covers StrippingResult.has_warnings."""

    def test_has_warnings_true(self):
        from temper_placer.io._write_types import StrippingResult

        sr = StrippingResult(
            output_path=Path("/tmp/stripped.pcb"),
            traces_removed=10,
            vias_removed=5,
            zones_removed=0,
            components_preserved=20,
            warnings=["something went wrong"],
        )
        assert sr.has_warnings is True

    def test_has_warnings_false(self):
        from temper_placer.io._write_types import StrippingResult

        sr = StrippingResult(
            output_path=Path("/tmp/stripped.pcb"),
            traces_removed=0,
            vias_removed=0,
            zones_removed=0,
            components_preserved=0,
            warnings=[],
        )
        assert sr.has_warnings is False


class TestIsolationSlotResult:
    """Covers IsolationSlotResult.has_warnings."""

    def test_has_warnings_true(self):
        from temper_placer.io._write_types import IsolationSlotResult

        isr = IsolationSlotResult(
            output_path=Path("/tmp/isolated.pcb"),
            slots_added=3,
            slots_skipped=1,  # Changed from skipped to slots_skipped
            warnings=["isolation warning"],
        )
        assert isr.has_warnings is True

    def test_has_warnings_false(self):
        from temper_placer.io._write_types import IsolationSlotResult

        isr = IsolationSlotResult(
            output_path=Path("/tmp/isolated.pcb"),
            slots_added=0,
            slots_skipped=0,
            warnings=[],
        )
        assert isr.has_warnings is False
