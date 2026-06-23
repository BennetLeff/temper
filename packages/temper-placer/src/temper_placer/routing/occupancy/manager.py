"""Occupancy management for maze routing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.grid import GridCell


class OccupancyManager:
    """Manages grid cell occupancy, net ownership, and congestion tracking.

    Provides a clean API for tracking which net owns which cells,
    managing blocked/occupied/free states, and handling rip-up and re-routing.
    """

    OCCUPIED = 2
    BLOCKED = -1
    FREE = 0

    def __init__(self, grid_size: tuple[int, int], num_layers: int = 1):
        """Initialize the occupancy manager.

        Args:
            grid_size: Tuple of (width, height) for the grid
            num_layers: Number of layers in the board
        """
        self.grid_size = grid_size
        self.num_layers = num_layers
        self.occupancy = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        self.net_occupancy: dict[tuple[int, int, int], set[str]] = {}
        self.cell_owner: dict[tuple[int, int, int], str] = {}
        self.owner_grid = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        self.congestion = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.float32)
        self._net_to_id: dict[str, int] = {}
        self._next_net_id = 1
        self._init_bitmap()

    def _is_valid(self, x: int, y: int, layer: int) -> bool:
        """Check if coordinates are within bounds."""
        return (
            0 <= x < self.grid_size[0]
            and 0 <= y < self.grid_size[1]
            and 0 <= layer < self.num_layers
        )

    def _key(self, x: int, y: int, layer: int) -> tuple[int, int, int]:
        """Create a tuple key for cell coordinates."""
        return (x, y, layer)

    def _init_bitmap(self) -> None:
        cols = self.grid_size[0]
        rows = self.grid_size[1]
        self._bitmap_stride = (cols + 63) // 64
        self.occupancy_bitmap = np.zeros(
            (rows, self._bitmap_stride, self.num_layers), dtype=np.uint64
        )

    def _sync_bitmap(self, net_id: int = 0) -> None:
        for layer in range(self.num_layers):
            occ = self.occupancy[:, :, layer]
            for row in range(self.grid_size[1]):
                for word in range(self._bitmap_stride):
                    start_col = word * 64
                    end_col = min(start_col + 64, self.grid_size[0])
                    word_val = np.uint64(0)
                    for col in range(start_col, end_col):
                        val = int(occ[col, row])
                        if val != 0 and val != net_id:
                            word_val |= np.uint64(1) << np.uint64(col - start_col)
                    self.occupancy_bitmap[row, word, layer] = word_val

    def _set_bitmap_bit(self, x: int, y: int, layer: int, blocked: bool) -> None:
        if not self._is_valid(x, y, layer):
            return
        word = x // 64
        bit = x % 64
        if blocked:
            self.occupancy_bitmap[y, word, layer] |= np.uint64(1) << np.uint64(bit)
        else:
            self.occupancy_bitmap[y, word, layer] &= ~(np.uint64(1) << np.uint64(bit))

    def _is_blocked_bitmap(self, x: int, y: int, layer: int) -> bool:
        if not self._is_valid(x, y, layer):
            return True
        word = x // 64
        bit = x % 64
        return bool(self.occupancy_bitmap[y, word, layer] & (np.uint64(1) << np.uint64(bit)))

    def get_net_id(self, net_name: str) -> int:
        """Get or create a numeric ID for a net name.

        Args:
            net_name: The name of the net

        Returns:
            Numeric ID for the net
        """
        if net_name not in self._net_to_id:
            self._net_to_id[net_name] = self._next_net_id
            self._next_net_id += 1
        return self._net_to_id[net_name]

    def block_cells(
        self,
        cells: list[GridCell] | list[tuple[int, int, int]],
        net_name: str | None = None,
    ) -> None:
        """Block multiple cells for routing.

        Args:
            cells: List of cell coordinates or GridCell objects
            net_name: Optional net name that is blocking these cells
        """
        for cell in cells:
            if isinstance(cell, tuple):
                x, y, layer = cell
            else:
                x, y, layer = cell.x, cell.y, cell.layer
            if self._is_valid(x, y, layer):
                self.occupancy[x, y, layer] = self.BLOCKED
                self._set_bitmap_bit(x, y, layer, True)
                if net_name is not None:
                    key = self._key(x, y, layer)
                    if key not in self.cell_owner:
                        self.cell_owner[key] = net_name
                        self.owner_grid[x, y, layer] = self.get_net_id(net_name)

    def unblock_cells(
        self,
        cells: list[GridCell] | list[tuple[int, int, int]],
        net_name: str | None = None,
    ) -> None:
        """Unblock multiple cells, making them free.

        Args:
            cells: List of cell coordinates or GridCell objects
            net_name: Optional net name to verify ownership before unblocking
        """
        for cell in cells:
            if isinstance(cell, tuple):
                x, y, layer = cell
            else:
                x, y, layer = cell.x, cell.y, cell.layer
            if not self._is_valid(x, y, layer):
                continue
            key = self._key(x, y, layer)
            if net_name is not None and self.cell_owner.get(key) != net_name:
                continue
            self.occupancy[x, y, layer] = self.FREE
            self._set_bitmap_bit(x, y, layer, False)

    def mark_routed(
        self,
        cells: list[GridCell] | list[tuple[int, int, int]],
        net_name: str,
    ) -> None:
        """Mark cells as routed by a specific net.

        Args:
            cells: List of cell coordinates or GridCell objects
            net_name: The name of the net that routed these cells
        """
        net_id = self.get_net_id(net_name)
        for cell in cells:
            if isinstance(cell, tuple):
                x, y, layer = cell
            else:
                x, y, layer = cell.x, cell.y, cell.layer
            if not self._is_valid(x, y, layer):
                continue
            key = self._key(x, y, layer)
            self.occupancy[x, y, layer] = self.OCCUPIED
            self._set_bitmap_bit(x, y, layer, True)
            if key not in self.net_occupancy:
                self.net_occupancy[key] = set()
            self.net_occupancy[key].add(net_name)
            self.congestion[x, y, layer] = len(self.net_occupancy[key])
            if key not in self.cell_owner:
                self.cell_owner[key] = net_name
                self.owner_grid[x, y, layer] = net_id

    def rip_up_net(self, net_name: str) -> list[tuple[int, int, int]]:
        """Rip up all cells routed by a specific net.

        Args:
            net_name: The name of the net to rip up

        Returns:
            List of cell coordinates that were freed
        """
        freed_cells = []
        for key in list(self.cell_owner.keys()):
            if self.cell_owner[key] == net_name:
                x, y, layer = key
                self.occupancy[x, y, layer] = self.FREE
                self._set_bitmap_bit(x, y, layer, False)
                del self.net_occupancy[key]
                del self.cell_owner[key]
                self.owner_grid[x, y, layer] = 0
                self.congestion[x, y, layer] = 0.0
                freed_cells.append(key)
        return freed_cells

    def get_cell_owner(
        self,
        cell: GridCell | tuple[int, int, int],
    ) -> str | None:
        """Get the net name that owns a cell.

        Args:
            cell: Cell coordinates or GridCell object

        Returns:
            Net name that owns the cell, or None if free
        """
        if isinstance(cell, tuple):
            x, y, layer = cell
        else:
            x, y, layer = cell.x, cell.y, cell.layer
        if not self._is_valid(x, y, layer):
            return None
        return self.cell_owner.get(self._key(x, y, layer))

    def is_blocked(self, x: int, y: int, layer: int) -> bool:
        """Check if a cell is blocked.

        Args:
            x, y, layer: Cell coordinates

        Returns:
            True if cell is blocked or out of bounds
        """
        if not self._is_valid(x, y, layer):
            return True
        return self.occupancy[x, y, layer] == self.BLOCKED

    def is_occupied(self, x: int, y: int, layer: int) -> bool:
        """Check if a cell is occupied by any route.

        Args:
            x, y, layer: Cell coordinates

        Returns:
            True if cell is occupied
        """
        if not self._is_valid(x, y, layer):
            return False
        return self.occupancy[x, y, layer] == self.OCCUPIED

    def is_free(self, x: int, y: int, layer: int) -> bool:
        """Check if a cell is free for routing.

        Args:
            x, y, layer: Cell coordinates

        Returns:
            True if cell is free
        """
        if not self._is_valid(x, y, layer):
            return False
        return self.occupancy[x, y, layer] == self.FREE

    def get_occupancy(self, x: int, y: int, layer: int) -> int:
        """Get the occupancy value for a cell.

        Args:
            x, y, layer: Cell coordinates

        Returns:
            Occupancy value (BLOCKED, OCCUPIED, or FREE)
        """
        if not self._is_valid(x, y, layer):
            return self.BLOCKED
        return int(self.occupancy[x, y, layer])

    def get_stats(self) -> dict[str, int]:
        """Get occupancy statistics.

        Returns:
            Dictionary with counts of free, blocked, routed, and congested cells
        """
        return {
            "free_cells": int(np.sum(self.occupancy == self.FREE)),
            "blocked_cells": int(np.sum(self.occupancy == self.BLOCKED)),
            "routed_cells": int(np.sum(self.occupancy == self.OCCUPIED)),
            "congested_cells": int(np.sum(self.congestion > 1.0)),
        }

    def get_all_routed_cells(self, net_name: str | None = None) -> list[tuple[int, int, int]]:
        """Get all cells that are routed.

        Args:
            net_name: Optional filter for specific net

        Returns:
            List of cell coordinates
        """
        cells = []
        for key, nets in self.net_occupancy.items():
            if net_name is None or net_name in nets:
                cells.append(key)
        return cells

    def clear_all(self) -> None:
        """Clear all occupancy data, resetting to free state."""
        self.occupancy.fill(self.FREE)
        self.occupancy_bitmap.fill(0)
        self.net_occupancy.clear()
        self.cell_owner.clear()
        self.owner_grid.fill(0)
        self.congestion.fill(0.0)

    def resize(self, new_grid_size: tuple[int, int]) -> None:
        """Resize the occupancy grid.

        Args:
            new_grid_size: New (width, height) for the grid
        """
        self.grid_size = new_grid_size
        self.occupancy = np.zeros(
            (new_grid_size[0], new_grid_size[1], self.num_layers), dtype=np.int32
        )
        self.owner_grid = np.zeros(
            (new_grid_size[0], new_grid_size[1], self.num_layers), dtype=np.int32
        )
        self.congestion = np.zeros(
            (new_grid_size[0], new_grid_size[1], self.num_layers), dtype=np.float32
        )
        self._init_bitmap()
        self.net_occupancy.clear()
        self.cell_owner.clear()
