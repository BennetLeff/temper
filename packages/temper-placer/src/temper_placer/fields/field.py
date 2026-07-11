"""CostField — per-cell scalar grid aligned to the A* occupancy grid coordinate system.

Layer-uniform by default: the same per-cell cost applies to all routing layers.
U8 adds this to A* g_score without resampling via ``to_flat()`` which returns a
``congestion_flat``-compatible ``(height_cells * width_cells,)`` float32 array.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class CostField:
    """Per-cell scalar cost grid aligned to the occupancy grid coordinate system.

    The ``grid`` has shape ``(height_cells, width_cells)`` with float32 scalars
    at each cell.  Row-major (C-order) flattening via ``to_flat()`` produces
    the ``congestion_flat``-compatible 1-D array that A* consumes (index
    ``r * cols + c``).
    """

    grid: np.ndarray  # (height_cells, width_cells) float32
    cell_size_mm: float
    origin_mm: tuple[float, float]

    @property
    def shape(self) -> tuple[int, int]:
        """Grid shape as ``(height_cells, width_cells)``."""
        return (self.height_cells, self.width_cells)

    @property
    def height_cells(self) -> int:
        """Number of rows (y-dimension) in cells."""
        return int(self.grid.shape[0])

    @property
    def width_cells(self) -> int:
        """Number of columns (x-dimension) in cells."""
        return int(self.grid.shape[1])

    def to_flat(self) -> np.ndarray:
        """Return ``(height_cells * width_cells,)`` float32, congestion_flat-compatible.

        Flatten order is row-major (C-order), matching A*'s ``r * cols + c``
        cell-indexing convention.
        """
        import numpy as np

        return np.ascontiguousarray(self.grid.ravel()).astype(np.float32)

    @property
    def total_cells(self) -> int:
        """Total number of cells (height_cells * width_cells)."""
        return self.height_cells * self.width_cells
