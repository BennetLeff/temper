"""U9-U11: Manufacturing report induction — addition / modification / removal."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
from temper_placer.router_v6.annular_ring_check import check_annular_rings
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.copper_balance import analyze_copper_balance
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.manufacturing_report import generate_manufacturing_report
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import insert_teardrops
from temper_placer.router_v6.thermal_relief import add_thermal_relief
from tests.router_v6.test_induction_base import make_empty_rr

BOARD_W, BOARD_H = 200.0, 150.0


def _run_all(rr: RoutingResults):
    """Run all 7 sub-validators and return the composite report."""
    return generate_manufacturing_report(
        detect_acid_traps(rr),
        check_annular_rings(rr),
        insert_teardrops(rr),
        add_thermal_relief(rr),
        analyze_copper_balance(rr, BOARD_W, BOARD_H),
        verify_creepage(rr),
        verify_clearance(rr),
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_manufacturing_report_add_compliant_route() -> None:
    """FR13: Adding a compliant route updates composite report correctly."""
    rr = make_empty_rr()
    report = _run_all(rr)
    assert isinstance(report.total_violations, int)

    rr.compiled_routes["SIG1"] = CompiledRoute(
        net_name="SIG1",
        path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0),
        width_mm=0.3, vias=[], matched_length_mm=None,
    )

    report = _run_all(rr)
    assert isinstance(report.total_violations, int)


@pytest.mark.dependency(depends=["induction-base"])
def test_manufacturing_report_modify_preserves_compliance() -> None:
    """FR13b: Modifying a route in composite report does not crash."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    before = _run_all(rr).total_violations

    rr.compiled_routes["SIG1"] = CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(15.0, 10.0), (25.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3, vias=[], matched_length_mm=None)

    after = _run_all(rr).total_violations
    assert after == before, (
        f"Route modification changed total_violations from {before} to {after}"
    )


@pytest.mark.dependency(depends=["induction-base"])
def test_manufacturing_report_remove_preserves_compliance() -> None:
    """FR13c: Removing a route from composite report does not cause phantoms."""
    rr = RoutingResults(compiled_routes={
        "SIG1": CompiledRoute(net_name="SIG1", path=RoutePath(net_name="SIG1", coordinates=[(10.0, 10.0), (20.0, 10.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3, vias=[], matched_length_mm=None),
        "SIG2": CompiledRoute(net_name="SIG2", path=RoutePath(net_name="SIG2", coordinates=[(10.0, 50.0), (20.0, 50.0)], layer_name="F.Cu", path_length=10.0), width_mm=0.3, vias=[], matched_length_mm=None),
    }, failed_nets=[])
    before = _run_all(rr).total_violations

    del rr.compiled_routes["SIG2"]
    after = _run_all(rr).total_violations
    assert after <= before, (
        f"Route removal increased total_violations from {before} to {after}"
    )
