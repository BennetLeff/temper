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
  It asserts the extension is present via
  :func:`_require_astar_extension` and runs the Rust kernel through
  :func:`_astar_search_rust_kernel`.  The path is returned as a list of
  ``(col, row)`` tuples matching the ``astar_core`` return shape.

  **There is no Python fallback** (removed 2026-08-18).  A missing
  ``temper_rust_router`` raises
  :class:`AstarExtensionUnavailableError` immediately instead of
  silently routing with a non-equivalent implementation -- see
  :func:`_require_astar_extension` for the measured differences and why
  failing open was unsafe on a mains-voltage board.  The pure-Python
  reference survives only as the frozen differential oracle at
  ``packages/temper-placer/tests/router_v6/_astar_search_py_oracle.py``.

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


class AstarExtensionUnavailableError(RuntimeError):
    """``temper_rust_router`` could not be imported.

    This is a hard environment failure, never a condition to route around.
    See :func:`_require_astar_extension` for why there is no fallback.
    """


def _require_astar_extension() -> None:
    """Assert the Rust A* kernel is importable, or raise.

    **Fail closed, never fail open.**  Until 2026-08-18 this function's
    predecessor (``_select_astar_backend``) caught ``ImportError`` and
    returned ``"python"``, and :func:`_astar_search_rust` then quietly ran
    ``astar_core._astar_search`` instead.  That fallback was *not*
    behaviour-equivalent, which is precisely what made it dangerous:

    * the Rust kernel accumulates ``g_score`` in **f32** and casts its
      octile heuristic f64->f32; the Python reference works in **f64**;
    * the Rust kernel maintains a closed set, the Python reference
      re-expands already-settled cells;
    * tie-breaking differs structurally -- Python's ``heapq`` orders on
      ``(priority, (x, y))`` and so breaks ties lexicographically by cell,
      the Rust binary heap breaks them by heap-array position;
    * the Rust kernel carries congestion and thermal cost terms that the
      Python signature does not even accept, so those fields were silently
      dropped on the fallback path.

    The consequence was that a broken or stale extension did not fail.  It
    laid **different copper on an IEC 60335-1 mains board**, with nothing in
    the routed output naming which implementation produced it.  Several
    wrong conclusions were drawn from routing runs before this was noticed.

    A missing extension is an environment fault with exactly one correct
    response: stop.  Run ``make extensions`` (or ``make venv-isolate`` in a
    fresh worktree).
    """
    try:
        import temper_rust_router  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment fault
        raise AstarExtensionUnavailableError(
            "temper_rust_router (the Rust A* kernel) could not be imported, "
            "so the router cannot run. There is deliberately NO pure-Python "
            "fallback: the Python reference is not behaviour-equivalent "
            "(f64 vs the kernel's f32, no closed set, different tie-breaking, "
            "no congestion/thermal terms), so falling back would silently "
            "emit different copper on a mains-voltage board. "
            "Fix the environment: `make extensions` rebuilds every pyo3 "
            "crate; `make extensions-check` reports staleness; "
            "`make venv-isolate` provisions a worktree-local .venv. "
            f"Underlying import error: {exc}"
        ) from exc


def _select_astar_backend() -> str:
    """Return the resolved A* backend name.

    Always ``"rust"`` -- there is no other backend.  Retained because the
    differential and LOS suites assert on it to prove the extension is
    genuinely engaged; it now raises
    :class:`AstarExtensionUnavailableError` rather than reporting
    ``"python"``.
    """
    _require_astar_extension()
    return "rust"


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
    net_id: int = -1,
    corridor_mask: np.ndarray | None = None,
) -> list | None:
    """Rust-backed A* front-end: mirrors :func:`_astar_search_rust`'s
    contract, calling the ported kernel in ``temper-rust-router``
    (``temper_rust_router_core::astar::astar_kernel_3d``).

    S8 (same-net wiring): when ``net_id >= 0``, the raw occupancy grid
    is passed to the Rust kernel instead of building a binary validity
    tensor.  The kernel does inline bounds+occupancy+corridor checks
    per expansion, including the 0.25× same-net cost discount.  When
    ``net_id < 0`` (the default), behaviour is unchanged — the
    validity-tensor path is used."""
    import temper_rust_router as _trr

    rows = grid.height_cells
    cols = grid.width_cells

    start_idx = int(start[1]) * cols + int(start[0])
    goal_idx = int(goal[1]) * cols + int(goal[0])

    # S8: when net_id >= 0, pass the raw int8 grid and skip the
    # validity-tensor build (which costs ~30ms on the production grid
    # and cannot encode the same-net predicate — see the companion
    # FFI-cost doc).
    if net_id >= 0:
        grid_contig = np.ascontiguousarray(grid.grid, dtype=np.int8)
        grid_bytes: bytes = grid_contig.tobytes()
        mask_bytes: bytes | None = None
        if corridor_mask is not None:
            mask_contig = np.ascontiguousarray(corridor_mask.astype(np.uint8))
            mask_bytes = mask_contig.tobytes()

        # When the grid is supplied, the kernel ignores the validity
        # tensor.  We pass a minimal dummy (one byte of 1) so the FFI
        # signature is satisfied; the kernel's `grid.is_some()` gate
        # ensures it is never read.
        dummy_validity = b"\x01"

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
            dummy_validity,
            max_iterations,
            None if congestion_arg is None else congestion_arg.tobytes(),
            np.float32(congestion_weight),
            np.float32(max_congestion_cost),
            None if thermal_arg is None else thermal_arg.tobytes(),
            np.float32(thermal_weight),
            grid_bytes,  # grid_bytes (Option<Vec<u8>>)
            net_id,  # net_id (i64)
            mask_bytes,  # corridor_mask_bytes (Option<Vec<u8>>)
        )
        _route_profile_stats.rust_time_ms += (time.perf_counter() - t0_rust) * 1000.0

        if len(path_flat) == 0:
            return None

        return [(int(i % cols), int(i // cols)) for i in path_flat]

    # net_id < 0: existing validity-tensor path (unchanged).
    if neighbor_tensor is None:
        from temper_placer.router_v6.neighbor_validity import (
            build_neighbor_validity_tensor_2d,
        )

        neighbor_tensor = build_neighbor_validity_tensor_2d(grid)

    validity_flat = np.ascontiguousarray(neighbor_tensor.astype(np.uint8).reshape(-1))

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
    net_id: int = -1,
    corridor_mask: np.ndarray | None = None,
) -> list | None:
    """A* search front-end.

    The Rust kernel (``temper-rust-router``) is the sole A* backend
    since cleanup C1 (2026-07-31); the JIT kernel and the
    ``TEMPER_ASTAR_BACKEND`` override were removed.  Since 2026-08-18
    there is no fallback either: if the extension cannot be imported this
    raises :class:`AstarExtensionUnavailableError` rather than routing
    with a different implementation.  Callers DO see that failure, by
    design -- it is an environment fault, not a routing condition.

    S8 (same-net wiring): ``net_id`` and ``corridor_mask`` are forwarded
    to the Rust kernel.  When ``net_id >= 0``, the raw occupancy grid
    is passed instead of building a validity tensor, and the Rust kernel
    performs inline same-net occupancy checks with the 0.25× cost
    discount per expansion.

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

    # Fail closed: a missing extension raises here rather than degrading to
    # a non-equivalent Python implementation.  See _require_astar_extension.
    _require_astar_extension()

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
        net_id=net_id,
        corridor_mask=corridor_mask,
    )
    _route_profile_stats.astar_total_ms += (time.perf_counter() - t0_total) * 1000.0
    return result
