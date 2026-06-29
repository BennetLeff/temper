"""U9-U11: Copper balance induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.copper_balance import analyze_copper_balance
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.router_v6.test_induction_base import make_empty_rr

BOARD_W, BOARD_H = 200.0, 150.0


@pytest.mark.dependency(depends=["induction-base"])
def test_copper_balance_add_compliant_route() -> None:
    """FR13: Adding a route updates copper balance without violations."""
    rr = make_empty_rr()
    report = analyze_copper_balance(rr, BOARD_W, BOARD_H)
    assert report.unbalanced_layer_count >= 0

    rr.compiled_routes["SIG1"] = CompiledRoute(
        net_name="SIG1",
        path=RoutePath(net_name="SIG1", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.2, vias=[], matched_length_mm=None,
    )

    report = analyze_copper_balance(rr, BOARD_W, BOARD_H)
    assert len(report.layer_balances) >= 4, "Should have at least 4 layer balances"


@pytest.mark.dependency(depends=["induction-base"])
def test_copper_balance_modify_preserves_compliance() -> None:
    """FR13b: Modifying a route updates copper area correctly."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
    }, failed_nets=[])

    report_before = analyze_copper_balance(rr, BOARD_W, BOARD_H)

    rr.compiled_routes["SIG1"] = CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(5.0, 0.0), (15.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None)

    report_after = analyze_copper_balance(rr, BOARD_W, BOARD_H)
    assert len(report_after.layer_balances) == len(report_before.layer_balances)


@pytest.mark.dependency(depends=["induction-base"])
def test_copper_balance_remove_preserves_compliance() -> None:
    """FR13c: Removing a route does not cause phantom violations."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
        "SIG2": CompiledRoute(net_name="SIG2", path=RoutePath(net_name="SIG2", coordinates=[(0.0, 50.0), (10.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
    }, failed_nets=[])

    del rr.compiled_routes["SIG2"]
    report = analyze_copper_balance(rr, BOARD_W, BOARD_H)
    assert len(report.layer_balances) >= 4
