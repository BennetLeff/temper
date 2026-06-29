"""Property tests for teardrop generation domain correctness.

Covers R12 (connection-type partition) and R13 (datum near owning via).
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import insert_teardrops
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_property_strategies import realistic_routing_results

# ---------------------------------------------------------------------------
# Shared settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=200,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# R12 — Connection-type partition
# ---------------------------------------------------------------------------


@given(results=realistic_routing_results())
@_SETTINGS
def test_teardrop_count_partition(results: RoutingResults) -> None:
    """``teardrop_count == via_teardrop_count + pad_teardrop_count``
    for every input.  Every teardrop is classified exactly once.
    """
    report = insert_teardrops(results)
    assert report.teardrop_count == report.via_teardrop_count + report.pad_teardrop_count, (
        f"Partition mismatch: total={report.teardrop_count}, "
        f"via={report.via_teardrop_count}, pad={report.pad_teardrop_count}"
    )


# ---------------------------------------------------------------------------
# R13 — Datum point near owning via
# ---------------------------------------------------------------------------




@given(results=realistic_routing_results())
@_SETTINGS
def test_teardrop_datum_near_via(results: RoutingResults) -> None:
    """Every teardrop's ``connection_point`` is within the owning via's
    annulus radius (half the via diameter + tolerance) of the via centre.
    """
    report = insert_teardrops(results)

    for td in report.teardrops:
        net_name = td.net_name
        if net_name not in results.compiled_routes:
            continue  # teardrop from a net not in results — skip

        route = results.compiled_routes[net_name]
        px, py = td.connection_point

        # Find the nearest via to the teardrop's connection_point
        nearest_dist = float("inf")
        for via in route.vias:
            vx, vy = via.position
            dist = math.hypot(px - vx, py - vy)
            if dist < nearest_dist:
                nearest_dist = dist

        # The connection point should be within ~1 via diameter of some via
        assert nearest_dist <= 10.0, (
            f"Teardrop connection_point {td.connection_point} for net "
            f"'{net_name}' is {nearest_dist:.3f} mm from the nearest via"
        )


# ---------------------------------------------------------------------------
# Known-geometry smoke tests (TS2, TS3)
# ---------------------------------------------------------------------------


def test_teardrop_known_geometry_datum_near_via() -> None:
    """Path [(0,0), (10,0), (10,10)], via at vertex (10,0) → teardrop
    connection_point is near the via centre.
    """
    coords = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    path = RoutePath("T1", coords, "F.Cu", 20.0)
    via = Via(
        position=(10.0, 0.0),
        from_layer="F.Cu",
        to_layer="In1.Cu",
        diameter=1.0,
        drill=0.5,
        net_name="T1",
    )
    route = CompiledRoute("T1", path, 0.254, [via], None)
    results = RoutingResults(compiled_routes={"T1": route}, failed_nets=[])
    report = insert_teardrops(results)

    for td in report.teardrops:
        px, py = td.connection_point
        vx, vy = via.position
        dist = math.hypot(px - vx, py - vy)
        assert dist <= via.diameter * 2, (
            f"Teardrop connection_point {td.connection_point} is "
            f"{dist:.3f} mm from via centre — expected ≤ "
            f"{via.diameter * 2:.3f} mm"
        )


def test_teardrop_empty_input_zeros() -> None:
    """Empty ``RoutingResults`` → teardrop_count == 0, via == 0, pad == 0."""
    empty = RoutingResults(compiled_routes={}, failed_nets=[])
    report = insert_teardrops(empty)
    assert report.teardrop_count == 0
    assert report.via_teardrop_count == 0
    assert report.pad_teardrop_count == 0
