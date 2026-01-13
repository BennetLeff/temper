"""Grid coordinate conversion utilities for maze routing.

Provides a centralized GridConverter class for world-to-grid and grid-to-world
coordinate transformations, ensuring consistent behavior across all routing code.
"""

from dataclasses import dataclass
from typing import NamedTuple


class GridCell(NamedTuple):
    """A cell in the routing grid."""

    x: int
    y: int
    layer: int = 0

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.layer))


@dataclass(frozen=True)
class GridConverter:
    """Converts between world coordinates and grid cell indices.

    Provides a single source of truth for all coordinate transformations,
    eliminating duplication and ensuring consistent clamping behavior.

    Example:
        >>> converter = GridConverter(
        ...     grid_size=(100, 100),
        ...     cell_size=0.2,
        ...     origin=(0.0, 0.0)
        ... )
        >>> converter.world_to_grid(5.0, 3.0)
        (25, 15)
        >>> converter.grid_to_world(25, 15)
        (5.0, 3.0)
    """

    grid_size: tuple[int, int]
    cell_size: float
    origin: tuple[float, float]

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid cell indices.

        Uses rounding for nearest-cell mapping, then clamps to valid range.

        Args:
            x: World X coordinate in mm
            y: World Y coordinate in mm

        Returns:
            Tuple of (grid_x, grid_y) cell indices
        """
        gx = int(round((x - self.origin[0]) / self.cell_size))
        gy = int(round((y - self.origin[1]) / self.cell_size))
        return self._clamp(gx, gy)

    def world_to_grid_floor(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates using floor instead of round.

        Uses truncation for cell mapping, then clamps to valid range.

        Args:
            x: World X coordinate in mm
            y: World Y coordinate in mm

        Returns:
            Tuple of (grid_x, grid_y) cell indices
        """
        gx = int((x - self.origin[0]) / self.cell_size)
        gy = int((y - self.origin[1]) / self.cell_size)
        return self._clamp(gx, gy)

    def world_to_grid_cell(self, x: float, y: float, layer: int = 0) -> GridCell:
        """Convert world coordinates to a GridCell.

        Args:
            x: World X coordinate in mm
            y: World Y coordinate in mm
            layer: Layer index (default 0)

        Returns:
            GridCell with grid coordinates and layer
        """
        gx, gy = self.world_to_grid(x, y)
        return GridCell(gx, gy, layer)

    def grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        """Convert grid cell indices to world coordinates.

        Returns the center of the grid cell in world coordinates.

        Args:
            gx: Grid X index
            gy: Grid Y index

        Returns:
            Tuple of (world_x, world_y) in mm
        """
        wx = gx * self.cell_size + self.origin[0]
        wy = gy * self.cell_size + self.origin[1]
        return (wx, wy)

    def grid_to_world_center(self, gx: int, gy: int, layer: int = 0) -> tuple[float, float]:
        """Convert grid cell to world coordinates at cell center.

        Args:
            gx: Grid X index
            gy: Grid Y index
            layer: Layer index (unused, for API consistency)

        Returns:
            Tuple of (world_x, world_y) at cell center in mm
        """
        return self.grid_to_world(gx, gy)

    def clamp_to_grid(self, gx: int, gy: int) -> tuple[int, int]:
        """Clamp grid coordinates to valid range.

        Args:
            gx: Grid X index (may be out of bounds)
            gy: Grid Y index (may be out of bounds)

        Returns:
            Tuple of (clamped_x, clamped_y) within valid grid bounds
        """
        return self._clamp(gx, gy)

    def is_valid_cell(self, gx: int, gy: int) -> bool:
        """Check if grid coordinates are within bounds.

        Args:
            gx: Grid X index
            gy: Grid Y index

        Returns:
            True if coordinates are within valid grid bounds
        """
        return 0 <= gx < self.grid_size[0] and 0 <= gy < self.grid_size[1]

    def is_valid_cell_3d(self, gx: int, gy: int, layer: int) -> bool:
        """Check if 3D grid coordinates are within bounds.

        Args:
            gx: Grid X index
            gy: Grid Y index
            layer: Layer index

        Returns:
            True if coordinates are within valid grid bounds
        """
        return self.is_valid_cell(gx, gy) and 0 <= layer < getattr(self, "_num_layers", 1)

    def _clamp(self, gx: int, gy: int) -> tuple[int, int]:
        """Clamp coordinates to valid grid range."""
        return (
            max(0, min(self.grid_size[0] - 1, gx)),
            max(0, min(self.grid_size[1] - 1, gy)),
        )

    def distance_cells(self, gx1: int, gy1: int, gx2: int, gy2: int) -> float:
        """Manhattan distance between two grid cells.

        Args:
            gx1, gy1: First cell coordinates
            gx2, gy2: Second cell coordinates

        Returns:
            Manhattan distance in cells
        """
        return abs(gx1 - gx2) + abs(gy1 - gy2)

    def distance_world(self, wx1: float, wy1: float, wx2: float, wy2: float) -> float:
        """Euclidean distance between two world coordinates.

        Args:
            wx1, wy1: First point in mm
            wx2, wy2: Second point in mm

        Returns:
            Euclidean distance in mm
        """
        dx = wx2 - wx1
        dy = wy2 - wy1
        return (dx * dx + dy * dy) ** 0.5
