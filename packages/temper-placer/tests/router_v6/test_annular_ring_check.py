"""
Tests for Router V6 Stage 5.2: Check Annular Rings

Part of temper-j2xd
"""

import pytest

from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    AnnularRingViolation,
    check_annular_rings,
)
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    CompiledTreeRoute,
    RoutingResults,
)
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry
from temper_placer.router_v6.via_placement import Via


def test_check_no_vias():
    """Test annular ring check with no vias."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = check_annular_rings(results)

    assert report.total_vias_checked == 0
    assert report.violation_count == 0
    assert report.pass_rate == 100.0


def test_check_via_passes():
    """Test via with adequate annular ring."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)

    # Via with good annular ring: 0.6mm pad, 0.3mm drill = 0.15mm ring
    via = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 1
    assert report.violation_count == 0
    assert report.pass_rate == 100.0


def test_check_via_fails():
    """Test via with insufficient annular ring."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)

    # Via with poor annular ring: 0.4mm pad, 0.35mm drill = 0.025mm ring
    via = Via((5, 5), "F.Cu", "B.Cu", 0.4, 0.35, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 1
    assert report.violation_count == 1
    assert report.pass_rate == 0.0


def test_annular_ring_violation_dataclass():
    """Test AnnularRingViolation dataclass."""
    violation = AnnularRingViolation(
        net_name="TEST_NET",
        via_position=(5.0, 5.0),
        pad_diameter=0.4,
        drill_diameter=0.35,
        actual_ring_width=0.025,
        minimum_required=0.1,
    )

    assert violation.net_name == "TEST_NET"
    assert violation.via_position == (5.0, 5.0)
    assert violation.deficiency == pytest.approx(0.075)


def test_annular_ring_report_dataclass():
    """Test AnnularRingReport dataclass."""
    violation = AnnularRingViolation("NET1", (0, 0), 0.4, 0.35, 0.025, 0.1)

    report = AnnularRingReport(violations=[violation], total_vias_checked=5)

    assert report.violation_count == 1
    assert report.total_vias_checked == 5
    assert report.pass_rate == 80.0  # 4 out of 5 pass


def test_check_multiple_vias():
    """Test checking multiple vias."""
    path = RoutePath("NET1", [(0, 0), (20, 20)], "F.Cu", 28.28)

    via1 = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")  # Pass
    via2 = Via((10, 10), "F.Cu", "B.Cu", 0.4, 0.35, "NET1")  # Fail
    via3 = Via((15, 15), "F.Cu", "B.Cu", 0.8, 0.4, "NET1")  # Pass

    route = CompiledRoute("NET1", path, 0.127, [via1, via2, via3], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 3
    assert report.violation_count == 1
    assert report.pass_rate == pytest.approx(66.67, abs=0.1)


def test_check_multiple_nets():
    """Test checking vias across multiple nets."""
    path1 = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    via1 = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")  # Pass
    route1 = CompiledRoute("NET1", path1, 0.127, [via1], None)

    path2 = RoutePath("NET2", [(0, 0), (10, 10)], "F.Cu", 14.14)
    via2 = Via((5, 5), "F.Cu", "B.Cu", 0.4, 0.35, "NET2")  # Fail
    route2 = CompiledRoute("NET2", path2, 0.127, [via2], None)

    results = RoutingResults(compiled_routes={"NET1": route1, "NET2": route2}, failed_nets=[])

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 2
    assert report.violation_count == 1


def test_check_annular_rings_inspects_tree_routed_vias():
    """Regression test: tree-routed nets' vias were never inspected.

    ``RoutingResults.tree_routes`` / ``.partial_tree_routes`` hold
    ``CompiledTreeRoute`` objects with their own ``.vias`` list -- the
    same kind of ``Via`` objects the exporter (``_adapter_convert.py``,
    "U7") writes real ``(via ...)`` s-expressions from. On a board where
    most copper is tree-routed (Steiner-style multi-terminal nets),
    ``check_annular_rings`` used to only walk ``compiled_routes`` and
    silently inspect zero vias while the exported board had dozens
    physically present -- this is the "0 violations over 0 checks on a
    board with 48 vias" bug from
    docs/evidence/2026-07-27-committed-route.md. This test fails before
    the fix (``total_vias_checked == 0``) and passes after
    (``total_vias_checked == 1``, and the undersized via is caught).
    """
    net_name = "NET1"
    root = PadIdentity("U1", "1", net_name, 0.0, 0.0, (0,))
    leaf = PadIdentity("U2", "1", net_name, 10.0, 0.0, (0,))
    geometry = TreeRouteGeometry(
        net_name,
        (
            TreeRouteBranch(
                TerminalTreeEdge(root, leaf),
                RoutePath(net_name, [(0, 0), (10, 0)], "F.Cu", 10.0),
            ),
        ),
    )
    # Undersized via: 0.4mm pad, 0.35mm drill = 0.025mm ring < 0.1mm min.
    bad_via = Via((5, 0), "F.Cu", "B.Cu", 0.4, 0.35, net_name)
    tree_route = CompiledTreeRoute(
        net_name=net_name,
        geometry=geometry,
        width_mm=0.127,
        vias=[bad_via],
    )
    results = RoutingResults(
        compiled_routes={},
        tree_routes={net_name: tree_route},
        failed_nets=[],
    )

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 1
    assert report.violation_count == 1


def test_check_annular_rings_inspects_partial_tree_routed_vias():
    """Same regression as above, for ``partial_tree_routes``."""
    net_name = "NET1"
    root = PadIdentity("U1", "1", net_name, 0.0, 0.0, (0,))
    leaf = PadIdentity("U2", "1", net_name, 10.0, 0.0, (0,))
    geometry = TreeRouteGeometry(
        net_name,
        (
            TreeRouteBranch(
                TerminalTreeEdge(root, leaf),
                RoutePath(net_name, [(0, 0), (10, 0)], "F.Cu", 10.0),
            ),
        ),
    )
    good_via = Via((5, 0), "F.Cu", "B.Cu", 0.6, 0.3, net_name)
    tree_route = CompiledTreeRoute(
        net_name=net_name,
        geometry=geometry,
        width_mm=0.127,
        vias=[good_via],
    )
    results = RoutingResults(
        compiled_routes={},
        partial_tree_routes={net_name: tree_route},
        failed_nets=[],
    )

    report = check_annular_rings(results, min_annular_ring=0.1)

    assert report.total_vias_checked == 1
    assert report.violation_count == 0
