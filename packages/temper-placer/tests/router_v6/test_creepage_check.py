"""
Tests for Router V6 Stage 5.6: Verify Creepage

Part of temper-ytm8
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    CreepageViolation,
    _is_high_voltage_net,
    verify_creepage,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def test_verify_no_hv_nets():
    """Test creepage verification with no HV nets."""
    path = RoutePath("SIG1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("SIG1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"SIG1": route}, failed_nets=[])

    report = verify_creepage(results)

    # No HV nets = no violations
    assert report.violation_count == 0


def test_verify_hv_net_safe_distance():
    """Test HV net with safe creepage distance."""
    # HV net
    hv_path = RoutePath("AC_L", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("AC_L", hv_path, 0.254, [], None)

    # LV net far away
    lv_path = RoutePath("SIG1", [(0, 20), (10, 20)], "F.Cu", 10.0)
    lv_route = CompiledRoute("SIG1", lv_path, 0.127, [], None)

    results = RoutingResults(compiled_routes={"AC_L": hv_route, "SIG1": lv_route}, failed_nets=[])

    report = verify_creepage(results)

    # Distance is 20mm >> required 3.2mm for 230V
    assert report.violation_count == 0


def test_verify_hv_net_violation():
    """Test HV net with insufficient creepage."""
    # HV net
    hv_path = RoutePath("AC_L", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("AC_L", hv_path, 0.254, [], None)

    # LV net too close
    lv_path = RoutePath("SIG1", [(0, 1), (10, 1)], "F.Cu", 10.0)
    lv_route = CompiledRoute("SIG1", lv_path, 0.127, [], None)

    results = RoutingResults(compiled_routes={"AC_L": hv_route, "SIG1": lv_route}, failed_nets=[])

    report = verify_creepage(results)

    # Distance is 1mm < required 3.2mm for 230V
    assert report.violation_count > 0


def test_creepage_violation_dataclass():
    """Test CreepageViolation dataclass."""
    violation = CreepageViolation(
        hv_net="AC_L",
        lv_net="SIG1",
        location=(5.0, 5.0),
        actual_distance=1.0,
        required_distance=3.2,
    )

    assert violation.hv_net == "AC_L"
    assert violation.lv_net == "SIG1"
    assert violation.deficiency == pytest.approx(2.2)


def test_creepage_report_dataclass():
    """Test CreepageReport dataclass."""
    violation = CreepageViolation("AC_L", "SIG1", (0, 0), 1.0, 3.2)

    report = CreepageReport(violations=[violation], total_checks=10)

    assert report.violation_count == 1
    assert report.total_checks == 10
    assert report.pass_rate == 90.0


def test_custom_voltage_ratings():
    """Test creepage with custom voltage ratings."""
    hv_path = RoutePath("HV_BUS", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("HV_BUS", hv_path, 0.254, [], None)

    lv_path = RoutePath("SIG1", [(0, 0.5), (10, 0.5)], "F.Cu", 10.0)
    lv_route = CompiledRoute("SIG1", lv_path, 0.127, [], None)

    results = RoutingResults(compiled_routes={"HV_BUS": hv_route, "SIG1": lv_route}, failed_nets=[])

    # 100V requires 0.8mm creepage
    report = verify_creepage(results, voltage_ratings={"HV_BUS": 100.0})

    # 0.5mm < 0.8mm required
    assert report.violation_count > 0


def test_multiple_lv_nets():
    """Test HV net against multiple LV nets."""
    hv_path = RoutePath("AC_L", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("AC_L", hv_path, 0.254, [], None)

    lv1_path = RoutePath("SIG1", [(0, 5), (10, 5)], "F.Cu", 10.0)
    lv1_route = CompiledRoute("SIG1", lv1_path, 0.127, [], None)

    lv2_path = RoutePath("SIG2", [(0, 10), (10, 10)], "F.Cu", 10.0)
    lv2_route = CompiledRoute("SIG2", lv2_path, 0.127, [], None)

    results = RoutingResults(
        compiled_routes={
            "AC_L": hv_route,
            "SIG1": lv1_route,
            "SIG2": lv2_route,
        },
        failed_nets=[],
    )

    report = verify_creepage(results)

    # Should check AC_L against both SIG1 and SIG2
    assert report.total_checks == 2


def test_creepage_violation_count_bounded_by_net_pair_not_segment_pair():
    """Regression test: violation_count must not blow up per-segment-pair.

    A routed net is internally decomposed into many short (grid-step)
    segments. The old implementation appended one ``CreepageViolation``
    per *segment-pair* that violated the required distance, so two long
    parallel-routed nets produced one violation for every pair of
    segments along their shared run -- hundreds or thousands of records
    for what is physically a single isolation defect between one net
    pair. On the committed board this produced 257,597 violations from
    175 net-pair checks (~1,472 violations per check), a ratio nobody
    could interpret as a count of real board defects (see
    docs/evidence/2026-07-27-drc-checks-repaired.md).

    This test builds two nets that run parallel and too close for their
    *entire* length (20 points each, 0.05mm apart, well under the 3.2mm
    required for a 230V default HV net) and asserts the check now
    reports exactly one violation for the one net pair -- not one per
    segment-pair. Fails before the fix (violation_count in the hundreds)
    and passes after (violation_count == 1, matching total_checks == 1).
    """
    n_points = 20
    hv_coords = [(float(i), 0.0) for i in range(n_points)]
    lv_coords = [(float(i), 0.05) for i in range(n_points)]

    hv_path = RoutePath("AC_L", hv_coords, "F.Cu", float(n_points - 1))
    hv_route = CompiledRoute("AC_L", hv_path, 0.254, [], None)

    lv_path = RoutePath("SIG1", lv_coords, "F.Cu", float(n_points - 1))
    lv_route = CompiledRoute("SIG1", lv_path, 0.127, [], None)

    results = RoutingResults(compiled_routes={"AC_L": hv_route, "SIG1": lv_route}, failed_nets=[])

    report = verify_creepage(results)

    assert report.total_checks == 1
    # Exactly one net pair was checked, so at most one violation for it --
    # never more than total_checks.
    assert report.violation_count == 1
    assert report.violation_count <= report.total_checks
    # The reported violation must reflect the true worst-case (closest
    # approach), not an arbitrary one of the many segment-pairs.
    assert report.violations[0].actual_distance == pytest.approx(0.05, abs=1e-9)


# ---------------------------------------------------------------------------
# _is_high_voltage_net word-boundary regression (2026-07-27)
#
# Before this fix, `broad_keywords` used plain substring matching, so "L1"/
# "L2" matched inside "COIL1"/"COIL2" (SELV relay-coil nets) and "LINE"
# matched inside "...-line" (internal safety-logic fault signals). On the
# live production board this made 14 of 16 "hv_net" matches false positives,
# and all 24 of one measured run's creepage violations involved one of them
# -- zero involved a genuine HV/mains conductor. See
# docs/evidence/2026-07-27-creepage-burndown.md Sec 4.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "net_name",
    [
        # "L1"/"L2" substring-collision inside relay-coil net names
        # (SELV per elec/domain_manifest.yaml).
        "discharge.k_dis1-coil1",
        "discharge.k_dis1-coil2",
        "discharge.k_dis2-coil1",
        "power_in.bypass_relay-coil1",
        "power_in.bypass_relay-coil2",
        # "LINE" substring-collision inside hyphen-delimited internal
        # safety-logic fault signals (not AC line voltage).
        "safety-line",
        "safety-line-1",
        "safety-line-2",
        "safety-line-3",
        "safety.coil_thermal-line",
        "safety.ocp-line",
        "safety.ovp-line",
        "safety.thermal-line",
        "safety.uvlo_logic-line",
    ],
)
def test_is_high_voltage_net_rejects_known_false_positives(net_name):
    """Regression: these 14 net names must NOT be classified HV.

    Each was a real false positive on the live production board (verified
    directly, not inferred) before the word-boundary fix. Fails before the
    fix (all 14 return True); passes after.
    """
    assert _is_high_voltage_net(net_name) is False


@pytest.mark.parametrize(
    "net_name",
    [
        "ac_l",
        "ac_n",
        "AC_L",
        "AC_N",
        "HV_BUS",
        "_AC",
        "AC1",
        "MAINS_L",
        "PHASE_A",
        # A genuinely standalone/word-bounded L1/L2/L3 net must still match
        # -- the fix must not blanket-disable these keywords, only require
        # a real boundary.
        "BUS_L1",
        "PHASE_L2",
    ],
)
def test_is_high_voltage_net_still_matches_true_positives(net_name):
    """The word-boundary fix must not lose genuine HV/mains matches."""
    assert _is_high_voltage_net(net_name) is True


def test_is_high_voltage_net_does_not_match_unrelated_trace():
    """Pre-existing invariant (docstring example): TRACE is not HV."""
    assert _is_high_voltage_net("TRACE") is False
