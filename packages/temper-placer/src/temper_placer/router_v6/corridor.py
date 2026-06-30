"""Coarse-to-fine corridor extraction for Router V6.

Given a coarse path (list of coarse grid cells), produces a boolean
mask on the fine grid that defines the routing corridor.  Only fine
cells within the expanded corridor may be used during constrained A*.
"""

from __future__ import annotations

import numpy as np


def extract_corridor_mask(
    coarse_path: list[tuple[int, int]],
    coarse_factor: int,
    buffer_cells: int,
    fine_rows: int,
    fine_cols: int,
) -> np.ndarray:
    """Return a boolean mask of shape ``(fine_rows, fine_cols)``.

    For each coarse cell ``(cx, cy)`` in ``coarse_path``:
    - Map to the fine-grid rectangle
      ``(cx * factor, cy * factor)``
      to ``((cx+1) * factor - 1, (cy+1) * factor - 1)`` inclusive.
    - Expand by ``buffer_cells`` in each direction, clamped to
      fine grid bounds.
    - OR all expanded rectangles into a single mask.

    Args:
        coarse_path: List of ``(col, row)`` coarse-grid cells.
        coarse_factor: Downsampling factor (e.g. 4).
        buffer_cells: Expansion margin in fine-grid cells.
        fine_rows: Height of the fine grid in cells.
        fine_cols: Width of the fine grid in cells.

    Returns:
        Boolean (bool) ndarray of shape ``(fine_rows, fine_cols)``
        where ``True`` indicates the cell is within the corridor.
    """
    mask = np.zeros((fine_rows, fine_cols), dtype=np.bool_)
    for cx, cy in coarse_path:
        r0 = max(0, cy * coarse_factor - buffer_cells)
        r1 = min(fine_rows, (cy + 1) * coarse_factor + buffer_cells)
        c0 = max(0, cx * coarse_factor - buffer_cells)
        c1 = min(fine_cols, (cx + 1) * coarse_factor + buffer_cells)
        mask[r0:r1, c0:c1] = True
    return mask
