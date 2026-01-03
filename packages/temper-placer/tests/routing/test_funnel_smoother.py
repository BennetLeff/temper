"""
Tests for the FunnelSmoother path smoothing algorithm.

Part of temper-flht: Path Smoother: Funnel Algorithm Implementation
"""

import numpy as np
import pytest

from temper_placer.routing.maze_router import GridCell
from temper_placer.routing.post_processing import FunnelSmoother, Point


class MockCSpaceGrid:
    """Mock C-Space grid for testing."""

    def __init__(self, width: int = 100, height: int = 100, resolution: float = 0.1):
        self.width_px = width
        self.height_px = height
        self.resolution = resolution
        self.origin = (0.0, 0.0)
        self.grid = np.zeros((height, width), dtype=np.uint8)

    def pixel_to_world(self, px: int, py: int) -> tuple[float, float]:
        return (
            px * self.resolution + self.resolution / 2,
            py * self.resolution + self.resolution / 2,
        )

    def world_to_pixel(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        px = int((x_mm - self.resolution / 2) / self.resolution)
        py = int((y_mm - self.resolution / 2) / self.resolution)
        px = max(0, min(px, self.width_px - 1))
        py = max(0, min(py, self.height_px - 1))
        return px, py

    def is_free(self, x_mm: float, y_mm: float) -> bool:
        px, py = self.world_to_pixel(x_mm, y_mm)
        return self.grid[py, px] == 0


class TestPoint:
    """Tests for the Point dataclass."""

    def test_point_creation(self):
        p = Point(1.0, 2.0)
        assert p.x == 1.0
        assert p.y == 2.0

    def test_point_subtraction(self):
        p1 = Point(3.0, 4.0)
        p2 = Point(1.0, 1.0)
        result = p1 - p2
        assert result == (2.0, 3.0)

    def test_point_addition(self):
        p = Point(1.0, 2.0)
        result = p + (3.0, 4.0)
        assert result.x == 4.0
        assert result.y == 6.0


class TestFunnelSmoother:
    """Tests for the FunnelSmoother class."""

    def setup_method(self):
        self.smoother = FunnelSmoother(resolution_mm=0.1)
        self.grid = MockCSpaceGrid(width=100, height=100, resolution=0.1)

    def test_empty_path(self):
        result = self.smoother.smooth([], self.grid)
        assert result == []

    def test_single_cell(self):
        cells = [GridCell(5, 5, 0)]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) == 1

    def test_two_cells(self):
        cells = [GridCell(5, 5, 0), GridCell(6, 5, 0)]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) == 2

    def test_straight_horizontal_path(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(7, 5, 0),
            GridCell(8, 5, 0),
            GridCell(9, 5, 0),
        ]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) == 2
        assert result[0].x == result[1].x

    def test_straight_vertical_path(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(5, 6, 0),
            GridCell(5, 7, 0),
            GridCell(5, 8, 0),
            GridCell(5, 9, 0),
        ]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) == 2

    def test_l_shaped_path(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(7, 5, 0),
            GridCell(7, 6, 0),
            GridCell(7, 7, 0),
        ]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) == 3
        assert result[0].x < result[1].x == result[2].x
        assert result[1].y < result[2].y

    def test_zigzag_path(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(6, 6, 0),
            GridCell(7, 6, 0),
            GridCell(7, 7, 0),
            GridCell(8, 7, 0),
        ]
        result = self.smoother.smooth(cells, self.grid)
        assert len(result) >= 2


class TestPathValidation:
    """Tests for path validation."""

    def setup_method(self):
        self.smoother = FunnelSmoother(resolution_mm=0.1)
        self.grid = MockCSpaceGrid(width=100, height=100, resolution=0.1)

    def test_empty_path_validation(self):
        result = self.smoother.validate_smoothed_path([], self.grid)
        assert result is True

    def test_single_point_validation(self):
        points = [Point(5.0, 5.0)]
        result = self.smoother.validate_smoothed_path(points, self.grid)
        assert result is True

    def test_valid_segment(self):
        points = [Point(5.0, 5.0), Point(10.0, 5.0)]
        result = self.smoother.validate_smoothed_path(points, self.grid)
        assert result is True

    def test_blocked_segment(self):
        self.grid.grid[50, :] = 255
        points = [Point(1.0, 5.0), Point(10.0, 5.0)]
        result = self.smoother.validate_smoothed_path(points, self.grid)
        assert result is False


class TestPathMetrics:
    """Tests for path length reduction and angle calculations."""

    def setup_method(self):
        self.smoother = FunnelSmoother(resolution_mm=0.1)
        self.grid = MockCSpaceGrid(width=100, height=100, resolution=0.1)

    def test_path_length_reduction(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(7, 5, 0),
            GridCell(8, 5, 0),
            GridCell(9, 5, 0),
        ]
        smooth_points = [
            Point(5.5, 5.5),
            Point(9.5, 5.5),
        ]
        reduction = self.smoother.path_length_reduction(cells, smooth_points)
        assert reduction > 0

    def test_empty_grid_path(self):
        reduction = self.smoother.path_length_reduction([], [])
        assert reduction == 0.0

    def test_min_segment_angle_straight(self):
        points = [Point(0, 0), Point(10, 0), Point(20, 0)]
        angle = self.smoother.min_segment_angle(points)
        assert angle == 180.0

    def test_min_segment_angle_right_turn(self):
        points = [Point(0, 0), Point(10, 0), Point(10, 10)]
        angle = self.smoother.min_segment_angle(points)
        assert 80.0 <= angle <= 100.0

    def test_min_segment_angle_too_few_points(self):
        points = [Point(0, 0), Point(10, 0)]
        angle = self.smoother.min_segment_angle(points)
        assert angle == 180.0


class TestCrossProduct:
    """Tests for cross product helper function."""

    def setup_method(self):
        self.smoother = FunnelSmoother()

    def test_cross_product_positive(self):
        from temper_placer.routing.post_processing.funnel_smoother import cross

        a = Point(0, 0)
        b = Point(1, 0)
        c = Point(1, 1)
        assert cross(a, b, c) > 0

    def test_cross_product_negative(self):
        from temper_placer.routing.post_processing.funnel_smoother import cross

        a = Point(0, 0)
        b = Point(1, 0)
        c = Point(1, -1)
        assert cross(a, b, c) < 0

    def test_cross_product_zero(self):
        from temper_placer.routing.post_processing.funnel_smoother import cross

        a = Point(0, 0)
        b = Point(1, 0)
        c = Point(2, 0)
        assert cross(a, b, c) == 0


class TestDistance:
    """Tests for distance helper function."""

    def setup_method(self):
        self.smoother = FunnelSmoother()

    def test_distance_same_point(self):
        from temper_placer.routing.post_processing.funnel_smoother import distance

        p = Point(5, 5)
        assert distance(p, p) == 0

    def test_distance_known_values(self):
        from temper_placer.routing.post_processing.funnel_smoother import distance

        p1 = Point(0, 0)
        p2 = Point(3, 4)
        assert abs(distance(p1, p2) - 5.0) < 0.001

    def test_distance_euclidean(self):
        from temper_placer.routing.post_processing.funnel_smoother import distance

        p1 = Point(0, 0)
        p2 = Point(1, 1)
        assert abs(distance(p1, p2) - np.sqrt(2)) < 0.001


class TestAcceptanceCriteria:
    """Tests for acceptance criteria from the issue."""

    def setup_method(self):
        self.smoother = FunnelSmoother(resolution_mm=0.1)
        self.grid = MockCSpaceGrid(width=100, height=100, resolution=0.1)

    def test_path_length_reduction_by_20_percent(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(7, 5, 0),
            GridCell(8, 5, 0),
            GridCell(9, 5, 0),
            GridCell(9, 6, 0),
            GridCell(9, 7, 0),
            GridCell(9, 8, 0),
            GridCell(9, 9, 0),
        ]
        smooth_points = self.smoother.smooth(cells, self.grid)
        reduction = self.smoother.path_length_reduction(cells, smooth_points)
        assert reduction >= 20.0, f"Expected >= 20% reduction, got {reduction}%"

    def test_all_smoothed_segments_pass_validation(self):
        cells = [
            GridCell(10, 10, 0),
            GridCell(11, 10, 0),
            GridCell(12, 10, 0),
            GridCell(12, 11, 0),
            GridCell(12, 12, 0),
        ]
        smooth_points = self.smoother.smooth(cells, self.grid)
        is_valid = self.smoother.validate_smoothed_path(smooth_points, self.grid)
        assert is_valid is True

    def test_no_acute_angles(self):
        cells = [
            GridCell(5, 5, 0),
            GridCell(6, 5, 0),
            GridCell(7, 5, 0),
            GridCell(7, 6, 0),
            GridCell(7, 7, 0),
        ]
        smooth_points = self.smoother.smooth(cells, self.grid)
        min_angle = self.smoother.min_segment_angle(smooth_points)
        assert min_angle >= 90.0, f"Expected no acute angles (< 90°), got {min_angle}°"
