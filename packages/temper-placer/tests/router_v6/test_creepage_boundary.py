"""
Boundary edge-case tests for Router V6 Stage 5.6: Creepage Check.

Covers voltage boundaries, default-creepage boundaries, net-name
boundaries, coordinate boundaries, voltage-bracket thresholds, and
empty-input handling.  Uses shared constants from
``dfm_boundary_constants.py``.
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.creepage_check import (
    _calculate_required_creepage,
    _extract_segments,
    _is_high_voltage_net,
    _point_to_segment_distance,
    _segment_to_segment_info,
    verify_creepage,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

from dfm_boundary_constants import (
    COORD_INF,
    COORD_NAN,
    COORD_NEGATIVE,
    COORD_ZERO,
    THRESHOLD_INF,
    THRESHOLD_NAN,
    THRESHOLD_NEGATIVE,
    THRESHOLD_ZERO,
    VOLTAGE_BOUNDARY,
    VOLTAGE_EXTREME,
    VOLTAGE_INF,
    VOLTAGE_NAN,
    VOLTAGE_NEGATIVE,
    VOLTAGE_ZERO,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_results(*routes: CompiledRoute) -> RoutingResults:
    """Build a ``RoutingResults`` from the given compiled routes."""
    return RoutingResults(
        compiled_routes={r.net_name: r for r in routes},
        failed_nets=[],
    )


def _make_route(
    net_name: str,
    coords: list[tuple[float, float]],
    layer: str = "F.Cu",
) -> CompiledRoute:
    """Build a ``CompiledRoute`` with a simple straight-line path."""
    path = RoutePath(
        net_name=net_name,
        coordinates=coords,
        layer_name=layer,
        path_length=0.0,
    )
    return CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=0.127,
        vias=[],
        matched_length_mm=None,
    )


# ===================================================================
# 1. Voltage boundaries
# ===================================================================


class TestVoltageBoundaries:
    """``_calculate_required_creepage`` with boundary voltage values."""

    @pytest.mark.parametrize("voltage", VOLTAGE_BOUNDARY)
    def test_does_not_crash(self, voltage: float):
        """Calling the lookup with any boundary voltage must not raise."""
        _calculate_required_creepage(voltage)  # no exception = pass

    @pytest.mark.parametrize("voltage", VOLTAGE_ZERO + VOLTAGE_EXTREME)
    def test_zero_and_extreme_return_positive(self, voltage: float):
        """Zero and large finite voltages must return a positive distance."""
        result = _calculate_required_creepage(voltage)
        assert isinstance(result, float)
        assert result > 0.0

    @pytest.mark.parametrize("voltage", VOLTAGE_NEGATIVE)
    def test_negative_voltage(self, voltage: float):
        """Negative voltages fall into the lowest bracket (0.13 mm).

        This is arguably a bug — negative voltage is physically
        meaningless — but the current implementation does not guard
        against it.
        """
        result = _calculate_required_creepage(voltage)
        assert result == pytest.approx(0.13)

    @pytest.mark.parametrize("voltage", VOLTAGE_NAN)
    def test_nan_voltage_should_be_rejected(self, voltage: float):
        """NaN voltage should raise ValueError."""
        assert math.isnan(voltage)
        with pytest.raises(ValueError, match="finite"):
            _calculate_required_creepage(voltage)

    @pytest.mark.parametrize("voltage", VOLTAGE_INF)
    def test_inf_voltage_should_be_rejected(self, voltage: float):
        """Infinite voltage should raise ValueError."""
        assert math.isinf(voltage)
        with pytest.raises(ValueError, match="finite"):
            _calculate_required_creepage(voltage)


# ===================================================================
# 2. Default creepage boundaries
# ===================================================================


class TestDefaultCreepageBoundaries:
    """``verify_creepage`` with boundary ``default_creepage`` values."""

    @pytest.fixture(autouse=True)
    def setup_routes(self):
        """Two routes: one HV, one LV — close enough to interact."""
        self.hv = _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)])
        self.lv = _make_route("SIG1", [(0.0, 0.5), (10.0, 0.5)])
        self.results = _make_results(self.hv, self.lv)

    # -- zero ----------------------------------------------------------

    @pytest.mark.parametrize("dc", THRESHOLD_ZERO)
    def test_default_zero_yields_no_violation(self, dc: float):
        """A required distance of 0 means no positive distance violates."""
        report = verify_creepage(self.results, default_creepage=dc)
        assert report.violation_count == 0

    # -- negative ------------------------------------------------------

    @pytest.mark.parametrize("dc", THRESHOLD_NEGATIVE)
    def test_default_negative_yields_no_violation(self, dc: float):
        """Negative required distance: no non-negative distance violates."""
        report = verify_creepage(self.results, default_creepage=dc)
        assert report.violation_count == 0

    # -- NaN -----------------------------------------------------------

    @pytest.mark.parametrize("dc", THRESHOLD_NAN)
    def test_default_nan(self, dc: float):
        """NaN default creepage should raise ValueError."""
        assert math.isnan(dc)
        with pytest.raises(ValueError, match="finite"):
            verify_creepage(self.results, default_creepage=dc)

    # -- inf -----------------------------------------------------------

    @pytest.mark.parametrize("dc", THRESHOLD_INF)
    def test_default_inf_flags_all(self, dc: float):
        """Infinite required distance makes every segment pair a violation."""
        report = verify_creepage(self.results, default_creepage=dc)
        # Every check between AC_L and SIG1 should violate
        assert report.violation_count > 0
        assert report.violation_count <= report.total_checks


# ===================================================================
# 3. Net name boundaries
# ===================================================================


class TestNetNameBoundaries:
    """``_is_high_voltage_net`` with boundary net names."""

    @pytest.mark.parametrize(
        "net_name, expected",
        [
            ("", False),
            ("   ", False),
            # HV keywords (substring)
            ("HIGH_VOLTAGE", True),
            ("high_voltage", True),
            ("MAINS", True),
            ("mains_return", True),
            ("LINE", True),
            ("NEUTRAL", True),
            ("PRIMARY", True),
            ("HOT", True),
            ("L1", True),
            ("L2", True),
            ("L3", True),
            ("PHASE", True),
            ("VBUS", True),
            ("B+", True),
            ("b+", True),
            # AC / HV regex boundaries
            ("AC", True),
            ("ac", True),
            ("AC1", True),
            ("AC_", True),
            ("_AC", True),
            ("_AC_", True),
            ("HV", True),
            ("hv", True),
            ("HV1", True),
            ("HV_", True),
            ("_HV", True),
            ("HV_BUS", True),
            # Should NOT match
            ("TRACE", False),
            ("SPACE", False),
            ("FACTORY", False),
            ("ACH", False),
            ("CAC", False),
            ("HIVE", False),
            ("BEHAVE", False),
            # HV as part of word should NOT match
            ("XHVX", False),
        ],
    )
    def test_hv_detection(self, net_name: str, expected: bool):
        """HV detection should classify known patterns correctly."""
        assert _is_high_voltage_net(net_name) is expected

    @pytest.mark.parametrize(
        "net_name",
        [
            "\N{GREEK CAPITAL LETTER ALPHA}\N{GREEK CAPITAL LETTER BETA}",
            "\N{CYRILLIC CAPITAL LETTER A}\N{CYRILLIC CAPITAL LETTER BE}",
            "\N{LATIN SMALL LETTER A WITH ACUTE}",
            "\u4e2d\u6587",  # Chinese characters
            "\u3042\u3044",  # Hiragana
            "net\N{EN DASH}name",  # en-dash
        ],
    )
    def test_non_ascii_names_do_not_crash(self, net_name: str):
        """Non-ASCII net names must not cause a crash or exception."""
        result = _is_high_voltage_net(net_name)
        assert isinstance(result, bool)

    # -- HV keywords with boundary punctuation -------------------------

    @pytest.mark.parametrize(
        "net_name, expected",
        [
            ("AC_L", True),
            ("AC_N", True),
            ("HV_BUS", True),
            ("HV_GATE", True),
            # AC/HV immediately followed by non-word char
            ("AC-", False),   # hyphen is not [\d_] nor end
            ("AC.", False),
            ("AC:", False),
        ],
    )
    def test_ac_hv_punctuation_boundaries(self, net_name: str, expected: bool):
        """AC/HV followed by non-digit, non-underscore, non-end should not match."""
        assert _is_high_voltage_net(net_name) is expected


# ===================================================================
# 4. Coordinate boundaries
# ===================================================================


class TestCoordinateBoundaries:
    """Functions that consume coordinates with boundary values."""

    # -- extract_segments -----------------------------------------------

    @pytest.mark.parametrize("coord", COORD_ZERO + COORD_NEGATIVE)
    def test_extract_segments_valid_coords(self, coord: tuple[float, float]):
        """Normal and negative coordinates extract cleanly."""
        route = _make_route("NET", [(0.0, 0.0), coord])
        segs = _extract_segments(route)
        assert len(segs) == 1
        x1, y1, x2, y2, layer = segs[0]
        assert layer == "F.Cu"
        assert x1 == 0.0 and y1 == 0.0
        assert x2 == coord[0] and y2 == coord[1]

    @pytest.mark.parametrize("coord", COORD_NAN)
    def test_extract_segments_nan_coords(self, coord: tuple[float, float]):
        """NaN coordinates are silently skipped (no segments extracted)."""
        route = _make_route("NET", [(0.0, 0.0), coord])
        segs = _extract_segments(route)
        assert len(segs) == 0

    @pytest.mark.parametrize("coord", COORD_INF)
    def test_extract_segments_inf_coords(self, coord: tuple[float, float]):
        """Infinite coordinates are silently skipped (no segments extracted)."""
        route = _make_route("NET", [(0.0, 0.0), coord])
        segs = _extract_segments(route)
        assert len(segs) == 0

    # -- point_to_segment_distance -------------------------------------

    @pytest.mark.parametrize("px,py", COORD_ZERO + COORD_NEGATIVE)
    def test_point_to_segment_valid(self, px: float, py: float):
        """Distance from a valid point to a valid segment is computed."""
        d = _point_to_segment_distance(px, py, 0.0, 0.0, 10.0, 0.0)
        assert isinstance(d, float)
        assert d >= 0.0 or math.isnan(d)

    @pytest.mark.parametrize("px,py", COORD_NAN)
    def test_point_to_segment_nan_point(self, px: float, py: float):
        """Distance from a NaN point to a segment does not crash."""
        d = _point_to_segment_distance(px, py, 0.0, 0.0, 10.0, 0.0)
        # NaN point produces NaN distance
        assert math.isnan(d)

    @pytest.mark.parametrize("px,py", COORD_INF)
    def test_point_to_segment_inf_point(self, px: float, py: float):
        """Distance from an infinite point to a segment does not crash."""
        d = _point_to_segment_distance(px, py, 0.0, 0.0, 10.0, 0.0)
        # inf point produces inf distance
        assert math.isinf(d)

    def test_point_to_segment_zero_length_segment(self):
        """Distance to a zero-length segment (point) is point-to-point."""
        d = _point_to_segment_distance(3.0, 4.0, 1.0, 1.0, 1.0, 1.0)
        assert d == pytest.approx(math.hypot(2.0, 3.0))

    def test_point_to_segment_nan_segment_endpoint(self):
        """Segment with one NaN endpoint does not crash."""
        d = _point_to_segment_distance(5.0, 0.0, 0.0, 0.0, float("nan"), 0.0)
        # The NaN endpoint arm evaluates to NaN and is ignored by < check
        assert d >= 0.0 or math.isnan(d)

    # -- segment_to_segment_info ---------------------------------------

    @pytest.mark.parametrize("x2,y2", COORD_ZERO + COORD_NEGATIVE)
    def test_segment_to_segment_valid(self, x2: float, y2: float):
        """Valid segment pairs produce a distance."""
        dist, p1, p2 = _segment_to_segment_info(
            0.0, 0.0, x2, y2,
            5.0, 5.0, 15.0, 5.0,
        )
        assert isinstance(dist, float)
        assert dist >= 0.0

    @pytest.mark.parametrize("x2,y2", COORD_NAN)
    def test_segment_to_segment_nan(self, x2: float, y2: float):
        """Segment with NaN endpoint does not crash segment-to-segment."""
        dist, p1, p2 = _segment_to_segment_info(
            0.0, 0.0, x2, y2,
            5.0, 5.0, 15.0, 5.0,
        )
        # The NaN segment contributes NaN distances that are skipped
        assert not math.isnan(dist)  # falls back to finite endpoint

    @pytest.mark.parametrize("x2,y2", COORD_INF)
    def test_segment_to_segment_inf(self, x2: float, y2: float):
        """Segment with inf endpoint does not crash segment-to-segment."""
        dist, p1, p2 = _segment_to_segment_info(
            0.0, 0.0, x2, y2,
            5.0, 5.0, 15.0, 5.0,
        )
        # inf endpoint → distance is inf (ignored) → falls back
        assert dist >= 0.0 or math.isinf(dist)

    def test_segment_intersection(self):
        """Crossing segments report distance 0."""
        dist, p1, p2 = _segment_to_segment_info(
            0.0, 0.0, 10.0, 10.0,
            0.0, 10.0, 10.0, 0.0,
        )
        assert dist == pytest.approx(0.0)

    # -- verify_creepage with boundary route coordinates ----------------

    def test_verify_creepage_zero_coords(self):
        """HV and LV routes at (0,0) should still not crash."""
        hv = _make_route("AC_L", [(0.0, 0.0), (0.0, 0.0)])
        lv = _make_route("SIG1", [(0.0, 0.0), (0.0, 0.0)])
        report = verify_creepage(_make_results(hv, lv))
        # Both paths are zero-length points at the same location
        assert report.total_checks == 1
        # Distance is 0 → violation
        assert report.violation_count >= 0  # at minimum doesn't crash

    @pytest.mark.parametrize("coord", COORD_NAN)
    def test_verify_creepage_nan_route_coords(self, coord: tuple[float, float]):
        """verify_creepage with NaN in route coordinates must not crash."""
        hv = _make_route("AC_L", [(0.0, 0.0), coord])
        lv = _make_route("SIG1", [(5.0, 5.0), (15.0, 5.0)])
        report = verify_creepage(_make_results(hv, lv))
        assert report.total_checks >= 0  # no crash

    @pytest.mark.parametrize("coord", COORD_INF)
    def test_verify_creepage_inf_route_coords(self, coord: tuple[float, float]):
        """verify_creepage with inf in route coordinates must not crash."""
        hv = _make_route("AC_L", [(0.0, 0.0), coord])
        lv = _make_route("SIG1", [(5.0, 5.0), (15.0, 5.0)])
        report = verify_creepage(_make_results(hv, lv))
        assert report.total_checks >= 0  # no crash

    def test_verify_creepage_negative_coords(self):
        """Negative coordinates are valid in PCB space."""
        hv = _make_route("AC_L", [(-5.0, -5.0), (-15.0, -5.0)])
        lv = _make_route("SIG1", [(0.0, 0.0), (10.0, 0.0)])
        report = verify_creepage(_make_results(hv, lv))
        assert report.total_checks == 1
        assert isinstance(report.violation_count, int)


# ===================================================================
# 5. Voltage bracket threshold boundaries
# ===================================================================


# (voltage, expected_creepage_mm)
_BRACKET_CASES = [
    # ≤ 15 V → 0.13
    (0.0, 0.13),
    (15.0, 0.13),
    # 16-30 V → 0.25
    (15.000001, 0.25),
    (30.0, 0.25),
    # 31-50 V → 0.5
    (30.000001, 0.5),
    (50.0, 0.5),
    # 51-100 V → 0.8
    (50.000001, 0.8),
    (100.0, 0.8),
    # 101-150 V → 1.25
    (100.000001, 1.25),
    (150.0, 1.25),
    # 151-170 V → 1.6
    (150.000001, 1.6),
    (170.0, 1.6),
    # 171-250 V → 3.2
    (170.000001, 3.2),
    (250.0, 3.2),
    # 251-300 V → 6.4
    (250.000001, 6.4),
    (300.0, 6.4),
    # 301-600 V → 8.0
    (300.000001, 8.0),
    (600.0, 8.0),
    # 601-1000 V → 12.0 (and > 600)
    (600.000001, 12.0),
    (1000.0, 12.0),
]


class TestBracketThresholds:
    """Required distance at each IPC-2221 voltage bracket transition."""

    @pytest.mark.parametrize("voltage, expected", _BRACKET_CASES)
    def test_bracket_lookup(self, voltage: float, expected: float):
        """Voltage exactly at or just above each boundary maps correctly."""
        result = _calculate_required_creepage(voltage)
        assert result == pytest.approx(expected)

    # -- Double-check with the shared helpers --------------------------

    def test_15v_is_lowest_bracket(self):
        """15 V is still the 0.13 mm bracket."""
        from dfm_boundary_constants import exactly_at, just_above

        assert _calculate_required_creepage(exactly_at(15.0)) == pytest.approx(0.13)
        assert _calculate_required_creepage(just_above(15.0)) == pytest.approx(0.25)

    def test_600v_is_8mm_not_12mm(self):
        """600 V is the 8.0 mm bracket, 601 V is 12.0 mm."""
        from dfm_boundary_constants import exactly_at, just_above

        assert _calculate_required_creepage(exactly_at(600.0)) == pytest.approx(8.0)
        assert _calculate_required_creepage(just_above(600.0)) == pytest.approx(12.0)

    def test_301v_is_8mm_bracket(self):
        """301 V enters the 8.0 mm bracket (not 6.4 mm)."""
        assert _calculate_required_creepage(301.0) == pytest.approx(8.0)


# ===================================================================
# 6. Empty input / single-net
# ===================================================================


class TestEmptyInput:
    """``verify_creepage`` with no routes or only one net."""

    def test_zero_routes(self):
        """No routes → no checks, no violations."""
        results = RoutingResults(compiled_routes={}, failed_nets=[])
        report = verify_creepage(results)
        assert report.total_checks == 0
        assert report.violation_count == 0
        assert report.pass_rate == 100.0

    def test_single_non_hv_net(self):
        """A lone non-HV net triggers zero checks."""
        route = _make_route("SIG1", [(0.0, 0.0), (10.0, 10.0)])
        report = verify_creepage(_make_results(route))
        assert report.total_checks == 0
        assert report.violation_count == 0

    def test_single_hv_net_no_pair(self):
        """A lone HV net has no other route to compare against."""
        route = _make_route("AC_L", [(0.0, 0.0), (10.0, 10.0)])
        report = verify_creepage(_make_results(route))
        # The HV net is recognised but there is no other net to pair with
        assert report.total_checks == 0
        assert report.violation_count == 0

    def test_two_non_hv_nets(self):
        """Two non-HV nets → no HV detected → zero checks."""
        r1 = _make_route("SIG1", [(0.0, 0.0), (10.0, 0.0)])
        r2 = _make_route("SIG2", [(0.0, 5.0), (10.0, 5.0)])
        report = verify_creepage(_make_results(r1, r2))
        assert report.total_checks == 0
        assert report.violation_count == 0

    def test_hv_net_with_default_creepage_zero(self):
        """Single HV + single LV with default_creepage=0 — no violation."""
        hv = _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)])
        lv = _make_route("SIG1", [(0.0, 0.5), (10.0, 0.5)])
        report = verify_creepage(_make_results(hv, lv), default_creepage=0.0)
        assert report.total_checks == 1
        assert report.violation_count == 0
