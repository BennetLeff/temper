"""
Tests for path simplification (temper-itv5).
"""

import pytest

from temper_placer.routing.maze_router import GridCell
from temper_placer.routing.path_simplify import (
    estimate_segment_count,
    is_collinear,
    simplify_path,
)


class TestIsCollinear:
    """Tests for collinearity detection."""

    def test_horizontal_line(self):
        """Three points on horizontal line should be collinear."""
        p1 = GridCell(0, 5, 0)
        p2 = GridCell(1, 5, 0)
        p3 = GridCell(2, 5, 0)
        assert is_collinear(p1, p2, p3) is True

    def test_vertical_line(self):
        """Three points on vertical line should be collinear."""
        p1 = GridCell(3, 0, 0)
        p2 = GridCell(3, 1, 0)
        p3 = GridCell(3, 2, 0)
        assert is_collinear(p1, p2, p3) is True

    def test_l_shape(self):
        """L-shaped path should not be collinear."""
        p1 = GridCell(0, 0, 0)
        p2 = GridCell(1, 0, 0)
        p3 = GridCell(1, 1, 0)  # Corner
        assert is_collinear(p1, p2, p3) is False

    def test_diagonal_not_collinear(self):
        """Diagonal paths are not simplified (router uses Manhattan routing)."""
        p1 = GridCell(0, 0, 0)
        p2 = GridCell(1, 1, 0)  # Diagonal step
        p3 = GridCell(2, 2, 0)
        # Not collinear in axis-aligned sense
        assert is_collinear(p1, p2, p3) is False

    def test_different_layers(self):
        """Points on different layers should not be collinear."""
        p1 = GridCell(0, 0, 0)
        p2 = GridCell(1, 0, 0)
        p3 = GridCell(2, 0, 1)  # Different layer
        assert is_collinear(p1, p2, p3) is False


class TestSimplifyPath:
    """Tests for path simplification."""

    def test_straight_line_collapses(self):
        """Straight horizontal line should collapse to 2 points."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        simplified = simplify_path(cells)
        assert len(simplified) == 2
        assert simplified == [GridCell(0, 0, 0), GridCell(2, 0, 0)]

    def test_vertical_line_collapses(self):
        """Straight vertical line should collapse to 2 points."""
        cells = [GridCell(5, 0, 0), GridCell(5, 1, 0), GridCell(5, 2, 0), GridCell(5, 3, 0)]
        simplified = simplify_path(cells)
        assert len(simplified) == 2
        assert simplified[0] == GridCell(5, 0, 0)
        assert simplified[-1] == GridCell(5, 3, 0)

    def test_l_shape_preserved(self):
        """L-shaped path should keep all 3 points."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]
        simplified = simplify_path(cells)
        assert len(simplified) == 3
        assert simplified == cells

    def test_zigzag_preserved(self):
        """Zigzag path should keep all direction changes."""
        cells = [
            GridCell(0, 0, 0),  # Start
            GridCell(1, 0, 0),  # Right
            GridCell(1, 1, 0),  # Up - corner 1
            GridCell(2, 1, 0),  # Right - corner 2
            GridCell(2, 2, 0),  # Up - corner 3
        ]
        simplified = simplify_path(cells)
        # All corners must be preserved
        assert len(simplified) == 5
        assert simplified == cells

    def test_layer_transition_preserved(self):
        """Layer changes should always be kept."""
        cells = [
            GridCell(0, 0, 0),  # L0
            GridCell(1, 0, 0),  # L0
            GridCell(1, 0, 1),  # L1 - via location
            GridCell(2, 0, 1),  # L1
        ]
        simplified = simplify_path(cells)
        
        # Via location must be preserved even if collinear in x,y
        assert GridCell(1, 0, 1) in simplified
        assert len(simplified) == 3  # Start, via, end

    def test_two_point_path_unchanged(self):
        """Two-point path cannot be simplified."""
        cells = [GridCell(0, 0, 0), GridCell(5, 5, 0)]
        simplified = simplify_path(cells)
        assert simplified == cells

    def test_single_point_path_unchanged(self):
        """Single-point path is returned as-is."""
        cells = [GridCell(3, 3, 0)]
        simplified = simplify_path(cells)
        assert simplified == cells

    def test_empty_path_unchanged(self):
        """Empty path is returned as-is."""
        cells = []
        simplified = simplify_path(cells)
        assert simplified == []

    def test_complex_path_with_layer_changes(self):
        """Complex path with both direction changes and layer transitions."""
        cells = [
            GridCell(0, 0, 0),  # Start L0
            GridCell(1, 0, 0),  # L0
            GridCell(2, 0, 0),  # L0 - collinear, should be removed
            GridCell(3, 0, 0),  # L0 - collinear, should be removed
            GridCell(4, 0, 0),  # L0
            GridCell(4, 1, 0),  # L0 - corner, keep
            GridCell(4, 1, 1),  # L1 - via, keep
            GridCell(5, 1, 1),  # L1
            GridCell(6, 1, 1),  # L1 - collinear, should be removed
            GridCell(7, 1, 1),  # L1 end
        ]
        simplified = simplify_path(cells)
        
        expected = [
            GridCell(0, 0, 0),  # Start
            GridCell(4, 0, 0),  # Endpoint of horizontal segment
            GridCell(4, 1, 0),  # Corner before via
            GridCell(4, 1, 1),  # Via
            GridCell(7, 1, 1),  # End
        ]
        assert simplified == expected


class TestEstimateSegmentCount:
    """Tests for segment count estimation."""

    def test_straight_line(self):
        """Simple path should produce one segment."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        count = estimate_segment_count(cells)
        assert count == 1  # Simplifies to 2 points = 1 segment

    def test_l_shape(self):
        """L-shaped path should produce 2 segments."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]
        count = estimate_segment_count(cells)
        assert count == 2  # 3 points = 2 segments

    def test_layer_transition_no_segment(self):
        """Via (layer change) should not count as segment."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),  # Segment 1 (L0)
            GridCell(1, 0, 1),  # Via (no segment)
            GridCell(2, 0, 1),  # Segment 2 (L1)
        ]
        count = estimate_segment_count(cells)
        assert count == 2  # One segment per layer

    def test_complex_multi_layer_path(self):
        """Path with multiple segments on different layers."""
        cells = [
            GridCell(0, 0, 0),  # L0 start
            GridCell(2, 0, 0),  # L0 - segment 1
            GridCell(2, 1, 0),  # L0 - segment 2
            GridCell(2, 1, 1),  # Via to L1
            GridCell(4, 1, 1),  # L1 - segment 3
        ]
        simplified = simplify_path(cells)
        count = estimate_segment_count(cells)
        
        # Simplified: start, corner, via, end = 4 points
        # Segments: L0 horiz, L0 vert, via (no seg), L1 horiz = 3 segments
        assert count == 3
