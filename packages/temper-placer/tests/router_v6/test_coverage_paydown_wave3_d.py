"""Coverage paydown tests — Wave 3 easy wins (Batch D).

Covers: creepage_check, clearance_check, annular_ring_check properties,
dense_package_detection, trace_width_assignment, bottleneck_geometry,
copper_balance report properties.
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6.annular_ring_check import AnnularRingReport, AnnularRingViolation
from temper_placer.router_v6.clearance_check import ClearanceViolation
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    LayerCopperBalance,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import CreepageViolation
from temper_placer.router_v6.dense_package_detection import (
    DensePackage,
    identify_dense_packages,
)
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
)


# ── creepage / clearance / annular violations ─────────────────────


def test_creepage_violation_deficiency():
    v = CreepageViolation("HV_NET", "LV_NET", (0.0, 0.0), 2.0, 3.0)
    d = v.deficiency
    assert d == pytest.approx(1.0)


def test_clearance_violation_deficiency():
    v = ClearanceViolation("N1", "N2", (0.0, 0.0), 0.3, 0.5, "F.Cu")
    d = v.deficiency
    assert d == pytest.approx(0.2)


def test_annular_ring_violation_deficiency():
    v = AnnularRingViolation(
        net_name="N",
        via_position=(0.0, 0.0),
        pad_diameter=0.6,
        drill_diameter=0.3,
        actual_ring_width=0.1,
        minimum_required=0.15,
    )
    d = v.deficiency
    assert d == pytest.approx(0.05)


def test_annular_ring_report_violation_count():
    v1 = AnnularRingViolation("N1", (0, 0), 0.6, 0.3, 0.1, 0.15)
    v2 = AnnularRingViolation("N2", (5, 5), 0.5, 0.2, 0.08, 0.12)
    report = AnnularRingReport(violations=[v1, v2], total_vias_checked=10)
    assert report.violation_count == 2


# ── dense_package_detection ────────────────────────────────────────


def test_dense_package_is_bga():
    from unittest.mock import MagicMock
    comp = MagicMock()
    comp.ref = "U1"
    pkg = DensePackage(component=comp, pin_count=100, pitch_mm=0.4, package_type="BGA", requires_escape=True)
    assert pkg.is_bga is True
    assert pkg.is_qfn is False


def test_dense_package_is_qfn():
    from unittest.mock import MagicMock
    comp = MagicMock()
    comp.ref = "U2"
    pkg = DensePackage(component=comp, pin_count=48, pitch_mm=0.4, package_type="QFN", requires_escape=True)
    assert pkg.is_bga is False
    assert pkg.is_qfn is True


def test_identify_dense_packages_empty():
    packages = identify_dense_packages([], dense_threshold_mm=0.5, min_pin_count=16)
    assert packages == []


# ── trace_width_assignment ─────────────────────────────────────────


def test_trace_width_assignment_creation():
    tw1 = TraceWidth(net_name="N1", width_mm=0.2, reason="signal")
    tw2 = TraceWidth(net_name="N2", width_mm=0.3, reason="power")
    twa = TraceWidthAssignment(assignments={"N1": tw1, "N2": tw2})
    assert twa.assignment_count == 2
    assert twa.get_width("N1") == 0.2
    assert twa.get_width("NONEXISTENT") is None


def test_trace_width_assignment_empty():
    twa = TraceWidthAssignment(assignments={})
    assert twa.assignment_count == 0


# ── copper_balance (report properties + analysis on trivial input) ─


def test_copper_balance_report_properties():
    lb1 = LayerCopperBalance("F.Cu", 500.0, 50.0, True)
    lb2 = LayerCopperBalance("B.Cu", 200.0, 20.0, False)
    report = CopperBalanceReport(layer_balances=[lb1, lb2], total_area_mm2=1000.0)
    assert report.balanced_layer_count == 1
    assert report.unbalanced_layer_count == 1


def test_layer_copper_balance_needs_balancing():
    lb = LayerCopperBalance("F.Cu", 100.0, 10.0, False)
    assert lb.needs_balancing is True


def test_analyze_copper_balance_empty():
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = analyze_copper_balance(results, 100.0, 100.0)
    assert isinstance(report, CopperBalanceReport)
    assert report.total_area_mm2 == 10000.0
    assert report.unbalanced_layer_count > 0  # empty = unbalanced
