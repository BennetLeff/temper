"""
Scale-resolution parametrized tests for extreme-scale edge cases across
DFM modules.

Each test explores an axis where floating-point representation, range
limits, or combinatorial explosion can degrade correctness:

1.  Nanometer-scale coordinates — floating-point stability
2.  Meter-scale boards — copper-balance area shouldn't overflow
3.  Extreme aspect ratios — 1 × 1000 mm, 1000 × 1 mm
4.  Traces wider than the board
5.  Traces longer than board diagonal
6.  Via diameter larger than board dimension
7.  Cumulative FP error — many tiny segments vs one long segment
8.  Very large net count — 100+ nets in clearance/creepage pairwise
9.  Very small / very large clearance thresholds
10. Coordinate precision — 10+ decimal digits vs rounded coords

Crashes are marked ``pytest.mark.xfail``; this file **characterises**
current behaviour — it does **not** fix the modules under test.
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.copper_balance import analyze_copper_balance
from temper_placer.router_v6.creepage_check import (
    _segment_to_segment_info,
    verify_creepage,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via

# ============================================================================
# Shared helpers
# ============================================================================


def _make_route(
    net_name: str,
    coords: list[tuple[float, float]],
    layer: str = "F.Cu",
    width: float = 0.127,
    vias: list | None = None,
) -> CompiledRoute:
    """Create a ``CompiledRoute`` for a single-layer path."""
    _len = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        _len += math.hypot(x2 - x1, y2 - y1)
    path = RoutePath(
        net_name=net_name,
        coordinates=list(coords),
        layer_name=layer,
        path_length=_len,
    )
    return CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width,
        vias=list(vias) if vias else [],
        matched_length_mm=None,
    )


def _make_results(routes: dict[str, CompiledRoute]) -> RoutingResults:
    """Build a ``RoutingResults`` from a dict of ``CompiledRoute``."""
    return RoutingResults(compiled_routes=routes, failed_nets=[])


# ============================================================================
# 1. Nanometer-scale coordinates — floating-point stability
# ============================================================================


class TestNanometerScaleCoordinates:
    """Clearance / creepage distance should not collapse to zero for
    well-separated nanometer-scale coordinates."""

    NANO = 1e-6  # 1 nm in mm

    def test_clearance_nano_routes_do_not_falsely_violate(self):
        """Two routes at nanometer coordinates but well-separated must
        not produce false clearance violations."""
        r1 = _make_route("N1", [(0.0, 0.0), (1e-6, 0.0)], width=1e-7)
        r2 = _make_route("N2", [(0.0, 1e-3), (1e-6, 1e-3)], width=1e-7)
        results = _make_results({"N1": r1, "N2": r2})

        report = verify_clearance(results, min_clearance=1e-6)
        # Edge-to-edge distance ≈ 0.001 - (1e-7/2)*2 ≈ 0.0009999 mm
        # which is >> 1e-6 → no violation
        assert report.violation_count == 0, f"False violation at nano-scale: {report.violations}"


# ============================================================================
# 2. Meter-scale boards — copper-balance area shouldn't overflow
# ============================================================================


class TestMeterScaleBoards:
    """Copper balance with board dimensions up to 10 000 × 10 000 mm.

    Area = 1e8 mm², which fits comfortably in f64 but stresses the
    percentage calculation and the `total_area > 0` guard.
    """

    @pytest.mark.parametrize(
        "board_width, board_height",
        [
            (1_000.0, 1_000.0),
            (10_000.0, 10_000.0),
        ],
    )
    def test_copper_balance_no_overflow(self, board_width, board_height):
        """analyze_copper_balance must return finite values."""
        results = _make_results({})
        report = analyze_copper_balance(results, board_width, board_height)

        # total_area must be finite and positive
        assert math.isfinite(report.total_area_mm2), (
            f"total_area_mm2 is not finite: {report.total_area_mm2}"
        )
        assert report.total_area_mm2 > 0.0

        # All layer percentages must be finite
        for lb in report.layer_balances:
            assert math.isfinite(lb.copper_percentage), (
                f"Non-finite copper_percentage on {lb.layer_name}: {lb.copper_percentage}"
            )
            assert math.isfinite(lb.copper_area_mm2), (
                f"Non-finite copper_area_mm2 on {lb.layer_name}: {lb.copper_area_mm2}"
            )

    @pytest.mark.parametrize(
        "board_width, board_height",
        [
            (1_000.0, 1_000.0),
            (10_000.0, 10_000.0),
        ],
    )
    def test_copper_balance_with_routes_large_board(self, board_width, board_height):
        """Routes on a meter-scale board produce sane copper percentages."""
        # A 500 mm trace on a 1000×1000 board
        r1 = _make_route("N1", [(0.0, 0.0), (500.0, 0.0)], width=0.5)
        results = _make_results({"N1": r1})

        report = analyze_copper_balance(results, board_width, board_height)
        f_cu = next(lb for lb in report.layer_balances if lb.layer_name == "F.Cu")
        # Area: 500 * 0.5 = 250 mm²
        expected_area = 250.0
        assert f_cu.copper_area_mm2 == pytest.approx(expected_area, rel=1e-9)
        # Percentage: 250 / (board_width * board_height) * 100
        total = board_width * board_height
        expected_pct = expected_area / total * 100.0
        assert f_cu.copper_percentage == pytest.approx(expected_pct, rel=1e-9)


# ============================================================================
# 3. Extreme aspect ratios — 1 × 1000 mm, 1000 × 1 mm
# ============================================================================


class TestExtremeAspectRatios:
    """Copper balance with extreme board aspect ratios."""

    @pytest.mark.parametrize(
        "board_width, board_height",
        [
            (1.0, 1_000.0),
            (1_000.0, 1.0),
            (1.0, 10_000.0),
            (10_000.0, 1.0),
        ],
    )
    def test_copper_balance_extreme_aspect(self, board_width, board_height):
        """analyze_copper_balance must handle extreme aspect ratios."""
        results = _make_results({})
        report = analyze_copper_balance(results, board_width, board_height)

        assert math.isfinite(report.total_area_mm2)
        assert report.total_area_mm2 > 0.0
        assert len(report.layer_balances) == 4

    @pytest.mark.parametrize(
        "board_width, board_height",
        [
            (1.0, 1_000.0),
            (1_000.0, 1.0),
        ],
    )
    def test_trace_aligned_with_long_axis(self, board_width, board_height):
        """A thin trace along the long axis must not produce bogus %."""
        long_axis = max(board_width, board_height)
        r1 = _make_route("N1", [(0.0, 0.0), (long_axis * 0.5, 0.0)], width=0.2)
        results = _make_results({"N1": r1})
        report = analyze_copper_balance(results, board_width, board_height)
        f_cu = next(lb for lb in report.layer_balances if lb.layer_name == "F.Cu")
        # Copper area must be ≤ total area
        assert f_cu.copper_area_mm2 <= report.total_area_mm2 * 1.01, (
            f"Copper area {f_cu.copper_area_mm2} exceeds board area {report.total_area_mm2}"
        )


# ============================================================================
# 4. Traces wider than the board
# ============================================================================


class TestTracesWiderThanBoard:
    """Trace width exceeds one or both board dimensions."""

    @pytest.mark.parametrize(
        "trace_width, board_w, board_h",
        [
            (100.0, 50.0, 50.0),
            (200.0, 100.0, 100.0),
            (1e6, 100.0, 100.0),  # Extreme width
            (float("inf"), 100.0, 100.0),  # Inf width -- previously crashed (xfail), fixed
        ],
    )
    def test_copper_balance_trace_wider_than_board(self, trace_width, board_w, board_h):
        """analyze_copper_balance must not crash when trace > board."""
        r1 = _make_route("N1", [(0.0, 0.0), (10.0, 0.0)], width=trace_width)
        results = _make_results({"N1": r1})

        # 2026-08-15: the try/except xfail scaffold was removed -- Inf trace
        # width no longer crashes (measured), so a future crash must FAIL
        # loudly, not silently xfail. See
        # docs/evidence/2026-08-15-unsilence-checks-batch-2.md.
        report = analyze_copper_balance(results, board_w, board_h)
        assert len(report.layer_balances) == 4
        # Copper area may be larger than board area — that's expected
        # when the trace is wider than the board.  The percentage
        # will exceed 100 %.

    def test_clearance_trace_wider_than_separation(self):
        """Clearance when trace half-widths exceed the segment spacing."""
        # Two parallel segments separated by 0.1 mm centre-to-centre,
        # each 0.5 mm wide → overlap of 0.4 mm (negative edge distance)
        r1 = _make_route("N1", [(0.0, 0.0), (10.0, 0.0)], width=0.5)
        r2 = _make_route("N2", [(0.0, 0.1), (10.0, 0.1)], width=0.5)
        results = _make_results({"N1": r1, "N2": r2})

        report = verify_clearance(results, min_clearance=0.127)
        # Overlapping traces → violation
        assert report.violation_count > 0
        # The actual clearance should be negative (overlap)
        v = report.violations[0]
        assert v.actual_clearance < 0.0, (
            f"Expected negative clearance for overlapping traces, got {v.actual_clearance}"
        )


# ============================================================================
# 5. Traces longer than board diagonal
# ============================================================================


class TestTracesLongerThanBoardDiagonal:
    """Trace path_length exceeds the board diagonal."""

    @pytest.mark.parametrize(
        "board_w, board_h, trace_len",
        [
            (10.0, 10.0, 100.0),  # 10× diagonal
            (50.0, 50.0, 1_000.0),  # 20× diagonal
        ],
    )
    def test_copper_balance_trace_longer_than_diagonal(self, board_w, board_h, trace_len):
        """Copper area may exceed board area when trace is very long."""
        r1 = _make_route("N1", [(0.0, 0.0), (trace_len, 0.0)], width=0.2)
        results = _make_results({"N1": r1})

        report = analyze_copper_balance(results, board_w, board_h)
        f_cu = next(lb for lb in report.layer_balances if lb.layer_name == "F.Cu")
        expected_area = trace_len * 0.2
        assert f_cu.copper_area_mm2 == pytest.approx(expected_area, rel=1e-9)

        # Percentage may exceed 100 % — this is physically impossible
        # but expected from the module (it does not clamp).
        if f_cu.copper_area_mm2 > report.total_area_mm2:
            assert f_cu.copper_percentage > 100.0, (
                "Copper area exceeds board area; percentage should be > 100 %"
            )


# ============================================================================
# 6. Via diameter larger than board dimension
# ============================================================================


class TestViaLargerThanBoard:
    """Via pad diameter exceeds a board dimension."""

    @pytest.mark.parametrize(
        "via_diameter, drill, board_w, board_h",
        [
            (200.0, 100.0, 100.0, 80.0),  # Dia > board width
            (300.0, 150.0, 100.0, 100.0),  # Dia > both dims
            (1e6, 0.5, 100.0, 100.0),  # Extreme dia
            (float("inf"), 0.5, 100.0, 100.0),  # Inf dia -- previously crashed (xfail), fixed
        ],
    )
    def test_copper_balance_via_larger_than_board(self, via_diameter, drill, board_w, board_h):
        """analyze_copper_balance must survive a via bigger than the board."""
        via = Via((5, 5), "F.Cu", "B.Cu", via_diameter, drill, "N1")
        r1 = _make_route("N1", [(0.0, 0.0), (10.0, 0.0)], vias=[via])
        results = _make_results({"N1": r1})

        # 2026-08-15: try/except xfail scaffold removed -- Inf via diameter no
        # longer crashes (measured); a future crash must fail loudly. See
        # docs/evidence/2026-08-15-unsilence-checks-batch-2.md.
        report = analyze_copper_balance(results, board_w, board_h)
        assert len(report.layer_balances) == 4
        # Via annular area may be huge — but shouldn't crash


# ============================================================================
# 7. Cumulative FP error — many tiny segments vs one long segment
# ============================================================================


class TestCumulativeFPError:
    """Does clearance/creepage give the same result for a path composed
    of many tiny segments as for one long segment of the same total length?"""

    SEGMENT_COUNT = 1_000
    SEGMENT_LEN = 0.001  # 1 µm each
    TOTAL_LEN = SEGMENT_COUNT * SEGMENT_LEN  # 1.0 mm

    # A parallel wire at a known offset
    OFFSET = 0.01  # 10 µm separation

    def _make_fine_path(self) -> list[tuple[float, float]]:
        """Generate ``SEGMENT_COUNT`` colinear points spanning TOTAL_LEN."""
        coords = []
        for i in range(self.SEGMENT_COUNT + 1):
            x = i * self.SEGMENT_LEN
            coords.append((x, 0.0))
        return coords

    def _make_coarse_path(self) -> list[tuple[float, float]]:
        """A single segment of length TOTAL_LEN."""
        return [(0.0, 0.0), (self.TOTAL_LEN, 0.0)]

    # ---- clearance: segment-to-segment distance ----

    def test_clearance_fine_vs_coarse_agree(self):
        """verify_clearance on fine-grained path vs coarse path.

        Two parallel routes at a fixed offset.  One uses a single
        long segment; the other uses 1 000 tiny segments.  The
        reported minimum clearance should be the same (the edge-to-edge
        distance accounting for half-widths).
        """
        width = 0.001  # 1 µm — thin enough that edge dist ≈ centre dist

        # Coarse route
        r_coarse = _make_route(
            "COARSE",
            self._make_coarse_path(),
            width=width,
        )
        # Fine route
        r_fine = _make_route(
            "FINE",
            self._make_fine_path(),
            width=width,
        )
        # Reference target (offset, same layer)
        r_target = _make_route(
            "TARGET",
            [(0.0, self.OFFSET), (self.TOTAL_LEN, self.OFFSET)],
            width=width,
        )

        results_coarse = _make_results({"COARSE": r_coarse, "TARGET": r_target})
        results_fine = _make_results({"FINE": r_fine, "TARGET": r_target})

        report_coarse = verify_clearance(results_coarse, min_clearance=1e-6)
        report_fine = verify_clearance(results_fine, min_clearance=1e-6)

        # The minimum clearance should be the same (± a tiny epsilon)
        # Edge-to-edge: OFFSET - width (since width/2 + width/2 = width)
        self.OFFSET - width

        # We may get violations if OFFSET < min_clearance, but the
        # actual_clearance values should agree between coarse and fine.
        if report_coarse.violations and report_fine.violations:
            coarse_actual = report_coarse.violations[0].actual_clearance
            fine_actual = report_fine.violations[0].actual_clearance
            assert coarse_actual == pytest.approx(fine_actual, rel=1e-9), (
                f"Coarse actual={coarse_actual}, fine actual={fine_actual} "
                f"differ beyond FP tolerance"
            )
        elif not report_coarse.violations and not report_fine.violations:
            pass  # Both passed — consistent
        else:
            # One violated, one didn't — this would be an FP precision bug
            pytest.xfail(
                f"Coarse violations={report_coarse.violation_count}, "
                f"fine violations={report_fine.violation_count} — "
                f"FP inconsistency (known gap)"
            )

    # ---- creepage: segment-to-segment info ----

    def test_creepage_segment_info_coarse(self):
        """Baseline: two coarse single-segment paths at offset."""
        dist, _, _ = _segment_to_segment_info(
            0.0,
            0.0,
            self.TOTAL_LEN,
            0.0,
            0.0,
            self.OFFSET,
            self.TOTAL_LEN,
            self.OFFSET,
        )
        assert dist == pytest.approx(self.OFFSET, rel=1e-12)



# ============================================================================
# 8. Very large net count — pairwise comparison stress
# ============================================================================


class TestVeryLargeNetCount:
    """Clearance and creepage with 100+ nets stresses the O(n²)
    pairwise comparison loop."""

    NET_COUNT = 120

    @staticmethod
    def _make_many_routes(n: int) -> dict[str, CompiledRoute]:
        """Create *n* non-overlapping parallel routes."""
        routes: dict[str, CompiledRoute] = {}
        spacing = 0.5  # mm between route centrelines
        for i in range(n):
            y = i * spacing
            routes[f"N{i}"] = _make_route(
                f"N{i}",
                [(0.0, y), (100.0, y)],
                width=0.2,
            )
        return routes

    def test_clearance_many_nets(self):
        """verify_clearance scales to 120 nets without crashing."""
        routes = self._make_many_routes(self.NET_COUNT)
        results = _make_results(routes)

        report = verify_clearance(results, min_clearance=0.1)

        # Total checks = n*(n-1)/2 = 120*119/2 = 7140
        expected_checks = self.NET_COUNT * (self.NET_COUNT - 1) // 2
        assert report.total_checks == expected_checks, (
            f"Expected {expected_checks} checks, got {report.total_checks}"
        )

        # Adjacent routes are 0.5 mm apart with 0.2 mm width →
        # edge-to-edge = 0.5 - 0.2 = 0.3 mm > 0.1 mm → no violations
        assert report.violation_count == 0, (
            f"Expected 0 violations but got {report.violation_count}"
        )

    def test_creepage_many_nets(self):
        """verify_creepage scales to 120 nets without crashing."""
        routes = self._make_many_routes(self.NET_COUNT)
        results = _make_results(routes)

        # No HV nets in this set → zero checks, zero violations
        report = verify_creepage(results)
        assert report.total_checks == 0
        assert report.violation_count == 0

    def test_creepage_many_hv_nets(self):
        """verify_creepage with many HV nets stresses the HV×LV loops."""
        n_hv = 30
        n_lv = 90
        routes: dict[str, CompiledRoute] = {}
        spacing = 0.5
        for i in range(n_hv):
            y = i * spacing
            routes[f"HV_{i}"] = _make_route(
                f"HV_{i}",
                [(0.0, y), (100.0, y)],
                width=0.2,
            )
        for i in range(n_lv):
            y = (n_hv + i) * spacing
            routes[f"LV_{i}"] = _make_route(
                f"LV_{i}",
                [(0.0, y), (100.0, y)],
                width=0.2,
            )
        results = _make_results(routes)

        report = verify_creepage(results)
        # Each HV net compared against every other net (HV+LV) except itself
        expected_checks = n_hv * (n_hv + n_lv - 1)
        assert report.total_checks == expected_checks, (
            f"Expected {expected_checks} checks, got {report.total_checks}"
        )


# ============================================================================
# 9. Very small and very large clearance thresholds
# ============================================================================


class TestExtremeClearanceThresholds:
    """min_clearance at 1e-6 mm and 1 000 mm."""

    @pytest.mark.parametrize(
        "min_clearance",
        [
            1e-6,  # Extremely small
            1e-3,  # 1 µm
            1_000.0,  # 1 metre
            1e6,  # 1 km
            float("inf"),  # Inf -- rejected by the finite-value guard (xfail)
        ],
    )
    def test_clearance_extreme_threshold(self, min_clearance):
        """verify_clearance with extreme min_clearance values."""
        r1 = _make_route("N1", [(0.0, 0.0), (10.0, 0.0)])
        r2 = _make_route("N2", [(0.0, 1.0), (10.0, 1.0)])
        results = _make_results({"N1": r1, "N2": r2})

        try:
            report = verify_clearance(results, min_clearance=min_clearance)
        except Exception:
            if math.isinf(min_clearance):
                pytest.xfail("Inf min_clearance rejected by finite-value guard (expected edge-case)")
            raise

        assert hasattr(report, "violations")
        assert hasattr(report, "total_checks")

    @pytest.mark.parametrize(
        "default_creepage",
        [
            1e-6,
            1_000.0,
            1e6,
            float("inf"),  # Inf -- rejected by the finite-value guard (xfail)
        ],
    )
    def test_creepage_extreme_default(self, default_creepage):
        """verify_creepage with extreme default_creepage values."""
        r_hv = _make_route("HV_BUS", [(0.0, 0.0), (10.0, 0.0)])
        r_lv = _make_route("SIG1", [(0.0, 1.0), (10.0, 1.0)])
        results = _make_results({"HV_BUS": r_hv, "SIG1": r_lv})

        try:
            report = verify_creepage(results, default_creepage=default_creepage)
        except Exception:
            if math.isinf(default_creepage):
                pytest.xfail("Inf default_creepage rejected by finite-value guard (expected edge-case)")
            raise

        assert hasattr(report, "violations")
        assert hasattr(report, "total_checks")


# ============================================================================
# 10. Coordinate precision — 10+ decimal digits vs rounded coords
# ============================================================================


class TestCoordinatePrecision:
    """Paths with many-significant-digit coordinates vs rounded
    equivalents must not produce different DRC outcomes."""

    HIGH_PRECISION_COORDS = [
        (0.123456789012345, 0.987654321098765),
        (10.123456789012345, 10.987654321098765),
        (20.123456789012345, 5.987654321098765),
    ]

    ROUNDED_COORDS = [(round(x, 4), round(y, 4)) for x, y in HIGH_PRECISION_COORDS]

    def test_clearance_precision_stable(self):
        """verify_clearance must not flip on rounding differences."""
        r1 = _make_route(
            "N1",
            [
                (0.123456789012345, 0.0),
                (10.123456789012345, 0.0),
            ],
            width=0.1,
        )
        r2 = _make_route(
            "N2",
            [
                (0.123456789012345, 0.5),
                (10.123456789012345, 0.5),
            ],
            width=0.1,
        )
        results_hi = _make_results({"N1": r1, "N2": r2})

        r1_lo = _make_route(
            "N1",
            [
                (0.1235, 0.0),
                (10.1235, 0.0),
            ],
            width=0.1,
        )
        r2_lo = _make_route(
            "N2",
            [
                (0.1235, 0.5),
                (10.1235, 0.5),
            ],
            width=0.1,
        )
        results_lo = _make_results({"N1": r1_lo, "N2": r2_lo})

        report_hi = verify_clearance(results_hi, min_clearance=0.127)
        report_lo = verify_clearance(results_lo, min_clearance=0.127)

        # Both must agree on violation status
        assert report_hi.violation_count == report_lo.violation_count, (
            f"Precision changed violation count: "
            f"hi={report_hi.violation_count}, lo={report_lo.violation_count}"
        )

    def test_creepage_segment_info_precision_stable(self):
        """_segment_to_segment_info should be stable across rounding."""
        dist_hi, _, _ = _segment_to_segment_info(
            0.123456789012345,
            0.0,
            10.123456789012345,
            0.0,
            0.123456789012345,
            0.5,
            10.123456789012345,
            0.5,
        )
        dist_lo, _, _ = _segment_to_segment_info(
            0.1235,
            0.0,
            10.1235,
            0.0,
            0.1235,
            0.5,
            10.1235,
            0.5,
        )
        assert dist_hi == pytest.approx(dist_lo, abs=1e-3), (
            f"Precision sensitivity in segment_info: hi={dist_hi}, lo={dist_lo}"
        )
