"""
Grid coordinate conversion utilities for router export.

Converts internal routing grid cells to PCB world coordinates (mm).

Wave-4 migration note: the four kernels now run in the ``temper-geometry``
crate (``via_clearance.rs``) — ``grid_to_world_py``,
``extract_vias_py``, ``compute_path_length_py``, ``count_vias_in_path_py``.
The ``GridCell`` dataclass and the module-level public functions stay here
and delegate.  Bit-identical parity is pinned by
``tests/router_v6/test_via_clearance_tier2_rust_differential.py``.
"""

from dataclasses import dataclass

import temper_geometry as _tg


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
    return _tg.grid_to_world_py(cell.x, cell.y, origin[0], origin[1], cell_size)


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
    return list(_tg.extract_vias_py([c.layer for c in cells]))


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
    return _tg.compute_path_length_py(
        [c.x for c in cells], [c.y for c in cells], cell_size
    )


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
    return _tg.count_vias_in_path_py([c.layer for c in cells])
