"""U9-U11: Creepage induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


@pytest.mark.dependency(depends=["induction-base"])
def test_creepage_add_compliant_route() -> None:
    """FR13: Adding a compliant route on same layer does not cause creepage violations."""
    min_clearance = 0.127
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    assert verify_creepage(rr).violation_count == 0

    rr.compiled_routes["SIG2"] = CompiledRoute(net_name="SIG2", path=RoutePath(net_name="SIG2", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None)

    report = verify_creepage(rr)
    assert report.violation_count == 0, (
        f"Adding compliant route caused {report.violation_count} creepage violations"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_creepage_modify_preserves_compliance() -> None:
    """FR13b: Modifying a compliant route does not introduce creepage violations."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
        "SIG2": CompiledRoute(net_name="SIG2", path=RoutePath(net_name="SIG2", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    assert verify_creepage(rr).violation_count == 0

    # Modify SIG1
    rr.compiled_routes["SIG1"] = CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(15.0, 10.0), (25.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None)

    report = verify_creepage(rr)
    assert report.violation_count == 0, (
        f"Route modification caused {report.violation_count} creepage violations"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_creepage_remove_preserves_compliance() -> None:
    """FR13c: Removing a compliant route does not cause phantom violations."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
        "SIG2": CompiledRoute(net_name="SIG2", path=RoutePath(net_name="SIG2", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
        "SIG3": CompiledRoute(net_name="SIG3", path=RoutePath(net_name="SIG3", coordinates=[(10.0, 100.0), (20.0, 100.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.2, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    assert verify_creepage(rr).violation_count == 0

    del rr.compiled_routes["SIG2"]
    report = verify_creepage(rr)
    assert report.violation_count == 0, (
        f"Route removal caused {report.violation_count} creepage violations"
    )
