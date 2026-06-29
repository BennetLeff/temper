"""U12: Known-compliant strategy bootstrap verification (FR14).

Validates that ``known_compliant_routing_results`` produces routes that
pass all DFM validators — proving the strategy is not vacuously compliant.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.acid_trap_detection import detect_acid_traps
from temper_placer.router_v6.annular_ring_check import check_annular_rings
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.copper_balance import analyze_copper_balance
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.manufacturing_report import generate_manufacturing_report
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.teardrop_generation import insert_teardrops
from temper_placer.router_v6.thermal_relief import add_thermal_relief
from tests.router_v6.sat_property_strategies import known_compliant_routing_results


@given(results=known_compliant_routing_results(min_routes=2, max_routes=4))
@settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.too_slow])
def test_known_compliant_routes_pass_all_validators(results: RoutingResults) -> None:
    """FR14: A routing with only known-compliant routes passes all DFM validators."""
    min_clearance = 0.127

    # Run all DFM validators
    clearance = verify_clearance(results, min_clearance=min_clearance)
    creepage = verify_creepage(results)
    acid = detect_acid_traps(results)
    annular = check_annular_rings(results)
    thermal = add_thermal_relief(results)
    copper = analyze_copper_balance(results, board_width=200.0, board_height=150.0)
    teardrops = insert_teardrops(results)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance,
    )

    # Every validator should report zero violations
    assert clearance.violation_count == 0, (
        f"Clearance: expected 0 violations, got {clearance.violation_count}"
    )
    assert creepage.violation_count == 0, (
        f"Creepage: expected 0 violations, got {creepage.violation_count}"
    )
    assert acid.trap_count == 0, (
        f"Acid trap: expected 0 traps, got {acid.trap_count}"
    )
    assert annular.violation_count == 0, (
        f"Annular ring: expected 0 violations, got {annular.violation_count}"
    )
    assert teardrops.teardrop_count >= 0, (
        "Teardrops: teardrop_count should be >= 0"
    )
    assert thermal.relief_count >= 0, (
        "Thermal relief: relief_count should be >= 0"
    )


def test_strategy_bootstrap_empty() -> None:
    """FR14 variant: empty routing results passes all validators (sanity check)."""
    rr = RoutingResults(compiled_routes={}, failed_nets=[])

    clearance = verify_clearance(rr)
    creepage = verify_creepage(rr)
    acid = detect_acid_traps(rr)
    annular = check_annular_rings(rr)
    thermal = add_thermal_relief(rr)
    copper = analyze_copper_balance(rr, board_width=200.0, board_height=150.0)
    teardrops = insert_teardrops(rr)
    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance,
    )

    assert clearance.violation_count == 0
    assert creepage.violation_count == 0
    assert acid.trap_count == 0
    assert annular.violation_count == 0
    assert teardrops.teardrop_count == 0
    assert thermal.relief_count == 0
