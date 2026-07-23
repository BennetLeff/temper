"""
Tests for Router V6 octilinear compliance metric and diagonal cost incentive.

Part of temper-U1: Human-Like Routing Quality Gate (W4).
"""

import math
import tempfile
from pathlib import Path

import pytest

import temper_placer.router_v6.astar_core as _astar
from temper_placer.router_v6.grid_converter import GridCell
from temper_placer.router_v6.metrics.octilinear import (
    _angle_deg,
    _is_diagonal_angle,
    _segment_classification,
    add_diagonal_incentive,
    octilinear_compliance,
    octilinear_fraction,
)


def _write_temp_pcb(content: str) -> Path:
    """Helper to write a temporary KiCad PCB file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".kicad_pcb",
        delete=False,
    ) as f:
        f.write(content)
        return Path(f.name)


# ---------------------------------------------------------------------------
# octilinear_fraction tests (simplified grid paths)
# ---------------------------------------------------------------------------


class TestOctilinearFraction:
    def test_all_diagonal_path(self):
        """Straight diagonal path (dx=dy at every step)  1.0."""
        cells = [GridCell(0, 0, 0), GridCell(1, 1, 0), GridCell(2, 2, 0), GridCell(3, 3, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(1.0)

    def test_all_orthogonal_path(self):
        """Straight orthogonal path (dx=0 or dy=0)  0.0."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0), GridCell(3, 0, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(0.0)

    def test_all_orthogonal_vertical(self):
        """Vertical path  0.0."""
        cells = [GridCell(0, 0, 0), GridCell(0, 1, 0), GridCell(0, 2, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(0.0)

    def test_mixed_path(self):
        """Mixed path: 3 diagonal steps + 2 cardinal steps."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 1, 0),  # diagonal
            GridCell(2, 2, 0),  # diagonal
            GridCell(3, 3, 0),  # diagonal
            GridCell(4, 3, 0),  # cardinal
            GridCell(5, 3, 0),  # cardinal
        ]
        expected = (3 * math.sqrt(2)) / (3 * math.sqrt(2) + 2)
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(expected)

    def test_single_cell_path(self):
        """Single-cell path  0.0."""
        cells = [GridCell(0, 0, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == 0.0

    def test_two_cell_path_diagonal(self):
        """Two cells with diagonal step  1.0."""
        cells = [GridCell(0, 0, 0), GridCell(1, 1, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(1.0)

    def test_two_cell_path_orthogonal(self):
        """Two cells with orthogonal step  0.0."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0)]
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(0.0)

    def test_layer_transition_excluded(self):
        """Layer transitions excluded from denominator."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 1, 0),  # diagonal, L0
            GridCell(1, 1, 1),  # via, excluded
            GridCell(2, 1, 1),  # cardinal, L1
        ]
        expected = math.sqrt(2) / (math.sqrt(2) + 1.0)
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(expected)

    def test_cell_size_scales_length(self):
        """Ratio is independent of cell_size."""
        cells = [GridCell(0, 0, 0), GridCell(1, 1, 0), GridCell(2, 0, 0)]
        r1 = octilinear_fraction(cells, cell_size=1.0)
        r2 = octilinear_fraction(cells, cell_size=0.5)
        assert r1 == pytest.approx(r2)

    def test_all_vias_only(self):
        """All layer transitions, no same-layer segments  0.0."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(0, 0, 1),
            GridCell(0, 0, 2),
        ]
        assert octilinear_fraction(cells, cell_size=1.0) == 0.0

    def test_empty_path(self):
        """Empty path  0.0."""
        assert octilinear_fraction([], cell_size=1.0) == 0.0

    def test_l_shaped_path(self):
        """L-shaped: one diagonal + one cardinal."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 1, 0),  # diagonal
            GridCell(2, 1, 0),  # cardinal
        ]
        expected = math.sqrt(2) / (math.sqrt(2) + 1.0)
        assert octilinear_fraction(cells, cell_size=1.0) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# octilinear_compliance tests (parsed PCB)
# ---------------------------------------------------------------------------


class TestOctilinearCompliance:
    def test_compliance_mixed(self):
        """PCB with 2 diagonal + 1 orthogonal segment."""
        pcb = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (net 0 "")
  (net 1 "NET1")
  (footprint "Test:Pad1" (layer "F.Cu")
    (pad "1" thru_hole circle (at 0 0) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (footprint "Test:Pad2" (layer "F.Cu")
    (pad "1" thru_hole circle (at 20 20) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (segment (start 0 0) (end 10 10) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000001"))
  (segment (start 10 10) (end 20 20) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000002"))
  (segment (start 20 20) (end 30 20) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000003"))
)
"""
        path = _write_temp_pcb(pcb)
        try:
            result = octilinear_compliance(path)
            expected = (2 * math.hypot(10, 10)) / (2 * math.hypot(10, 10) + 10.0)
            assert result == pytest.approx(expected, rel=1e-4)
        finally:
            path.unlink(missing_ok=True)

    def test_compliance_empty_traces(self):
        """PCB with no track segments  0.0."""
        pcb = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (net 0 "")
  (net 1 "NET1")
  (footprint "Test:Pad1" (layer "F.Cu")
    (pad "1" thru_hole circle (at 0 0) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
)
"""
        path = _write_temp_pcb(pcb)
        try:
            result = octilinear_compliance(path)
            assert result == 0.0
        finally:
            path.unlink(missing_ok=True)

    def test_compliance_all_orthogonal(self):
        """File with only orthogonal segments  0.0."""
        pcb = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (net 0 "")
  (net 1 "NET1")
  (footprint "Test:Pad1" (layer "F.Cu")
    (pad "1" thru_hole circle (at 0 0) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (footprint "Test:Pad2" (layer "F.Cu")
    (pad "1" thru_hole circle (at 30 0) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (segment (start 0 0) (end 15 0) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000001"))
  (segment (start 15 0) (end 30 0) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000002"))
)
"""
        path = _write_temp_pcb(pcb)
        try:
            result = octilinear_compliance(path)
            assert result == 0.0
        finally:
            path.unlink(missing_ok=True)

    def test_compliance_all_diagonal(self):
        """File with only perfect diagonal segments  1.0."""
        pcb = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (net 0 "")
  (net 1 "NET1")
  (footprint "Test:Pad1" (layer "F.Cu")
    (pad "1" thru_hole circle (at 0 0) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (footprint "Test:Pad2" (layer "F.Cu")
    (pad "1" thru_hole circle (at 20 20) (size 1.0 1.0) (drill 0.8) (layers "F.Cu" "B.Cu") (net 1 "NET1"))
  )
  (segment (start 0 0) (end 10 10) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000001"))
  (segment (start 10 10) (end 20 20) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaaaaaa-bbbb-cccc-dddd-000000000002"))
)
"""
        path = _write_temp_pcb(pcb)
        try:
            result = octilinear_compliance(path)
            assert result == pytest.approx(1.0)
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# add_diagonal_incentive tests
# ---------------------------------------------------------------------------


class TestDiagonalIncentive:
    def test_default_is_one(self):
        add_diagonal_incentive(1.0)
        assert pytest.approx(1.0) == _astar.DIAGONAL_COST_FACTOR

    def test_set_lower_value(self):
        add_diagonal_incentive(0.707)
        assert pytest.approx(0.707) == _astar.DIAGONAL_COST_FACTOR

    def test_standard_octile_behavior(self):
        add_diagonal_incentive(1.0)
        diagonal_cost = _astar.DIAGONAL_COST_FACTOR * _astar._BASE_DIAGONAL_COST
        assert diagonal_cost == pytest.approx(math.sqrt(2))

    def test_no_preference_behavior(self):
        """At cost_ratio=0.707, diagonal cost  1.0 (same as cardinal)."""
        add_diagonal_incentive(0.707)
        diagonal_cost = _astar.DIAGONAL_COST_FACTOR * _astar._BASE_DIAGONAL_COST
        # 0.707 * sqrt(2)  0.99985 (approx 1.0)
        assert diagonal_cost == pytest.approx(1.0, rel=1e-3)

    def test_strong_incentive(self):
        add_diagonal_incentive(0.5)
        diagonal_cost = _astar.DIAGONAL_COST_FACTOR * _astar._BASE_DIAGONAL_COST
        assert diagonal_cost == pytest.approx(0.5 * math.sqrt(2))

    @pytest.fixture(autouse=True)
    def _restore_default(self):
        """Restore diagonal cost factor to default after each test."""
        yield
        add_diagonal_incentive(1.0)


# ---------------------------------------------------------------------------
# Angle classification unit tests
# ---------------------------------------------------------------------------


class TestAngleClassification:
    @pytest.mark.parametrize(
        "dx,dy,expected_angle",
        [
            (1, 1, 45.0),
            (-1, 1, 135.0),
            (-1, -1, 225.0),
            (1, -1, 315.0),
            (1, 0, 0.0),
            (0, 1, 90.0),
            (-1, 0, 180.0),
            (0, -1, 270.0),
        ],
    )
    def test_angle_computation(self, dx, dy, expected_angle):
        assert _angle_deg(float(dx), float(dy)) == pytest.approx(expected_angle)

    @pytest.mark.parametrize(
        "angle,expected",
        [
            (45.0, True),
            (135.0, True),
            (225.0, True),
            (315.0, True),
            (0.0, False),
            (90.0, False),
            (180.0, False),
            (270.0, False),
            (50.0, True),
            (40.0, True),
            (130.0, True),
            (140.0, True),
        ],
    )
    def test_is_diagonal_angle(self, angle, expected):
        assert _is_diagonal_angle(angle) == expected

    def test_is_diagonal_near_wrapping(self):
        """Angles near 0/360 wrapping."""
        # 355 is not within 5 of 315 (40 away)
        assert not _is_diagonal_angle(355.0)

    def test_tolerance_boundary(self):
        """Exactly at the 5 tolerance boundary."""
        assert _is_diagonal_angle(40.0)  # 5.0 from 45
        assert not _is_diagonal_angle(39.9)  # 5.1 from 45

    @pytest.mark.parametrize(
        "x1,y1,x2,y2,expected_len,expected_diag",
        [
            (0.0, 0.0, 1.0, 1.0, math.sqrt(2), True),
            (0.0, 0.0, 1.0, 0.0, 1.0, False),
            (0.0, 0.0, 0.0, 1.0, 1.0, False),
            (0.0, 0.0, -1.0, -1.0, math.sqrt(2), True),
            (0.0, 0.0, 0.0, 0.0, 0.0, False),
        ],
    )
    def test_segment_classification(self, x1, y1, x2, y2, expected_len, expected_diag):
        length, is_diag = _segment_classification(x1, y1, x2, y2)
        assert length == pytest.approx(expected_len)
        assert is_diag == expected_diag
