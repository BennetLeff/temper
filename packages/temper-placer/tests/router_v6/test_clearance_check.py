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
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    CompiledTreeRoute,
    RoutingResults,
)
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry


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

    results = RoutingResults(compiled_routes={"NET1": route1, "NET2": route2}, failed_nets=[])

    report = verify_clearance(results, min_clearance=0.127)

    # 5mm spacing >> 0.127mm requirement
    assert report.violation_count == 0


def test_verify_clearance_violation():
    """Test routes with insufficient clearance."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.2, [], None)  # Wide trace

    path2 = RoutePath("NET2", [(0, 0.2), (10, 0.2)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.2, [], None)  # Wide trace

    results = RoutingResults(compiled_routes={"NET1": route1, "NET2": route2}, failed_nets=[])

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

    results = RoutingResults(compiled_routes={"AC_L": hv_route, "SIG1": sig_route}, failed_nets=[])

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
        failed_nets=[],
    )

    report = verify_clearance(results)

    # Should check 3 pairs: NET1-NET2, NET1-NET3, NET2-NET3
    assert report.total_checks == 3


def _make_tree_route(net_name: str, other_x: float, y: float) -> CompiledTreeRoute:
    root = PadIdentity("U1", "1", net_name, 0.0, y, (0,))
    leaf = PadIdentity("U2", "1", net_name, other_x, y, (0,))
    geometry = TreeRouteGeometry(
        net_name,
        (
            TreeRouteBranch(
                TerminalTreeEdge(root, leaf),
                RoutePath(net_name, [(0, y), (other_x, y)], "F.Cu", abs(other_x)),
            ),
        ),
    )
    return CompiledTreeRoute(net_name=net_name, geometry=geometry, width_mm=0.2, vias=[])


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_verify_clearance_inspects_tree_routed_nets(backend):
    """Regression: tree-routed nets were invisible to clearance checking.

    ``verify_clearance`` used to walk only ``routing_results.compiled_routes``.
    ``RoutingResults.tree_routes`` / ``.partial_tree_routes`` hold
    ``CompiledTreeRoute`` objects (Steiner/multi-terminal routes) with their
    own copper geometry (``.geometry``) -- these were never checked against
    anything, so two tree-routed nets could overlap with zero clearance and
    the check would report 0 checks / 0 violations for that pair. Same class
    of bug as the ``annular_ring`` tree-route gap fixed in
    docs/evidence/2026-07-27-drc-checks-repaired.md. See
    docs/evidence/2026-07-27-clearance-copper-balance.md.

    Fails before the fix (``total_checks == 0``, tree routes never entered
    the pairwise walk at all); passes after (``total_checks == 1`` and the
    overlapping tree-routed pair is caught).
    """
    # Two tree-routed nets, both running along y=0 and y=0.05mm for 10mm --
    # 0.05mm apart, well under any plausible clearance requirement, exactly
    # like test_creepage_violation_count_bounded_by_net_pair_not_segment_pair's
    # fixture shape.
    tree1 = _make_tree_route("TREE1", 10.0, 0.0)
    tree2 = _make_tree_route("TREE2", 10.0, 0.05)

    results = RoutingResults(
        compiled_routes={},
        tree_routes={"TREE1": tree1, "TREE2": tree2},
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127, backend=backend)

    assert report.total_checks == 1
    assert report.violation_count == 1


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_verify_clearance_checks_compiled_against_tree_routed(backend):
    """A compiled_routes net and a tree_routes net must be checked against
    each other too, not just within their own dict."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    compiled = CompiledRoute("NET1", path1, 0.2, [], None)
    tree = _make_tree_route("NET2", 10.0, 0.05)

    results = RoutingResults(
        compiled_routes={"NET1": compiled},
        tree_routes={"NET2": tree},
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127, backend=backend)

    assert report.total_checks == 1
    assert report.violation_count == 1
