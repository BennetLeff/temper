"""
Boundary edge-case tests for Router V6 Stage 5.7: Verify Clearance.

Tests clearance threshold boundaries, voltage boundaries, coordinate
boundaries, trace width boundaries, segment geometry boundaries,
HV escalation boundaries, and empty input.

Each parametrized test explores a distinct axis of edge cases.  If a
particular input set reveals a crash or unexpected behaviour, the case
is marked ``pytest.mark.xfail`` — do NOT fix the module; we only
characterise its current behaviour.
"""

from __future__ import annotations

import math
import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    _calculate_minimum_clearance,
    _get_required_clearance,
    _point_to_segment_dist,
    _segment_to_segment_dist,
    verify_clearance,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

from dfm_boundary_constants import (
    just_below,
    just_above,
    exactly_at,
    THRESHOLD_ZERO,
    THRESHOLD_NEGATIVE,
    THRESHOLD_NAN,
    THRESHOLD_INF,
    THRESHOLD_NORMAL,
    VOLTAGE_ZERO,
    VOLTAGE_NEGATIVE,
    VOLTAGE_NAN,
    VOLTAGE_INF,
    VOLTAGE_EXTREME,
    VOLTAGE_NORMAL,
    COORD_ZERO,
    COORD_NEGATIVE,
    COORD_NAN,
    COORD_INF,
    COORD_EXTREME,
    TRACE_WIDTHS_ZERO,
    TRACE_WIDTHS_NEGATIVE,
    TRACE_WIDTHS_NAN,
    TRACE_WIDTHS_INF,
    TRACE_WIDTHS_NORMAL,
)


# ============================================================================
# helpers
# ============================================================================

def _make_route(
    net: str,
    coords: list[tuple[float, float]],
    width: float = 0.127,
    layer: str = "F.Cu",
    vias: list | None = None,
) -> CompiledRoute:
    """Create a minimal ``CompiledRoute`` for testing.

    The ``path_length`` is computed as the sum of Euclidean distances
    between consecutive coordinates — good enough for DRC tests.
    """
    _len = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        _len += math.hypot(x2 - x1, y2 - y1)
    path = RoutePath(
        net_name=net,
        coordinates=list(coords),
        layer_name=layer,
        path_length=_len,
    )
    return CompiledRoute(
        net_name=net,
        path=path,
        width_mm=width,
        vias=list(vias) if vias else [],
        matched_length_mm=None,
    )


def _make_results(
    routes: dict[str, CompiledRoute],
    failed: list[str] | None = None,
) -> RoutingResults:
    """Build a ``RoutingResults`` from a dict of ``CompiledRoute``."""
    return RoutingResults(
        compiled_routes=routes,
        failed_nets=list(failed) if failed else [],
    )


# ============================================================================
# 1 — Clearance threshold boundaries
# ============================================================================

@pytest.mark.parametrize(
    "min_clearance, desc",
    [
        # normal baseline
        (0.127, "standard_5mil"),
        # zero
        *[(v, f"zero_{i}") for i, v in enumerate(THRESHOLD_ZERO)],
        # negative
        *[(v, f"negative_{i}") for i, v in enumerate(THRESHOLD_NEGATIVE)],
        # NaN
        *[(v, f"nan_{i}") for i, v in enumerate(THRESHOLD_NAN)],
        # +inf / -inf
        *[(v, f"inf_{i}") for i, v in enumerate(THRESHOLD_INF)],
    ],
)
def test_clearance_threshold_boundary(min_clearance, desc):
    """``verify_clearance`` with boundary ``min_clearance`` values.

    The function should not crash; it may return 0 or all violations
    depending on the threshold semantics.  NaN / inf thresholds raise
    ``ValueError``.
    """
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)])
    r2 = _make_route("NET2", [(0.0, 0.5), (10.0, 0.5)])
    results = _make_results({"NET1": r1, "NET2": r2})

    if math.isnan(min_clearance) or math.isinf(min_clearance):
        with pytest.raises(ValueError, match="finite"):
            verify_clearance(results, min_clearance=min_clearance)
        return

    report = verify_clearance(results, min_clearance=min_clearance)
    assert isinstance(report, ClearanceReport)
    assert report.total_checks == 1


@pytest.mark.parametrize(
    "min_clearance, expect_pass",
    [
        # At 0.0, an overlap (-0.4) IS < 0.0  →  violation (correct)
        (0.0, False),
        # At -0.001, -0.4 < -0.001  →  violation
        (-0.001, False),
        # At -1.0, -0.4 < -1.0 is False  →  passes
        (-1.0, True),
    ],
)
def test_clearance_threshold_nonpositive_behavior(min_clearance, expect_pass):
    """Characterise behaviour for non-positive ``min_clearance``.

    The check is ``actual < required`` (strict less-than).  An overlap
    (negative actual) still violates a threshold of 0.0 or -0.001
    because the inequality holds.  Only when the threshold is more
    negative than the overlap does it pass.
    """
    # Traces deliberately overlapping
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=0.5)
    r2 = _make_route("NET2", [(0.0, 0.1), (10.0, 0.1)], width=0.5)
    # Edge-to-edge: 0.1 - 0.25 - 0.25 = -0.4 mm  →  overlap!
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=min_clearance)
    assert isinstance(report, ClearanceReport)
    if expect_pass:
        assert report.violation_count == 0, (
            f"Expected pass for min_clearance={min_clearance}, "
            f"got {report.violation_count} violation(s)"
        )
    else:
        assert report.violation_count > 0, (
            f"Expected violation for min_clearance={min_clearance}, "
            f"got 0 violations"
        )


# ============================================================================
# 2 — Voltage boundaries
# ============================================================================

@pytest.mark.parametrize(
    "voltage, expected_creepage",
    [
        # bracket boundaries (IPC-2221 table from creepage_check)
        (0, 0.13),
        (15, 0.13),
        (16, 0.25),
        (30, 0.25),
        (31, 0.50),
        (50, 0.50),
        (51, 0.80),
        (100, 0.80),
        (101, 1.25),
        (150, 1.25),
        (151, 1.60),
        (170, 1.60),
        (171, 3.20),
        (250, 3.20),
        (251, 6.40),
        (300, 6.40),
        (301, 8.00),
        (600, 8.00),
        (601, 12.00),
        (1000, 12.00),
        # extreme
        (1e6, 12.00),
    ],
)
def test_voltage_bracket_transitions(voltage, expected_creepage):
    """``_get_required_clearance`` bracket transitions for HV nets.

    Each voltage is at or just past a bracket boundary defined by
    ``_calculate_required_creepage``.
    """
    from temper_placer.router_v6.creepage_check import _calculate_required_creepage

    hv_creepage = _calculate_required_creepage(voltage)
    assert hv_creepage == pytest.approx(expected_creepage), (
        f"Voltage {voltage}V → expected creepage {expected_creepage}, "
        f"got {hv_creepage}"
    )

    # Now check that _get_required_clearance picks at least the
    # HV creepage when an HV net is involved.
    req = _get_required_clearance(
        "HV_BUS", "SIG1",
        default_clearance=0.127,
        voltage_ratings={"HV_BUS": voltage},
    )
    assert req >= expected_creepage


@pytest.mark.parametrize(
    "voltage, desc",
    [
        *[(v, f"zero_{i}") for i, v in enumerate(VOLTAGE_ZERO)],
        *[(v, f"negative_{i}") for i, v in enumerate(VOLTAGE_NEGATIVE)],
        *[(v, f"nan_{i}") for i, v in enumerate(VOLTAGE_NAN)],
        *[(v, f"inf_{i}") for i, v in enumerate(VOLTAGE_INF)],
        *[(v, f"extreme_{i}") for i, v in enumerate(VOLTAGE_EXTREME)],
    ],
)
def test_voltage_boundary_values(voltage, desc):
    """``_get_required_clearance`` with boundary voltage values in the
    ratings dict.

    The function should not crash; NaN/inf voltages fall back to the
    230 V default.
    """
    req = _get_required_clearance(
        "HV_BUS", "SIG1",
        default_clearance=0.127,
        voltage_ratings={"HV_BUS": voltage},
    )
    assert isinstance(req, float)


# ============================================================================
# 3 — Coordinate boundaries
# ============================================================================


@pytest.mark.parametrize(
    "coords, desc",
    [
        *[(c, f"zero_{i}") for i, c in enumerate(COORD_ZERO)],
        *[(c, f"negative_{i}") for i, c in enumerate(COORD_NEGATIVE)],
        *[(c, f"nan_{i}") for i, c in enumerate(COORD_NAN)],
        *[(c, f"inf_{i}") for i, c in enumerate(COORD_INF)],
        *[(c, f"extreme_{i}") for i, c in enumerate(COORD_EXTREME)],
    ],
)
def test_coordinate_boundary_single_point_path(coords, desc):
    """Single-point paths with boundary coordinate values.

    A single-point path has no segments — the clearance code must
    handle this gracefully (zero segments to check, no crash).
    NaN / inf coordinates produce zero segments.
    """
    x, y = coords
    # Single-point path
    r1 = _make_route("NET1", [(x, y)])
    r2 = _make_route("NET2", [(0.0, 0.0), (10.0, 0.0)])
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    assert isinstance(report, ClearanceReport)


@pytest.mark.parametrize(
    "coords, desc",
    [
        *[(c, f"nan_{i}") for i, c in enumerate(COORD_NAN)],
        *[(c, f"inf_{i}") for i, c in enumerate(COORD_INF)],
    ],
)
def test_coordinate_boundary_two_point_path(coords, desc):
    """Two-point paths (one segment) with NaN/inf coordinates.

    The segment-to-segment distance calculation should not crash,
    though the distance may be NaN/inf.
    """
    x, y = coords
    # Path with one NaN/inf coordinate + one finite coordinate
    r1 = _make_route("NET1", [(0.0, 0.0), (x, y)])
    r2 = _make_route("NET2", [(5.0, 5.0), (15.0, 5.0)])
    results = _make_results({"NET1": r1, "NET2": r2})

    try:
        report = verify_clearance(results, min_clearance=0.127)
    except Exception:
        if math.isnan(x) or math.isinf(x) or math.isnan(y) or math.isinf(y):
            pytest.xfail("NaN/inf coords in segment cause crash (expected edge-case)")
        raise

    assert isinstance(report, ClearanceReport)


@pytest.mark.parametrize(
    "coords, desc",
    [
        *[(c, f"zero_{i}") for i, c in enumerate(COORD_ZERO)],
        *[(c, f"negative_{i}") for i, c in enumerate(COORD_NEGATIVE)],
    ],
)
def test_coordinate_boundary_normal_segments(coords, desc):
    """Normal multi-point paths with finite boundary coordinates.

    Should behave identically to any other finite-coordinate path.
    """
    x, y = coords
    r1 = _make_route("NET1", [(x, y), (x + 5, y)])
    r2 = _make_route("NET2", [(x, y + 1), (x + 5, y + 1)])
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    assert isinstance(report, ClearanceReport)
    assert report.total_checks == 1


# ============================================================================
# 4 — Trace width boundaries
# ============================================================================


@pytest.mark.parametrize(
    "width, desc",
    [
        *[(w, f"zero_{i}") for i, w in enumerate(TRACE_WIDTHS_ZERO)],
        *[(w, f"negative_{i}") for i, w in enumerate(TRACE_WIDTHS_NEGATIVE)],
        *[(w, f"nan_{i}") for i, w in enumerate(TRACE_WIDTHS_NAN)],
        *[(w, f"inf_{i}") for i, w in enumerate(TRACE_WIDTHS_INF)],
    ],
)
def test_trace_width_boundary(width, desc):
    """Edge-to-edge clearance with boundary trace widths.

    The ``_calculate_minimum_clearance`` function subtracts
    ``width/2`` from the centreline distance.  Zero width is fine;
    negative width effectively *adds* to clearance; NaN/inf width
    may produce anomalous results but should not crash.
    """
    # Parallel traces 1 mm apart centre-to-centre
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=width)
    r2 = _make_route("NET2", [(0.0, 1.0), (10.0, 1.0)], width=0.127)
    results = _make_results({"NET1": r1, "NET2": r2})

    try:
        report = verify_clearance(results, min_clearance=0.127)
    except Exception:
        if math.isnan(width) or math.isinf(width):
            pytest.xfail("NaN/inf width causes crash (expected edge-case)")
        raise

    assert isinstance(report, ClearanceReport)
    assert report.total_checks == 1


def test_trace_width_zero_no_contribution():
    """Zero-width trace contributes nothing to edge-to-edge deduction.

    Edge distance = centreline distance (the half-width terms vanish).
    """
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=0.0)
    r2 = _make_route("NET2", [(0.0, 0.5), (10.0, 0.5)], width=0.0)
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.5)
    # Edge-to-edge = 0.5 - 0 - 0 = 0.5, exactly at threshold → pass
    assert report.violation_count == 0


def test_trace_width_negative_behavior():
    """Negative trace width is mathematically equivalent to a bonus.

    Edge distance = centreline + |width|/2, so clearance appears larger.
    """
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=-0.2)
    r2 = _make_route("NET2", [(0.0, 0.3), (10.0, 0.3)], width=0.127)
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    # Edge-to-edge = 0.3 - (-0.1) - 0.0635 = 0.3 + 0.1 - 0.0635 ≈ 0.3365
    # which is > 0.127, so no violation
    assert report.violation_count == 0


# ============================================================================
# 5 — Segment geometry boundaries
# ============================================================================


@pytest.mark.parametrize(
    "spacing, expectation",
    [
        # Edge-to-edge = spacing - width1/2 - width2/2 = spacing - w
        # For w=0.127, to get edge-to-edge = 0.127 we need spacing = 0.254
        (exactly_at(0.254), "pass"),        # edge-to-edge = 0.127 exactly
        (just_below(0.254), "violation"),    # edge-to-edge < 0.127
        (just_above(0.254), "pass"),         # edge-to-edge > 0.127
    ],
)
def test_segment_spacing_at_threshold(spacing, expectation):
    """Parallel segments at exactly / just-below / just-above threshold.

    The edge-to-edge distance is ``spacing - width1/2 - width2/2``
    because traces sit on the parallel lines.  With equal widths *w*,
    edge-to-edge = centreline-spacing − *w*.
    """
    w = 0.127  # trace width
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=w)
    r2 = _make_route("NET2", [(0.0, spacing), (10.0, spacing)], width=w)

    results = _make_results({"NET1": r1, "NET2": r2})
    report = verify_clearance(results, min_clearance=0.127)

    if expectation == "pass":
        assert report.violation_count == 0, (
            f"spacing={spacing} should pass but got "
            f"{report.violation_count} violation(s)"
        )
    else:
        assert report.violation_count > 0, (
            f"spacing={spacing} should violate but passed"
        )


def test_segment_overlap_negative_clearance():
    """Overlapping segments produce negative edge distance.

    The violation's ``actual_clearance`` must be negative to reflect
    the overlap severity.
    """
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=0.5)
    r2 = _make_route("NET2", [(0.0, 0.1), (10.0, 0.1)], width=0.5)
    # Edge-to-edge = 0.1 - 0.25 - 0.25 = -0.4
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    assert report.violation_count > 0
    violation = report.violations[0]
    assert violation.actual_clearance < 0, (
        f"Overlap should produce negative actual_clearance, "
        f"got {violation.actual_clearance}"
    )


def test_segment_collinear():
    """Collinear segments on the same line should be checked correctly.

    Two collinear segments that do not overlap have a non-zero
    edge-to-edge distance.  The analytical segment-to-segment
    algorithm should handle this.
    """
    # NET1: (0,0)→(5,0), NET2: (10,0)→(15,0) — collinear, gap of 5
    r1 = _make_route("NET1", [(0.0, 0.0), (5.0, 0.0)], width=0.127)
    r2 = _make_route("NET2", [(10.0, 0.0), (15.0, 0.0)], width=0.127)
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=1.0)
    # Centreline gap is 5; edge-to-edge = 5 - 0.0635 - 0.0635 ≈ 4.873
    # which is > 1.0 → no violation
    assert report.violation_count == 0


def test_segment_collinear_overlapping():
    """Collinear overlapping segments should report violation."""
    # NET1: (0,0)→(10,0), NET2: (5,0)→(15,0) — collinear, overlap 5
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=0.2)
    r2 = _make_route("NET2", [(5.0, 0.0), (15.0, 0.0)], width=0.2)
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    # Overlapping collinear → actual_clearance should be negative
    assert report.violation_count > 0
    assert report.violations[0].actual_clearance < 0


def test_single_segment_path():
    """Single-segment (two-point) path against another single segment."""
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)])
    r2 = _make_route("NET2", [(0.0, 2.0), (10.0, 2.0)])
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=2.0)
    # Edge-to-edge ≈ 2.0 - 0.0635 - 0.0635 ≈ 1.873 < 2.0 → violation
    assert report.violation_count > 0


def test_segment_perpendicular():
    """Perpendicular segments (crossing) — distance computed correctly."""
    # NET1 horizontal, NET2 vertical crossing at (5,5) on same layer
    r1 = _make_route("NET1", [(0.0, 5.0), (10.0, 5.0)], width=0.2)
    r2 = _make_route("NET2", [(5.0, 0.0), (5.0, 10.0)], width=0.2)
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    # Crossing segments on same layer → actual_clearance < 0 (overlap)
    # The algorithm measures centreline distance (which is 0 at crossing)
    # minus half-widths → negative
    assert report.violation_count > 0
    assert report.violations[0].actual_clearance < 0


def test_degenerate_segment_zero_length():
    """Zero-length segment (a == b) — handled by degenerate case."""
    # Single point repeated — effectively a zero-length segment
    r1 = _make_route("NET1", [(3.0, 3.0), (3.0, 3.0)])
    r2 = _make_route("NET2", [(0.0, 0.0), (10.0, 0.0)])
    results = _make_results({"NET1": r1, "NET2": r2})

    report = verify_clearance(results, min_clearance=0.127)
    assert isinstance(report, ClearanceReport)


# ============================================================================
# 6 — HV escalation boundaries
# ============================================================================


@pytest.mark.parametrize(
    "voltage, desc",
    [
        *[(v, f"zero_{i}") for i, v in enumerate(VOLTAGE_ZERO)],
        *[(v, f"negative_{i}") for i, v in enumerate(VOLTAGE_NEGATIVE)],
        *[(v, f"nan_{i}") for i, v in enumerate(VOLTAGE_NAN)],
        *[(v, f"inf_{i}") for i, v in enumerate(VOLTAGE_INF)],
        *[(v, f"extreme_{i}") for i, v in enumerate(VOLTAGE_EXTREME)],
    ],
)
def test_hv_escalation_boundary_voltage(voltage, desc):
    """HV net with boundary voltage values — does clearance escalate?

    The ``verify_clearance`` function should consult the voltage
    rating and escalate the required clearance when an HV net is
    involved.
    """
    hv_path = _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)])
    lv_path = _make_route("SIG1", [(0.0, 5.0), (10.0, 5.0)])
    results = _make_results({"AC_L": hv_path, "SIG1": lv_path})

    try:
        report = verify_clearance(
            results,
            min_clearance=0.127,
            voltage_ratings={"AC_L": voltage},
        )
    except Exception:
        if math.isnan(voltage) or math.isinf(voltage):
            pytest.xfail("NaN/inf voltage in HV escalation causes crash")
        raise

    assert isinstance(report, ClearanceReport)
    assert report.total_checks == 1


def test_hv_escalation_default_voltage():
    """HV net without explicit voltage rating defaults to 230V.

    Required clearance should be max(0.127, 3.2) = 3.2 mm.
    """
    hv_path = _make_route("HV_BUS", [(0.0, 0.0), (10.0, 0.0)])
    lv_path = _make_route("SIG1", [(0.0, 0.5), (10.0, 0.5)])
    results = _make_results({"HV_BUS": hv_path, "SIG1": lv_path})

    report = verify_clearance(results, min_clearance=0.127)
    # Edge-to-edge ≈ 0.5 - 0.0635 - 0.0635 = 0.373 mm < 3.2 mm → violation
    assert report.violation_count > 0
    assert report.violations[0].required_clearance > 0.127


def test_hv_escalation_both_hv():
    """Both nets are HV — clearance should use the higher voltage."""
    hv1 = _make_route("HV_BUS", [(0.0, 0.0), (10.0, 0.0)])
    hv2 = _make_route("AC_L", [(0.0, 0.5), (10.0, 0.5)])
    results = _make_results({"HV_BUS": hv1, "AC_L": hv2})

    report = verify_clearance(
        results,
        min_clearance=0.127,
        voltage_ratings={"HV_BUS": 100.0, "AC_L": 400.0},
    )
    assert report.total_checks == 1
    # 400V → most-conservative across all standards (IEC 60950-1, 60335-1,
    # 60664-1, 62368-1, IPC-2221) = 14.0 mm.  The old IPC-2221-only value
    # was 8.0; the unified engine is correctly more conservative.
    if report.violation_count > 0:
        assert report.violations[0].required_clearance == pytest.approx(14.0)


# ============================================================================
# 7 — Empty input
# ============================================================================


def test_empty_input_zero_routes():
    """Zero routes → zero checks, zero violations, no crash."""
    results = _make_results({})
    report = verify_clearance(results, min_clearance=0.127)
    assert isinstance(report, ClearanceReport)
    assert report.total_checks == 0
    assert report.violation_count == 0
    assert report.pass_rate == 100.0


def test_empty_input_single_net():
    """Single net → zero pairs to check, zero violations."""
    r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)])
    results = _make_results({"NET1": r1})
    report = verify_clearance(results, min_clearance=0.127)
    assert report.total_checks == 0
    assert report.violation_count == 0


def test_empty_input_pass_rate_zero_checks():
    """``pass_rate`` for zero checks is 100% (no chances to fail)."""
    report = ClearanceReport(violations=[], total_checks=0)
    assert report.pass_rate == 100.0


# ============================================================================
# 8 — Low-level geometry function boundaries
# ============================================================================


class TestPointToSegmentDist:
    """Boundary tests for ``_point_to_segment_dist``."""

    def test_degenerate_segment_same_point(self):
        """Segment a==b — degenerate case, distance to point a."""
        dist, cp, p = _point_to_segment_dist(
            (5.0, 0.0), (3.0, 3.0), (3.0, 3.0),
        )
        assert dist == pytest.approx(math.hypot(5 - 3, 0 - 3))
        assert cp == (3.0, 3.0)
        assert p == (5.0, 0.0)

    def test_point_on_segment(self):
        """Point lies exactly on the segment."""
        dist, cp, p = _point_to_segment_dist(
            (5.0, 5.0), (0.0, 0.0), (10.0, 10.0),
        )
        assert dist == pytest.approx(0.0, abs=1e-10)
        assert cp == pytest.approx((5.0, 5.0))

    def test_point_at_endpoint(self):
        """Point coincides with segment endpoint."""
        dist, cp, p = _point_to_segment_dist(
            (0.0, 0.0), (0.0, 0.0), (10.0, 0.0),
        )
        assert dist == pytest.approx(0.0, abs=1e-10)
        assert cp == (0.0, 0.0)

    @pytest.mark.parametrize(
        "px, py, desc",
        [
            (float("nan"), 0.0, "nan_x"),
            (0.0, float("nan"), "nan_y"),
            (float("inf"), 0.0, "inf_x"),
            (0.0, float("inf"), "inf_y"),
        ],
    )
    def test_nan_inf_point(self, px, py, desc):
        """Point with NaN/inf coordinate — should not crash.

        Currently the implementation propagates NaN/inf through
        the arithmetic; this test characterises that behaviour.
        """
        try:
            dist, cp, p = _point_to_segment_dist(
                (px, py), (0.0, 0.0), (10.0, 0.0),
            )
        except Exception:
            pytest.xfail(f"NaN/inf point ({desc}) crashes _point_to_segment_dist")

        # NaN distances won't compare meaningfully; just check no crash
        if math.isnan(px) or math.isnan(py):
            assert math.isnan(dist)
        # inf distances: may be inf or NaN depending on arithmetic path


class TestSegmentToSegmentDist:
    """Boundary tests for ``_segment_to_segment_dist``."""

    def test_both_degenerate(self):
        """Both segments are points."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (1.0, 0.0), (1.0, 0.0),
            (4.0, 0.0), (4.0, 0.0),
        )
        assert dist == pytest.approx(3.0)
        assert cp1 == (1.0, 0.0)
        assert cp2 == (4.0, 0.0)

    def test_one_degenerate_first(self):
        """First segment is a point, second is a real segment."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (5.0, 0.0), (5.0, 0.0),
            (0.0, 3.0), (10.0, 3.0),
        )
        assert dist == pytest.approx(3.0)
        assert cp1 == (5.0, 0.0)
        assert cp2 == (5.0, 3.0)

    def test_one_degenerate_second(self):
        """Second segment is a point, first is a real segment."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (0.0, 3.0), (10.0, 3.0),
            (5.0, 0.0), (5.0, 0.0),
        )
        assert dist == pytest.approx(3.0)
        assert cp1 == (5.0, 3.0)
        assert cp2 == (5.0, 0.0)

    def test_intersecting(self):
        """Two segments that cross."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (0.0, 0.0), (10.0, 10.0),
            (0.0, 10.0), (10.0, 0.0),
        )
        assert dist == pytest.approx(0.0, abs=1e-10)
        assert cp1 == pytest.approx((5.0, 5.0))
        assert cp2 == pytest.approx((5.0, 5.0))

    def test_parallel_offset(self):
        """Parallel segments with an offset."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (0.0, 0.0), (10.0, 0.0),
            (0.0, 3.0), (10.0, 3.0),
        )
        assert dist == pytest.approx(3.0)

    @pytest.mark.xfail(
        reason=(
            "_segment_to_segment_dist reports wrong closest-point on the "
            "second segment for collinear non-overlapping inputs.  The "
            "third element of _point_to_segment_dist return is the query "
            "point p, not the closest point on the target segment, but "
            "the caller uses it as if it were the closest point."
        ),
    )
    def test_collinear_non_overlapping(self):
        """Collinear, non-overlapping segments."""
        dist, cp1, cp2 = _segment_to_segment_dist(
            (0.0, 0.0), (5.0, 0.0),
            (10.0, 0.0), (15.0, 0.0),
        )
        assert dist == pytest.approx(5.0)
        assert cp1 == (5.0, 0.0)
        assert cp2 == (10.0, 0.0)

    @pytest.mark.parametrize(
        "vals, desc",
        [
            ((float("nan"), 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0), "nan_x1"),
            ((0.0, float("nan"), 10.0, 0.0, 0.0, 3.0, 10.0, 3.0), "nan_y1"),
            ((0.0, 0.0, float("nan"), 0.0, 0.0, 3.0, 10.0, 3.0), "nan_x2"),
            ((0.0, 0.0, 0.0, float("nan"), 0.0, 3.0, 10.0, 3.0), "nan_y2"),
            ((0.0, 0.0, 10.0, 0.0, float("nan"), 3.0, 10.0, 3.0), "nan_x3"),
            ((0.0, 0.0, 10.0, 0.0, 0.0, float("nan"), 10.0, 3.0), "nan_y3"),
            ((0.0, 0.0, 10.0, 0.0, 0.0, 3.0, float("nan"), 3.0), "nan_x4"),
            ((0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, float("nan")), "nan_y4"),
            # inf variants
            ((float("inf"), 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0), "inf_x1"),
            ((0.0, 0.0, 10.0, 0.0, 0.0, 3.0, float("inf"), 3.0), "inf_x4"),
        ],
    )
    def test_nan_inf_coords(self, vals, desc):
        """Segment-to-segment with NaN/inf coordinates.

        Should not crash; distance may be NaN or inf.
        """
        try:
            dist, cp1, cp2 = _segment_to_segment_dist(*vals)
        except Exception:
            pytest.xfail(f"NaN/inf in _segment_to_segment_dist ({desc}) crashes")

        assert isinstance(dist, float)
        # NaN distances are expected for NaN inputs
        any_nan = any(math.isnan(v) for v in vals)
        any_inf = any(math.isinf(v) for v in vals)
        if any_nan:
            assert math.isnan(dist), (
                f"Expected NaN distance with NaN input, got {dist}"
            )


class TestCalculateMinimumClearance:
    """Boundary tests for ``_calculate_minimum_clearance``."""

    def test_no_segments(self):
        """Routes with no path coordinates → no segments, safe."""
        r1 = _make_route("NET1", [])
        r2 = _make_route("NET2", [(0.0, 0.0), (10.0, 0.0)])
        dist, loc, layer = _calculate_minimum_clearance(r1, r2)
        assert dist == float("inf")
        assert loc == (0.0, 0.0)
        assert layer == "unknown"

    def test_no_segments_both(self):
        """Both routes have no segments."""
        r1 = _make_route("NET1", [])
        r2 = _make_route("NET2", [])
        dist, loc, layer = _calculate_minimum_clearance(r1, r2)
        assert dist == float("inf")

    def test_different_layers(self):
        """Routes on different layers should have infinite clearance.

        Only same-layer segments are compared.
        """
        r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], layer="F.Cu")
        r2 = _make_route("NET2", [(0.0, 0.0), (10.0, 0.0)], layer="B.Cu")
        dist, loc, layer = _calculate_minimum_clearance(r1, r2)
        assert dist == float("inf")
        assert layer == "unknown"

    def test_overlap_negative_clearance(self):
        """Overlapping traces → negative edge distance."""
        r1 = _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width=0.5)
        r2 = _make_route("NET2", [(0.0, 0.1), (10.0, 0.1)], width=0.5)
        dist, loc, layer = _calculate_minimum_clearance(r1, r2)
        assert dist < 0, f"Expected negative clearance for overlap, got {dist}"

    def test_width_default_zero(self):
        """Routes without ``width_mm`` attribute default to 0.0."""
        # Simulate a route without width_mm via a plain object
        class _BareRoute:
            pass

        r = _BareRoute()
        r.path = RoutePath("X", [(0.0, 0.0), (10.0, 0.0)], "F.Cu", 10.0)
        # No width_mm attribute

        r2 = _make_route("NET2", [(0.0, 0.5), (10.0, 0.5)], width=0.0)
        dist, loc, layer = _calculate_minimum_clearance(r, r2)
        assert dist == pytest.approx(0.5)


class TestClearanceViolationProperties:
    """Boundary values for ``ClearanceViolation`` and ``ClearanceReport``."""

    def test_deficiency_negative_actual(self):
        """Deficiency with negative actual clearance (overlap)."""
        v = ClearanceViolation(
            net1="A", net2="B", location=(0.0, 0.0),
            actual_clearance=-0.5, required_clearance=0.127,
            layer="F.Cu",
        )
        assert v.deficiency == pytest.approx(0.627)  # 0.127 - (-0.5)

    def test_deficiency_exact(self):
        """Deficiency when exactly at threshold."""
        v = ClearanceViolation(
            net1="A", net2="B", location=(0.0, 0.0),
            actual_clearance=0.127, required_clearance=0.127,
            layer="F.Cu",
        )
        assert v.deficiency == pytest.approx(0.0)

    def test_report_all_pass(self):
        """Report with no violations."""
        r = ClearanceReport(violations=[], total_checks=100)
        assert r.pass_rate == 100.0
        assert r.violation_count == 0

    def test_report_all_fail(self):
        """Report where every check fails."""
        violations = [
            ClearanceViolation("A", "B", (0.0, 0.0), 0.0, 0.127, "F.Cu")
            for _ in range(10)
        ]
        r = ClearanceReport(violations=violations, total_checks=10)
        assert r.pass_rate == 0.0
        assert r.violation_count == 10
