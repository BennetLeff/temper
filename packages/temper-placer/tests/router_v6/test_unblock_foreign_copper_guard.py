"""
Regression test for the foreign-copper unblock guard (2026-08-16).

Root cause (measured via the rtd_force_n-vs-U8-gnd-pad shorting item on
the 2026-08-16 fixed route): ``_unblock_net_pads`` unblocks a circle of
radius pad_radius + C-space inflation around each of the net's own pads.
In a dense package (U8 at 0.635mm pitch) that circle overlaps the NEXT
pad's copper, so the neighbour's static cells were temporarily freed and
a via dropped at its own pad's edge passed the via-span clearance check
while its barrel overlapped the neighbour pad.

Fix: cells inside ANY OTHER net's pad or via copper are never unblocked
(astar_grid._unblock_net_pads' foreign-copper guard). This test pins the
guard: two pads 0.635mm apart, unblocking net A must not free net B's
pad cells.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_grid import _restore_net_pads, _unblock_net_pads
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _grid(layer: str, size: int = 120) -> OccupancyGrid:
    return OccupancyGrid(
        layer_name=layer,
        grid=np.zeros((size, size), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=size,
        height_cells=size,
    )


def test_unblock_net_pads_never_frees_foreign_pad_copper():
    fcu = _grid("F.Cu")
    # Two pads 0.635mm apart on F.Cu (U8's rtd_force_n pad 12 at (97.6,
    # 247.3)-ish and gnd pad 13 0.635mm away), rasterised as static -1
    # circles of radius 0.6 (the family grid's circumscribed pad copper).
    own_pad = (5.0, 5.0)
    foreign_pad = (4.365, 5.0)  # 0.635mm left of the own pad
    for cx, cy in (own_pad, foreign_pad):
        gx, gy = fcu.world_to_grid(cx, cy)
        for y in range(gy - 7, gy + 8):
            for x in range(gx - 7, gx + 8):
                wx, wy = fcu.grid_to_world(x, y)
                if (wx - cx) ** 2 + (wy - cy) ** 2 <= 0.6 ** 2:
                    fcu.grid[y, x] = -1

    grids = {"F.Cu": fcu, "In3.Cu": _grid("In3.Cu")}
    # pad_info carries BOTH nets' pads; the unblock is for the own net.
    pad_info = {
        "NET_A": [(own_pad[0], own_pad[1], 0.6, "F.Cu")],
        "NET_B": [(foreign_pad[0], foreign_pad[1], 0.6, "F.Cu")],
    }
    restoration = _unblock_net_pads("NET_A", pad_info, grids, inflation_mm=0.3)

    # The own pad's cells are freed...
    gx, gy = fcu.world_to_grid(*own_pad)
    assert fcu.grid[gy, gx] == 0
    # ...but the foreign pad's copper stays blocked even though it lies
    # inside NET_A's unblock circle (0.6 + 0.3 - 0.01 = 0.89mm radius,
    # and the pads are 0.635mm apart).
    gx2, gy2 = fcu.world_to_grid(*foreign_pad)
    assert fcu.grid[gy2, gx2] == -1, "foreign pad copper was unblocked!"

    _restore_net_pads(restoration)
    # Everything restored.
    assert fcu.grid[gy, gx] == -1
    assert fcu.grid[gy2, gx2] == -1


def test_unblock_net_pads_frees_own_pad_and_own_via():
    fcu = _grid("F.Cu")
    own_pad = (5.0, 5.0)
    own_via = (6.0, 5.0)  # the net's own pre-existing via, 1mm away
    foreign_via = (5.0, 4.0)  # another net's via, 1mm away
    for cx, cy, r in ((*own_pad, 0.6), (*own_via, 0.4), (*foreign_via, 0.4)):
        gx, gy = fcu.world_to_grid(cx, cy)
        rad = int(np.ceil(r / fcu.cell_size)) + 1
        for y in range(gy - rad, gy + rad + 1):
            for x in range(gx - rad, gx + rad + 1):
                wx, wy = fcu.grid_to_world(x, y)
                if (wx - cx) ** 2 + (wy - cy) ** 2 <= r * r:
                    fcu.grid[y, x] = -1
    grids = {"F.Cu": fcu}
    pad_info = {"NET_A": [(own_pad[0], own_pad[1], 0.6, "F.Cu")]}
    existing = {"NET_A": [(own_via[0], own_via[1], 0.8)], "NET_B": [(foreign_via[0], foreign_via[1], 0.8)]}
    restoration = _unblock_net_pads("NET_A", pad_info, grids, inflation_mm=0.3, existing_vias_map=existing)

    gx, gy = fcu.world_to_grid(*own_pad)
    assert fcu.grid[gy, gx] == 0  # own pad freed
    gx2, gy2 = fcu.world_to_grid(*own_via)
    assert fcu.grid[gy2, gx2] == 0  # own via freed
    gx3, gy3 = fcu.world_to_grid(*foreign_via)
    assert fcu.grid[gy3, gx3] == -1  # foreign via copper never freed
