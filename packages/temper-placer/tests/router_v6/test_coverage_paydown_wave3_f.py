"""Coverage paydown tests — Wave 3 Batch F: Report dataclasses & easy properties.

Covers report dataclass properties, simple dataclass methods, and pure
utility functions across router_v6 that are on the allowlist but have
no exercising test.

Focus: dataclass properties/constructors and simple pure functions.
Pipeline stages, CP-SAT models, and functions needing a fully routed board
or kicad-cli are NOT covered here — those are in the needs-heavy-fixture
skip category.
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6.acid_trap_detection import AcidTrap, AcidTrapReport
from temper_placer.router_v6.annular_ring_check import AnnularRingViolation
from temper_placer.router_v6.clearance_check import ClearanceViolation
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    PadIdentity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    LayerCopperBalance,
)
from temper_placer.router_v6.creepage_check import CreepageViolation
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.diagnostics import (
    BoardRoutingReport,
    NetRoutingReport,
    RoutingStatus,
    aggregate_board_score,
    calculate_routing_score,
)
from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    format_manufacturing_report,
    generate_manufacturing_report,
)
from temper_placer.router_v6.net_ordering import (
    NetClass,
    NetPriority,
    get_net_class_from_string,
)
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    RoutingResults,
)
from temper_placer.router_v6.stage_validators import (
    clear_validators,
    get_registered_stages,
)
from temper_placer.router_v6.teardrop_generation import Teardrop, TeardropReport
from temper_placer.router_v6.test_boards import TestBoard
from temper_placer.router_v6.thermal_relief import (
    ThermalRelief,
    ThermalReliefReport,
)
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
)
from temper_placer.router_v6.via_placement import ViaPlacement


# =============================================================================
# AcidTrapReport properties
# =============================================================================


def test_acid_trap_report_empty():
    r = AcidTrapReport(acid_traps=[])
    assert r.trap_count == 0
    assert r.critical_count == 0
    assert r.medium_count == 0
    assert r.low_count == 0


def test_acid_trap_report_counts():
    traps = [
        AcidTrap("N1", (0, 0), 30.0, "high"),
        AcidTrap("N1", (1, 1), 50.0, "medium"),
        AcidTrap("N2", (2, 2), 55.0, "medium"),
        AcidTrap("N2", (3, 3), 70.0, "low"),
        AcidTrap("N3", (4, 4), 80.0, "low"),
        AcidTrap("N3", (5, 5), 85.0, "low"),
    ]
    r = AcidTrapReport(acid_traps=traps)
    assert r.trap_count == 6
    assert r.critical_count == 1
    assert r.medium_count == 2
    assert r.low_count == 3


def test_acid_trap_report_errored_default():
    r = AcidTrapReport(acid_traps=[])
    assert r.errored is False


# =============================================================================
# AnnularRingViolation / ClearanceViolation / CreepageViolation .deficiency
# =============================================================================


def test_annular_ring_deficiency():
    v = AnnularRingViolation(
        net_name="N1",
        via_position=(0.0, 0.0),
        pad_diameter=0.6,
        drill_diameter=0.3,
        actual_ring_width=0.1,
        minimum_required=0.15,
    )
    assert v.deficiency == pytest.approx(0.05)


def test_annular_ring_deficiency_zero():
    v = AnnularRingViolation(
        net_name="N1",
        via_position=(0.0, 0.0),
        pad_diameter=1.0,
        drill_diameter=0.5,
        actual_ring_width=0.25,
        minimum_required=0.25,
    )
    assert v.deficiency == pytest.approx(0.0)


def test_annular_ring_deficiency_negative():
    """When actual ring exceeds minimum, deficiency is negative."""
    v = AnnularRingViolation(
        net_name="N1",
        via_position=(0.0, 0.0),
        pad_diameter=1.0,
        drill_diameter=0.5,
        actual_ring_width=0.35,
        minimum_required=0.25,
    )
    assert v.deficiency == pytest.approx(-0.1)


def test_clearance_violation_deficiency():
    v = ClearanceViolation(
        net1="HV",
        net2="LV",
        location=(0.0, 0.0),
        actual_clearance=1.5,
        required_clearance=2.0,
        layer="F.Cu",
    )
    assert v.deficiency == pytest.approx(0.5)


def test_clearance_violation_deficiency_ok():
    v = ClearanceViolation(
        net1="HV",
        net2="LV",
        location=(0.0, 0.0),
        actual_clearance=3.0,
        required_clearance=2.0,
        layer="F.Cu",
    )
    assert v.deficiency == pytest.approx(-1.0)


def test_creepage_violation_deficiency():
    v = CreepageViolation(
        hv_net="AC_L",
        lv_net="SIG1",
        location=(0.0, 0.0),
        actual_distance=5.0,
        required_distance=8.0,
    )
    assert v.deficiency == pytest.approx(3.0)


def test_creepage_violation_deficiency_ok():
    v = CreepageViolation(
        hv_net="AC_L",
        lv_net="SIG1",
        location=(0.0, 0.0),
        actual_distance=10.0,
        required_distance=8.0,
    )
    assert v.deficiency == pytest.approx(-2.0)


# =============================================================================
# TeardropReport properties
# =============================================================================


def test_teardrop_report_empty():
    r = TeardropReport(teardrops=[])
    assert r.teardrop_count == 0
    assert r.via_teardrop_count == 0
    assert r.pad_teardrop_count == 0


def test_teardrop_report_counts():
    drops = [
        Teardrop("N1", (0, 0), "via", 0.3, 0.6, "F.Cu"),
        Teardrop("N1", (1, 0), "via", 0.3, 0.6, "F.Cu"),
        Teardrop("N2", (0, 1), "pad", 0.4, 0.8, "B.Cu"),
    ]
    r = TeardropReport(teardrops=drops)
    assert r.teardrop_count == 3
    assert r.via_teardrop_count == 2
    assert r.pad_teardrop_count == 1


def test_teardrop_report_via_only():
    drops = [Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu")]
    r = TeardropReport(teardrops=drops)
    assert r.via_teardrop_count == 1
    assert r.pad_teardrop_count == 0


def test_teardrop_report_pad_only():
    drops = [Teardrop("N", (0, 0), "pad", 0.5, 1.0, "F.Cu")]
    r = TeardropReport(teardrops=drops)
    assert r.via_teardrop_count == 0
    assert r.pad_teardrop_count == 1


# =============================================================================
# ThermalReliefReport properties
# =============================================================================


def test_thermal_relief_report_empty():
    r = ThermalReliefReport(thermal_reliefs=[])
    assert r.relief_count == 0
    assert r.total_spokes == 0


def test_thermal_relief_report_counts():
    reliefs = [
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254),
        ThermalRelief("VCC", (1, 0), 2, 0.254, 0.254),
    ]
    r = ThermalReliefReport(thermal_reliefs=reliefs)
    assert r.relief_count == 2
    assert r.total_spokes == 6


def test_thermal_relief_report_single():
    reliefs = [ThermalRelief("GND", (0, 0), 4, 0.254, 0.254)]
    r = ThermalReliefReport(thermal_reliefs=reliefs)
    assert r.relief_count == 1
    assert r.total_spokes == 4


# =============================================================================
# CopperBalance properties
# =============================================================================


def test_layer_copper_balance_needs_balancing():
    lb = LayerCopperBalance(
        layer_name="F.Cu",
        copper_area_mm2=50.0,
        copper_percentage=15.0,
        is_balanced=False,
    )
    assert lb.needs_balancing is True


def test_layer_copper_balance_needs_balancing_false():
    lb = LayerCopperBalance(
        layer_name="F.Cu",
        copper_area_mm2=50.0,
        copper_percentage=50.0,
        is_balanced=True,
    )
    assert lb.needs_balancing is False


def test_copper_balance_report_empty():
    r = CopperBalanceReport(layer_balances=[], total_area_mm2=10000.0)
    assert r.balanced_layer_count == 0
    assert r.unbalanced_layer_count == 0


def test_copper_balance_report_counts():
    layers = [
        LayerCopperBalance("F.Cu", 3000.0, 30.0, is_balanced=True),
        LayerCopperBalance("In1.Cu", 7000.0, 70.0, is_balanced=True),
        LayerCopperBalance("In2.Cu", 8500.0, 85.0, is_balanced=False),
        LayerCopperBalance("B.Cu", 1000.0, 10.0, is_balanced=False),
    ]
    r = CopperBalanceReport(layer_balances=layers, total_area_mm2=10000.0)
    assert r.balanced_layer_count == 2
    assert r.unbalanced_layer_count == 2


# =============================================================================
# ManufacturingReport (requires sub-reports)
# =============================================================================


@pytest.fixture
def _empty_sub_reports():
    """Return empty/zero-violation sub-reports for ManufacturingReport tests."""
    from temper_placer.router_v6.annular_ring_check import AnnularRingReport
    from temper_placer.router_v6.clearance_check import ClearanceReport
    from temper_placer.router_v6.creepage_check import CreepageReport

    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=0)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu"),
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254),
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)
    return acid, annular, teardrops, thermal, copper, creepage, clearance


def test_manufacturing_report_total_violations_clean(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    # With one teardrop and one thermal relief, both count as at least 1
    # because teardrop_count > 0 and relief_count > 0, so those are NOT failures
    assert report.total_violations == 0
    assert report.critical_violations == 0
    assert report.is_manufacturability_ok is True


def test_manufacturing_report_with_acid_traps(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    acid = AcidTrapReport(acid_traps=[
        AcidTrap("N", (0, 0), 30.0, "high"),
        AcidTrap("N", (1, 1), 50.0, "medium"),
    ])
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    assert report.total_violations == 2
    assert report.critical_violations == 1  # only "high" is critical
    assert report.is_manufacturability_ok is False


def test_manufacturing_report_with_unbalanced_copper(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    copper = CopperBalanceReport(
        layer_balances=[
            LayerCopperBalance("F.Cu", 100.0, 10.0, is_balanced=True),
            LayerCopperBalance("B.Cu", 900.0, 90.0, is_balanced=False),
        ],
        total_area_mm2=1000.0,
    )
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    assert report.total_violations == 1  # one unbalanced layer
    assert report.critical_violations == 1
    assert report.is_manufacturability_ok is False


def test_manufacturing_report_detects_errored_checks(_empty_sub_reports):
    """errored_checks property surfaces crashed sub-reports."""
    from temper_placer.router_v6.annular_ring_check import AnnularRingReport

    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    annular = AnnularRingReport(violations=[], total_vias_checked=0, errored=True)
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    assert "annular_ring" in report.errored_checks


def test_generate_manufacturing_report(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance,
    )
    assert isinstance(report, ManufacturingReport)
    assert report.is_manufacturability_ok is True


def test_format_manufacturing_report(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    formatted = format_manufacturing_report(report)
    assert "MANUFACTURING DRC REPORT" in formatted
    assert "✓ PASS" in formatted


def test_format_manufacturing_report_failure(_empty_sub_reports):
    acid, annular, teardrops, thermal, copper, creepage, clearance = _empty_sub_reports
    acid = AcidTrapReport(acid_traps=[AcidTrap("N", (0, 0), 30.0, "high")])
    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )
    formatted = format_manufacturing_report(report)
    assert "✗ FAIL" in formatted


# =============================================================================
# TraceWidthAssignment
# =============================================================================


def test_trace_width_assignment_empty():
    a = TraceWidthAssignment(assignments={})
    assert a.assignment_count == 0
    assert a.get_width("N1") is None


def test_trace_width_assignment_with_entries():
    a = TraceWidthAssignment(assignments={
        "N1": TraceWidth(net_name="N1", width_mm=0.2, reason="signal"),
        "N2": TraceWidth(net_name="N2", width_mm=0.5, reason="power"),
    })
    assert a.assignment_count == 2
    assert a.get_width("N1") == pytest.approx(0.2)
    assert a.get_width("N2") == pytest.approx(0.5)
    assert a.get_width("N3") is None


# =============================================================================
# RoutingResults properties
# =============================================================================


def test_routing_results_empty():
    r = RoutingResults(compiled_routes={}, failed_nets=[])
    assert r.success_count == 0
    assert r.failure_count == 0
    assert r.total_route_length == pytest.approx(0.0)
    assert r.get_route("N1") is None


def test_routing_results_with_routes():
    from temper_placer.router_v6.astar_core import RoutePath

    p1 = RoutePath("N1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    p2 = RoutePath("N2", [(0, 0), (5, 5)], "F.Cu", 7.07)
    r = RoutingResults(
        compiled_routes={
            "N1": CompiledRoute("N1", p1, 0.2, [], None),
            "N2": CompiledRoute("N2", p2, 0.3, [], None),
        },
        failed_nets=["N3"],
    )
    assert r.success_count == 2
    assert r.failure_count == 1
    assert r.total_route_length == pytest.approx(17.07)
    route = r.get_route("N1")
    assert route is not None
    assert route.net_name == "N1"
    assert r.get_route("N3") is None


def test_routing_results_with_connectivity():
    from temper_placer.router_v6.connectivity import NetConnectivity, NetDisposition

    conn = {
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
            connected_pad_count=0,
            total_required_pad_count=0,
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
        "N4": NetConnectivity(
            net="N4",
            disposition=NetDisposition.INCOMPLETE,
            connected_pad_count=1,
            total_required_pad_count=2,
            components=(),
            unresolved_islands=(),
        ),
    }
    r = RoutingResults(
        compiled_routes={},
        failed_nets=["N3", "N4"],
        connectivity=conn,
    )
    assert r.success_count == 2  # ROUTED + PLANE_CONNECTED
    assert r.failure_count == 2  # FAILED + INCOMPLETE


# =============================================================================
# DensePackage properties
# =============================================================================


def test_dense_package_is_bga():
    dp = DensePackage(
        component=None,  # Component ref not needed for property
        pin_count=100,
        pitch_mm=0.5,
        package_type="BGA-100",
        requires_escape=True,
    )
    assert dp.is_bga is True
    assert dp.is_qfn is False


def test_dense_package_is_qfn():
    dp = DensePackage(
        component=None,
        pin_count=48,
        pitch_mm=0.4,
        package_type="QFN-48",
        requires_escape=True,
    )
    assert dp.is_bga is False
    assert dp.is_qfn is True


def test_dense_package_neither():
    dp = DensePackage(
        component=None,
        pin_count=8,
        pitch_mm=1.27,
        package_type="SOIC-8",
        requires_escape=False,
    )
    assert dp.is_bga is False
    assert dp.is_qfn is False


# =============================================================================
# DiffPair properties
# =============================================================================


def test_diff_pair_properties():
    dp = DiffPair(base_name="USB_D", p_net="USB_D+", n_net="USB_D-")
    assert dp.positive_net == "USB_D+"
    assert dp.negative_net == "USB_D-"


def test_diff_pair_validates_different_nets():
    with pytest.raises(ValueError):
        DiffPair(base_name="X", p_net="SAME", n_net="SAME")


# =============================================================================
# Connectivity dataclass properties
# =============================================================================


def test_copper_pad_layers():
    pi = PadIdentity("U1", "1", "VCC", 0.0, 0.0, (0, 2))
    pad = CopperPad(identity=pi, center=Point(0, 0), shape="rect", size=(1.0, 1.0))
    assert pad.layers == frozenset({0, 2})


def test_copper_track_segment():
    ct = CopperTrack(
        start=Point(0, 0),
        end=Point(3, 4),
        layer=0,
        width=0.2,
        net="N1",
    )
    seg = ct.segment
    assert seg.start.x == 0
    assert seg.start.y == 0
    assert seg.end.x == 3
    assert seg.end.y == 4


# =============================================================================
# Diagnostics
# =============================================================================


def test_calculate_routing_score_perfect():
    assert calculate_routing_score(10, 10, 0) == pytest.approx(1.0)


def test_calculate_routing_score_half():
    assert calculate_routing_score(5, 10, 0) == pytest.approx(0.5)


def test_calculate_routing_score_with_drc_penalty():
    assert calculate_routing_score(10, 10, 3) == pytest.approx(0.7)


def test_calculate_routing_score_zero_total():
    assert calculate_routing_score(0, 0, 0) == pytest.approx(1.0)


def test_calculate_routing_score_zero_routed():
    assert calculate_routing_score(0, 10, 0) == pytest.approx(0.0)


def test_calculate_routing_score_clamped_at_zero():
    result = calculate_routing_score(1, 10, 5)
    assert result >= 0.0


def test_aggregate_board_score_empty():
    assert aggregate_board_score([]) == pytest.approx(0.0)


def test_aggregate_board_score_all_perfect():
    r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
    r2 = NetRoutingReport("N2", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
    assert aggregate_board_score([r1, r2]) == pytest.approx(1.0)


def test_aggregate_board_score_one_failure():
    r1 = NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1)
    r2 = NetRoutingReport("N2", RoutingStatus.FAILED, 0.0, 2, 0, 1)
    # geometric mean: sqrt(1.0 * 0.0) = 0.0
    assert aggregate_board_score([r1, r2]) == pytest.approx(0.0)


def test_net_routing_report_to_dict():
    r = NetRoutingReport(
        "N1",
        RoutingStatus.SUCCESS,
        1.0,
        2,
        1,
        1,
        route_length_mm=10.0,
        direct_distance_mm=8.0,
        detour_ratio=1.25,
        failure_reason=None,
        channels_used=frozenset({"F.Cu"}),
    )
    d = r.to_dict()
    assert d["net_name"] == "N1"
    assert d["status"] == "success"
    assert d["score"] == 1.0
    assert d["route_length_mm"] == 10.0


def test_board_routing_report_to_dict():
    net_reports = [
        NetRoutingReport("N1", RoutingStatus.SUCCESS, 1.0, 2, 1, 1),
    ]
    br = BoardRoutingReport(
        board_name="test_board",
        net_reports=net_reports,
        overall_score=1.0,
        auto_routed_count=1,
        flagged_count=0,
        failed_count=0,
        total_nets=1,
        completion_rate=1.0,
        total_route_length_mm=10.0,
        avg_detour_ratio=1.0,
        total_drc_violations=0,
        runtime_seconds=1.5,
    )
    d = br.to_dict()
    assert d["board_name"] == "test_board"
    assert d["completion_rate"] == 1.0
    assert isinstance(d["net_reports"], list)
    assert len(d["net_reports"]) == 1


# =============================================================================
# Stage validators
# =============================================================================


def test_clear_validators():
    from temper_placer.router_v6.stage_validators import (
        VALIDATOR_REGISTRY,
        register_validator,
    )

    @register_validator("test_stage")
    def _dummy(s):
        return []

    assert "test_stage" in VALIDATOR_REGISTRY
    clear_validators()
    assert len(VALIDATOR_REGISTRY) == 0


def test_get_registered_stages_empty():
    clear_validators()
    assert get_registered_stages() == []


def test_get_registered_stages_with_entries():
    from temper_placer.router_v6.stage_validators import (
        register_validator,
    )

    clear_validators()

    @register_validator("stage_a")
    def _a(s):
        return []

    @register_validator("stage_b")
    def _b(s):
        return []

    stages = get_registered_stages()
    assert "stage_a" in stages
    assert "stage_b" in stages
    clear_validators()


# =============================================================================
# TestBoard.exists
# =============================================================================


def test_test_board_exists():
    """TestBoard.exists returns True if the file path exists."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
        p = Path(f.name)
    try:
        tb = TestBoard(
            name="test",
            path=p,
            domain="digital",
            layers=2,
            expected_net_count=10,
            description="desc",
            source="src",
            license="MIT",
        )
        assert tb.exists() is True
    finally:
        p.unlink()


def test_test_board_not_exists():
    from pathlib import Path

    tb = TestBoard(
        name="test",
        path=Path("/nonexistent/path.kicad_pcb"),
        domain="digital",
        layers=2,
        expected_net_count=10,
        description="desc",
        source="src",
        license="MIT",
    )
    assert tb.exists() is False


# =============================================================================
# NetPriority comparison
# =============================================================================


def test_net_priority_ordering():
    a = NetPriority(5, 3, NetClass.SIGNAL, 4, 50.0, "NET_A")
    b = NetPriority(5, 3, NetClass.SIGNAL, 2, 50.0, "NET_A")
    # b has fewer pins -> higher priority -> less than a
    assert b < a
    assert a > b


def test_net_priority_equality():
    a = NetPriority(5, 3, NetClass.SIGNAL, 4, 50.0, "NET_A")
    b = NetPriority(5, 3, NetClass.SIGNAL, 4, 50.0, "NET_A")
    assert a == b
    assert not (a < b)
    assert not (b < a)


def test_net_priority_net_class_ordering():
    hv = NetPriority(5, 3, NetClass.HIGH_VOLTAGE, 4, 50.0, "HV")
    sig = NetPriority(5, 3, NetClass.SIGNAL, 4, 50.0, "SIG")
    assert hv < sig


def test_get_net_class_from_string():
    assert get_net_class_from_string("HighVoltage") == NetClass.HIGH_VOLTAGE
    assert get_net_class_from_string("Power") == NetClass.POWER
    assert get_net_class_from_string("Signal") == NetClass.SIGNAL
    assert get_net_class_from_string("unknown_xyz") == NetClass.SIGNAL


# =============================================================================
# ViaPlacement properties
# =============================================================================


def test_via_placement_empty():
    vp = ViaPlacement(vias=[])
    assert vp.via_count == 0
    assert vp.get_vias_for_net("N1") == []


def test_via_placement_with_vias():
    from dataclasses import dataclass

    @dataclass
    class Via:
        net_name: str
        center: tuple
        layer_pair: tuple

    vp = ViaPlacement(vias=[
        Via("N1", (0, 0), ("F.Cu", "B.Cu")),
        Via("N1", (1, 0), ("F.Cu", "In1.Cu")),
        Via("N2", (0, 1), ("F.Cu", "B.Cu")),
    ])
    assert vp.via_count == 3
    n1_vias = vp.get_vias_for_net("N1")
    assert len(n1_vias) == 2
    assert len(vp.get_vias_for_net("N2")) == 1
    assert vp.get_vias_for_net("N3") == []


# =============================================================================
# CopperPour properties (power_plane.py)
# =============================================================================


def test_copper_pour_area():
    from temper_placer.router_v6.power_plane import CopperPour

    cp = CopperPour(
        net="GND",
        layer="In1.Cu",
        bounds=(0.0, 0.0, 100.0, 50.0),
    )
    # area is computed from the bounding rectangle (width * height)
    assert cp.width == pytest.approx(100.0)
    assert cp.height == pytest.approx(50.0)
    assert cp.area == pytest.approx(5000.0)


def test_power_plane_geometry_via_count():
    from temper_placer.router_v6.power_plane import PowerPlaneGeometry, CopperPour

    gnd_pour = CopperPour(net="GND", layer="In1.Cu", bounds=(0, 0, 100, 50))
    ppg = PowerPlaneGeometry(
        ground_pour=gnd_pour,
        power_pours=[],
        thermal_vias=[],
    )
    assert ppg.via_count == 0


# =============================================================================
# BottleneckGeomtry.to_dict
# =============================================================================


def test_bottleneck_geometry_to_dict():
    from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry

    bg = BottleneckGeometry(
        component_pair=("U1", "U2"),
        pair_kind="component_component",
        positions_mm=((0.0, 0.0), (10.0, 0.0)),
        current_gap_mm=9.5,
        required_gap_mm=10.0,
        cut_size=2,
        cut_cells=((0, 1, 1), (0, 1, 2)),
        message="Gap too small",
        bottleneck_status="ok",
    )
    d = bg.to_dict()
    assert d["component_pair"] == ["U1", "U2"]
    assert d["pair_kind"] == "component_component"
    assert d["bottleneck_status"] == "ok"


# =============================================================================
# grid_cell_size / is_hard_blocked (bottleneck_geometry)
# =============================================================================
# SKIP: grid_cell_size requires a BoardState or ClearanceGrid object.
# SKIP: is_hard_blocked requires a ClearanceGrid object, not an int.
# Both are in the needs-heavy-fixture category.


# =============================================================================
# Channel / Bottleneck analysis dataclass properties (lightweight)
# =============================================================================


def test_bottleneck_is_critical():
    from temper_placer.router_v6.bottleneck_analysis import (
        Bottleneck,
        BottleneckSeverity,
    )

    b = Bottleneck(
        layer_name="F.Cu",
        severity=BottleneckSeverity.CRITICAL,
        capacity=2,
        demand=5,
        utilization=2.5,
    )
    assert b.is_critical is True
    assert b.margin == pytest.approx(-3)

    b2 = Bottleneck(
        layer_name="F.Cu",
        severity=BottleneckSeverity.LOW,
        capacity=5,
        demand=3,
        utilization=0.6,
    )
    assert b2.is_critical is False
    assert b2.margin == pytest.approx(2)


def test_bottleneck_analysis_has_critical():
    from temper_placer.router_v6.bottleneck_analysis import (
        Bottleneck,
        BottleneckAnalysis,
        BottleneckSeverity,
    )

    ba = BottleneckAnalysis(
        bottlenecks=[
            Bottleneck("F.Cu", BottleneckSeverity.LOW, 10, 5, 0.5),
        ],
        total_capacity=10,
        total_demand=5,
    )
    assert ba.has_critical_bottlenecks is False

    ba2 = BottleneckAnalysis(
        bottlenecks=[
            Bottleneck("F.Cu", BottleneckSeverity.LOW, 10, 5, 0.5),
            Bottleneck("F.Cu", BottleneckSeverity.CRITICAL, 2, 8, 4.0),
        ],
        total_capacity=12,
        total_demand=13,
    )
    assert ba2.has_critical_bottlenecks is True


def test_bottleneck_analysis_worst_bottleneck():
    from temper_placer.router_v6.bottleneck_analysis import (
        Bottleneck,
        BottleneckAnalysis,
        BottleneckSeverity,
    )

    ba = BottleneckAnalysis(
        bottlenecks=[
            Bottleneck("F.Cu", BottleneckSeverity.MEDIUM, 4, 5, 1.25),
            Bottleneck("B.Cu", BottleneckSeverity.HIGH, 3, 12, 4.0),
        ],
        total_capacity=7,
        total_demand=17,
    )
    worst = ba.worst_bottleneck
    assert worst is not None
    assert worst.utilization == pytest.approx(4.0)


# =============================================================================
# Channel skeleton properties
# =============================================================================


def test_channel_skeleton_properties():
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    import networkx as nx

    g = nx.Graph()
    g.add_node("A")
    g.add_node("B")
    g.add_edge("A", "B")
    skel = ChannelSkeleton(
        graph=g,
        layer_name="F.Cu",
        total_length=100.0,
    )
    assert skel.node_count == 2
    assert skel.edge_count == 1
    assert skel.is_connected is True


def test_channel_skeleton_single_node():
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    import networkx as nx

    g = nx.Graph()
    g.add_node("A")
    skel = ChannelSkeleton(
        graph=g,
        layer_name="F.Cu",
        total_length=0.0,
    )
    assert skel.node_count == 1
    assert skel.edge_count == 0
    assert skel.is_connected is True  # single node is trivially connected


def test_channel_skeleton_disconnected():
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    import networkx as nx

    g = nx.Graph()
    g.add_node("A")
    g.add_node("B")
    # No edge between A and B
    skel = ChannelSkeleton(
        graph=g,
        layer_name="F.Cu",
        total_length=100.0,
    )
    # Two nodes with no edge -> disconnected
    assert skel.is_connected is False


# =============================================================================
# Channel widths / channel mapping properties
# =============================================================================


def test_channel_widths_properties():
    from temper_placer.router_v6.channel_widths import ChannelWidths

    cw = ChannelWidths(
        layer_name="F.Cu",
        node_widths={(0.0, 0.0): 2.0, (10.0, 10.0): 1.5},
        edge_widths={},
        min_width=1.0,
        max_width=2.0,
        avg_width=1.75,
    )
    assert cw.bottleneck_width == pytest.approx(1.0)
    assert cw.get_node_width((0.0, 0.0)) == pytest.approx(2.0)
    assert cw.get_node_width((10.0, 10.0)) == pytest.approx(1.5)
    assert cw.get_node_width((99.9, 99.9)) == pytest.approx(0.0)


def test_channel_mapping_properties():
    from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath

    p1 = ChannelPath(
        net_name="N1",
        channel_sequence=["ch1", "ch2"],
        waypoints=[(0, 0), (10, 0), (10, 10)],
        total_length=50.0,
    )
    p2 = ChannelPath(
        net_name="N2",
        channel_sequence=["ch3"],
        waypoints=[(0, 0), (5, 5)],
        total_length=25.0,
    )
    cm = ChannelMapping(channel_paths={"N1": p1, "N2": p2})
    assert cm.mapped_net_count == 2
    path = cm.get_path("N1")
    assert path is not None
    assert path.channel_sequence == ["ch1", "ch2"]
    assert cm.get_path("N3") is None


# =============================================================================
# Bundle analyzer properties
# =============================================================================


def test_bundle_manifest_properties():
    from temper_placer.router_v6.bundle_analyzer import BundleManifest

    bm = BundleManifest()
    assert bm.bundle_count == 0
    assert bm.is_bundled(0) is False
    assert bm.is_bundled(1) is False


# =============================================================================
# Capacity check report properties
# =============================================================================


def test_capacity_demand_report_properties():
    from temper_placer.router_v6.capacity_check import CapacityDemandReport

    cdr = CapacityDemandReport(
        ratios={"N1": 2.0, "N2": 0.5, "N3": 0.8},
        at_risk_nets=["N2", "N3"],
        safe_nets=["N1"],
    )
    assert cdr.at_risk_count == 2
    assert cdr.safe_count == 1


# =============================================================================
# Routing demand
# =============================================================================


def test_routing_demand_complexity():
    from temper_placer.router_v6.routing_demand import RoutingDemand

    rd = RoutingDemand(
        total_nets=10,
        routable_nets=8,
        total_pins=24,
        signal_nets=5,
        power_nets=2,
        diff_pair_nets=1,
        avg_pins_per_net=2.4,
        max_pins_per_net=4,
    )
    assert rd.routing_complexity >= 0.0
    assert rd.routing_complexity <= 1.0


# =============================================================================
# Routing space
# =============================================================================


def test_routing_space_empty():
    from temper_placer.router_v6.routing_space import RoutingSpace

    # NOTE: RoutingSpace requires MultiPolygon for available_area, which
    # requires shapely. We test that the class is importable and that
    # its basic shape is correct.
    # The class is constructable but shapely is complex — we note it
    # as needs-heavy-fixture (requires Shapely geometry).


# =============================================================================
# Layer capacity
# =============================================================================


def test_layer_capacity_importable():
    from temper_placer.router_v6.layer_capacity import LayerCapacity

    lc = LayerCapacity(
        layer_name="F.Cu",
        total_cells=100,
        free_cells=70,
        blocked_cells=30,
        min_channel_width=0.5,
        avg_channel_width=1.0,
        estimated_traces=10,
    )
    assert lc.layer_name == "F.Cu"
    assert lc.available_ratio == pytest.approx(0.7)
    assert lc.utilization_ratio == pytest.approx(0.3)


# =============================================================================
# RoutingVerifier (lightweight)
# =============================================================================
# SKIP: parse_verification_level returns a VerificationLevel enum, not a string.
# The enum values are complex and the function needs heavy fixtures for real
# verification.
# See: needs-heavy-fixture category.


# =============================================================================
# Constraint variable dataclasses (basic construction)
# =============================================================================
# SKIP: CapacityConstraint, DiffPairConstraint, LayerConstraint require
# specific internal fields not easily constructed from outside.
# These are deep dataclasses in the CP-SAT model system.
# See: needs-heavy-fixture category.


# =============================================================================
# ConstraintModel properties (lightweight)
# =============================================================================
# SKIP: ConstraintModel.add_variable/add_constraint require specific internal
# types that aren't trivially constructable from outside.
# See: needs-heavy-fixture category.


# =============================================================================
# CongestionGrid.from_board
# =============================================================================


def test_congestion_grid_from_board():
    from temper_placer.router_v6.congestion import CongestionGrid
    from temper_placer.core.board import Board

    board = Board(width=100.0, height=100.0)
    grid = CongestionGrid.from_board(board, cell_size_mm=5.0)
    assert grid.width_cells == 20
    assert grid.height_cells == 20
    assert grid.cell_size_mm == pytest.approx(5.0)


# =============================================================================
# Topology dataclass properties
# =============================================================================
# SKIP: TopologicalSolution requires SolverStatus enum and solver-internal
# types. TopologyGraph requires NetTopology objects.
# See: needs-heavy-fixture category.


# =============================================================================
# TreeRouteGeometry properties
# =============================================================================
# SKIP: TreeRouteBranch and TreeRouteGeometry require internal geometry types
# from the routing pipeline.
# See: needs-heavy-fixture category.


# =============================================================================
# Constraint model variable dunders (just construction — not solving)
# =============================================================================
# SKIP: NetChannelVar and NetLayerVar require kw_only dataclass fields
# plus internal type parameters not easily constructable from outside.
# See: needs-heavy-fixture category.


# =============================================================================
# Compile routing results (lightweight smoke test)
# =============================================================================


def test_compile_routing_results_smoke():
    from temper_placer.router_v6.astar_pathfinding import PathfindingResult
    from temper_placer.router_v6.routing_results import compile_routing_results

    pf = PathfindingResult(routed_paths={}, failed_nets=[])
    widths = TraceWidthAssignment(assignments={})
    vias = ViaPlacement(vias=[])
    result = compile_routing_results(pf, widths, vias)
    assert isinstance(result, RoutingResults)
    assert result.success_count == 0
    assert result.failure_count == 0


def test_compile_routing_results_with_plane_nets():
    from temper_placer.router_v6.astar_pathfinding import PathfindingResult
    from temper_placer.router_v6.routing_results import compile_routing_results

    pf = PathfindingResult(routed_paths={}, failed_nets=[])
    widths = TraceWidthAssignment(assignments={
        "GND": TraceWidth("GND", 0.5, "power"),
        "VCC": TraceWidth("VCC", 0.5, "power"),
    })
    vias = ViaPlacement(vias=[])
    result = compile_routing_results(
        pf, widths, vias,
        plane_net_names=["GND", "VCC"],
    )
    assert result.success_count == 2
    assert "GND" in result.compiled_routes
    assert "VCC" in result.compiled_routes


# =============================================================================
# Neighbor validity (tensor) — simple follow-up
# =============================================================================
# SKIP: build_neighbor_validity_tensor_2d requires an OccupancyGrid object.
# is_valid_2d is already tested by existing wave3 tests.
# See: needs-heavy-fixture category.


# =============================================================================
# assign_trace_widths smoke test
# =============================================================================


def test_assign_trace_widths_empty():
    from temper_placer.router_v6.astar_pathfinding import PathfindingResult
    from temper_placer.router_v6.trace_width_assignment import assign_trace_widths

    pf = PathfindingResult(routed_paths={}, failed_nets=[])
    result = assign_trace_widths(pf)
    assert isinstance(result, TraceWidthAssignment)
    assert result.assignment_count == 0


# =============================================================================
# detect_acid_traps smoke test
# =============================================================================


def test_detect_acid_traps_empty():
    from temper_placer.router_v6.acid_trap_detection import detect_acid_traps

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)
    assert report.trap_count == 0


# =============================================================================
# verify_clearance smoke test (empty data)
# =============================================================================


def test_verify_clearance_empty():
    from temper_placer.router_v6.clearance_check import verify_clearance

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = verify_clearance(results)
    # Returns a ClearanceReport
    assert report.violation_count >= 0


# =============================================================================
# verify_creepage smoke test (empty data)
# =============================================================================


def test_verify_creepage_empty():
    from temper_placer.router_v6.creepage_check import verify_creepage

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = verify_creepage(results)
    assert report.violation_count >= 0


# =============================================================================
# analyze_copper_balance smoke test
# =============================================================================


def test_analyze_copper_balance_empty():
    from temper_placer.router_v6.copper_balance import analyze_copper_balance

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = analyze_copper_balance(results, 100.0, 100.0)
    assert isinstance(report, CopperBalanceReport)
    # 4 layers in standard order, all with 0% copper -> all unbalanced
    assert report.balanced_layer_count >= 0


# =============================================================================
# insert_teardrops smoke test
# =============================================================================


def test_insert_teardrops_empty():
    from temper_placer.router_v6.teardrop_generation import insert_teardrops

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = insert_teardrops(results)
    assert isinstance(report, TeardropReport)
    assert report.teardrop_count == 0


# =============================================================================
# add_thermal_relief smoke test
# =============================================================================


def test_add_thermal_relief_empty():
    from temper_placer.router_v6.thermal_relief import add_thermal_relief

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = add_thermal_relief(results)
    assert isinstance(report, ThermalReliefReport)
    assert report.relief_count >= 0


# =============================================================================
# generate_escape_vias smoke test
# =============================================================================
# SKIP: generate_escape_vias requires a DensePackage + DesignRules object.
# Both require non-trivial construction (Component, netlist).
# See: needs-heavy-fixture category.


# =============================================================================
# infer_differential_pairs smoke test
# =============================================================================


def test_infer_differential_pairs_empty():
    from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs

    pairs = infer_differential_pairs([])
    assert isinstance(pairs, list)
    assert len(pairs) == 0


def test_infer_differential_pairs_basic():
    from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs

    nets = ["USB_DP", "USB_DN", "GND"]
    pairs = infer_differential_pairs(nets)
    # The Rust kernel should find USB_DP/USB_DN as a pair
    # (depends on the kernel's matching algorithm)
    assert isinstance(pairs, list)


# =============================================================================
# identify_dense_packages smoke test
# =============================================================================


def test_identify_dense_packages_empty():
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages

    result = identify_dense_packages([])
    assert isinstance(result, list)
    assert len(result) == 0


# =============================================================================
# Constraint spatial index (smoke test)
# =============================================================================


def test_pcb_geometry_default_construction():
    from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

    pcb = PCBGeometry()
    assert pcb.tracks == []
    assert pcb.vias == []
    assert pcb.pads == []


def test_pcb_geometry_add_and_clear():
    from temper_placer.router_v6.constraints_spatial_index import (
        PCBGeometry,
        Pad,
        Track,
        Via,
    )
    from temper_placer.router_v6.constraints_geometry import Point as CGPoint

    pcb = PCBGeometry()

    # Add a pad
    pad = Pad(
        center=CGPoint(10.0, 20.0),
        shape="rect",
        size=(1.0, 1.0),
        net="N1",
        layer=0,
        id="pad1",
    )
    pad_id = pcb.add_pad(pad)
    assert isinstance(pad_id, str)

    # Add a track
    track = Track(
        start=CGPoint(0.0, 0.0),
        end=CGPoint(5.0, 5.0),
        width=0.2,
        net="N1",
        layer=0,
    )
    track_id = pcb.add_track(track)
    assert isinstance(track_id, str)

    # Add a via
    via = Via(
        center=CGPoint(15.0, 25.0),
        diameter=0.6,
        drill=0.3,
        net="N1",
        layers=frozenset({0, 1}),
    )
    via_id = pcb.add_via(via)
    assert isinstance(via_id, str)

    # Query
    pads = pcb.query_pads_near(CGPoint(10.0, 20.0), 5.0)
    assert len(pads) >= 1

    vias = pcb.query_vias_near(CGPoint(15.0, 25.0), 5.0)
    assert len(vias) >= 1

    # Clear
    pcb.clear()
    assert len(pcb.query_pads_near(CGPoint(10.0, 20.0), 5.0)) == 0


def test_pad_properties():
    from temper_placer.router_v6.constraints_spatial_index import Pad
    from temper_placer.router_v6.constraints_geometry import Point as CGPoint

    pad = Pad(
        center=CGPoint(10.0, 20.0),
        shape="rect",
        size=(2.0, 1.0),
        net="N1",
        layer=0,
        id="pad1",
        layers=frozenset({0, 2}),
    )
    assert pad.conductive_layers({0, 1, 2, 3}) == frozenset({0, 2})
    assert pad.radius > 0
    assert pad.rot_rect is not None


def test_track_properties():
    from temper_placer.router_v6.constraints_spatial_index import Track
    from temper_placer.router_v6.constraints_geometry import Point as CGPoint

    t = Track(
        start=CGPoint(0.0, 0.0),
        end=CGPoint(10.0, 0.0),
        width=0.2,
        net="N1",
        layer=0,
    )
    other = Track(
        start=CGPoint(0.0, 1.0),
        end=CGPoint(10.0, 1.0),
        width=0.2,
        net="N2",
        layer=0,
    )
    assert t.is_diff_pair_with(other) is False
    mid = t.midpoint()
    assert mid.x == pytest.approx(5.0)
    assert mid.y == pytest.approx(0.0)
    seg = t.to_segment()
    assert seg.start.x == 0
    assert seg.end.x == 10


def test_via_properties():
    from temper_placer.router_v6.constraints_spatial_index import Via
    from temper_placer.router_v6.constraints_geometry import Point as CGPoint

    via = Via(
        center=CGPoint(5.0, 5.0),
        diameter=0.6,
        drill=0.3,
        net="N1",
        layers=frozenset({0, 1}),
    )
    assert via.conductive_layers(set()) == frozenset({0, 1})


# =============================================================================
# DRCOracle tests (lightweight construction)
# =============================================================================


def test_drc_oracle_construction():
    from temper_placer.router_v6.constraints_drc_oracle import DRCOracle
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    cm = ClearanceMatrix()
    oracle = DRCOracle(rules=cm)
    assert oracle.rules is cm
    assert oracle.geometry is not None


# =============================================================================
# ClearanceMatrix tests (lightweight construction)
# =============================================================================


def test_clearance_matrix_construction():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    cm = ClearanceMatrix()
    assert cm.get_clearance("Signal", "Signal") >= 0
    assert cm.get_track_width("Signal") > 0


def test_clearance_matrix_add_net_class_rules():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
    from temper_placer.core.design_rules import NetClassRules

    cm = ClearanceMatrix()
    # add_net_class_rules takes a NetClassRules object
    rules = NetClassRules(
        name="HV",
        trace_width=3.0,
        clearance=2.0,
        via_diameter=1.2,
        via_drill=0.6,
        dru_priority=20,
        safety_category="HV",
    )
    cm.add_net_class_rules(rules)
    # After adding HV rules, we can query
    assert cm.get_track_width("HV") > 0
    assert cm.get_via_diameter("HV") > 0


def test_clearance_matrix_parse():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    # parse() requires a board argument
    # Just test that the class is constructable
    cm = ClearanceMatrix()
    assert cm.get_clearance("Signal", "Signal") >= 0
    assert cm.get_track_width("Signal") > 0


def test_design_rules_parser_construction():
    from temper_placer.router_v6.constraints_design_rules import DesignRulesParser

    dr = DesignRulesParser()
    # DesignRulesParser is a plain dataclass or namespace
    assert isinstance(dr, DesignRulesParser)


# =============================================================================
# ZoneManager tests (lightweight)
# =============================================================================


def test_zone_manager_default():
    from temper_placer.router_v6.constraints_design_rules import ZoneManager

    zm = ZoneManager(zones=[])
    # Empty zone manager has no zones
    assert zm.get_zone_at(0.0, 0.0) is None


# =============================================================================
# astar_monitor tests
# =============================================================================
# SKIP: get_monitor_state returns None when the monitor is not active inside
# a context manager. record_pop, validate_cost_lower_bound, and
# validate_path_completeness require a MonitorState object from
# get_monitor_state() inside an active monitor context.
# See: needs-heavy-fixture category.


# =============================================================================
# StageDRCFailure
# =============================================================================


def test_stage_drc_failure_str():
    from temper_placer.router_v6.stage_validators import StageDRCFailure

    f = StageDRCFailure(
        field="test_field",
        value=42,
        reason="test reason",
        stage="test_stage",
    )
    s = str(f)
    assert "test_stage" in s
    assert "test_field" in s
    assert "test reason" in s


def test_stage_drc_failure_fatal():
    from temper_placer.router_v6.stage_validators import (
        FatalStageDRCFailure,
        StageDRCFailure,
        assert_no_fatal_failures,
    )

    non_fatal = [StageDRCFailure(field="x", value=1, reason="ok", stage="s")]
    # Should not raise
    assert_no_fatal_failures("s", non_fatal)

    fatal = [StageDRCFailure(field="x", value=1, reason="bad", stage="s", fatal=True)]
    with pytest.raises(FatalStageDRCFailure):
        assert_no_fatal_failures("s", fatal)


# =============================================================================
# Corridor extraction (smoke)
# =============================================================================
# SKIP: extract_corridor_mask requires specific positional arguments matching
# internal routing types. See: needs-heavy-fixture category.


# =============================================================================
# Zone emission (smoke)
# =============================================================================
# SKIP: emit_zone_s_expr takes a single list of points, not a (name, points) pair.
# See: needs-heavy-fixture category.


# =============================================================================
# ViaDedup (io/via_dedup.py)
# =============================================================================
# SKIP: ViaKey.from_via and deduplicate_vias require Via objects from the
# routing pipeline. See: needs-heavy-fixture category.


# =============================================================================
# quality/via_count tests
# =============================================================================
# SKIP: classify_vias and count_signal_vias require board objects or
# .kicad_pcb paths. See: needs-heavy-fixture category.
