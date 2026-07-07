"""
Router V6: Netclass-aware obstacle-grid pre-inflation.

Before routing each net, this module expands the binary occupancy grid
so that cells occupied by differently-classed already-routed nets are
inflated by the per-pair clearance from the YAML-configured
``ClearanceMatrix``.

Part of feat/netclass-clearance-ssot U6.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.netclass_rules import NetClassRulesDict
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

_SENTINEL: int = -2


def populate_clearance_matrix_from_rules(
    matrix: ClearanceMatrix,
    rules: NetClassRulesDict,
) -> None:
    """Populate a ``ClearanceMatrix`` from the YAML-derived netclass rules.

    Sets per-class rules and cross-class pair clearances so that
    ``get_clearance(net_a, net_b)`` resolves correctly for inflation.
    """
    for _class_name, class_rules in rules["net_classes"].items():
        matrix.add_net_class_rules(class_rules)

    for (class_a, class_b), clearance_mm in rules["pair_clearances"].items():
        matrix.set_class_to_class_clearance(class_a, class_b, clearance_mm)


def inflate_obstacles_by_netclass(
    grid: OccupancyGrid,
    current_net_name: str,
    id_to_net: dict[int, str],
    clearance_matrix: ClearanceMatrix,
    grid_cell_size: float,
) -> None:
    """Mark cells as occupied that are too close to differently-classed routes.

    For each cell already occupied by a previously-routed net:
    1. Resolve that net's class via ``clearance_matrix``.
    2. If the class differs from *current_net_name*'s class, compute the
       required clearance via ``clearance_matrix.get_clearance()``.
    3. Inflate a square region of radius ``ceil(clearance / grid_cell_size)``
       around the cell, marking free cells with the sentinel ``-2``.

    Call ``clear_netclass_inflation()`` after routing to restore sentinel
    cells.
    """
    height, width = grid.grid.shape
    occupied_ys, occupied_xs = np.where(grid.grid > 0)
    if len(occupied_ys) == 0:
        return

    current_class = clearance_matrix._net_to_class.get(current_net_name, "Default")

    for idx in range(len(occupied_ys)):
        cy, cx = occupied_ys[idx], occupied_xs[idx]
        cell_val = int(grid.grid[cy, cx])
        routed_net_name = id_to_net.get(cell_val)
        if routed_net_name is None or routed_net_name == current_net_name:
            continue

        # Same class: self-clearance already handled by _mark_route_blocked.
        routed_class = clearance_matrix._net_to_class.get(routed_net_name, "Default")
        if routed_class == current_class:
            continue

        clearance_mm = clearance_matrix.get_clearance(routed_net_name, current_net_name)
        radius_cells = int(math.ceil(clearance_mm / grid_cell_size))
        if radius_cells <= 0:
            continue

        x_start = max(0, cx - radius_cells)
        x_end = min(width, cx + radius_cells + 1)
        y_start = max(0, cy - radius_cells)
        y_end = min(height, cy + radius_cells + 1)

        region = grid.grid[y_start:y_end, x_start:x_end]
        region[(region == 0)] = _SENTINEL


def clear_netclass_inflation(grid: OccupancyGrid) -> None:
    """Clear cells that were temporarily inflated for netclass clearance."""
    grid.grid[grid.grid == _SENTINEL] = 0
