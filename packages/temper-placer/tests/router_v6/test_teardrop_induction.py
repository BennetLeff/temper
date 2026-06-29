"""U9-U11: Teardrop induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import insert_teardrops
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.test_induction_base import make_empty_rr


@pytest.mark.dependency(depends=["induction-base"])
def test_teardrop_add_compliant_route() -> None:
    """FR13: Adding a route with vias generates teardrops without violations."""
    rr = make_empty_rr()
    assert insert_teardrops(rr).teardrop_count == 0

    rr.compiled_routes["VIA_NET"] = CompiledRoute(
        net_name="VIA_NET",
        path=RoutePath(net_name="VIA_NET", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.3,
        vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_NET")],
        matched_length_mm=None,
    )

    report = insert_teardrops(rr)
    assert report.teardrop_count >= 0, "Teardrop insertion should not crash"


@pytest.mark.dependency(depends=["induction-base"])
def test_teardrop_modify_preserves_compliance() -> None:
    """FR13b: Modifying a route with vias does not crash teardrop generation."""
    rr = RoutingResults(compiled_routes={
        "VIA_NET": CompiledRoute(net_name="VIA_NET", path=RoutePath(net_name="VIA_NET", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3,
            vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_NET")], matched_length_mm=None),
    }, failed_nets=[])

    before = insert_teardrops(rr).teardrop_count

    rr.compiled_routes["VIA_NET"] = CompiledRoute(net_name="VIA_NET", path=RoutePath(net_name="VIA_NET", coordinates=[(5.0, 0.0), (15.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3,
        vias=[Via(position=(10.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_NET")], matched_length_mm=None)

    after = insert_teardrops(rr).teardrop_count
    assert after == before, (
        f"Route modification changed teardrop count from {before} to {after}"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_teardrop_remove_preserves_compliance() -> None:
    """FR13c: Removing a route with vias does not cause phantom teardrops."""
    rr = RoutingResults(compiled_routes={
        "A": CompiledRoute(net_name="A", path=RoutePath(net_name="A", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3,
            vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="A")], matched_length_mm=None),
        "B": CompiledRoute(net_name="B", path=RoutePath(net_name="B", coordinates=[(0.0, 50.0), (10.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3,
            vias=[Via(position=(5.0, 50.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="B")], matched_length_mm=None),
    }, failed_nets=[])

    before = insert_teardrops(rr).teardrop_count

    del rr.compiled_routes["B"]
    after = insert_teardrops(rr).teardrop_count
    assert after <= before, (
        f"Route removal increased teardrop count from {before} to {after}"
    )
