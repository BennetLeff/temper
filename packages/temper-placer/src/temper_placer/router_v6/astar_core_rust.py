"""Rust-backed A* inner loop for router_v6 (cleanup C1).

Wave 4 PR-B (R10) originally ported the A* inner loop to a JIT-compiled
``@njit`` kernel.  The Python→Rust migration program replaced that
kernel with ``temper-rust-router`` (``astar_kernel_3d_py`` +
``line_of_sight_py``), proven bit-identical to the retired JIT kernel
by the differential suite (path cell-sequence identity on randomized
grids) and by the full-pipeline A/B (identical completion rate 0.3750
and bit-identical route length 9354.65 mm — see
``packages/temper-rust-router-core/VERIFICATION.md``).  The JIT
fallback was removed on 2026-07-31; the Rust kernel is now the sole
backend.

This module was renamed from its former JIT-era name in cleanup C6
(2026-08-01) once the JIT backend was fully gone; the entry point
below is the direct Rust dispatch.

Public API
----------
- :func:`_astar_search_rust` is the Python-callable dispatch entry.
  It resolves the backend via :func:`_select_astar_backend` and runs
  the Rust kernel through :func:`_astar_search_rust_kernel`, falling
  back to the pure-Python
  :func:`temper_placer.router_v6.astar_core._astar_search` only when
  ``temper_rust_router`` cannot be imported (broken/stale extension
  environment).  The path is returned as a list of ``(col, row)``
  tuples matching the ``astar_core`` return shape.

- :func:`_line_of_sight_rust` is the Rust-backed Bresenham LOS check
  used by the Theta* family; the retired JIT LOS kernel had the same
  contract and was validated PBT-equal to the pure-Python
  ``_line_of_sight`` reference.

- :func:`RouteProfileStats` aggregates A* timing stats (``rust_time_ms``
  kept; the retired JIT timing field was removed with the JIT
  backend).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np


@dataclass
class RouteProfileStats:
    """Aggregate timing stats collected across A* search calls."""

    rust_time_ms: float = 0.0
    python_time_ms: float = 0.0
    astar_total_ms: float = 0.0
    dist_map_ms: float = 0.0

    def reset(self) -> None:
        self.rust_time_ms = 0.0
        self.python_time_ms = 0.0
        self.astar_total_ms = 0.0
        self.dist_map_ms = 0.0


_route_profile_stats = RouteProfileStats()


def get_route_profile_stats() -> RouteProfileStats:
    """Return the module-level aggregate A* timing stats."""
    return _route_profile_stats


def reset_route_profile_stats() -> None:
    """Reset the module-level aggregate A* timing stats."""
    _route_profile_stats.reset()


def _select_astar_backend() -> str:
    """Probe the A* backend.

    The Rust kernel (``temper-rust-router``) is the sole A* backend
    since cleanup C1; the ``TEMPER_ASTAR_BACKEND`` override was removed
    with the JIT fallback.  Returns ``"rust"`` when the extension
    imports, ``"python"`` when it does not (the pure-Python reference
    is the only remaining fallback).  Read per call so tests can assert
    the extension is actually engaged.
    """
    try:
        import temper_rust_router  # noqa: F401

        return "rust"
    except ImportError:
        return "python"


def _astar_search_rust_kernel(
    start: tuple,
    goal: tuple,
    grid,
    neighbor_tensor: np.ndarray | None = None,
    max_iterations: int = 1_000_000,
    congestion_flat: np.ndarray | None = None,
    congestion_weight: float = 1.0,
    max_congestion_cost: float = 100.0,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
) -> list | None:
    """Rust-backed A* front-end: mirrors :func:`_astar_search_rust`'s
    contract, calling the ported kernel in ``temper-rust-router``
    (``temper_rust_router_core::astar::astar_kernel_3d``)."""
    import temper_rust_router as _trr

    if neighbor_tensor is None:
        from temper_placer.router_v6.neighbor_validity import (
            build_neighbor_validity_tensor_2d,
        )

        neighbor_tensor = build_neighbor_validity_tensor_2d(grid)

    rows = grid.height_cells
    cols = grid.width_cells
    validity_flat = np.ascontiguousarray(neighbor_tensor.astype(np.uint8).reshape(-1))

    start_idx = int(start[1]) * cols + int(start[0])
    goal_idx = int(goal[1]) * cols + int(goal[0])

    congestion_arg = None
    if congestion_flat is not None:
        congestion_arg = np.ascontiguousarray(congestion_flat.astype(np.float32))
    thermal_arg = None
    if thermal_flat is not None:
        thermal_arg = np.ascontiguousarray(thermal_flat.astype(np.float32))

    t0_rust = time.perf_counter()
    path_flat, _iters = _trr.astar_kernel_3d_py(
        start_idx,
        goal_idx,
        rows,
        cols,
        validity_flat.tobytes(),
        max_iterations,
        None if congestion_arg is None else congestion_arg.tobytes(),
        np.float32(congestion_weight),
        np.float32(max_congestion_cost),
        None if thermal_arg is None else thermal_arg.tobytes(),
        np.float32(thermal_weight),
    )
    _route_profile_stats.rust_time_ms += (time.perf_counter() - t0_rust) * 1000.0

    if len(path_flat) == 0:
        return None

    return [(int(i % cols), int(i // cols)) for i in path_flat]


def _line_of_sight_rust(p1, p2, grid, net_id: int) -> bool:
    """Rust-backed Bresenham LOS check (mirrors the retired JIT LOS
    kernel's contract)."""
    import temper_rust_router as _trr

    x0, y0 = p1
    x1, y1 = p2
    # int8 is the documented CellState dtype; normalize so the Rust byte
    # indexing matches the reference kernel's native-dtype reads.
    grid_contig = np.ascontiguousarray(grid.grid, dtype=np.int8)
    return bool(
        _trr.line_of_sight_py(
            int(x0),
            int(y0),
            int(x1),
            int(y1),
            grid_contig.tobytes(),
            int(grid.width_cells),
            int(grid.height_cells),
            int(net_id),
        )
    )


def _astar_search_rust(
    start: tuple,
    goal: tuple,
    grid,
    neighbor_tensor: np.ndarray | None = None,
    max_iterations: int = 1_000_000,
    congestion_flat: np.ndarray | None = None,
    congestion_weight: float = 1.0,
    max_congestion_cost: float = 100.0,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
) -> list | None:
    """A* search front-end.

    The Rust kernel (``temper-rust-router``) is the sole A* backend
    since cleanup C1 (2026-07-31); the JIT kernel and the
    ``TEMPER_ASTAR_BACKEND`` override were removed.  Falls through to
    the pure-Python :func:`temper_placer.router_v6.astar_core._astar_search`
    only if the extension cannot be imported.  No caller sees an
    ImportError.

    U7 / R11: optional ``congestion_flat`` is a flat
    ``(rows*cols,)`` float32 array of per-cell usage counts
    (built by :class:`temper_placer.router_v6.congestion_tensor.CongestionTensor`).
    When supplied, the per-cell cost is folded into ``f_score``
    so the next net naturally detours around already-routed
    channels.  ``congestion_weight`` is a multiplier (1.0 by
    default); ``max_congestion_cost`` caps the per-cell cost
    (100.0 by default).

    U8: optional ``thermal_flat`` is a flat ``(rows*cols,)``
    float32 cost field (built via
    :class:`temper_placer.fields.CostFieldInput`).  When supplied,
    the per-cell thermal cost is added to the step-cost sum
    alongside congestion.  ``thermal_weight`` (0.0 by default) is
    the scalar multiplier — U9 sets a non-zero value.
    """
    t0_total = time.perf_counter()

    if _select_astar_backend() == "rust":
        result = _astar_search_rust_kernel(
            start,
            goal,
            grid,
            neighbor_tensor=neighbor_tensor,
            max_iterations=max_iterations,
            congestion_flat=congestion_flat,
            congestion_weight=congestion_weight,
            max_congestion_cost=max_congestion_cost,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )
        _route_profile_stats.astar_total_ms += (time.perf_counter() - t0_total) * 1000.0
        return result

    # Graceful degrade: temper_rust_router missing/stale.  The pure-Python
    # reference cannot honor congestion/thermal fields; that matches the
    # pre-cleanup JIT-missing fallback contract.
    t0 = time.perf_counter()
    from temper_placer.router_v6.astar_core import _astar_search

    result = _astar_search(start, goal, grid, neighbor_tensor=neighbor_tensor)
    _route_profile_stats.python_time_ms += (time.perf_counter() - t0) * 1000.0
    _route_profile_stats.astar_total_ms += (time.perf_counter() - t0_total) * 1000.0
    return result
