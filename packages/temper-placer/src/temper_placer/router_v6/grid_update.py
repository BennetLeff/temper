"""
Router V6 Stage 4.6: Update Occupancy Grid

Updates occupancy grid to mark routed traces as occupied.
Part of temper-t523 (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid


def update_occupancy_grid(
    grid: OccupancyGrid,
    pathfinding_result: PathfindingResult,
    clearance_cells: int = 1,
) -> None:
    """
    Update occupancy grid to mark routed traces as occupied.

    Marks cells occupied by routed paths and adds clearance inflation
    to prevent subsequent routes from violating DRC.

    Args:
        grid: Occupancy grid to update (modified in place)
        pathfinding_result: Routed paths from Stage 4.2
        clearance_cells: Number of cells around trace to block (clearance)

    Example:
        >>> import numpy as np
        >>> from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> grid = OccupancyGrid("F.Cu", np.zeros((10, 10), dtype=np.int8), (0, 0), 1.0, 10, 10)
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> update_occupancy_grid(grid, result)
    """
    for net_name, route_path in pathfinding_result.routed_paths.items():
        # Mark all cells along the route as occupied
        _mark_path_occupied(grid, route_path, clearance_cells)


def _mark_path_occupied(
    grid: OccupancyGrid,
    route_path,
    clearance_cells: int,
) -> None:
    """
    Mark a single routed path as occupied in the grid.

    Args:
        grid: Occupancy grid
        route_path: RoutePath to mark
        clearance_cells: Clearance inflation
    """
    # Convert each coordinate to grid cells and mark as occupied
    for coord in route_path.coordinates:
        x_mm, y_mm = coord
        x_cell, y_cell = grid.world_to_grid(x_mm, y_mm)
        
        # Mark this cell and surrounding clearance cells as occupied
        for dx in range(-clearance_cells, clearance_cells + 1):
            for dy in range(-clearance_cells, clearance_cells + 1):
                cell_x = x_cell + dx
                cell_y = y_cell + dy
                
                # Check bounds
                if 0 <= cell_x < grid.width_cells and 0 <= cell_y < grid.height_cells:
                    # Mark as blocked/reserved
                    grid.grid[cell_y, cell_x] = CellState.RESERVED.value
