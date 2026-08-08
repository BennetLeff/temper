"""Tests for core.courtyard module."""

import pytest

from temper_placer.core.courtyard import Courtyard, check_overlap


class TestCourtyard:
    """Tests for Courtyard."""

    def test_create_with_points(self):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        court = Courtyard(component_ref="U1", points=points)
        assert court.component_ref == "U1"

    def test_create_with_few_points_fallback(self):
        """Less than 3 points should trigger fallback to small box."""
        court = Courtyard(component_ref="U1", points=[(0.0, 0.0), (1.0, 1.0)])
        # Should have 4 points from fallback
        assert len(court.points) == 4

    def test_get_global_polygon_no_rotation(self):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        court = Courtyard(component_ref="U1", points=points)
        poly = court.get_global_polygon(x=10.0, y=20.0, rotation_idx=0)
        # Should be centered at (10, 20), same bounds
        bounds = poly.bounds
        assert bounds[0] == 9.0  # x_min = 10 - 1
        assert bounds[1] == 19.0  # y_min = 20 - 1
        assert bounds[2] == 11.0  # x_max = 10 + 1
        assert bounds[3] == 21.0  # y_max = 20 + 1

    def test_get_global_polygon_90_rotation(self):
        points = [(-1.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-1.0, 1.0)]
        court = Courtyard(component_ref="U1", points=points)
        poly = court.get_global_polygon(x=0.0, y=0.0, rotation_idx=1)
        bounds = poly.bounds
        # After 90deg CW rotation around origin
        # Points become: (-1,1), (-1,-2), (1,-2), (1,1)
        assert bounds[0] == pytest.approx(-1.0)
        assert bounds[1] == pytest.approx(-2.0)
        assert bounds[2] == pytest.approx(1.0)
        assert bounds[3] == pytest.approx(1.0)

    def test_get_global_polygon_translated(self):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        court = Courtyard(component_ref="U1", points=points)
        poly = court.get_global_polygon(x=5.0, y=10.0, rotation_idx=0)
        bounds = poly.bounds
        assert bounds[0] == 4.0
        assert bounds[1] == 9.0
        assert bounds[2] == 6.0
        assert bounds[3] == 11.0


class TestCheckOverlap:
    """Tests for check_overlap."""

    def _make_square(self, ref="U1"):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        return Courtyard(component_ref=ref, points=points)

    def test_no_overlap_separated(self):
        c1 = self._make_square("U1")
        c2 = self._make_square("U2")
        assert check_overlap(c1, (0.0, 0.0), 0, c2, (10.0, 10.0), 0) is False

    def test_overlap_same_position(self):
        c1 = self._make_square("U1")
        c2 = self._make_square("U2")
        assert check_overlap(c1, (0.0, 0.0), 0, c2, (0.0, 0.0), 0) is True

    def test_overlap_partial(self):
        c1 = self._make_square("U1")
        c2 = self._make_square("U2")
        # Offset by 1.0 in x: should still overlap
        assert check_overlap(c1, (0.0, 0.0), 0, c2, (1.0, 0.0), 0) is True
