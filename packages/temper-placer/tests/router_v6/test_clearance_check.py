"""
Tests for Router V6 Stage 5.7: Verify Clearance

Part of temper-8vjm
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    verify_clearance,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def test_verify_no_routes():
    """Test clearance verification with no routes."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    report = verify_clearance(results)

    assert report.violation_count == 0
    assert report.total_checks == 0


def test_verify_single_route():
    """Test clearance with single route (no violations possible)."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = verify_clearance(results)

    assert report.violation_count == 0


def test_verify_safe_clearance():
    """Test routes with safe clearance."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.127, [], None)

    path2 = RoutePath("NET2", [(0, 5), (10, 5)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.127, [], None)

    results = RoutingResults(
        compiled_routes={"NET1": route1, "NET2": route2},
        failed_nets=[]
    )

    report = verify_clearance(results, min_clearance=0.127)

    # 5mm spacing >> 0.127mm requirement
    assert report.violation_count == 0


def test_verify_clearance_violation():
    """Test routes with insufficient clearance."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.2, [], None)  # Wide trace

    path2 = RoutePath("NET2", [(0, 0.2), (10, 0.2)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.2, [], None)  # Wide trace

    results = RoutingResults(
        compiled_routes={"NET1": route1, "NET2": route2},
        failed_nets=[]
    )

    report = verify_clearance(results, min_clearance=0.127)

    # Edge-to-edge: 0.2 - 0.1 - 0.1 = 0.0 < 0.127mm
    assert report.violation_count > 0


def test_clearance_violation_dataclass():
    """Test ClearanceViolation dataclass."""
    violation = ClearanceViolation(
        net1="NET1",
        net2="NET2",
        location=(5.0, 5.0),
        actual_clearance=0.05,
        required_clearance=0.127,
        layer="F.Cu",
    )

    assert violation.net1 == "NET1"
    assert violation.net2 == "NET2"
    assert violation.layer == "F.Cu"
    assert violation.deficiency == pytest.approx(0.077)


def test_clearance_report_dataclass():
    """Test ClearanceReport dataclass."""
    violation = ClearanceViolation("NET1", "NET2", (0, 0), 0.05, 0.127, "F.Cu")

    report = ClearanceReport(violations=[violation], total_checks=10)

    assert report.violation_count == 1
    assert report.total_checks == 10
    assert report.pass_rate == 90.0


def test_hv_clearance_requirement():
    """Test increased clearance for HV nets."""
    # HV net
    hv_path = RoutePath("AC_L", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("AC_L", hv_path, 0.127, [], None)

    # Regular net
    sig_path = RoutePath("SIG1", [(0, 0.4), (10, 0.4)], "F.Cu", 10.0)
    sig_route = CompiledRoute("SIG1", sig_path, 0.127, [], None)

    results = RoutingResults(
        compiled_routes={"AC_L": hv_route, "SIG1": sig_route},
        failed_nets=[]
    )

    # Standard clearance 0.127mm
    report = verify_clearance(results, min_clearance=0.127)

    # Should still violate due to HV requiring 0.5mm
    # Edge-to-edge: ~0.336mm < 0.5mm
    assert report.violation_count > 0


def test_multiple_route_pairs():
    """Test clearance checking multiple route combinations."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.127, [], None)

    path2 = RoutePath("NET2", [(0, 5), (10, 5)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.127, [], None)

    path3 = RoutePath("NET3", [(0, 10), (10, 10)], "F.Cu", 10.0)
    route3 = CompiledRoute("NET3", path3, 0.127, [], None)

    results = RoutingResults(
        compiled_routes={
            "NET1": route1,
            "NET2": route2,
            "NET3": route3,
        },
        failed_nets=[]
    )

    report = verify_clearance(results)

    # Should check 3 pairs: NET1-NET2, NET1-NET3, NET2-NET3
    assert report.total_checks == 3
