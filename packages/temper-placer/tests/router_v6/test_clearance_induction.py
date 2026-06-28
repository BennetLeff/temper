"""U9-U11: Clearance induction — addition / modification / removal (FR13, FR13b, FR13c)."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.router_v6.sat_property_strategies import known_compliant_route


def _empty_rr() -> RoutingResults:
    return RoutingResults(compiled_routes={}, failed_nets=[])


@pytest.mark.dependency(depends=["induction-base"], name="clearance-add")
def test_clearance_add_compliant_route() -> None:
    """FR13: Adding a compliant route on the same layer does not cause
    clearance violations."""
    min_clearance = 0.127

    rr = _empty_rr()
    assert verify_clearance(rr, min_clearance=min_clearance).violation_count == 0

    route = known_compliant_route(layer="F.Cu")
    # Simulate the draw
    from hypothesis import find
    route = find(
        known_compliant_route(layer="F.Cu"),
        lambda r: r.net_name and len(r.path.coordinates) >= 2,
    )

    rr.compiled_routes[route.net_name] = route
    report = verify_clearance(rr, min_clearance=min_clearance)
    assert report.violation_count == 0, (
        f"Adding compliant route {route.net_name} caused {report.violation_count} "
        f"clearance violations"
    )


@pytest.mark.dependency(depends=["clearance-add"])
def test_clearance_add_non_compliant_detected() -> None:
    """SC5: Adding a non-compliant route (0.01mm below threshold) must be detected."""
    min_clearance = 0.127

    rr = RoutingResults(
        compiled_routes={
            "A": CompiledRoute(
                net_name="A",
                path=RoutePath(net_name="A", coordinates=[(0.0, 0.0), (10.0, 0.0)], layer_name="F.Cu", path_length=10.0),
                width_mm=0.127, vias=[], matched_length_mm=None,
            ),
        },
        failed_nets=[],
    )
    assert verify_clearance(rr, min_clearance=min_clearance).violation_count == 0

    # Add a non-compliant route too close to "A"
    non_compliant = CompiledRoute(
        net_name="B",
        path=RoutePath(net_name="B", coordinates=[(0.0, min_clearance - 0.01), (10.0, min_clearance - 0.01)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.127, vias=[], matched_length_mm=None,
    )
    rr.compiled_routes["B"] = non_compliant
    report = verify_clearance(rr, min_clearance=min_clearance)
    assert report.violation_count >= 1, (
        f"Non-compliant route should be detected, got {report.violation_count} violations"
    )


@pytest.mark.dependency(depends=["clearance-add"], name="clearance-modify")
def test_clearance_modify_preserves_compliance() -> None:
    """FR13b: Modifying a compliant route (shifting it) does not introduce
    false positives."""
    min_clearance = 0.127

    path_a = RoutePath(net_name="A", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0)
    path_b = RoutePath(net_name="B", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0)
    rr = RoutingResults(
        compiled_routes={
            "A": CompiledRoute(net_name="A", path=path_a, width_mm=0.127, vias=[], matched_length_mm=None),
            "B": CompiledRoute(net_name="B", path=path_b, width_mm=0.127, vias=[], matched_length_mm=None),
        },
        failed_nets=[],
    )
    assert verify_clearance(rr, min_clearance=min_clearance).violation_count == 0

    # Modify route A by shifting it 5mm in x
    modified_path = RoutePath(net_name="A", coordinates=[(15.0, 10.0), (25.0, 10.0)], layer_name="F.Cu", path_length=10.0)
    rr.compiled_routes["A"] = CompiledRoute(net_name="A", path=modified_path, width_mm=0.127, vias=[], matched_length_mm=None)

    report = verify_clearance(rr, min_clearance=min_clearance)
    assert report.violation_count == 0, (
        f"Route modification caused {report.violation_count} clearance violations"
    )


@pytest.mark.dependency(depends=["clearance-add"], name="clearance-remove")
def test_clearance_remove_preserves_compliance() -> None:
    """FR13c: Removing a compliant route does not cause phantom violations."""
    min_clearance = 0.127

    path_a = RoutePath(net_name="A", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0)
    path_b = RoutePath(net_name="B", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0)
    path_c = RoutePath(net_name="C", coordinates=[(10.0, 100.0), (20.0, 100.0)], layer_name="F.Cu", path_length=10.0)
    rr = RoutingResults(
        compiled_routes={
            "A": CompiledRoute(net_name="A", path=path_a, width_mm=0.127, vias=[], matched_length_mm=None),
            "B": CompiledRoute(net_name="B", path=path_b, width_mm=0.127, vias=[], matched_length_mm=None),
            "C": CompiledRoute(net_name="C", path=path_c, width_mm=0.127, vias=[], matched_length_mm=None),
        },
        failed_nets=[],
    )
    assert verify_clearance(rr, min_clearance=min_clearance).violation_count == 0

    # Remove route B
    del rr.compiled_routes["B"]
    report = verify_clearance(rr, min_clearance=min_clearance)
    assert report.violation_count == 0, (
        f"Route removal caused {report.violation_count} clearance violations"
    )
