"""U9-U11: Annular ring induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.annular_ring_check import check_annular_rings
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via


@pytest.mark.dependency(depends=["induction-base"])
def test_annular_ring_add_compliant_route() -> None:
    """FR13: Adding a route with compliant vias does not create violations."""
    rr = RoutingResults(compiled_routes={}, failed_nets=[])
    assert check_annular_rings(rr).violation_count == 0

    # Via with pad=1.0, drill=0.3, ring=0.35 >= 0.05 → compliant
    compliant = CompiledRoute(
        net_name="VIA_OK",
        path=RoutePath(net_name="VIA_OK", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.2,
        vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_OK")],
        matched_length_mm=None,
    )
    rr.compiled_routes["VIA_OK"] = compliant

    report = check_annular_rings(rr)
    assert report.violation_count == 0, (
        f"Adding compliant-via route caused {report.violation_count} annular ring violations"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_annular_ring_modify_preserves_compliance() -> None:
    """FR13b: Modifying a route while keeping vias compliant does not cause violations."""
    rr = RoutingResults(compiled_routes={
        "VIA_OK": CompiledRoute(net_name="VIA_OK", path=RoutePath(net_name="VIA_OK", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2,
            vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_OK")], matched_length_mm=None),
    }, failed_nets=[])
    assert check_annular_rings(rr).violation_count == 0

    # Shift route but keep same via
    rr.compiled_routes["VIA_OK"] = CompiledRoute(net_name="VIA_OK", path=RoutePath(net_name="VIA_OK", coordinates=[(5.0, 0.0), (15.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2,
        vias=[Via(position=(10.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="VIA_OK")], matched_length_mm=None)

    report = check_annular_rings(rr)
    assert report.violation_count == 0, (
        f"Route modification caused {report.violation_count} annular ring violations"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_annular_ring_remove_preserves_compliance() -> None:
    """FR13c: Removing a route with vias does not cause phantom violations."""
    rr = RoutingResults(compiled_routes={
        "A": CompiledRoute(net_name="A", path=RoutePath(net_name="A", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2,
            vias=[Via(position=(5.0, 0.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="A")], matched_length_mm=None),
        "B": CompiledRoute(net_name="B", path=RoutePath(net_name="B", coordinates=[(0.0, 50.0), (10.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2,
            vias=[Via(position=(5.0, 50.0), from_layer="F.Cu", to_layer="In1.Cu", diameter=1.0, drill=0.3, net_name="B")], matched_length_mm=None),
    }, failed_nets=[])
    before = check_annular_rings(rr).violation_count

    del rr.compiled_routes["B"]
    after = check_annular_rings(rr).violation_count
    assert after <= before, (
        f"Route removal increased violations from {before} to {after}"
    )
