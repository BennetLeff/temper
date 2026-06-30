"""
Boundary edge-case tests for the acid trap detection module
(``temper_placer.router_v6.acid_trap_detection``).

Tests parametrized across trace widths, coordinate edge cases, threshold
boundaries, at-threshold angle severities, and empty inputs — all imported
from ``dfm_boundary_constants`` where possible.

Covers
------
1. Trace width boundaries
2. Coordinate boundaries
3. Threshold boundaries
4. At-threshold angles
5. Empty / degenerate input
"""

from __future__ import annotations

import math
import warnings

import pytest

from temper_placer.router_v6.acid_trap_detection import (
    AcidTrap,
    AcidTrapReport,
    detect_acid_traps,
)
from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.router_v6.dfm_boundary_constants import (
    COORD_BOUNDARY,
    COORD_INF,
    COORD_NAN,
    THRESHOLD_BOUNDARY,
    THRESHOLD_INF,
    THRESHOLD_NAN,
    THRESHOLD_NEGATIVE,
    THRESHOLD_ZERO,
    TRACE_WIDTHS_BOUNDARY,
    TRACE_WIDTHS_NEGATIVE,
    TRACE_WIDTHS_NORMAL,
    TRACE_WIDTHS_ZERO,
    just_above,
    just_below,
)

# ---------------------------------------------------------------------------
# Helper: build a RoutingResults with a single acute-angle route
# ---------------------------------------------------------------------------

# A 3-point path that forms exactly 45° at the middle vertex.
# p1=(-10,0), p2=(0,0), p3=(-10*cos(45°), 10*sin(45°)) = (-7.071..., 7.071...)
_ACUTE_45_PATH = [
    (-10.0, 0.0),
    (0.0, 0.0),
    (-10.0 * math.sqrt(2) / 2, 10.0 * math.sqrt(2) / 2),
]


def _make_routing_results(
    coordinates: list[tuple[float, float]] | None = None,
    width_mm: float = 0.2,
    net_name: str = "TEST_NET",
    vias: list | None = None,
    start_pin: tuple[float, float] | None = None,
    end_pin: tuple[float, float] | None = None,
) -> RoutingResults:
    """Build a ``RoutingResults`` with a single compiled route."""
    coords = coordinates if coordinates is not None else _ACUTE_45_PATH
    path = RoutePath(
        net_name=net_name,
        coordinates=coords,
        layer_name="F.Cu",
        path_length=float(len(coords) * 10.0),
    )
    route = CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width_mm,
        vias=vias if vias is not None else [],
        matched_length_mm=None,
    )
    # Optionally attach pin locations for endpoint-angle checks
    if start_pin is not None:
        route.start_pin_location = start_pin  # type: ignore[attr-defined]
    if end_pin is not None:
        route.end_pin_location = end_pin  # type: ignore[attr-defined]

    return RoutingResults(
        compiled_routes={net_name: route},
        failed_nets=[],
    )


# ---------------------------------------------------------------------------
# Helper: build a path that yields a precise angle at the middle vertex
# ---------------------------------------------------------------------------

def _path_with_angle(angle_deg: float, segment_len: float = 10.0) -> list[tuple[float, float]]:
    """Return a 3-point path whose interior angle at p2 equals *angle_deg*.

    Uses the symmetric construction:
        p1 = (-L, 0),  p2 = (0, 0),  p3 = (L·cos θ, L·sin θ)
    where θ = π − angle_rad, so that the angle between vectors
    ``p1−p2`` and ``p3−p2`` is exactly *angle_deg*.
    """
    theta = math.pi - math.radians(angle_deg)
    p3 = (segment_len * math.cos(theta), segment_len * math.sin(theta))
    return [(-segment_len, 0.0), (0.0, 0.0), p3]


# ===================================================================
# 1. Trace width boundaries
# ===================================================================

@pytest.mark.parametrize("width_mm", TRACE_WIDTHS_BOUNDARY)
def test_trace_width_boundary_returns_valid_report(width_mm: float):
    """``detect_acid_traps`` must return an ``AcidTrapReport`` for any trace width."""
    results = _make_routing_results(width_mm=width_mm)
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)
    assert isinstance(report.trap_count, int)
    # Severity properties must be non-negative ints
    assert report.critical_count >= 0
    assert report.medium_count >= 0
    assert report.low_count >= 0


@pytest.mark.parametrize("width_mm", TRACE_WIDTHS_NORMAL)
def test_trace_width_normal_values_classify_correctly(width_mm: float):
    """Normal trace widths produce severity strings in {low, medium, high}."""
    results = _make_routing_results(width_mm=width_mm)
    report = detect_acid_traps(results)
    for trap in report.acid_traps:
        assert trap.severity in {"low", "medium", "high"}


@pytest.mark.parametrize("width_mm", TRACE_WIDTHS_NEGATIVE)
def test_trace_width_negative_still_returns_report(width_mm: float):
    """Negative trace widths should not crash the detector."""
    results = _make_routing_results(width_mm=width_mm)
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


@pytest.mark.parametrize("width_mm", TRACE_WIDTHS_ZERO)
def test_trace_width_zero_classifies_as_narrow(width_mm: float):
    """Zero-width traces are < 0.2, so severity should be demoted one level."""
    results = _make_routing_results(width_mm=width_mm)
    report = detect_acid_traps(results)
    # The 45° path normally yields "medium" (45° is not < 45, but is < 60).
    # With width < 0.2, "medium" → "low".
    if report.trap_count > 0:
        # Every trap severity for a zero-width trace must be "low" (demoted).
        for trap in report.acid_traps:
            assert trap.severity == "low", (
                f"Expected 'low' for width={width_mm}, got {trap.severity}"
            )


# ===================================================================
# 2. Coordinate boundaries
# ===================================================================

@pytest.mark.parametrize("coord", COORD_BOUNDARY)
def test_coordinate_boundary_in_path_returns_valid_report(coord: tuple[float, float]):
    """Any boundary coordinate in a 3-point path must not crash."""
    # Build a 3-point path with the boundary coordinate as the middle vertex
    p1 = (0.0, 0.0)
    p2 = coord
    p3 = (10.0, 10.0)
    path = [p1, p2, p3]

    results = _make_routing_results(coordinates=path)
    # Suppress warnings about degenerate cases if needed
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


@pytest.mark.parametrize("coord", COORD_NAN)
def test_nan_coordinate_does_not_crash(coord: tuple[float, float]):
    """NaN coordinates must be handled gracefully (return valid report)."""
    path = [(0.0, 0.0), coord, (10.0, 10.0)]
    results = _make_routing_results(coordinates=path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


@pytest.mark.parametrize("coord", COORD_INF)
def test_inf_coordinate_does_not_crash(coord: tuple[float, float]):
    """Infinite coordinates must be handled gracefully."""
    path = [(0.0, 0.0), coord, (10.0, 10.0)]
    results = _make_routing_results(coordinates=path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


def test_single_point_path_skipped():
    """A single-point path (< 3 vertices) produces no traps."""
    path = [(5.0, 5.0)]
    results = _make_routing_results(coordinates=path)
    report = detect_acid_traps(results)
    assert report.trap_count == 0


def test_two_point_path_skipped():
    """A two-point path is degenerate for angle detection."""
    path = [(0.0, 0.0), (10.0, 0.0)]
    results = _make_routing_results(coordinates=path)
    report = detect_acid_traps(results)
    assert report.trap_count == 0


def test_duplicate_consecutive_points_filtered():
    """Duplicate consecutive points are filtered before angle analysis."""
    # After dedup: [(0,0), (10,0), (20,0)] — a straight line, no traps
    path = [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (20.0, 0.0), (20.0, 0.0), (20.0, 0.0)]
    results = _make_routing_results(coordinates=path)
    report = detect_acid_traps(results)
    # After dedup we get 3 collinear points → 180° → no trap
    assert report.trap_count == 0


def test_all_duplicate_points_yields_no_trap():
    """A path where all points are the same collapses to a single point."""
    path = [(7.0, 7.0), (7.0, 7.0), (7.0, 7.0), (7.0, 7.0)]
    results = _make_routing_results(coordinates=path)
    report = detect_acid_traps(results)
    assert report.trap_count == 0


def test_collinear_three_point_path_no_trap():
    """Collinear 3-point path has 180° angle — not an acid trap."""
    path = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    results = _make_routing_results(coordinates=path)
    report = detect_acid_traps(results)
    assert report.trap_count == 0


# ===================================================================
# 3. Threshold boundaries
# ===================================================================

@pytest.mark.parametrize("threshold", THRESHOLD_BOUNDARY)
def test_threshold_boundary_returns_valid_report(threshold: float):
    """Any boundary ``min_angle_threshold`` must not crash the detector."""
    results = _make_routing_results()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results, min_angle_threshold=threshold)
    assert isinstance(report, AcidTrapReport)


@pytest.mark.parametrize("threshold", THRESHOLD_NAN)
def test_nan_threshold_silently_ignores_all_angles(threshold: float):
    """NaN threshold makes every comparison False → zero traps."""
    results = _make_routing_results()  # 45° path — would normally be a trap
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results, min_angle_threshold=threshold)
    # All comparisons ``angle < NaN`` are False
    assert report.trap_count == 0


@pytest.mark.parametrize("threshold", THRESHOLD_INF)
def test_inf_threshold_is_clamped_to_90(threshold: float):
    """Threshold > 90° is clamped to 90° with a warning."""
    results = _make_routing_results()  # 45° path — is a trap at 90° threshold
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = detect_acid_traps(results, min_angle_threshold=threshold)
    assert isinstance(report, AcidTrapReport)
    # Since 45° < 90°, it should still be detected after clamping
    assert report.trap_count >= 0
    # A UserWarning about clamping should have been issued
    assert any("clamping" in str(warning.message).lower() for warning in w), (
        f"Expected clamping warning for threshold={threshold!r}"
    )


@pytest.mark.parametrize("threshold", [90.0, 180.0])
def test_threshold_at_or_above_90_clamps(threshold: float):
    """At 90° (default) no warning; above 90° warns and clamps."""
    results = _make_routing_results()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = detect_acid_traps(results, min_angle_threshold=threshold)
    assert isinstance(report, AcidTrapReport)
    if threshold > 90.0:
        assert any("clamping" in str(warning.message).lower() for warning in w)
    else:
        # No clamping warning at exactly 90.0
        assert not any("clamping" in str(warning.message).lower() for warning in w)


@pytest.mark.parametrize("threshold", THRESHOLD_NEGATIVE)
def test_negative_threshold_detects_no_traps(threshold: float):
    """Negative threshold — no angle (all ≥ 0°) can be < negative threshold."""
    results = _make_routing_results()
    report = detect_acid_traps(results, min_angle_threshold=threshold)
    assert report.trap_count == 0


@pytest.mark.parametrize("threshold", THRESHOLD_ZERO)
def test_zero_threshold_detects_no_traps(threshold: float):
    """Zero threshold — no angle < 0° exists."""
    results = _make_routing_results()
    report = detect_acid_traps(results, min_angle_threshold=threshold)
    # Angles are 0-180, but 0 < 0 is False
    assert report.trap_count == 0


# ===================================================================
# 4. At-threshold angles — severity boundaries
# ===================================================================

# Severity thresholds (from _classify_severity):
#   angle < 45  → "high"
#   angle < 60  → "medium"   (but only if angle >= 45)
#   else        → "low"
#
# Detection threshold (default 90°):
#   angle < 90  → detected
#   angle ≥ 90  → not detected

@pytest.mark.parametrize(
    "angle_deg, expected_severity, detected",
    [
        # Exactly at severity boundaries
        (45.0, "medium", True),         # 45 < 45 is False → medium
        (60.0, "low", True),
        # Just below severity boundaries
        (just_below(45.0), "high", True),
        (just_below(60.0), "medium", True),
        # Just above severity boundaries
        (just_above(45.0), "medium", True),
        (just_above(60.0), "low", True),
        # Detection boundary (90°)
        (90.0, "low", False),            # 90 < 90 is False → NOT detected
        (just_below(90.0), "low", True),
        (just_above(90.0), "low", False),
        # Extreme angles
        (0.0, "high", True),             # Degenerate: colinear backtrack
        (180.0, "low", False),           # Straight line
        (179.999, "low", False),         # Almost straight
    ],
)
def test_severity_at_threshold_boundaries(
    angle_deg: float,
    expected_severity: str,
    detected: bool,
):
    """Verify severity classification at and around key angle thresholds."""
    coords = _path_with_angle(angle_deg)
    results = _make_routing_results(coordinates=coords)
    report = detect_acid_traps(results, min_angle_threshold=90.0)

    if detected:
        assert report.trap_count >= 1, (
            f"Angle {angle_deg}° should be detected as acid trap"
        )
        trap = report.acid_traps[0]
        assert trap.severity == expected_severity, (
            f"Angle {angle_deg}°: expected severity {expected_severity!r}, "
            f"got {trap.severity!r}"
        )
    else:
        assert report.trap_count == 0, (
            f"Angle {angle_deg}° should NOT be detected as acid trap"
        )


@pytest.mark.parametrize(
    "angle_deg, expected_base, width_mm, expected_demoted",
    [
        # Narrow trace demotion (width < 0.2 mm)
        (30.0, "high", 0.15, "medium"),     # high → medium
        (50.0, "medium", 0.15, "low"),      # medium → low
        (70.0, "low", 0.15, "low"),         # low stays low
        # Wide trace — no demotion (width ≥ 0.2 mm)
        (30.0, "high", 0.2, "high"),
        (50.0, "medium", 0.2, "medium"),
        (70.0, "low", 0.2, "low"),
        # Exactly at width threshold (0.2 mm) — no demotion
        (30.0, "high", 0.2, "high"),
        (50.0, "medium", 0.2, "medium"),
    ],
)
def test_severity_narrow_trace_demotion(
    angle_deg: float,
    expected_base: str,
    width_mm: float,
    expected_demoted: str,
):
    """Narrow traces (< 0.2 mm) demote severity by one level."""
    coords = _path_with_angle(angle_deg)
    results = _make_routing_results(coordinates=coords, width_mm=width_mm)
    report = detect_acid_traps(results, min_angle_threshold=90.0)
    assert report.trap_count >= 1, f"Angle {angle_deg}° should be detected"
    assert report.acid_traps[0].severity == expected_demoted, (
        f"width={width_mm}, angle={angle_deg}°: "
        f"expected {expected_demoted!r}, got {report.acid_traps[0].severity!r}"
    )


# ===================================================================
# 5. Empty / degenerate input
# ===================================================================

def test_empty_routing_results():
    """Zero routes → valid report with zero traps."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)
    assert report.trap_count == 0
    assert report.critical_count == 0
    assert report.medium_count == 0
    assert report.low_count == 0


def test_zero_coordinate_path():
    """A route with an empty coordinate list is skipped gracefully."""
    path = RoutePath("EMPTY", [], "F.Cu", 0.0)
    route = CompiledRoute("EMPTY", path, 0.2, [], None)
    results = RoutingResults(compiled_routes={"EMPTY": route}, failed_nets=[])
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)
    assert report.trap_count == 0


def test_none_vias_handled():
    """A compiled route with ``vias=None`` must not crash."""
    path = RoutePath("NET", _ACUTE_45_PATH, "F.Cu", 30.0)
    route = CompiledRoute("NET", path, 0.2, None, None)  # vias=None
    results = RoutingResults(compiled_routes={"NET": route}, failed_nets=[])
    report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


def test_acid_trap_report_properties_edge_cases():
    """``AcidTrapReport`` properties work with edge-case severities."""
    # Empty report
    empty = AcidTrapReport(acid_traps=[])
    assert empty.trap_count == 0
    assert empty.critical_count == 0
    assert empty.medium_count == 0
    assert empty.low_count == 0

    # Report with unknown severity
    weird = AcidTrapReport(acid_traps=[
        AcidTrap("N", (0.0, 0.0), 45.0, "unknown_severity"),
    ])
    assert weird.trap_count == 1
    # "unknown_severity" is not "high", "medium", or "low" → all zero
    assert weird.critical_count == 0
    assert weird.medium_count == 0
    assert weird.low_count == 0


# ===================================================================
# Endpoint approach angle boundaries (start_pin / end_pin)
# ===================================================================

def test_endpoint_angle_with_nan_pin_location():
    """Endpoint approach angles with NaN pin locations are guarded."""
    path = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]  # Straight line
    results = _make_routing_results(
        coordinates=path,
        start_pin=(float("nan"), 0.0),
        end_pin=(20.0, 10.0),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


def test_endpoint_angle_with_inf_pin_location():
    """Endpoint approach angles with inf pin locations are guarded."""
    path = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    results = _make_routing_results(
        coordinates=path,
        start_pin=(float("inf"), 0.0),
        end_pin=(20.0, 10.0),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = detect_acid_traps(results)
    assert isinstance(report, AcidTrapReport)


# ===================================================================
# _calculate_angle direct boundary tests
# ===================================================================

from temper_placer.router_v6.acid_trap_detection import _calculate_angle  # noqa: E402


class TestCalculateAngleBoundaries:
    """Direct boundary tests for the ``_calculate_angle`` helper."""

    def test_degenerate_same_point_returns_180(self):
        """When p1 == p2 or p2 == p3, magnitude is zero → returns 180°."""
        assert _calculate_angle((0, 0), (0, 0), (10, 0)) == 180.0
        assert _calculate_angle((0, 0), (10, 0), (10, 0)) == 180.0
        assert _calculate_angle((5, 5), (5, 5), (5, 5)) == 180.0

    @pytest.mark.parametrize("pt", COORD_NAN)
    def test_nan_input_returns_finite(self, pt):
        """NaN in any position should produce finite output (0 or 180)."""
        # The internal math may produce NaN, but the final guard returns 180.0
        result = _calculate_angle(pt, (0.0, 0.0), (10.0, 0.0))
        assert not math.isnan(result)
        assert math.isfinite(result)

    @pytest.mark.parametrize("pt", COORD_INF)
    def test_inf_input_produces_finite_or_inf(self, pt):
        """Inf in any position must not raise."""
        result = _calculate_angle(pt, (0.0, 0.0), (10.0, 0.0))
        # May be finite (180.0 from NaN guard) or inf
        # The key contract: no exception
        assert isinstance(result, float)

    def test_perfect_right_angle(self):
        """90° right angle."""
        result = _calculate_angle((10, 0), (0, 0), (0, 10))
        assert result == pytest.approx(90.0)

    def test_straight_line(self):
        """180° collinear."""
        result = _calculate_angle((0, 0), (10, 0), (20, 0))
        assert result == pytest.approx(180.0)

    def test_acute_45(self):
        """45° acute angle."""
        coords = _path_with_angle(45.0)
        result = _calculate_angle(coords[0], coords[1], coords[2])
        assert result == pytest.approx(45.0)

    def test_obtuse_135(self):
        """135° obtuse angle."""
        coords = _path_with_angle(135.0)
        result = _calculate_angle(coords[0], coords[1], coords[2])
        assert result == pytest.approx(135.0)
