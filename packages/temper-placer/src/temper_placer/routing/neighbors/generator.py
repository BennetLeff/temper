"""Neighbor generation for maze routing A* algorithm.

Provides focused functions for generating neighbor cells:
- Cardinal neighbors (up, down, left, right)
- Layer change neighbors (via transitions)
- Combined neighbor generation with mode handling

These functions are extracted from MazeRouter._get_neighbors for better
testability and reusability.
"""

import numpy as np

from temper_placer.routing.grid import GridCell


def get_cardinal_neighbors(
    cell: GridCell,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    soft_blocking: bool = True,
    is_plane_layer: bool = False,
    allowed_layers: list[int] | None = None,
) -> list[GridCell]:
    """Generate cardinal (horizontal/vertical) neighbor cells.

    Args:
        cell: Current cell position
        occupancy: 3D occupancy grid (-1=blocked, 0=free, 2=routed)
        grid_size: (width, height) of the grid
        soft_blocking: If True, occupied cells (2) are traversable at high cost
        is_plane_layer: If True, no horizontal movement allowed on this layer
        allowed_layers: List of allowed layer indices, or None for all

    Returns:
        List of valid cardinal neighbor cells
    """
    neighbors = []

    # Skip horizontal movement on plane layers
    if is_plane_layer:
        return neighbors

    # Check if current layer is allowed
    if allowed_layers is not None and cell.layer not in allowed_layers:
        return neighbors

    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = cell.x + dx, cell.y + dy

        # Bounds check
        if not (0 <= nx < grid_size[0] and 0 <= ny < grid_size[1]):
            continue

        occ = int(occupancy[nx, ny, cell.layer])

        # Hard obstacle (-1) is always blocked
        if occ == -1:
            continue

        # Occupied (2) is blocked in strict mode (not soft_blocking)
        if occ == 2 and not soft_blocking:
            continue

        neighbors.append(GridCell(nx, ny, cell.layer))

    return neighbors


def get_layer_neighbors(
    cell: GridCell,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    soft_blocking: bool = True,
    allowed_layers: list[int] | None = None,
    num_layers: int = 1,
) -> list[GridCell]:
    """Generate layer change neighbor cells (via transitions).

    Args:
        cell: Current cell position
        occupancy: 3D occupancy grid (-1=blocked, 0=free, 2=routed)
        grid_size: (width, height) of the grid
        soft_blocking: If True, occupied cells (2) are traversable at high cost
        allowed_layers: List of allowed layer indices, or None for all
        num_layers: Total number of layers in the board

    Returns:
        List of valid layer change neighbor cells (same x,y, different layer)
    """
    neighbors = []

    if num_layers <= 1:
        return neighbors

    layers = allowed_layers if allowed_layers is not None else list(range(num_layers))

    for nl in layers:
        # Skip same layer and invalid indices
        if nl == cell.layer or not (0 <= nl < num_layers):
            continue

        occ = int(occupancy[cell.x, cell.y, nl])

        # Hard obstacle (-1) is always blocked
        if occ == -1:
            continue

        # Occupied (2) is blocked in strict mode (not soft_blocking)
        if occ == 2 and not soft_blocking:
            continue

        neighbors.append(GridCell(cell.x, cell.y, nl))

    return neighbors


def get_all_neighbors(
    cell: GridCell,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    soft_blocking: bool = True,
    is_plane_layer: bool = False,
    allow_layer_change: bool = False,
    allowed_layers: list[int] | None = None,
    num_layers: int = 1,
) -> list[GridCell]:
    """Generate all valid neighbor cells (cardinal + layer changes).

    This is the main function that combines cardinal and layer neighbor generation.

    Args:
        cell: Current cell position
        occupancy: 3D occupancy grid (-1=blocked, 0=free, 2=routed)
        grid_size: (width, height) of the grid
        soft_blocking: If True, occupied cells (2) are traversable at high cost
        is_plane_layer: If True, no horizontal movement allowed on this layer
        allow_layer_change: If True, generate layer change neighbors
        allowed_layers: List of allowed layer indices, or None for all
        num_layers: Total number of layers in the board

    Returns:
        List of all valid neighbor cells
    """
    neighbors = []

    # Cardinal neighbors
    cardinal = get_cardinal_neighbors(
        cell=cell,
        occupancy=occupancy,
        grid_size=grid_size,
        soft_blocking=soft_blocking,
        is_plane_layer=is_plane_layer,
        allowed_layers=allowed_layers,
    )
    neighbors.extend(cardinal)

    # Layer change neighbors
    if allow_layer_change:
        layer = get_layer_neighbors(
            cell=cell,
            occupancy=occupancy,
            grid_size=grid_size,
            soft_blocking=soft_blocking,
            allowed_layers=allowed_layers,
            num_layers=num_layers,
        )
        neighbors.extend(layer)

    return neighbors


def count_neighbors(
    cell: GridCell,
    occupancy: np.ndarray,
    grid_size: tuple[int, int],
    soft_blocking: bool = True,
    is_plane_layer: bool = False,
    allow_layer_change: bool = False,
    allowed_layers: list[int] | None = None,
    num_layers: int = 1,
) -> int:
    """Count the number of valid neighbors for a cell.

    Useful for analyzing routing density and identifying constrained cells.

    Args:
        cell: Current cell position
        occupancy: 3D occupancy grid
        grid_size: (width, height) of the grid
        soft_blocking: If True, occupied cells are traversable
        is_plane_layer: If True, no horizontal movement allowed
        allow_layer_change: If True, include layer change neighbors
        allowed_layers: List of allowed layer indices
        num_layers: Total number of layers

    Returns:
        Number of valid neighbor cells
    """
    neighbors = get_all_neighbors(
        cell=cell,
        occupancy=occupancy,
        grid_size=grid_size,
        soft_blocking=soft_blocking,
        is_plane_layer=is_plane_layer,
        allow_layer_change=allow_layer_change,
        allowed_layers=allowed_layers,
        num_layers=num_layers,
    )
    return len(neighbors)
