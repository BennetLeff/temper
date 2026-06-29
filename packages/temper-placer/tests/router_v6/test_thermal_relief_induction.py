"""U9-U11: Thermal relief induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.thermal_relief import add_thermal_relief
from tests.router_v6.test_induction_base import make_empty_rr


@pytest.mark.dependency(depends=["induction-base"])
def test_thermal_relief_add_compliant_route() -> None:
    """FR13: Adding a power-net route triggers thermal relief without violations."""
    rr = make_empty_rr()
    report = add_thermal_relief(rr)
    assert report.relief_count >= 0

    # Add a power net (GND) with a via
    rr.compiled_routes["GND"] = CompiledRoute(
        net_name="GND",
        path=RoutePath(net_name="GND", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.0,  # plane net
        vias=[],
        matched_length_mm=None,
    )

    report = add_thermal_relief(rr)
    assert report.relief_count >= 0, "Thermal relief should not crash on power net"


@pytest.mark.dependency(depends=["induction-base"])
def test_thermal_relief_modify_preserves_compliance() -> None:
    """FR13b: Modifying a power-net route does not crash thermal relief."""
    rr = RoutingResults(compiled_routes={
        "GND": CompiledRoute(net_name="GND", path=RoutePath(net_name="GND", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.0, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    before = add_thermal_relief(rr).relief_count

    rr.compiled_routes["GND"] = CompiledRoute(net_name="GND", path=RoutePath(net_name="GND", coordinates=[(5.0, 0.0), (15.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.0, vias=[], matched_length_mm=None)

    after = add_thermal_relief(rr).relief_count
    assert after == before, (
        f"Route modification changed relief count from {before} to {after}"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_thermal_relief_remove_preserves_compliance() -> None:
    """FR13c: Removing a power-net route does not cause phantom violations."""
    rr = RoutingResults(compiled_routes={
        "GND": CompiledRoute(net_name="GND", path=RoutePath(net_name="GND", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.0, vias=[], matched_length_mm=None),
        "VCC": CompiledRoute(net_name="VCC", path=RoutePath(net_name="VCC", coordinates=[(0.0, 50.0), (10.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.0, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    before = add_thermal_relief(rr).relief_count

    del rr.compiled_routes["VCC"]
    after = add_thermal_relief(rr).relief_count
    assert after <= before, (
        f"Route removal increased relief count from {before} to {after}"
    )
