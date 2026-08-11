"""Configuration-space corridor erosion for width-aware A* (spike).

``docs/evidence/2026-08-11-track-width-shorting-root-cause.md`` traces
199 ``track_width``/``shorting_items`` DRC violations to one mechanism:
``OccupancyGrid.mark_path_blocked`` marks copper WIDTH-AWARE (a
``trace_width / 2 + clearance`` square stamp swept along the path --
see ``temper_geometry.occupancy_raster.mark_point_rect``), while A*
searches the ``validity`` tensor WIDTH-BLIND (one free/blocked bit per
cell, no notion of the trace's own footprint). A* can therefore return a
centreline that is clear at the centre and not clear at the trace's
actual width, and the router lays the trace down anyway.

The fix is a standard configuration-space (C-space) erosion: shrink the
free-space mask by the net's own footprint radius BEFORE A* searches it.
The computation lives in ``temper_geometry``'s ``corridor_erosion`` Rust
module (``packages/temper-geometry/src/corridor_erosion.rs`` --
see that module's own doc comment for the structuring-element-parity and
own-net-exemption reasoning); this module is the thin Python wrapper,
matching the existing ``corridor.py`` / ``extract_corridor_mask`` pattern
so the result can be fed straight into
``neighbor_validity.build_neighbor_validity_tensor_2d``'s existing
``corridor_mask`` parameter, or (for a direct, net_id-aware search) into
``astar_core._astar_search``'s ``corridor_mask`` parameter.
"""

from __future__ import annotations

import numpy as np
import temper_geometry as _tg

from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def corridor_mask_for_net(
    grid: OccupancyGrid,
    net_id: int,
    trace_width: float,
    clearance: float,
) -> np.ndarray:
    """Return a ``(height_cells, width_cells)`` boolean corridor mask.

    A cell is ``True`` iff a trace of ``trace_width`` with ``clearance``
    centred at that cell would touch no cell belonging to a net other
    than ``net_id`` (and no static obstacle). ``net_id``'s own copper and
    pads are exempt -- see the Rust module's doc comment for why that
    exemption is required for correctness, not merely convenience (a
    net's own start/goal pads are themselves marked obstacles on the
    grid; without the exemption, erosion would report "no path" for
    almost every net).

    Args:
        grid: The ``OccupancyGrid`` to erode (same grid the A* search
            that consumes the result will run against).
        net_id: The net whose corridor this is. Must be the same
            ``net_id`` used when that net's own pads/copper were marked
            onto ``grid``.
        trace_width: The net's required trace width in mm (from its
            resolved net-class rule -- NOT the width the pre-existing,
            possibly-buggy centerline-only router happened to emit).
        clearance: The net's required clearance in mm.

    Returns:
        Boolean ``np.ndarray`` of shape
        ``(grid.height_cells, grid.width_cells)``, ``True`` = usable.
    """
    raw = _tg.corridor_mask_for_net_py(
        grid.grid,
        net_id,
        trace_width,
        clearance,
        grid.cell_size,
    )
    return np.frombuffer(raw, dtype=np.bool_).reshape((grid.height_cells, grid.width_cells))
