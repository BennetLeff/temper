"""Rust-backed replacement for ``astar_core._astar_search``.

``temper_rust_router.astar_search_2d_py`` is a **faithful f64 port** of the
pure-Python search: no closed set (nodes re-expand and stale heap entries are
re-processed), heap ties broken lexicographically on the ``(x, y)`` integer
tuple, ``None`` — not ``[]`` — when the frontier empties, and no iteration cap.

It is a *different* kernel from ``astar_kernel_3d_py``
(``astar_core_rust._astar_search_rust``), which computes in f32, keeps a
closed set, and hardcodes ``SQRT_2`` with no counterpart to the
runtime-mutable ``astar_core.DIAGONAL_COST_FACTOR``. That kernel is the live
2D primary search for every net and is deliberately left untouched; see
``temper_rust_router_core::astar_search2d``'s module docs.

``DIAGONAL_COST_FACTOR`` is read from ``astar_core`` **on every call**, not
captured at import, because it is a plain module attribute the module's own
docstring documents as assignable at runtime.
"""

from __future__ import annotations

import numpy as np


def _astar_search_2d_rust(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid,
    neighbor_tensor: np.ndarray | None = None,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
    corridor_mask: np.ndarray | None = None,
) -> list[tuple[int, int]] | None:
    """Signature-compatible drop-in for ``astar_core._astar_search``."""
    import temper_rust_router as _trr

    from temper_placer.router_v6 import astar_core

    width = int(grid.width_cells)
    height = int(grid.height_cells)

    grid_bytes = np.ascontiguousarray(grid.grid, dtype=np.int8).tobytes()

    tensor_bytes = None
    if net_id < 0:
        tensor = neighbor_tensor
        if tensor is None:
            from temper_placer.router_v6.neighbor_validity import (
                build_neighbor_validity_tensor_2d,
            )

            tensor = build_neighbor_validity_tensor_2d(grid)
        tensor_bytes = np.ascontiguousarray(tensor, dtype=np.uint8).tobytes()

    mask_bytes = None
    if corridor_mask is not None:
        mask_bytes = np.ascontiguousarray(corridor_mask, dtype=np.uint8).tobytes()

    thermal_bytes = None
    if thermal_flat is not None:
        thermal_bytes = np.ascontiguousarray(thermal_flat, dtype=np.float32).tobytes()

    flat = _trr.astar_search_2d_py(
        int(start[0]),
        int(start[1]),
        int(goal[0]),
        int(goal[1]),
        width,
        height,
        grid_bytes,
        tensor_bytes,
        thermal_bytes,
        float(thermal_weight),
        int(net_id),
        mask_bytes,
        float(astar_core.DIAGONAL_COST_FACTOR),
    )
    if flat is None:
        return None
    return [(int(flat[i]), int(flat[i + 1])) for i in range(0, len(flat), 2)]
