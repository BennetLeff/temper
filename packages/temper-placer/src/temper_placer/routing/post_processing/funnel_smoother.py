"""
Funnel Algorithm for Path Smoothing.

Converts jagged grid paths from A* into smooth, manufacturable traces by finding
the shortest path through the corridor of safe cells.

Part of temper-flht: Path Smoother: Funnel Algorithm Implementation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.routing.maze_router import GridCell

if TYPE_CHECKING:
    from temper_placer.routing.c_space_builder import CSpaceGrid


@dataclass
class Point:
    """2D point in world coordinates."""

    x: float
    y: float

    def __sub__(self, other: Point) -> tuple[float, float]:
        return (self.x - other.x, self.y - other.y)

    def __add__(self, other: tuple[float, float]) -> Point:
        return Point(self.x + other[0], self.y + other[1])


def cross(a: Point, b: Point, c: Point) -> float:
    """Cross product of vectors AB x AC."""
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def distance(p1: Point, p2: Point) -> float:
    """Euclidean distance between two points."""
    return np.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


class FunnelSmoother:
    """Implements the Funnel Algorithm for path smoothing.

    The Funnel Algorithm finds the shortest path through a corridor of cells
    by maintaining a "funnel" of valid angles and emitting waypoints when
    the funnel collapses.

    Example:
        >>> from temper_placer.routing import MazeRouter, RoutePath
        >>> from temper_placer.routing.post_processing import FunnelSmoother
        >>>
        >>> # Get grid path from router
        >>> path = RoutePath(net="NET1", cells=[...], length=10.5, via_count=0, success=True)
        >>>
        >>> # Smooth the path
        >>> smoother = FunnelSmoother()
        >>> smooth_points = smoother.smooth(path.cells, c_space_grid)
        >>>
        >>> # Validate the smoothed path
        >>> is_valid = smoother.validate_smoothed_path(smooth_points, c_space_grid)
    """

    def __init__(self, resolution_mm: float = 0.1):
        """Initialize the FunnelSmoother.

        Args:
            resolution_mm: Grid resolution in mm (used for cell to point conversion)
        """
        self.resolution_mm = resolution_mm

    def smooth(self, cells: list[GridCell], c_space_grid: CSpaceGrid) -> list[Point]:
        """Convert a grid path to a smooth path using the Funnel Algorithm.

        Args:
            cells: Path from A* as list of grid cells
            c_space_grid: C-Space grid for validation and coordinate conversion

        Returns:
            List of waypoints in world coordinates (smooth path)
        """
        if len(cells) < 2:
            if len(cells) == 1:
                return [self._cell_to_point(cells[0], c_space_grid)]
            return []

        if len(cells) == 2:
            return [
                self._cell_to_point(cells[0], c_space_grid),
                self._cell_to_point(cells[1], c_space_grid),
            ]

        result: list[Point] = []
        apex = self._cell_to_point(cells[0], c_space_grid)
        result.append(apex)

        left_apex = apex
        right_apex = apex
        left_idx = 0
        right_idx = 0

        for i in range(1, len(cells)):
            portal_left, portal_right = self._get_portal(cells[i - 1], cells[i], c_space_grid)

            if i == 1:
                left_apex = portal_left
                right_apex = portal_right
                left_idx = 1
                right_idx = 1
                continue

            new_left = portal_left
            new_right = portal_right

            if cross(apex, right_apex, new_left) >= 0:
                if cross(apex, left_apex, new_left) <= 0:
                    if distance(apex, right_apex) < distance(apex, left_apex):
                        result.append(right_apex)
                        apex = right_apex
                        left_apex = apex
                        right_apex = new_right
                        left_idx = i
                        right_idx = i
                    else:
                        result.append(left_apex)
                        apex = left_apex
                        right_apex = new_right
                        left_idx = i
                        right_idx = i
                else:
                    right_apex = new_right
                    right_idx = i
            else:
                if cross(apex, left_apex, new_right) <= 0:
                    left_apex = new_left
                    left_idx = i
                else:
                    result.append(left_apex)
                    apex = left_apex
                    left_apex = new_left
                    right_apex = new_right
                    left_idx = i
                    right_idx = i

        result.append(self._cell_to_point(cells[-1], c_space_grid))
        return result

    def _cell_to_point(self, cell: GridCell, c_space_grid: CSpaceGrid) -> Point:
        """Convert a grid cell to world coordinates.

        Args:
            cell: Grid cell to convert
            c_space_grid: C-Space grid for coordinate conversion

        Returns:
            Point in world coordinates (center of the cell)
        """
        x_mm, y_mm = c_space_grid.pixel_to_world(cell.x, cell.y)
        return Point(x_mm, y_mm)

    def _get_portal(
        self, prev_cell: GridCell, curr_cell: GridCell, c_space_grid: CSpaceGrid
    ) -> tuple[Point, Point]:
        """Get the left and right portal edges between two adjacent cells.

        The portal is the corridor edge between two cells. For axis-aligned
        adjacent cells, this gives perpendicular edges at the shared boundary.

        Args:
            prev_cell: Previous cell in the path
            curr_cell: Current cell in the path
            c_space_grid: C-Space grid for coordinate conversion

        Returns:
            Tuple of (left_point, right_point) defining the portal edge
        """
        prev_x, prev_y = c_space_grid.pixel_to_world(prev_cell.x, prev_cell.y)
        curr_x, curr_y = c_space_grid.pixel_to_world(curr_cell.x, curr_cell.y)

        cell_width = c_space_grid.resolution
        cell_height = c_space_grid.resolution

        dx = curr_cell.x - prev_cell.x
        dy = curr_cell.y - prev_cell.y

        if dx > 0:
            return (
                Point(curr_x, curr_y - cell_height / 2),
                Point(curr_x, curr_y + cell_height / 2),
            )
        elif dx < 0:
            return (
                Point(curr_x + cell_width, curr_y - cell_height / 2),
                Point(curr_x + cell_width, curr_y + cell_height / 2),
            )
        elif dy > 0:
            return (
                Point(curr_x - cell_width / 2, curr_y),
                Point(curr_x + cell_width / 2, curr_y),
            )
        else:
            return (
                Point(curr_x - cell_width / 2, curr_y + cell_height),
                Point(curr_x + cell_width / 2, curr_y + cell_height),
            )

    def validate_smoothed_path(
        self, points: list[Point], c_space_grid: CSpaceGrid, samples_per_segment: int = 10
    ) -> bool:
        """Validate that a smoothed path is collision-free.

        Checks that each straight segment between consecutive points passes
        through free space in the C-Space grid.

        Args:
            points: Smoothed path as list of points
            c_space_grid: C-Space grid for validation
            samples_per_segment: Number of sample points per segment

        Returns:
            True if all segments are collision-free
        """
        if len(points) < 2:
            return True

        for i in range(1, len(points)):
            if not self._segment_is_clear(
                points[i - 1], points[i], c_space_grid, samples_per_segment
            ):
                return False
        return True

    def _segment_is_clear(
        self, p1: Point, p2: Point, c_space_grid: CSpaceGrid, samples: int
    ) -> bool:
        """Check if a line segment is collision-free.

        Args:
            p1: Start point
            p2: End point
            c_space_grid: C-Space grid for validation
            samples: Number of sample points along the segment

        Returns:
            True if the segment is collision-free
        """
        for t in np.linspace(0, 1, samples):
            x = p1.x + t * (p2.x - p1.x)
            y = p1.y + t * (p2.y - p1.y)
            if not c_space_grid.is_free(x, y):
                return False
        return True

    def path_length_reduction(self, grid_path: list[GridCell], smooth_path: list[Point]) -> float:
        """Calculate the path length reduction percentage.

        Args:
            grid_path: Original grid path (Manhattan length)
            smooth_path: Smoothed path (Euclidean length)

        Returns:
            Reduction percentage (e.g., 25.0 for 25% reduction)
        """
        if len(grid_path) < 2:
            return 0.0

        grid_length = self._grid_path_length(grid_path)
        smooth_length = sum(
            distance(smooth_path[i], smooth_path[i + 1]) for i in range(len(smooth_path) - 1)
        )

        if grid_length == 0:
            return 0.0

        return ((grid_length - smooth_length) / grid_length) * 100

    def _grid_path_length(self, cells: list[GridCell]) -> float:
        """Calculate Manhattan path length through grid cells.

        Args:
            cells: Grid path

        Returns:
            Total Manhattan distance
        """
        if len(cells) < 2:
            return 0.0

        total = 0.0
        for i in range(1, len(cells)):
            total += abs(cells[i].x - cells[i - 1].x) * self.resolution_mm
            total += abs(cells[i].y - cells[i - 1].y) * self.resolution_mm
        return total

    def min_segment_angle(self, points: list[Point]) -> float:
        """Find the minimum angle between consecutive segments.

        Args:
            points: Path as list of points

        Returns:
            Minimum angle in degrees (180 if fewer than 3 points)
        """
        if len(points) < 3:
            return 180.0

        min_angle = 180.0
        for i in range(1, len(points) - 1):
            v1 = (points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
            v2 = (points[i + 1].x - points[i].x, points[i + 1].y - points[i].y)

            dot = v1[0] * v2[0] + v1[1] * v2[1]
            mag1 = np.sqrt(v1[0] ** 2 + v1[1] ** 2)
            mag2 = np.sqrt(v2[0] ** 2 + v2[1] ** 2)

            if mag1 > 0 and mag2 > 0:
                cos_angle = dot / (mag1 * mag2)
                cos_angle = max(-1.0, min(1.0, cos_angle))
                angle = np.degrees(np.arccos(cos_angle))
                min_angle = min(min_angle, angle)

        return min_angle
