"""Pre-baked neighbor-validity tensors for Router V6 A*.

Builds a boolean tensor once at the start of an A* pass so the inner
loop's neighbor-validity check is a single bit read instead of an
inlined bounds + numpy + occupancy check.

Shapes
-----
2D (single layer): ``(rows, cols, 8)`` — for ``_astar_search`` and
    the lazy / any-angle variants which all operate on a single
    layer at a time.
3D (multi-layer): ``(layers, rows, cols, 8)`` — for
    ``_astar_search_3d``.

A *True* value at ``tensor[layer, row, col, dir]`` means "moving from
(row, col) on layer in direction ``dir`` lands on a free, in-bounds
cell".  A *False* value means the move is invalid (out of bounds, or
the destination cell is occupied).

Direction encoding (matches the 8-move convention used elsewhere in
the router): 0=E, 1=SE, 2=S, 3=SW, 4=W, 5=NW, 6=N, 7=NE.  The
``DIRS_8`` constant is the matching ``(dx, dy)`` table.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid


DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0),    # 0: E
    (1, 1),    # 1: SE
    (0, 1),    # 2: S
    (-1, 1),   # 3: SW
    (-1, 0),   # 4: W
    (-1, -1),  # 5: NW
    (0, -1),   # 6: N
    (1, -1),   # 7: NE
)


def build_neighbor_validity_tensor_2d(
    grid: OccupancyGrid,
) -> np.ndarray:
    """Build a ``(rows, cols, 8)`` boolean tensor for a 2D grid.

    Each entry ``tensor[r, c, dir]`` is True iff moving from cell
    (c, r) in direction ``dir`` (using the 8-move encoding in
    ``DIRS_8``) lands on a free, in-bounds cell on the same layer.

    Args:
        grid: An ``OccupancyGrid`` instance (the same one the A*
            inner loop will read from).

    Returns:
        A ``np.ndarray`` of dtype ``np.bool_`` with shape
        ``(rows, cols, 8)``.  Indexing is ``tensor[r, c, dir]``.
        A read on a non-existent direction index (e.g. dir >= 8)
        returns whatever NumPy's default bounds-check returns
        (raises IndexError); A* code is expected to stay within
        the 0..7 range.
    """
    rows = grid.height_cells
    cols = grid.width_cells
    tensor = np.zeros((rows, cols, 8), dtype=np.bool_)

    arr = grid.grid
    for dir_idx, (dx, dy) in enumerate(DIRS_8):
        # For each source cell (r, c) we mark whether (r + dy, c + dx)
        # is in bounds and free.  The source range is the set of
        # cells that stay in-bounds *after* shifting; the destination
        # range is the same shape, shifted.  Out-of-bounds sources
        # are left False (the tensor was initialized to all False).
        r_src_lo = max(0, -dy)
        r_src_hi = min(rows, rows - dy)
        c_src_lo = max(0, -dx)
        c_src_hi = min(cols, cols - dx)
        if r_src_lo >= r_src_hi or c_src_lo >= c_src_hi:
            # Shift pushes the entire view out of bounds; every
            # move in this direction is invalid.
            continue
        dst = arr[r_src_lo + dy : r_src_hi + dy, c_src_lo + dx : c_src_hi + dx]
        dst_free = dst == 0
        tensor[r_src_lo:r_src_hi, c_src_lo:c_src_hi, dir_idx] = dst_free

    return tensor


def is_valid_2d(
    tensor: np.ndarray, row: int, col: int, dir_idx: int
) -> bool:
    """Read a single bit from a 2D neighbor-validity tensor.

    Out-of-bounds reads return False (the move is invalid).  A* code
    should pre-check bounds for the source cell; the destination
    bounds check is implicit in the tensor build.
    """
    if row < 0 or col < 0:
        return False
    rows, cols, _ = tensor.shape
    if row >= rows or col >= cols:
        return False
    return bool(tensor[row, col, dir_idx])
