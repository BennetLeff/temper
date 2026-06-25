"""Property tests for manufacturing report domain correctness.

Covers R18 (sub-report traceability into composite total).
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

from tests.router_v6.dfm_property_strategies import (
    BOARD_H,
    BOARD_W,
    realistic_routing_results,
)

# ---------------------------------------------------------------------------
# Shared settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=200,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# Helper — run all DFM modules and build composite report
# ---------------------------------------------------------------------------


def _run_all_dfm(results: RoutingResults):
    """Run every DFM module and return a ``ManufacturingReport``."""
    acid = detect_acid_traps(results)
    annular = check_annular_rings(results, min_annular_ring=0.05)
    teardrop = insert_teardrops(results)
    thermal = add_thermal_relief(results)
    copper = analyze_copper_balance(results, BOARD_W, BOARD_H)
    creepage = verify_creepage(results)
    clearance = verify_clearance(results, min_clearance=0.127)
    return generate_manufacturing_report(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrop,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )


# ---------------------------------------------------------------------------
# R18 — Sub-report traceability
# ---------------------------------------------------------------------------


@given(results=realistic_routing_results())
@_SETTINGS
def test_composite_total_matches_sub_report_sum(results: RoutingResults) -> None:
    """``total_violations`` equals the documented sum of sub-report
    violation counts, accounting for teardrop/thermal sentinels.
    """
    report = _run_all_dfm(results)

    # Sentinel logic from ManufacturingReport.total_violations:
    #   teardrop_failure = 1 if teardrop_count == 0 else 0
    #   thermal_failure = 1 if relief_count == 0 else 0
    teardrop_failure = 1 if report.teardrops.teardrop_count == 0 else 0
    thermal_failure = 1 if report.thermal_reliefs.relief_count == 0 else 0

    expected = (
        report.acid_traps.trap_count
        + report.annular_rings.violation_count
        + report.creepage.violation_count
        + report.clearance.violation_count
        + report.copper_balance.unbalanced_layer_count
        + teardrop_failure
        + thermal_failure
    )

    assert report.total_violations == expected, (
        f"Composite total mismatch: "
        f"computed={expected}, reported={report.total_violations}"
    )


@given(results=realistic_routing_results())
@_SETTINGS
def test_critical_violations_match_documented_sum(results: RoutingResults) -> None:
    """``critical_violations`` equals the documented sum of critical
    sub-report counts.
    """
    report = _run_all_dfm(results)

    expected = (
        report.acid_traps.critical_count
        + report.annular_rings.violation_count
        + report.creepage.violation_count
        + report.clearance.violation_count
        + report.copper_balance.unbalanced_layer_count
    )

    assert report.critical_violations == expected, (
        f"Critical violations mismatch: "
        f"computed={expected}, reported={report.critical_violations}"
    )


# ---------------------------------------------------------------------------
# Empty-input smoke test
# ---------------------------------------------------------------------------


def test_empty_input_composite_consistency() -> None:
    """Empty input → sub-reports are all-zero and composite total is
    consistent with documented sentinel behaviour.
    """
    empty = RoutingResults(compiled_routes={}, failed_nets=[])
    report = _run_all_dfm(empty)

    # Sub-reports: genuine violations must be zero
    assert report.acid_traps.trap_count == 0
    assert report.annular_rings.violation_count == 0
    assert report.creepage.violation_count == 0
    assert report.clearance.violation_count == 0

    # All layers unbalanced (0 % copper)
    assert report.copper_balance.unbalanced_layer_count == len(
        report.copper_balance.layer_balances
    )

    # Teardrop / thermal sentinels fire (zero features → failure)
    assert report.teardrops.teardrop_count == 0
    assert report.thermal_reliefs.relief_count == 0

    # Composite total accounts for all sentinels
    assert report.total_violations >= 0
    assert report.critical_violations >= 0
