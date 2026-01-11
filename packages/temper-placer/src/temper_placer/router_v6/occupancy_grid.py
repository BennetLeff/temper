"""
Router V6 Stage 2.5: Build Occupancy Grid

Creates discretized routing grid for A* pathfinding.
Part of temper-8bj1 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from shapely.geometry import Point

from temper_placer.router_v6.routing_space import RoutingSpace


class CellState(Enum):
    """State of a grid cell."""

    FREE = 0  # Available for routing
    BLOCKED = 1  # Occupied by obstacle
    RESERVED = 2  # Reserved for specific net


@dataclass
class OccupancyGrid:
    """Discretized routing grid for pathfinding."""

    layer_name: str
    grid: np.ndarray  # 2D array of CellState values
    origin: tuple[float, float]  # (x, y) origin in mm
    cell_size: float  # Cell size in mm
    width_cells: int  # Grid width in cells
    height_cells: int  # Grid height in cells

    @property
    def width_mm(self) -> float:
        """Grid width in mm."""
        return self.width_cells * self.cell_size

    @property
    def height_mm(self) -> float:
        """Grid height in mm."""
        return self.height_cells * self.cell_size

    def is_free(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is free for routing."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            return self.grid[y_cell, x_cell] == CellState.FREE.value
        return False

    def is_blocked(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is blocked."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            return self.grid[y_cell, x_cell] == CellState.BLOCKED.value
        return False

    def world_to_grid(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates (mm) to grid coordinates."""
        x_cell = int((x_mm - self.origin[0]) / self.cell_size)
        y_cell = int((y_mm - self.origin[1]) / self.cell_size)
        return (x_cell, y_cell)

    def grid_to_world(self, x_cell: int, y_cell: int) -> tuple[float, float]:
        """Convert grid coordinates to world coordinates (mm)."""
        x_mm = self.origin[0] + (x_cell + 0.5) * self.cell_size
        y_mm = self.origin[1] + (y_cell + 0.5) * self.cell_size
        return (x_mm, y_mm)

    @property
    def free_cell_count(self) -> int:
        """Count of free cells."""
        return int(np.sum(self.grid == CellState.FREE.value))

    @property
    def blocked_cell_count(self) -> int:
        """Count of blocked cells."""
        return int(np.sum(self.grid == CellState.BLOCKED.value))

    @property
    def occupancy_ratio(self) -> float:
        """Ratio of blocked cells to total cells."""
        total = self.width_cells * self.height_cells
        return self.blocked_cell_count / total if total > 0 else 0.0

    def mark_path_blocked(
        self,
        path: list[tuple[float, float]],
        trace_width: float,
        clearance: float,
    ) -> None:
        """
        Mark cells occupied by a routed path (with clearance expansion).
        
        Args:
            path: List of (x, y) coordinates
            trace_width: Width of the trace in mm
            clearance: Required clearance in mm
        """
        # Calculate how many cells to block around center
        # width/2 + clearance gives blocking radius
        radius_mm = (trace_width / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))
        
        # Helper to mark a single point
        def mark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)
            
            # Simple square expansion for now (fast)
            # For 0.1mm grid, expansion=2 typically (0.2+0.127)/0.1 = 3.27 -> 4
            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)
            
            self.grid[y_start:y_end, x_start:x_end] = CellState.BLOCKED.value

        # Mark all points in path
        if not path:
            return
            
        # Rasterize lines between points
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i+1]
            
            # Interpolate for smooth blocking if segment is long
            dist = ((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)**0.5
            steps = int(np.ceil(dist / (self.cell_size / 2))) # 2x density for safety
            
            if steps > 0:
                for s in range(steps + 1):
                    t = s / steps
                    x = p1[0] + t * (p2[0] - p1[0])
                    y = p1[1] + t * (p2[1] - p1[1])
                    mark_point(x, y)


def build_occupancy_grid(
    routing_space: RoutingSpace,
    cell_size: float = 0.1,
    margin: float = 2.0,
) -> OccupancyGrid:
    """
    Build occupancy grid from routing space.

    Args:
        routing_space: Routing space from Stage 2.2
        cell_size: Grid cell size in mm (default 0.1mm)
        margin: Margin around routing area in mm

    Returns:
        OccupancyGrid with blocked cells marked

    Example:
        >>> grid = build_occupancy_grid(routing_space, cell_size=0.5)
        >>> grid.free_cell_count > 0
        True
    """
    # Get board bounds from routing space
    x_min, y_min, x_max, y_max = routing_space.available_area.bounds

    # Add margin
    x_min -= margin
    y_min -= margin
    x_max += margin
    y_max += margin

    # Calculate grid dimensions
    width_mm = x_max - x_min
    height_mm = y_max - y_min

    width_cells = max(1, int(np.ceil(width_mm / cell_size)))
    height_cells = max(1, int(np.ceil(height_mm / cell_size)))

    # Initialize grid as all blocked
    grid = np.full((height_cells, width_cells), CellState.BLOCKED.value, dtype=np.int8)

    # Mark cells that are inside routing space as free
    for y in range(height_cells):
        for x in range(width_cells):
            # Get cell center in world coordinates
            x_world = x_min + (x + 0.5) * cell_size
            y_world = y_min + (y + 0.5) * cell_size

            # Check if cell center is inside available routing area
            point = Point(x_world, y_world)
            if routing_space.available_area.contains(point):
                grid[y, x] = CellState.FREE.value

    return OccupancyGrid(
        layer_name=routing_space.layer_name,
        grid=grid,
        origin=(x_min, y_min),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )
