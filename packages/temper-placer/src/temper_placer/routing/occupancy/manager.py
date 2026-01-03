"""Occupancy management for maze routing."""

import numpy as np


class OccupancyManager:
    """Manages grid cell occupancy, net ownership, and congestion tracking."""

    OCCUPIED = 2
    BLOCKED = -1
    FREE = 0

    def __init__(self, grid_size, num_layers=1):
        self.grid_size = grid_size
        self.num_layers = num_layers
        self.occupancy = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        self.net_occupancy = {}
        self.cell_owner = {}
        self.owner_grid = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        self.congestion = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.float32)
        self._net_to_id = {}
        self._next_net_id = 1

    def _is_valid(self, x, y, layer):
        return (
            0 <= x < self.grid_size[0]
            and 0 <= y < self.grid_size[1]
            and 0 <= layer < self.num_layers
        )

    def get_net_id(self, net_name):
        if net_name not in self._net_to_id:
            self._net_to_id[net_name] = self._next_net_id
            self._next_net_id += 1
        return self._net_to_id[net_name]

    def block_cell(self, x, y, layer):
        if self._is_valid(x, y, layer):
            self.occupancy[x, y, layer] = self.BLOCKED

    def block_cells(self, cells):
        for x, y, layer in cells:
            if self._is_valid(x, y, layer):
                self.occupancy[x, y, layer] = self.BLOCKED

    def unblock_cell(self, x, y, layer):
        if self._is_valid(x, y, layer):
            self.occupancy[x, y, layer] = self.FREE

    def mark_routed(self, cells, net_name):
        net_id = self.get_net_id(net_name)
        for x, y, layer in cells:
            if not self._is_valid(x, y, layer):
                continue
            key = (x, y, layer)
            was_routed = self.occupancy[x, y, layer] == self.OCCUPIED
            self.occupancy[x, y, layer] = self.OCCUPIED
            if key not in self.net_occupancy:
                self.net_occupancy[key] = set()
            self.net_occupancy[key].add(net_name)
            self.congestion[x, y, layer] = len(self.net_occupancy[key])
            if key not in self.cell_owner:
                self.cell_owner[key] = net_name
                self.owner_grid[x, y, layer] = net_id

    def rip_up_net(self, net_name, cells):
        for x, y, layer in cells:
            if not self._is_valid(x, y, layer):
                continue
            key = (x, y, layer)
            if key in self.net_occupancy:
                self.net_occupancy[key].discard(net_name)
                if not self.net_occupancy[key]:
                    self.occupancy[x, y, layer] = self.FREE
                    del self.net_occupancy[key]
                    del self.cell_owner[key]
                    self.owner_grid[x, y, layer] = 0
                    self.congestion[x, y, layer] = 0.0
                else:
                    if self.cell_owner.get(key) == net_name:
                        remaining_net = next(iter(self.net_occupancy[key]))
                        self.cell_owner[key] = remaining_net
                        self.owner_grid[x, y, layer] = self.get_net_id(remaining_net)
                    self.congestion[x, y, layer] = len(self.net_occupancy[key])

    def get_cell_owner(self, x, y, layer):
        if not self._is_valid(x, y, layer):
            return None
        return self.cell_owner.get((x, y, layer))

    def is_blocked(self, x, y, layer):
        if not self._is_valid(x, y, layer):
            return True
        return self.occupancy[x, y, layer] == self.BLOCKED

    def is_occupied(self, x, y, layer):
        if not self._is_valid(x, y, layer):
            return False
        return self.occupancy[x, y, layer] == self.OCCUPIED

    def is_free(self, x, y, layer):
        if not self._is_valid(x, y, layer):
            return False
        return self.occupancy[x, y, layer] == self.FREE

    def get_occupancy(self, x, y, layer):
        if not self._is_valid(x, y, layer):
            return self.BLOCKED
        return int(self.occupancy[x, y, layer])

    def get_stats(self):
        return {
            "free_cells": int(np.sum(self.occupancy == self.FREE)),
            "blocked_cells": int(np.sum(self.occupancy == self.BLOCKED)),
            "routed_cells": int(np.sum(self.occupancy == self.OCCUPIED)),
            "congested_cells": int(np.sum(self.congestion > 1.0)),
        }

    def get_all_routed_cells(self, net_name=None):
        cells = []
        for key, nets in self.net_occupancy.items():
            if net_name is None or net_name in nets:
                cells.append(key)
        return cells

    def clear_all(self):
        self.occupancy.fill(self.FREE)
        self.net_occupancy.clear()
        self.cell_owner.clear()
        self.owner_grid.fill(0)
        self.congestion.fill(0.0)

    def resize(self, new_grid_size):
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
        self.net_occupancy.clear()
        self.cell_owner.clear()
