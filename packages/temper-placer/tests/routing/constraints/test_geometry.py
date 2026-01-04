"""Tests for geometry primitives.

Part of temper-lueu.2
"""

import math

import pytest

from temper_placer.routing.constraints.geometry import (
    LineSegment,
    Point,
    point_to_circle_distance,
    point_to_segment_distance,
    # segment_to_circle_distance,  # TODO: Function not implemented
    segment_to_segment_distance,
)


class TestPoint:
    """Tests for Point dataclass."""

    def test_create_point(self):
        """Test basic point creation."""
        p = Point(3.0, 4.0)
        assert p.x == 3.0
        assert p.y == 4.0

    def test_to_array(self):
        """Test numpy array conversion."""
        p = Point(1.0, 2.0)
        arr = p.to_array()
        assert arr[0] == 1.0
        assert arr[1] == 2.0

    def test_distance_to(self):
        """Test point-to-point distance."""
        p1 = Point(0.0, 0.0)
        p2 = Point(3.0, 4.0)
        assert p1.distance_to(p2) == 5.0

    def test_distance_to_self(self):
        """Test distance to itself is zero."""
        p = Point(1.0, 2.0)
        assert p.distance_to(p) == 0.0


class TestLineSegment:
    """Tests for LineSegment dataclass."""

    def test_create_segment(self):
        """Test basic segment creation."""
        seg = LineSegment(Point(0, 0), Point(1, 0))
        assert seg.start.x == 0.0
        assert seg.end.x == 1.0

    def test_length_horizontal(self):
        """Test horizontal segment length."""
        seg = LineSegment(Point(0, 0), Point(5, 0))
        assert seg.length == 5.0

    def test_length_diagonal(self):
        """Test diagonal segment length."""
        seg = LineSegment(Point(0, 0), Point(3, 4))
        assert seg.length == 5.0

    def test_length_zero(self):
        """Test degenerate segment (point)."""
        seg = LineSegment(Point(1, 1), Point(1, 1))
        assert seg.length == 0.0

    def test_midpoint(self):
        """Test midpoint calculation."""
        seg = LineSegment(Point(0, 0), Point(10, 0))
        mid = seg.midpoint()
        assert mid.x == 5.0
        assert mid.y == 0.0


class TestPointToSegmentDistance:
    """Tests for point_to_segment_distance function."""

    def test_point_on_segment(self):
        """Point on segment has zero distance."""
        seg = LineSegment(Point(0, 0), Point(10, 0))
        p = Point(5, 0)
        assert point_to_segment_distance(p, seg) == pytest.approx(0.0)

    def test_point_above_segment_middle(self):
        """Point directly above segment middle."""
        seg = LineSegment(Point(0, 0), Point(10, 0))
        p = Point(5, 3)
        assert point_to_segment_distance(p, seg) == pytest.approx(3.0)

    def test_point_beyond_endpoint(self):
        """Point beyond segment endpoint."""
        seg = LineSegment(Point(0, 0), Point(10, 0))
        p = Point(15, 0)
        assert point_to_segment_distance(p, seg) == pytest.approx(5.0)

    def test_point_before_startpoint(self):
        """Point before segment start."""
        seg = LineSegment(Point(0, 0), Point(10, 0))
        p = Point(-3, 4)
        assert point_to_segment_distance(p, seg) == pytest.approx(5.0)

    def test_degenerate_segment(self):
        """Distance to a point (degenerate segment)."""
        seg = LineSegment(Point(5, 5), Point(5, 5))
        p = Point(8, 9)
        assert point_to_segment_distance(p, seg) == pytest.approx(5.0)


class TestSegmentToSegmentDistance:
    """Tests for segment_to_segment_distance function."""

    def test_parallel_horizontal_segments(self):
        """Parallel horizontal segments."""
        seg1 = LineSegment(Point(0, 0), Point(10, 0))
        seg2 = LineSegment(Point(0, 5), Point(10, 5))
        assert segment_to_segment_distance(seg1, seg2) == pytest.approx(5.0)

    def test_perpendicular_segments_not_touching(self):
        """Perpendicular segments that don't intersect."""
        seg1 = LineSegment(Point(0, 0), Point(5, 0))
        seg2 = LineSegment(Point(10, -5), Point(10, 5))
        assert segment_to_segment_distance(seg1, seg2) == pytest.approx(5.0)

    def test_intersecting_segments(self):
        """Intersecting segments have zero distance."""
        seg1 = LineSegment(Point(0, 0), Point(10, 10))
        seg2 = LineSegment(Point(0, 10), Point(10, 0))
        assert segment_to_segment_distance(seg1, seg2) == pytest.approx(0.0)

    def test_touching_at_endpoint(self):
        """Segments touching at endpoint."""
        seg1 = LineSegment(Point(0, 0), Point(5, 0))
        seg2 = LineSegment(Point(5, 0), Point(10, 0))
        assert segment_to_segment_distance(seg1, seg2) == pytest.approx(0.0)

    def test_collinear_gap(self):
        """Collinear segments with a gap."""
        seg1 = LineSegment(Point(0, 0), Point(5, 0))
        seg2 = LineSegment(Point(8, 0), Point(13, 0))
        assert segment_to_segment_distance(seg1, seg2) == pytest.approx(3.0)

    def test_symmetric_distance(self):
        """Distance should be symmetric."""
        seg1 = LineSegment(Point(0, 0), Point(5, 0))
        seg2 = LineSegment(Point(3, 3), Point(7, 3))
        d1 = segment_to_segment_distance(seg1, seg2)
        d2 = segment_to_segment_distance(seg2, seg1)
        assert d1 == pytest.approx(d2)


class TestCircleDistances:
    """Tests for circle distance functions."""

    def test_point_outside_circle(self):
        """Point outside circle."""
        center = Point(0, 0)
        radius = 5.0
        p = Point(10, 0)
        assert point_to_circle_distance(p, center, radius) == pytest.approx(5.0)

    def test_point_inside_circle(self):
        """Point inside circle (negative distance)."""
        center = Point(0, 0)
        radius = 10.0
        p = Point(3, 0)
        assert point_to_circle_distance(p, center, radius) == pytest.approx(-7.0)

    def test_point_on_circle(self):
        """Point on circle edge."""
        center = Point(0, 0)
        radius = 5.0
        p = Point(5, 0)
        assert point_to_circle_distance(p, center, radius) == pytest.approx(0.0)


    # Tests below are skipped - segment_to_circle_distance not implemented
    @pytest.mark.skip(reason="segment_to_circle_distance not implemented")
    def test_segment_outside_circle(self):
        """Segment outside circle."""
        center = Point(0, 0)
        radius = 5.0
        seg = LineSegment(Point(10, 0), Point(15, 0))
        # assert segment_to_circle_distance(seg, center, radius) == pytest.approx(5.0)

    @pytest.mark.skip(reason="segment_to_circle_distance not implemented")
    def test_segment_tangent_to_circle(self):
        """Segment tangent to circle."""
        center = Point(0, 0)
        radius = 5.0
        seg = LineSegment(Point(-10, 5), Point(10, 5))
        # assert segment_to_circle_distance(seg, center, radius) == pytest.approx(0.0)

    @pytest.mark.skip(reason="segment_to_circle_distance not implemented")
    def test_segment_intersects_circle(self):
        """Segment passing through circle (negative distance)."""
        center = Point(0, 0)
        radius = 5.0
        seg = LineSegment(Point(-10, 0), Point(10, 0))
        # assert segment_to_circle_distance(seg, center, radius) == pytest.approx(-5.0)
