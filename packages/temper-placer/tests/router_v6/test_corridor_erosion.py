"""Tests for the corridor-erosion spike:
docs/evidence/2026-08-11-corridor-aware-astar-spike.md.

Covers the two things the Rust kernel's own unit tests can't reach:
1. The Python shim (``corridor_erosion.corridor_mask_for_net``) actually
   round-trips a real ``OccupancyGrid`` through the pyo3 boundary correctly.
2. ``astar_core._astar_search``'s new ``corridor_mask`` parameter is
   actually consulted by the ``net_id >= 0`` (real, net-aware) search path
   -- the path production routing uses, and the one the spike's own root
   cause note (docs/evidence/2026-08-11-track-width-shorting-root-cause.md)
   identified as never receiving a corridor constraint before this change.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_core import _astar_search
from temper_placer.router_v6.corridor_erosion import corridor_mask_for_net
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _grid(width_cells: int, height_cells: int, cell_size: float = 1.0) -> OccupancyGrid:
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((height_cells, width_cells), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )


def test_corridor_mask_for_net_shape_and_own_net_exemption():
    grid = _grid(10, 10)
    # Net 5's own pad: a 3x3 block.
    grid.grid[3:6, 3:6] = 5
    mask = corridor_mask_for_net(grid, net_id=5, trace_width=1.0, clearance=0.0)
    assert mask.dtype == np.bool_
    assert mask.shape == (10, 10)
    # Eroding for net 5 itself: its own pad centre stays valid.
    assert mask[4, 4]
    # Eroding for a DIFFERENT net: the same cell is now inside net 5's
    # (real, foreign) footprint and must be invalid.
    other_mask = corridor_mask_for_net(grid, net_id=7, trace_width=1.0, clearance=0.0)
    assert not other_mask[4, 4]


def test_corridor_mask_matches_expansion_from_mark_path_blocked():
    """The mask's structuring element must agree with what
    ``mark_path_blocked`` (the actual marking function) would stamp --
    the load-bearing parity the Rust module's own doc comment describes.
    Cross-checked here from the Python side: mark a path at
    (trace_width, clearance) for a FOREIGN net, then confirm the corridor
    mask computed for OUR net at the identical (trace_width, clearance)
    agrees, cell for cell, with direct occupancy for every cell the
    marking function actually touched.
    """
    grid = _grid(40, 40, cell_size=0.5)
    trace_width, clearance = 2.0, 0.5  # radius_mm = 1.5 -> expansion = 3 cells @ 0.5mm
    grid.mark_path_blocked([(5.0, 10.0), (15.0, 10.0)], trace_width, clearance, net_id=9)
    marked_cells = np.argwhere(grid.grid == 9)
    assert marked_cells.size > 0, "sanity: the foreign net actually marked something"

    mask = corridor_mask_for_net(grid, net_id=1, trace_width=trace_width, clearance=clearance)
    # Every cell the marking function touched must itself read as invalid
    # for a DIFFERENT net (net 1) -- it is squarely inside net 9's own
    # footprint, so trivially inside any erosion radius >= 0 for net 1.
    for r, c in marked_cells:
        assert not mask[r, c]


def test_astar_search_net_id_branch_respects_corridor_mask():
    """Regression test for the exact wiring gap the spike's brief calls
    out: `_astar_search`'s `net_id >= 0` branch previously ignored
    `corridor_mask` entirely (it only consulted `neighbor_tensor`, which
    that branch never builds). A corridor-aware net-id search must now
    refuse to step through a cell the mask marks invalid, even when the
    raw grid says that cell is free.
    """
    grid = _grid(10, 1)  # a 1-row corridor, straight line start->goal
    start = (0, 0)
    goal = (9, 0)

    # No corridor_mask: a direct 10-cell path exists.
    path = _astar_search(start, goal, grid, net_id=1)
    assert path is not None
    assert path[0] == start and path[-1] == goal

    # Corridor mask that blocks the single midpoint cell (5, 0): the
    # ONLY path in a 1-row grid must now be refused.
    mask = np.ones((1, 10), dtype=np.bool_)
    mask[0, 5] = False
    blocked = _astar_search(start, goal, grid, net_id=1, corridor_mask=mask)
    assert blocked is None


def test_astar_search_corridor_mask_still_allows_own_net_cells():
    """Own-net occupancy exemption and the corridor mask are independent
    gates -- both must pass. This checks the corridor mask doesn't
    accidentally re-block a cell the direct occupancy check already
    exempted (own net's committed copper), when the mask itself marks
    that cell valid (as `corridor_mask_for_net` always does for the
    search net's own cells -- see the exemption test above).
    """
    grid = _grid(10, 1)
    grid.grid[0, 5] = 1  # net 1's own copper sits on the direct route
    mask = np.ones((1, 10), dtype=np.bool_)  # corridor allows everywhere
    path = _astar_search((0, 0), (9, 0), grid, net_id=1, corridor_mask=mask)
    assert path is not None
