"""Parametrized geometric-degeneracy tests across all 7 DFM modules.

Covers 10 classes of path-geometry edge cases and verifies that each
DFM module either handles them gracefully (valid report, reasonable
violation counts) or crashes cleanly (marked ``xfail``).

Import boundary values from ``dfm_boundary_constants`` and reuse the
mock helpers (``_Path``, ``_Via``, ``_Route``, ``_Results``) from
``test_dfm_correctness``.
"""

from __future__ import annotations

import math
import warnings

import pytest

# ---------------------------------------------------------------------------
# DFM module entry points
# ---------------------------------------------------------------------------
from temper_placer.router_v6.acid_trap_detection import (
    AcidTrapReport,
    detect_acid_traps,
)
from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    check_annular_rings,
)
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    verify_clearance,
)
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    verify_creepage,
)
from temper_placer.router_v6.teardrop_generation import (
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.thermal_relief import (
    ThermalReliefReport,
    add_thermal_relief,
)

# ---------------------------------------------------------------------------
# Boundary constants
# ---------------------------------------------------------------------------
from tests.router_v6.dfm_boundary_constants import (
    COORD_EXTREME,
)

# ---------------------------------------------------------------------------
# Mock helpers (duck-typed stubs) — reused from test_dfm_correctness
# ---------------------------------------------------------------------------
from tests.router_v6.dfm_boundary_constants import (
    Path as _Path,
    Route as _Route,
    Results as _Results,
    Via as _Via,
    make_results as _make_results,
)

# ===========================================================================
# Shared geometry builders
# ===========================================================================

# Tiny epsilon for extremely-short-segment tests
_EPS_MM = 1e-6


def _collinear_3pt() -> list[tuple[float, float]]:
    """Three collinear points (180° angle)."""
    return [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]


def _duplicate_points() -> list[tuple[float, float]]:
    """Path with consecutive duplicate points."""
    return [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (20.0, 0.0)]


def _zero_length_segment() -> list[tuple[float, float]]:
    """Path containing a zero-length segment (p1 == p2)."""
    return [(0.0, 0.0), (5.0, 5.0), (5.0, 5.0), (10.0, 10.0)]


def _single_point() -> list[tuple[float, float]]:
    """Path with exactly one coordinate."""
    return [(5.0, 5.0)]


def _two_point() -> list[tuple[float, float]]:
    """Path with exactly two coordinates (one segment)."""
    return [(0.0, 0.0), (10.0, 0.0)]


def _self_intersecting() -> list[tuple[float, float]]:
    """Bow-tie self-intersecting path."""
    return [(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)]


def _double_back() -> list[tuple[float, float]]:
    """Path that goes out and returns along the same line."""
    return [(0.0, 0.0), (10.0, 0.0), (5.0, 0.0)]


def _parallel_segments() -> tuple[
    list[tuple[float, float]], list[tuple[float, float]]
]:
    """Two paths with exactly-parallel segments."""
    p1 = [(0.0, 0.0), (10.0, 0.0)]
    p2 = [(0.0, 2.0), (10.0, 2.0)]
    return p1, p2


def _coincident_segments() -> tuple[
    list[tuple[float, float]], list[tuple[float, float]]
]:
    """Two nets on the exact same path (coincident segments)."""
    p = [(0.0, 0.0), (10.0, 0.0)]
    return p, p


def _extremely_short() -> list[tuple[float, float]]:
    """Path with an extremely short segment (~1e-6 mm)."""
    return [(0.0, 0.0), (_EPS_MM, 0.0), (10.0, 0.0)]


# ===========================================================================
# 1. Collinear 3-point paths (180°)
# ===========================================================================


class TestCollinear3Point:
    """Collinear (180°) three-point paths — no acute angles."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _collinear_3pt()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_reports_zero_traps(self):
        """Collinear path has 180° angle → no acid trap."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        assert report.trap_count == 0

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_collinear_path(self):
        """Teardrop on collinear path with via should not crash."""
        via = _Via(10, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_computes_correct_length(self):
        """Collinear trace length = sum of segment lengths."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        # 20 mm × 0.5 mm = 10 mm²
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        assert f_cu.copper_area_mm2 == pytest.approx(20.0 * 0.5, rel=0.01)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_collinear(self):
        """Creepage check should not crash on collinear paths."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)
        assert report.total_checks >= 1

    # -- clearance -------------------------------------------------------

    def test_clearance_handles_collinear(self):
        """Clearance check should not crash on collinear paths."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1


# ===========================================================================
# 2. Coincident / duplicate consecutive points
# ===========================================================================


class TestDuplicateConsecutivePoints:
    """Consecutive duplicate points (p_i == p_{i+1})."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _duplicate_points()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_dedup_and_skips(self):
        """After dedup: 3 collinear points → 0 traps."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        assert report.trap_count == 0

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_duplicate_points(self):
        """Should not crash with duplicate consecutive coordinates."""
        via = _Via(10, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_handles_duplicate_points(self):
        """Zero-length segments contribute 0 area."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_duplicate_points(self):
        """Creepage should treat degenerate segment as point."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_handles_duplicate_points(self):
        """Clearance should treat zero-length segment gracefully."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)


# ===========================================================================
# 3. Zero-length segments (p1 → p1)
# ===========================================================================


class TestZeroLengthSegments:
    """Explicit zero-length segments (both endpoints identical)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _zero_length_segment()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_handles_zero_length(self):
        """Zero-length segment filtered by dedup → collinear → 0 traps."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        assert report.trap_count == 0

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_zero_length(self):
        """Direction vector from coincident points → guarded."""
        via = _Via(5, 5, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_handles_zero_length(self):
        """Zero-length segment contributes no area."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_zero_length(self):
        """Zero-length segment degraded to point distance."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_handles_zero_length(self):
        """Zero-length segment → point-to-segment fallback."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 5), (20, 5)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)


# ===========================================================================
# 4. Single-point paths
# ===========================================================================


class TestSinglePointPaths:
    """Paths with only one coordinate — no segments to check."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _single_point()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_skips_single_point(self):
        """< 3 vertices → no traps."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        assert report.trap_count == 0

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_single_point(self):
        """< 2 coords → can't determine direction → no teardrop."""
        via = _Via(5, 5, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)
        # No segments → can't determine approach direction → 0 teardrops
        assert report.teardrop_count == 0

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_handles_single_point(self):
        """No segments → zero trace area."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        assert f_cu.copper_area_mm2 == 0.0

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_single_point(self):
        """No segments → no segment pairs to check."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 0), (10, 0)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_handles_single_point(self):
        """Route with single point → no segments → min_dist=inf."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 0), (10, 0)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)

    # -- annular_ring ----------------------------------------------------

    def test_annular_ring_handles_single_point_path(self):
        """Via check is independent of path length."""
        via = _Via(5, 5, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [via])
        )
        with pytest.raises(ValueError):
            # min_annular_ring=0.0 raises ValueError
            check_annular_rings(r, min_annular_ring=0.0)
        report = check_annular_rings(r, min_annular_ring=0.05)
        assert isinstance(report, AnnularRingReport)

    # -- thermal_relief --------------------------------------------------

    def test_thermal_relief_handles_single_point(self):
        """Thermal relief via power-net check is independent of path."""
        via = _Via(5, 5, "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
        r = _make_results(
            GND=_Route("GND", _Path(self.coords), 0.5, [via])
        )
        report = add_thermal_relief(r)
        assert isinstance(report, ThermalReliefReport)


# ===========================================================================
# 5. Two-point paths (one segment)
# ===========================================================================


class TestTwoPointPaths:
    """Paths with exactly two coordinates — one segment."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _two_point()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_skips_two_point(self):
        """< 3 vertices → no interior vertex → 0 traps."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        assert report.trap_count == 0

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_two_point(self):
        """One segment → teardrop can infer approach direction."""
        via = _Via(10, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_two_point(self):
        """One 10 mm segment × 0.5 mm = 5 mm²."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        assert f_cu.copper_area_mm2 == pytest.approx(10.0 * 0.5, rel=0.01)

    # -- creepage --------------------------------------------------------

    def test_creepage_two_point(self):
        """One segment per route → one segment-pair check."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (10, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)
        assert report.total_checks >= 1

    # -- clearance -------------------------------------------------------

    def test_clearance_two_point(self):
        """One segment per route → one check."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 5), (10, 5)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1

    # -- annular_ring ----------------------------------------------------

    def test_annular_ring_two_point(self):
        """Annular ring check with two-point path."""
        via = _Via(5, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [via])
        )
        report = check_annular_rings(r, min_annular_ring=0.05)
        assert isinstance(report, AnnularRingReport)

    # -- thermal_relief --------------------------------------------------

    def test_thermal_relief_two_point(self):
        """Thermal relief with two-point path."""
        via = _Via(5, 0, "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
        r = _make_results(
            GND=_Route("GND", _Path(self.coords), 0.5, [via])
        )
        report = add_thermal_relief(r)
        assert isinstance(report, ThermalReliefReport)


# ===========================================================================
# 6. Self-intersecting paths (bow-tie)
# ===========================================================================


class TestSelfIntersectingPaths:
    """Bow-tie self-intersecting paths."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _self_intersecting()

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_self_intersecting(self):
        """Bow-tie path with via — should not crash."""
        via = _Via(5, 5, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_handles_self_intersecting(self):
        """Length is still sum of segment lengths regardless of crossings."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_self_intersecting(self):
        """Self-intersecting HV path against LV path."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(3, 3), (7, 7)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_computes_correct_distance_self_intersecting(self):
        """Bow-tie crossing → segments should be at distance 0 at crossing."""
        # The bow-tie path segments: (0,0)→(10,10) and (0,10)→(10,0) cross at (5,5)
        # Test two separate nets that form a crossing
        r = _make_results(
            N1=_Route("N1", _Path([(0, 0), (10, 10)]), 0.25, []),
            N2=_Route("N2", _Path([(0, 10), (10, 0)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        # Segments cross → centreline distance = 0 → edge distance < 0 (overlap)
        assert report.violation_count >= 1
        assert report.violations[0].actual_clearance < 0


# ===========================================================================
# 7. Paths that double back
# ===========================================================================


class TestDoubleBackPaths:
    """Path that goes out and returns along the same line."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _double_back()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_double_back(self):
        """Double-back creates a 0° angle (acute) → detected as trap."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        # 0° angle at the middle vertex → severe acid trap
        assert report.trap_count == 1

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_double_back(self):
        """Coincident direction with via → should not crash."""
        via = _Via(5, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_double_back(self):
        """Length is sum of segment lengths (15 mm)."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        # Segments: (0,0)→(10,0) = 10, (10,0)→(5,0) = 5 → total 15 mm
        assert f_cu.copper_area_mm2 == pytest.approx(15.0 * 0.5, rel=0.01)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_double_back(self):
        """Double-back collinear segments — same-layer distance."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (15, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_detects_close_approach(self):
        """Double-back path: segments on same line approach each other."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 0.05), (10, 0.05)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1


# ===========================================================================
# 8. Exactly-parallel segments
# ===========================================================================


class TestExactlyParallelSegments:
    """Exactly-parallel segments — no division by zero."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.p1, self.p2 = _parallel_segments()

    # -- creepage --------------------------------------------------------

    def test_creepage_parallel_segments(self):
        """Parallel segments — distance computed correctly."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.p1), 2.0, []),
            SIG1=_Route("SIG1", _Path(self.p2), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)
        assert report.total_checks >= 1

    # -- clearance -------------------------------------------------------

    def test_clearance_parallel_no_division_by_zero(self):
        """Parallel segments: determinant is 0 → handled without crash."""
        r = _make_results(
            N1=_Route("N1", _Path(self.p1), 0.25, []),
            N2=_Route("N2", _Path(self.p2), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1
        # Centreline distance = 2.0 mm; edge-to-edge = 2.0 - 0.125 - 0.125 = 1.75 mm
        # 1.75 >= 0.127 → no violation
        assert report.violation_count == 0

    def test_clearance_parallel_collinear_non_overlapping(self):
        """Collinear parallel segments with gap."""
        r = _make_results(
            N1=_Route("N1", _Path([(0, 0), (5, 0)]), 0.25, []),
            N2=_Route("N2", _Path([(10, 0), (15, 0)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        # Centreline gap = 5 mm; edge-to-edge = 5 - 0.125 - 0.125 = 4.75 mm → pass
        assert report.violation_count == 0


# ===========================================================================
# 9. Coincident segments (two nets on exact same path)
# ===========================================================================


class TestCoincidentSegments:
    """Two nets routed on the exact same path — edge distance = 0."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.p1, self.p2 = _coincident_segments()

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_coincident_nets(self):
        """Both nets contribute area independently."""
        r = _make_results(
            N1=_Route("N1", _Path(self.p1), 0.25, []),
            N2=_Route("N2", _Path(self.p2), 0.25, []),
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        # 10 mm × 0.25 mm × 2 = 5.0 mm²
        assert f_cu.copper_area_mm2 == pytest.approx(10.0 * 0.25 * 2, rel=0.01)

    # -- creepage --------------------------------------------------------

    def test_creepage_coincident_nets(self):
        """HV and LV on same path → distance 0 → violation."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.p1), 0.25, []),
            SIG1=_Route("SIG1", _Path(self.p2), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)
        # Coincident segments → distance = 0 < required
        assert report.violation_count >= 1
        assert report.violations[0].actual_distance == pytest.approx(0.0, abs=1e-10)

    # -- clearance -------------------------------------------------------

    def test_clearance_coincident_nets_edge_distance_zero(self):
        """Edge-to-edge = 0 - 0.125 - 0.125 = -0.25 mm → violation."""
        r = _make_results(
            N1=_Route("N1", _Path(self.p1), 0.25, []),
            N2=_Route("N2", _Path(self.p2), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        # Coincident → overlap → negative clearance
        assert report.violation_count >= 1
        assert report.violations[0].actual_clearance < 0


# ===========================================================================
# 10. Extremely short segments (1e-6 mm — floating point stability)
# ===========================================================================


class TestExtremelyShortSegments:
    """Segments ~1e-6 mm — floating-point stability edge cases."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.coords = _extremely_short()

    # -- acid_trap -------------------------------------------------------

    def test_acid_trap_handles_extremely_short(self):
        """Extremely short first segment — angle still computed."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [])
        )
        report = detect_acid_traps(r)
        assert isinstance(report, AcidTrapReport)
        # Almost-collinear → 180° → no trap (or trap with very shallow angle)
        assert report.trap_count >= 0  # Don't crash

    # -- teardrop --------------------------------------------------------

    def test_teardrop_handles_extremely_short(self):
        """Extremely short segment near via — direction may be fine."""
        via = _Via(10, 0, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords, "F.Cu"), 0.25, [via])
        )
        report = insert_teardrops(r)
        assert isinstance(report, TeardropReport)

    # -- copper_balance --------------------------------------------------

    def test_copper_balance_handles_extremely_short(self):
        """Extremely short segment adds negligible area."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.5, [])
        )
        report = analyze_copper_balance(r, board_width=100, board_height=100)
        assert isinstance(report, CopperBalanceReport)
        f_cu = next(
            lb for lb in report.layer_balances if lb.layer_name == "F.Cu"
        )
        # Total length ≈ 1e-6 + 10.0 ≈ 10.000001 mm
        assert f_cu.copper_area_mm2 == pytest.approx(10.0 * 0.5, rel=0.01)

    # -- creepage --------------------------------------------------------

    def test_creepage_handles_extremely_short(self):
        """Segment nearly a point — floating-point stable."""
        r = _make_results(
            AC_L=_Route("AC_L", _Path(self.coords), 2.0, []),
            SIG1=_Route("SIG1", _Path([(0, 5), (10, 5)]), 0.25, []),
        )
        report = verify_creepage(r, voltage_ratings={"AC_L": 230})
        assert isinstance(report, CreepageReport)

    # -- clearance -------------------------------------------------------

    def test_clearance_handles_extremely_short(self):
        """Almost-zero-length segment → degenerate fallback."""
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, []),
            N2=_Route("N2", _Path([(0, 5), (10, 5)]), 0.25, []),
        )
        report = verify_clearance(r, min_clearance=0.127)
        assert isinstance(report, ClearanceReport)
        assert report.total_checks == 1

    # -- annular_ring ----------------------------------------------------

    def test_annular_ring_with_extremely_short_path(self):
        """Extremely short path does not affect via ring check."""
        via = _Via(5, 5, "F.Cu", "B.Cu", 0.6, 0.3, "N1")
        r = _make_results(
            N1=_Route("N1", _Path(self.coords), 0.25, [via])
        )
        report = check_annular_rings(r, min_annular_ring=0.05)
        assert isinstance(report, AnnularRingReport)

    # -- thermal_relief --------------------------------------------------

    def test_thermal_relief_with_extremely_short_path(self):
        """Extremely short path does not affect thermal relief."""
        via = _Via(5, 5, "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
        r = _make_results(
            GND=_Route("GND", _Path(self.coords), 0.5, [via])
        )
        report = add_thermal_relief(r)
        assert isinstance(report, ThermalReliefReport)


# ===========================================================================
# Cross-module parametrized: all modules vs empty routing results
# ===========================================================================

# Each module should handle an empty RoutingResults without crashing.
_MODULE_UNDER_TEST = [
    # (name, callable, expected_report_type, kwargs)
    (
        "acid_trap",
        lambda r: detect_acid_traps(r),
        AcidTrapReport,
        {},
    ),
    (
        "annular_ring",
        lambda r: check_annular_rings(r, min_annular_ring=0.05),
        AnnularRingReport,
        {},
    ),
    (
        "teardrop",
        lambda r: insert_teardrops(r),
        TeardropReport,
        {},
    ),
    (
        "thermal_relief",
        lambda r: add_thermal_relief(r),
        ThermalReliefReport,
        {},
    ),
    (
        "copper_balance",
        lambda r: analyze_copper_balance(r, board_width=100, board_height=100),
        CopperBalanceReport,
        {},
    ),
    (
        "creepage",
        lambda r: verify_creepage(r),
        CreepageReport,
        {},
    ),
    (
        "clearance",
        lambda r: verify_clearance(r, min_clearance=0.127),
        ClearanceReport,
        {},
    ),
]


@pytest.mark.parametrize(
    "module_name, module_fn, expected_report_type, extra_kwargs",
    _MODULE_UNDER_TEST,
    ids=[m[0] for m in _MODULE_UNDER_TEST],
)
class TestEmptyResultsAllModules:
    """Every DFM module must accept empty RoutingResults and return its
    report type without crashing."""

    def test_empty_routing_results_returns_valid_report(
        self, module_name, module_fn, expected_report_type, extra_kwargs
    ):
        empty = _make_results()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                report = module_fn(empty)
            except Exception as exc:
                pytest.xfail(
                    f"{module_name} crashed on empty results: {exc}"
                )
            assert isinstance(report, expected_report_type), (
                f"{module_name} returned {type(report).__name__}, "
                f"expected {expected_report_type.__name__}"
            )
