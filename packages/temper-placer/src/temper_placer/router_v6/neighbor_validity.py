"""Pre-baked neighbor-validity tensors for Router V6 A*.

Builds a boolean tensor once at the start of an A* pass so the inner
loop's neighbor-validity check is a single bit read instead of an
inlined bounds + numpy + occupancy check.

RUST-BACKED. ``build_neighbor_validity_tensor_2d`` is a thin shim over
``temper_geometry.build_neighbor_validity_tensor_2d_py``
(``packages/temper-geometry/src/neighbor_validity.rs``). The previous numpy
implementation -- eight full-grid slice assignments, one per direction, each
writing a stride-8 destination and materialising its own ``dst == 0``
temporary -- is pinned verbatim as the differential oracle at
``packages/temper-placer/tests/router_v6/_neighbor_validity_py_oracle.py``
and is compared against bit-for-bit by
``test_neighbor_validity_rust_differential.py``, including on this board's
real 2380x1680 routing grid.

Measured on a full production route (752 calls): 8.81 s -> 7.09 s, and the
routed board is BYTE-IDENTICAL either way
(``8a8c97e0115145fb7c6d8fdad8c4462c8e3b0e2125e640714cf323950c12a965``).
The remaining cost is dominated by materialising the ~32 MB tensor itself,
which no port can remove -- eliminating it needs the caller-side change
sized in ``docs/evidence/2026-08-11-astar-ffi-marshalling-cost.md`` §6
(pass the raw occupancy grid and check validity inline during expansion).

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
import temper_geometry as _tg

if TYPE_CHECKING:
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid


DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0),  # 0: E
    (1, 1),  # 1: SE
    (0, 1),  # 2: S
    (-1, 1),  # 3: SW
    (-1, 0),  # 4: W
    (-1, -1),  # 5: NW
    (0, -1),  # 6: N
    (1, -1),  # 7: NE
)


def build_neighbor_validity_tensor_2d(
    grid: OccupancyGrid,
    corridor_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Build a ``(rows, cols, 8)`` boolean tensor for a 2D grid.

    Each entry ``tensor[r, c, dir]`` is True iff moving from cell
    (c, r) in direction ``dir`` (using the 8-move encoding in
    ``DIRS_8``) lands on a free, in-bounds cell on the same layer.

    When ``corridor_mask`` is supplied (a bool array of the same
    shape as the grid), a move is also invalid if the destination
    cell lies outside the corridor.  This implements corridor-
    constrained coarse-to-fine A* without modifying the Rust
    kernel.

    Args:
        grid: An ``OccupancyGrid`` instance (the same one the A*
            inner loop will read from).
        corridor_mask: Optional boolean array of shape
            ``(height_cells, width_cells)`` where ``True`` marks
            cells allowed for routing.  ``None`` (default) imposes
            no extra constraint.

    Returns:
        A ``np.ndarray`` of dtype ``np.bool_`` with shape
        ``(rows, cols, 8)``.  Indexing is ``tensor[r, c, dir]``.
        A read on a non-existent direction index (e.g. dir >= 8)
        returns whatever NumPy's default bounds-check returns
        (raises IndexError); A* code is expected to stay within
        the 0..7 range.
    """
    rows = int(grid.height_cells)
    cols = int(grid.width_cells)

    # The tensor is allocated HERE and filled in place by Rust through the
    # buffer protocol -- the same zero-copy shape `mark_path_rect_into_grid_py`
    # already uses for the write direction (see the module doc). `np.empty` is
    # safe because the kernel assigns EVERY entry, including the border cells
    # whose destination is out of bounds; the previous numpy implementation
    # relied on `np.zeros` for those, so this is the one place the port must
    # not be taken on faith -- `test_neighbor_validity_rust_differential.py`
    # compares against the pinned oracle on the production board's own grids,
    # border included.
    tensor = np.empty((rows, cols, 8), dtype=np.bool_)
    if rows == 0 or cols == 0:
        return tensor

    arr = np.ascontiguousarray(grid.grid, dtype=np.int8)
    mask_u8 = None
    if corridor_mask is not None:
        mask_u8 = np.ascontiguousarray(corridor_mask, dtype=np.bool_).view(np.uint8)

    _tg.build_neighbor_validity_tensor_2d_py(
        arr, rows, cols, tensor.view(np.uint8), mask_u8
    )
    return tensor


def is_valid_2d(tensor: np.ndarray, row: int, col: int, dir_idx: int) -> bool:
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
