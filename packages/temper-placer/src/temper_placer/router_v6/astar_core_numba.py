"""Numba-jitted A* inner loop for router_v6.

Wave 4 PR-B (R10): port the A* inner loop to @njit for a 5-10x
inner-loop speedup.  Reads the pre-baked neighbor-validity tensor
from U5 (PR-A / R9) as a flat numpy array; per-iteration cost is
dominated by the heapq + dict operations, both of which drop out
under @njit (heap becomes two parallel float32/int32 arrays;
g_score / came_from become flat numpy arrays).

Public API
----------
- :func:`_astar_search_numba_kernel` is the @njit-compiled inner
  loop.  It does NOT do path reconstruction — that stays in
  Python (called from :func:`_astar_search_numba`).

- :func:`_astar_search_numba` is the Python-callable wrapper.  It
  allocates work arrays, calls the kernel, and reconstructs the
  path in Python.  The path is returned as a list of
  (col, row) tuples matching the existing
  :func:`temper_placer.router_v6.astar_core._astar_search` return
  shape.

Graceful degrade
----------------
If numba is not installed, the kernel falls through to the pure-
Python :func:`temper_placer.router_v6.astar_core._astar_search`.
The :func:`_astar_search_numba` wrapper detects this and dispatches
to the Python path.  No caller sees an ImportError.

Implementation notes
--------------------
- The kernel heap is a min-heap stored as two parallel arrays
  (priorities and cell indices).  Standard sift-up / sift-down
  in place — same algorithm as Python's heapq.
- The bit tensor is read with a single index into a flat bool
  array (sized ``rows * cols * 8``).  Direction ``d`` from cell
  ``i`` is ``validity[i * 8 + d]``.  The Python wrapper flattens
  the tensor at allocation time so the kernel never has to
  reshape.
- ``g_score`` is a flat ``float32`` array.  ``INF`` is a sentinel
  written at init; comparisons stay as float compares.
- ``came_from`` is a flat ``int32`` array (-1 = root, otherwise
  the previous cell index).
- ``closed`` is a flat ``uint8`` array (0 = open, 1 = closed).
"""
from __future__ import annotations

import numpy as np

try:
    from numba import njit

    _HAVE_NUMBA = True
except ImportError:  # pragma: no cover
    _HAVE_NUMBA = False


_NUMBA_KERNEL = None


def _get_kernel():
    """Lazily compile the @njit kernel on first use.

    Numba compilation is ~1s on the first call; doing it lazily
    keeps import time fast.  Re-imports after cache hits are
    sub-second.
    """
    global _NUMBA_KERNEL
    if _NUMBA_KERNEL is None:
        if not _HAVE_NUMBA:
            return None
        _NUMBA_KERNEL = _compile_kernel()
    return _NUMBA_KERNEL


def _compile_kernel():
    """Define and @njit-compile the A* inner-loop kernel."""

    @njit(cache=True, fastmath=False)
    def _heap_push(
        heap_pri: np.ndarray,
        heap_idx: np.ndarray,
        heap_size: int,
        heap_cap: int,
        pri: np.float32,
        idx: np.int32,
    ) -> tuple:
        """Push (pri, idx) onto the min-heap.

        Returns the new (heap_pri, heap_idx, heap_size, heap_cap)
        tuple.  Numba supports tuple return + array mutation; the
        caller assigns back the new arrays.  ``heap_cap`` grows
        exponentially on overflow.
        """
        if heap_size >= heap_cap:
            new_cap = heap_cap * 2
            new_pri = np.empty(new_cap, dtype=np.float32)
            new_idx = np.empty(new_cap, dtype=np.int32)
            new_pri[:heap_cap] = heap_pri[:heap_cap]
            new_idx[:heap_cap] = heap_idx[:heap_cap]
            heap_pri = new_pri
            heap_idx = new_idx
            heap_cap = new_cap
        i = heap_size
        heap_pri[i] = pri
        heap_idx[i] = idx
        heap_size += 1
        # Sift up
        while i > 0:
            parent = (i - 1) >> 1
            if heap_pri[parent] <= heap_pri[i]:
                break
            tmp_p = heap_pri[parent]
            tmp_i = heap_idx[parent]
            heap_pri[parent] = heap_pri[i]
            heap_idx[parent] = heap_idx[i]
            heap_pri[i] = tmp_p
            heap_idx[i] = tmp_i
            i = parent
        return heap_pri, heap_idx, heap_size, heap_cap

    @njit(cache=True, fastmath=False)
    def _heap_pop(
        heap_pri: np.ndarray,
        heap_idx: np.ndarray,
        heap_size: int,
    ) -> tuple:
        """Pop (pri, idx) from the min-heap.  Returns
        (heap_pri, heap_idx, heap_size, pri, idx).  Caller must
        check ``heap_size > 0`` before calling.
        """
        pri = heap_pri[0]
        idx = heap_idx[0]
        heap_size -= 1
        if heap_size > 0:
            heap_pri[0] = heap_pri[heap_size]
            heap_idx[0] = heap_idx[heap_size]
            i = 0
            while True:
                l = 2 * i + 1
                r = 2 * i + 2
                smallest = i
                if l < heap_size and heap_pri[l] < heap_pri[smallest]:
                    smallest = l
                if r < heap_size and heap_pri[r] < heap_pri[smallest]:
                    smallest = r
                if smallest == i:
                    break
                tmp_p = heap_pri[i]
                tmp_i = heap_idx[i]
                heap_pri[i] = heap_pri[smallest]
                heap_idx[i] = heap_idx[smallest]
                heap_pri[smallest] = tmp_p
                heap_idx[smallest] = tmp_i
                i = smallest
        return heap_pri, heap_idx, heap_size, pri, idx

    @njit(cache=True, fastmath=False)
    def _kernel(
        start_idx: int,
        goal_idx: int,
        rows: int,
        cols: int,
        validity_flat: np.ndarray,  # (rows*cols*8,) uint8
        max_iterations: int,
        congestion_flat: np.ndarray = None,  # (rows*cols,) float32; null = no congestion
        congestion_weight: float = 1.0,  # multiplier on per-cell congestion cost
        max_congestion_cost: float = 100.0,  # cap on per-cell cost
    ) -> tuple:
        """Run A* on the 2D grid.  Returns (path_indices, iterations).

        ``path_indices`` is a 1D array of cell indices from start to
        goal inclusive, or an empty array if no path was found.
        ``iterations`` is the number of heap pops performed.

        If ``congestion_flat`` is supplied (U7 / R11), each
        per-cell expansion adds a per-cell congestion penalty to
        ``f_score`` so the next net naturally detours around
        already-routed channels.  Cost formula is
        ``min(max_congestion_cost, 1 + log(1 + raw))`` at the
        cell; multiplied by ``congestion_weight``.  Logarithmic
        growth keeps the cost admissible as a tie-breaker.
        """
        INF = np.float32(1.0e30)
        n_cells = rows * cols
        # Hoist the U7 / R11 congestion branch decision out of the
        # inner loop.  When ``congestion_weight`` is zero, the
        # entire per-neighbor cost fold is mathematically a no-op,
        # but Numba does not eliminate the dead ``np.log``,
        # ``np.float32(...)``, and multiply at the call site.
        # Gating on ``congestion_weight > 0`` lets Numba prune the
        # branch at JIT time when callers (the closure test, the
        # smoke runner) pass weight=0.  This is the single biggest
        # source of the 1M-iter-cap wall-time blowup that the
        # full-pipeline profile surfaced on 2026-06-23.
        use_congestion = (
            congestion_flat is not None
            and congestion_weight > 0.0
        )

        # Work arrays
        g_score = np.full(n_cells, INF, dtype=np.float32)
        g_score[start_idx] = np.float32(0.0)

        came_from = np.full(n_cells, -1, dtype=np.int32)
        closed = np.zeros(n_cells, dtype=np.uint8)

        # Manual binary heap: parallel arrays for (priority, cell).
        heap_cap = 4096
        heap_pri = np.empty(heap_cap, dtype=np.float32)
        heap_idx = np.empty(heap_cap, dtype=np.int32)
        heap_size = 0

        # Octile distance heuristic — admissible, no via-cost.
        sr = start_idx // cols
        sc = start_idx - sr * cols
        gr = goal_idx // cols
        gc = goal_idx - gr * cols
        dx0 = abs(sc - gc)
        dy0 = abs(sr - gr)
        heuristic_start = np.float32(max(dx0, dy0) + 0.414 * min(dx0, dy0))

        heap_pri, heap_idx, heap_size, heap_cap = _heap_push(
            heap_pri, heap_idx, heap_size, heap_cap,
            heuristic_start, np.int32(start_idx),
        )

        iterations = 0
        while heap_size > 0 and iterations < max_iterations:
            iterations += 1
            heap_pri, heap_idx, heap_size, _, cur = _heap_pop(
                heap_pri, heap_idx, heap_size,
            )
            cur_i = cur

            if cur_i == goal_idx:
                back_list = []
                c = cur_i
                while c != -1:
                    back_list.append(c)
                    c = came_from[c]
                n = len(back_list)
                path = np.empty(n, dtype=np.int32)
                for k in range(n):
                    path[k] = back_list[n - 1 - k]
                return path, iterations

            if closed[cur_i] != np.uint8(0):
                continue
            closed[cur_i] = np.uint8(1)

            cur_r = cur_i // cols
            cur_c = cur_i - cur_r * cols

            # 8-connected expansion, all from the U5 bit tensor
            base = cur_i * 8
            for d in range(8):
                if validity_flat[base + d] == np.uint8(0):
                    continue
                # Direction table (E, SE, S, SW, W, NW, N, NE)
                if d == 0:
                    ndc = cur_c + 1
                    ndr = cur_r
                elif d == 1:
                    ndc = cur_c + 1
                    ndr = cur_r + 1
                elif d == 2:
                    ndc = cur_c
                    ndr = cur_r + 1
                elif d == 3:
                    ndc = cur_c - 1
                    ndr = cur_r + 1
                elif d == 4:
                    ndc = cur_c - 1
                    ndr = cur_r
                elif d == 5:
                    ndc = cur_c - 1
                    ndr = cur_r - 1
                elif d == 6:
                    ndc = cur_c
                    ndr = cur_r - 1
                else:  # d == 7
                    ndc = cur_c + 1
                    ndr = cur_r - 1
                if ndc < 0 or ndr < 0 or ndc >= cols or ndr >= rows:
                    continue
                n_idx = ndr * cols + ndc
                # Octile cost
                if d == 0 or d == 2 or d == 4 or d == 6:
                    step = np.float32(1.0)
                else:
                    step = np.float32(1.4142135)
                # U7 / R11: per-cell congestion penalty from the
                # PathFinder history tensor.  log1p + cap means
                # cost grows logarithmically; admissible as a
                # tie-breaker.
                if use_congestion:
                    raw = congestion_flat[n_idx]
                    if raw > np.float32(0.0):
                        # Inline: 1 + log(1 + raw), capped
                        cong_cost = np.float32(1.0) + np.log(np.float32(1.0) + raw)
                        if cong_cost > max_congestion_cost:
                            cong_cost = max_congestion_cost
                        step = step + np.float32(congestion_weight) * cong_cost
                tentative = g_score[cur_i] + step
                if tentative < g_score[n_idx]:
                    g_score[n_idx] = tentative
                    came_from[n_idx] = cur_i
                    gdx = abs(ndc - gc)
                    gdy = abs(ndr - gr)
                    h = np.float32(max(gdx, gdy) + 0.414 * min(gdx, gdy))
                    heap_pri, heap_idx, heap_size, heap_cap = _heap_push(
                        heap_pri, heap_idx, heap_size, heap_cap,
                        tentative + h, np.int32(n_idx),
                    )

        return np.empty(0, dtype=np.int32), iterations

    return _kernel


def _astar_search_numba(
    start: tuple,
    goal: tuple,
    grid,
    neighbor_tensor: np.ndarray | None = None,
    max_iterations: int = 1_000_000,
    congestion_flat: np.ndarray | None = None,
    congestion_weight: float = 1.0,
    max_congestion_cost: float = 100.0,
) -> list | None:
    """Numba-jitted A* front-end.  See module docstring.

    Falls through to the pure-Python
    :func:`temper_placer.router_v6.astar_core._astar_search` if
    numba is not installed.

    U7 / R11: optional ``congestion_flat`` is a flat
    ``(rows*cols,)`` float32 array of per-cell usage counts
    (built by :class:`temper_placer.router_v6.congestion_tensor.CongestionTensor`).
    When supplied, the per-cell cost is folded into ``f_score``
    so the next net naturally detours around already-routed
    channels.  ``congestion_weight`` is a multiplier (1.0 by
    default); ``max_congestion_cost`` caps the per-cell cost
    (100.0 by default).
    """
    if not _HAVE_NUMBA:
        # Graceful degrade to the pure-Python path
        from temper_placer.router_v6.astar_core import _astar_search
        return _astar_search(start, goal, grid, neighbor_tensor=neighbor_tensor)

    kernel = _get_kernel()
    if kernel is None:
        from temper_placer.router_v6.astar_core import _astar_search
        return _astar_search(start, goal, grid, neighbor_tensor=neighbor_tensor)

    # Build (or reuse) the validity tensor
    if neighbor_tensor is None:
        from temper_placer.router_v6.neighbor_validity import (
            build_neighbor_validity_tensor_2d,
        )
        neighbor_tensor = build_neighbor_validity_tensor_2d(grid)

    rows = grid.height_cells
    cols = grid.width_cells
    validity_flat = np.ascontiguousarray(
        neighbor_tensor.astype(np.uint8).reshape(-1)
    )

    start_idx = int(start[1]) * cols + int(start[0])
    goal_idx = int(goal[1]) * cols + int(goal[0])

    # Pass None for the congestion arg when the caller didn't
    # supply one; the kernel checks for None and skips the
    # per-expansion congestion-cost read.
    if congestion_flat is not None:
        congestion_arg = np.ascontiguousarray(
            congestion_flat.astype(np.float32)
        )
    else:
        congestion_arg = None

    path_flat, _iters = kernel(
        start_idx, goal_idx, rows, cols, validity_flat,
        max_iterations,
        congestion_arg,
        np.float32(congestion_weight),
        np.float32(max_congestion_cost),
    )

    if path_flat.shape[0] == 0:
        return None

    # Convert flat indices back to (col, row) tuples matching
    # the Python _astar_search return shape.
    return [(int(i % cols), int(i // cols)) for i in path_flat]
