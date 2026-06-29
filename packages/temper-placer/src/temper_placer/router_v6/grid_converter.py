"""
Grid coordinate conversion utilities for router export.

Converts internal routing grid cells to PCB world coordinates (mm).
"""

from dataclasses import dataclass


@dataclass
class GridCell:
    """Grid cell coordinates (x, y, layer)."""

    x: int
    y: int
    layer: int = 0


def grid_to_world(
    cell: GridCell,
    origin: tuple[float, float],
    cell_size: float,
) -> tuple[float, float]:
    """Convert grid cell to world coordinates (mm).

    Returns center of cell in PCB coordinate system.

    Args:
        cell: Grid cell coordinates
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm

    Returns:
        (x, y) position in mm, at cell center

    Example:
        >>> cell = GridCell(x=10, y=20, layer=0)
        >>> grid_to_world(cell, origin=(0, 0), cell_size=0.5)
        (5.25, 10.25)  # Cell center at (10*0.5 + 0.5/2, 20*0.5 + 0.5/2)
    """
    x = origin[0] + cell.x * cell_size + cell_size / 2
    y = origin[1] + cell.y * cell_size + cell_size / 2
    return (x, y)


def extract_vias(cells: list[GridCell]) -> list[int]:
    """Find indices where layer transitions occur.

    A via is required when consecutive cells are on different layers.

    Args:
        cells: Ordered list of grid cells forming a path

    Returns:
        List of cell indices where vias are needed

    Example:
        >>> cells = [
        ...     GridCell(0, 0, 0),
        ...     GridCell(1, 0, 0),
        ...     GridCell(1, 0, 1),  # Via here
        ...     GridCell(2, 0, 1),
        ... ]
        >>> extract_vias(cells)
        [2]  # Via at index 2 (transition from layer 0 to 1)
    """
    via_indices = []
    for i in range(1, len(cells)):
        if cells[i].layer != cells[i - 1].layer:
            via_indices.append(i)
    return via_indices


def compute_path_length(cells: list[GridCell], cell_size: float) -> float:
    """Calculate total path length in mm (Manhattan distance).

    Args:
        cells: Ordered list of grid cells forming a path
        cell_size: Grid cell size in mm

    Returns:
        Total path length in mm

    Example:
        >>> cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        >>> compute_path_length(cells, cell_size=0.5)
        1.0  # 2 steps * 0.5mm
    """
    if len(cells) < 2:
        return 0.0

    total_length = 0.0
    for i in range(1, len(cells)):
        # Manhattan distance between consecutive cells
        dx = abs(cells[i].x - cells[i - 1].x)
        dy = abs(cells[i].y - cells[i - 1].y)
        # Layer change doesn't add physical length (via is at same x,y)
        total_length += (dx + dy) * cell_size

    return total_length


def count_vias_in_path(cells: list[GridCell]) -> int:
    """Count the number of layer transitions (vias) in a path.

    Args:
        cells: Ordered list of grid cells forming a path

    Returns:
        Number of vias needed

    Example:
        >>> cells = [
        ...     GridCell(0, 0, 0),  # L0
        ...     GridCell(1, 0, 1),  # L1 - via 1
        ...     GridCell(2, 0, 1),
        ...     GridCell(3, 0, 0),  # L0 - via 2
        ... ]
        >>> count_vias_in_path(cells)
        2
    """
    return len(extract_vias(cells))
