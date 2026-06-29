"""U9-U11: Acid trap induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
from temper_placer.router_v6.astar_pathfinding import RoutePath
from tests.router_v6.test_induction_base import make_compliant_route, make_empty_rr
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


@pytest.mark.dependency(depends=["induction-base"])
def test_acid_trap_add_compliant_route() -> None:
    """FR13: Adding a compliant route (no acute angles) does not create traps."""
    rr = make_empty_rr()
    assert detect_acid_traps(rr).trap_count == 0

    # A wide-angle path (135-degree turns) — angles > 90 degrees
    compliant = CompiledRoute(
        net_name="WIDE",
        path=RoutePath(net_name="WIDE", coordinates=[(0.0, 0.0), (10.0, 0.0), (20.0, -10.0)], layer_name="F.Cu", path_length=24.14),
        width_mm=0.3, vias=[], matched_length_mm=None,
    )
    rr.compiled_routes["WIDE"] = compliant

    report = detect_acid_traps(rr)
    assert report.trap_count == 0, (
        f"Adding compliant route caused {report.trap_count} acid traps"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_acid_trap_detects_non_compliant() -> None:
    """SC5: Adding a route with an acute 45-degree angle must be detected."""
    import math
    angle = math.radians(45)
    d = 10.0
    p1 = (d, 0.0)
    p2 = (0.0, 0.0)
    p3 = (d * math.cos(angle), d * math.sin(angle))

    rr = RoutingResults(compiled_routes={
        "ACUTE": CompiledRoute(
            net_name="ACUTE",
            path=RoutePath(net_name="ACUTE", coordinates=[p1, p2, p3], layer_name="F.Cu", path_length=2.0 * d),
            width_mm=0.2, vias=[], matched_length_mm=None,
        ),
    }, failed_nets=[])

    report = detect_acid_traps(rr)
    assert report.trap_count >= 1, (
        f"Non-compliant acid-trap route should be detected, got {report.trap_count}"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_acid_trap_modify_preserves_compliance() -> None:
    """FR13b: Modifying a route while preserving angles does not create traps."""
    rr = RoutingResults(compiled_routes={
        "WIDE": CompiledRoute(
            net_name="WIDE",
            path=RoutePath(net_name="WIDE", coordinates=[(0.0, 0.0), (10.0, 0.0), (20.0, -10.0)], layer_name="F.Cu", path_length=24.14),
            width_mm=0.3, vias=[], matched_length_mm=None,
        ),
    }, failed_nets=[])
    assert detect_acid_traps(rr).trap_count == 0

    rr.compiled_routes["WIDE"] = CompiledRoute(
        net_name="WIDE",
        path=RoutePath(net_name="WIDE", coordinates=[(5.0, 0.0), (15.0, 0.0), (25.0, -10.0)], layer_name="F.Cu", path_length=24.14),
        width_mm=0.3, vias=[], matched_length_mm=None,
    )

    report = detect_acid_traps(rr)
    assert report.trap_count == 0, (
        f"Route modification caused {report.trap_count} acid traps"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_acid_trap_remove_preserves_compliance() -> None:
    """FR13c: Removing a route does not cause phantom acid traps."""
    rr = RoutingResults(compiled_routes={
        "A": CompiledRoute(net_name="A", path=RoutePath(net_name="A", coordinates=[(0.0, 0.0), (10.0, 0.0), (20.0, -10.0)], layer_name="F.Cu", path_length=24.14), width_mm=0.3, vias=[], matched_length_mm=None),
        "B": CompiledRoute(net_name="B", path=RoutePath(net_name="B", coordinates=[(0.0, 50.0), (10.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    before = detect_acid_traps(rr).trap_count

    del rr.compiled_routes["B"]
    after = detect_acid_traps(rr).trap_count
    assert after <= before, (
        f"Route removal increased acid traps from {before} to {after}"
    )
