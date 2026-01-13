"""
Signed Distance Field (SDF) Builder.

Converts discrete occupancy grids into high-precision signed distance fields
for continuous optimization.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


class SDFGrid:
    """
    Continuous Signed Distance Field wrapper around a discrete grid.

    Provides query methods for distance and gradient at arbitrary (x, y) coordinates.
    """

    def __init__(
        self,
        distance_grid: np.ndarray,
        origin: tuple[float, float],
        cell_size: float,
        width_cells: int,
        height_cells: int,
    ):
        self.distance_grid = distance_grid  # SDF values (positive = safe)
        self.origin = origin
        self.cell_size = cell_size
        self.width_cells = width_cells
        self.height_cells = height_cells

        # Precompute gradients for faster query
        # Gradient of distance field points towards safety (away from obstacles)
        self.grad_y, self.grad_x = np.gradient(distance_grid, cell_size)

    @classmethod
    def from_occupancy_grid(cls, occupancy_grid: OccupancyGrid, clearance_mm: float) -> SDFGrid:
        """
        Create an SDF from an occupancy grid.

        Args:
            occupancy_grid: The discrete grid (0=Free, !=0=Blocked)
            clearance_mm: The required safety margin.
                          The SDF will be shifted so 0 = exact clearance boundary.
        """
        # 1. Create binary mask (True = Blocked/Obstacle)
        # Note: We treat EVERYTHING non-zero as an obstacle initially
        obstacle_mask = occupancy_grid.grid != 0

        # 2. Compute Euclidean Distance Transform (EDT)
        # distance_transform_edt computes distance to nearest zero (background)
        # So we invert: distance from free space to nearest obstacle?
        # No, we want distance FROM obstacle boundary into free space.

        # Inside free space (0): distance to nearest obstacle (1)
        dist_free = distance_transform_edt(
            occupancy_grid.grid == 0, sampling=occupancy_grid.cell_size
        )

        # Inside obstacle (1): distance to nearest free space (0) (negative distance)
        dist_obstacle = distance_transform_edt(
            occupancy_grid.grid != 0, sampling=occupancy_grid.cell_size
        )

        # Combine: Positive in free space, Negative inside obstacles
        # On the boundary, dist is 0.
        raw_sdf = dist_free - dist_obstacle

        # 3. Shift by clearance
        # We want SDF=0 to mean "exactly clearance_mm away from obstacle surface"
        # Since occupancy grid blocks usually represent the *exact* obstacle + margin,
        # we need to be careful.
        #
        # In Router V6, occupancy grid cells are marked blocked if they are within
        # (trace_width/2 + clearance) of an obstacle.
        # So the boundary of 'Blocked' cells is ALREADY the safety boundary.
        #
        # Therefore, raw_sdf=0 is the safety boundary.
        # Positive values = Extra margin.
        # Negative values = Violation.

        return cls(
            distance_grid=raw_sdf,
            origin=occupancy_grid.origin,
            cell_size=occupancy_grid.cell_size,
            width_cells=occupancy_grid.width_cells,
            height_cells=occupancy_grid.height_cells,
        )

    def get_distance(self, x: float, y: float) -> float:
        """Get signed distance at world coordinates (bilinear interpolation)."""
        gx = (x - self.origin[0]) / self.cell_size - 0.5
        gy = (y - self.origin[1]) / self.cell_size - 0.5

        # Check bounds
        if not (0 <= gx < self.width_cells - 1 and 0 <= gy < self.height_cells - 1):
            return -1.0  # Treat out of bounds as obstacle/violation

        # Bilinear interpolation
        x0 = int(gx)
        y0 = int(gy)
        dx = gx - x0
        dy = gy - y0

        v00 = self.distance_grid[y0, x0]
        v10 = self.distance_grid[y0, x0 + 1]
        v01 = self.distance_grid[y0 + 1, x0]
        v11 = self.distance_grid[y0 + 1, x0 + 1]

        top = v00 * (1 - dx) + v10 * dx
        bottom = v01 * (1 - dx) + v11 * dx
        return top * (1 - dy) + bottom * dy

    def get_gradient(self, x: float, y: float) -> tuple[float, float]:
        """Get gradient (dx, dy) at world coordinates."""
        gx = (x - self.origin[0]) / self.cell_size - 0.5
        gy = (y - self.origin[1]) / self.cell_size - 0.5

        if not (0 <= gx < self.width_cells - 1 and 0 <= gy < self.height_cells - 1):
            return (0.0, 0.0)

        x0 = int(gx)
        y0 = int(gy)
        dx = gx - x0
        dy = gy - y0

        # Interpolate gradients
        # X gradient
        gx00 = self.grad_x[y0, x0]
        gx10 = self.grad_x[y0, x0 + 1]
        gx01 = self.grad_x[y0 + 1, x0]
        gx11 = self.grad_x[y0 + 1, x0 + 1]
        grad_x = (gx00 * (1 - dx) + gx10 * dx) * (1 - dy) + (gx01 * (1 - dx) + gx11 * dx) * dy

        # Y gradient
        gy00 = self.grad_y[y0, x0]
        gy10 = self.grad_y[y0, x0 + 1]
        gy01 = self.grad_y[y0 + 1, x0]
        gy11 = self.grad_y[y0 + 1, x0 + 1]
        grad_y = (gy00 * (1 - dx) + gy10 * dx) * (1 - dy) + (gy01 * (1 - dx) + gy11 * dx) * dy

        return (grad_x, grad_y)
