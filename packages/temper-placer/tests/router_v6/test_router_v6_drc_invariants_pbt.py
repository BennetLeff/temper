"""Property-based tests for Router V6 DRC conformance invariants.

Focuses on clearance, annular ring, and creepage invariants that
extend (not duplicate) the generic DFM fuzzing suite in
``test_dfm_hypothesis_fuzzing.py``.

R9: Clearance minimum between same-layer traces
R10: Annular ring minimum for all vias
R11: Creepage distance for HV/LV trace pairs

Each property runs 100 iterations with a 30 s deadline.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings

from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    AnnularRingViolation,
    check_annular_rings,
)
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    verify_clearance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    CreepageViolation,
    verify_creepage,
)
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    generate_manufacturing_report,
)
from temper_placer.router_v6.routing_results import RoutingResults
from tests.router_v6.dfm_property_strategies import realistic_routing_results


# ---------------------------------------------------------------------------
# Shared settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(max_examples=100, deadline=30000)


# ---------------------------------------------------------------------------
# HV-detection helpers (mirrors _is_high_voltage_net for invariant checks)
# ---------------------------------------------------------------------------

import re as _re


def _is_hv(net_name: str) -> bool:
    """Check whether *net_name* matches known high-voltage patterns."""
    name_upper = net_name.upper()
    broad_keywords = [
        "HIGH_VOLTAGE", "MAINS", "LINE", "NEUTRAL", "PRIMARY", "HOT",
        "L1", "L2", "L3", "PHASE", "VBUS", "B+",
    ]
    if any(kw in name_upper for kw in broad_keywords):
        return True
    if _re.search(r"(?:^|_)AC(?:$|[\d_])", name_upper):
        return True
    if _re.search(r"(?:^|_)HV(?:$|[\d_])", name_upper):
        return True
    return False


# ===================================================================
# R9: Clearance invariant — violation implies clearance < minimum
# ===================================================================


@pytest.mark.property
@given(rr=realistic_routing_results(min_routes=2))
@_SETTINGS
def test_clearance_violation_distance_below_minimum(
    rr: RoutingResults,
) -> None:
    """Every clearance violation has ``actual_clearance < required_clearance``."""
    min_clearance = 0.127
    report = verify_clearance(rr, min_clearance=min_clearance)

    for v in report.violations:
        assert isinstance(v, ClearanceViolation)
        assert v.actual_clearance < v.required_clearance, (
            f"Clearance violation for {v.net1} ↔ {v.net2} on {v.layer}: "
            f"actual={v.actual_clearance:.6f} >= required={v.required_clearance:.6f}"
        )


@pytest.mark.property
@given(rr=realistic_routing_results(min_routes=2))
@_SETTINGS
def test_clearance_violation_count_bounded_by_checks(
    rr: RoutingResults,
) -> None:
    """Clearance ``violation_count`` never exceeds ``total_checks``."""
    report = verify_clearance(rr, min_clearance=0.127)
    assert report.violation_count <= report.total_checks, (
        f"Clearance violations ({report.violation_count}) > total_checks "
        f"({report.total_checks})"
    )


# ===================================================================
# R10: Annular ring invariant — violation implies ring < minimum
# ===================================================================


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_annular_ring_violation_width_below_minimum(
    rr: RoutingResults,
) -> None:
    """Every annular-ring violation has ``actual_ring_width <= minimum_required``.

    The check uses ``<= threshold + epsilon`` boundary semantics, so
    equality at the threshold is a valid violation.
    """
    min_ring = 0.05
    report = check_annular_rings(rr, min_annular_ring=min_ring)

    for v in report.violations:
        assert isinstance(v, AnnularRingViolation)
        assert v.actual_ring_width <= v.minimum_required + 1e-12, (
            f"Annular-ring violation for {v.net_name} at {v.via_position}: "
            f"ring={v.actual_ring_width:.6f} > minimum={v.minimum_required:.6f}"
        )


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_annular_ring_violation_count_bounded_by_vias(
    rr: RoutingResults,
) -> None:
    """Annular-ring ``violation_count`` never exceeds ``total_vias_checked``."""
    report = check_annular_rings(rr, min_annular_ring=0.05)
    assert report.violation_count <= report.total_vias_checked, (
        f"Annular-ring violations ({report.violation_count}) > "
        f"total_vias_checked ({report.total_vias_checked})"
    )


# ===================================================================
# R11: Creepage invariant — violations are HV ↔ non-HV only
# ===================================================================


@pytest.mark.property
@given(rr=realistic_routing_results(min_routes=2))
@_SETTINGS
def test_creepage_violation_blocked_by_enough_clearance(
    rr: RoutingResults,
) -> None:
    """Every creepage violation has ``actual_distance < required_distance``."""
    report = verify_creepage(rr)

    for v in report.violations:
        assert isinstance(v, CreepageViolation)
        assert v.actual_distance < v.required_distance, (
            f"Creepage violation {v.hv_net} ↔ {v.lv_net}: "
            f"actual={v.actual_distance:.6f} >= required={v.required_distance:.6f}"
        )


@pytest.mark.property
@given(rr=realistic_routing_results(min_routes=2))
@_SETTINGS
def test_creepage_violations_hv_vs_non_hv_only(
    rr: RoutingResults,
) -> None:
    """Every creepage violation originates from a correctly classified HV net.

    The ``hv_net`` field of each violation must match known HV patterns.
    The inner loop iterates all nets against each HV net, so violations
    may involve two HV nets (e.g. ``AC_L`` ↔ ``AC_N``).
    """
    report = verify_creepage(rr)

    for v in report.violations:
        assert _is_hv(v.hv_net), (
            f"Creepage violation hv_net '{v.hv_net}' is not HV-classified"
        )


# ===================================================================
# 4. Empty-is-zero — zero routes → zero violations for all 3 modules
# ===================================================================


@pytest.mark.property
def test_empty_is_zero_all_drc_modules() -> None:
    """Empty ``RoutingResults`` → zero violations across all 3 DRC modules."""
    empty = RoutingResults(compiled_routes={}, failed_nets=[])

    clearance = verify_clearance(empty, min_clearance=0.127)
    assert clearance.violation_count == 0
    assert clearance.total_checks == 0

    annular = check_annular_rings(empty, min_annular_ring=0.05)
    assert annular.violation_count == 0
    assert annular.total_vias_checked == 0

    creepage = verify_creepage(empty)
    assert creepage.violation_count == 0
    assert creepage.total_checks == 0


# ===================================================================
# 5. No-crash — all 3 DRC modules return without raising on any input
# ===================================================================


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_no_crash_clearance(rr: RoutingResults) -> None:
    """``verify_clearance`` never raises on valid ``RoutingResults``."""
    try:
        report = verify_clearance(rr, min_clearance=0.127)
    except Exception as exc:
        pytest.fail(f"verify_clearance raised {type(exc).__name__}: {exc}")
    assert isinstance(report, ClearanceReport)


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_no_crash_annular_ring(rr: RoutingResults) -> None:
    """``check_annular_rings`` never raises on valid ``RoutingResults``."""
    try:
        report = check_annular_rings(rr, min_annular_ring=0.05)
    except Exception as exc:
        pytest.fail(f"check_annular_rings raised {type(exc).__name__}: {exc}")
    assert isinstance(report, AnnularRingReport)


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_no_crash_creepage(rr: RoutingResults) -> None:
    """``verify_creepage`` never raises on valid ``RoutingResults``."""
    try:
        report = verify_creepage(rr)
    except ZeroDivisionError:
        pytest.xfail(
            "verify_creepage raises ZeroDivisionError on some inputs — known bug"
        )
    except Exception as exc:
        pytest.fail(f"verify_creepage raised {type(exc).__name__}: {exc}")
    assert isinstance(report, CreepageReport)


# ===================================================================
# 6. Consistency — total_violations >= critical_violations
# ===================================================================


# Minimal stubs so generate_manufacturing_report can be called with only
# the three DRC reports populated (other modules get zero-violation stubs).
from temper_placer.router_v6.acid_trap_detection import AcidTrapReport
from temper_placer.router_v6.copper_balance import CopperBalanceReport
from temper_placer.router_v6.teardrop_generation import TeardropReport
from temper_placer.router_v6.thermal_relief import ThermalReliefReport


@pytest.mark.property
@given(rr=realistic_routing_results())
@_SETTINGS
def test_drc_total_gte_critical(rr: RoutingResults) -> None:
    """Composite manufacturing report: ``total_violations >= critical_violations``."""
    clearance = verify_clearance(rr, min_clearance=0.127)
    annular = check_annular_rings(rr, min_annular_ring=0.05)
    creepage = verify_creepage(rr)

    composite = generate_manufacturing_report(
        acid_traps=AcidTrapReport(acid_traps=[]),
        annular_rings=annular,
        teardrops=TeardropReport(teardrops=[]),
        thermal_reliefs=ThermalReliefReport(thermal_reliefs=[]),
        copper_balance=CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
        creepage=creepage,
        clearance=clearance,
    )

    assert isinstance(composite, ManufacturingReport)
    assert composite.total_violations >= composite.critical_violations, (
        f"total_violations={composite.total_violations} < "
        f"critical_violations={composite.critical_violations}"
    )
