"""
Wave 4 PR-C — PathFinder history cost (R11)

Verifies the PathFinder-style per-cell congestion tensor from
the closure-rate rollout plan.

R11: ``CongestionTensor`` in ``router_v6/congestion_tensor.py``
    stores per-cell usage counts.  After each successful net
    commit, the cells along the routed path are incremented.
    The Numba-jitted A* inner loop reads the tensor as a flat
    float32 array and adds ``min(100, 1 + log(1 + raw))`` to the
    f_score of every expansion, so the next net naturally
    detours around already-routed channels.

These tests cover the tensor math only (no end-to-end
closure-test rerun).  The integration test is the
``scripts/baseline_smoke_3min.py`` run on ``temper.kicad_pcb``:
with U7 wired in, the easy nets stay at 13/24, and the
previously-stuck hard nets (GATE_H, GATE_L, SPI_*, etc.) should
start routing.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from temper_placer.router_v6.congestion_tensor import (
    CongestionTensor,
    DECAY_FACTOR,
    MAX_COST,
)


def test_tensor_zeros_starts_at_one_cost():
    """Empty tensor: every cell cost is 1.0 (the base; no
    congestion penalty applied)."""
    t = CongestionTensor.zeros(5, 7)
    assert t.array.shape == (5, 7)
    assert t.array.dtype == np.float32
    assert (t.array == 0.0).all()
    assert t.cost(2, 3) == 1.0
    assert t.cost(0, 0) == 1.0


def test_tensor_increment_and_cost_grows_logarithmically():
    """After N increments, cost is min(max_cost, 1 + log(1 + N))."""
    t = CongestionTensor.zeros(3, 3)
    for _ in range(10):
        t.increment(1, 1)
    raw = float(t.array[1, 1])
    assert raw == 10.0
    expected = 1.0 + math.log1p(10.0)  # 1 + ln(11) ≈ 3.398
    assert abs(t.cost(1, 1) - expected) < 1e-5
    # Untouched cell stays at 1.0
    assert t.cost(0, 0) == 1.0


def test_tensor_cost_caps_at_max_cost():
    """Cost never exceeds ``max_cost`` (default 100)."""
    t = CongestionTensor.zeros(2, 2)
    # Need raw > e^(max_cost - 1) to hit the cap.  With max_cost=100,
    # e^99 ≈ 1e43 increments needed.  Use a much smaller custom
    # cap so the test runs in reasonable time.
    t = CongestionTensor(np.zeros((2, 2), dtype=np.float32), max_cost=10.0)
    for _ in range(100_000):
        t.increment(0, 0)
    assert t.cost(0, 0) == 10.0
    # And it's exactly 10, not larger
    assert t.cost(0, 0) <= 10.0


def test_tensor_increment_path_world_to_grid():
    """increment_path maps world coords to grid via the
    grid's ``world_to_grid`` and increments each cell.
    """
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid
    from shapely.geometry import MultiPolygon, Polygon

    class _Grid:
        width_cells = 10
        height_cells = 10

        def world_to_grid(self, x, y):
            return (int(x), int(y))

    g = _Grid()
    t = CongestionTensor.zeros(10, 10)
    # Path of 4 points: (1, 1), (2, 1), (3, 1), (4, 1)
    t.increment_path([(1, 1), (2, 1), (3, 1), (4, 1)], g)
    assert t.array[1, 1] == 1.0
    assert t.array[1, 2] == 1.0
    assert t.array[1, 3] == 1.0
    assert t.array[1, 4] == 1.0
    # Untouched cells stay at 0
    assert t.array[5, 5] == 0.0


def test_tensor_increment_path_skips_out_of_bounds():
    """increment_path skips coords that map outside the grid."""
    class _Grid:
        width_cells = 3
        height_cells = 3

        def world_to_grid(self, x, y):
            return (int(x), int(y))

    g = _Grid()
    t = CongestionTensor.zeros(3, 3)
    # Coords that map to out-of-bounds: (5, 5) → (5, 5) → OOB
    t.increment_path([(0, 0), (5, 5), (2, 2)], g)
    assert t.array[0, 0] == 1.0
    assert t.array[2, 2] == 1.0
    # (5, 5) was OOB; the array doesn't have a [5, 5] entry
    # so the increment was skipped (no exception, no off-by-one).
    assert t.array[1, 1] == 0.0


def test_tensor_decay_multiplies_by_factor():
    """decay(factor) multiplies every cell by ``factor`` (used by
    the optional global-iteration loop in the plan's deferred
    variant).  Default factor is 0.95.
    """
    t = CongestionTensor.zeros(3, 3)
    t.increment(1, 1)
    t.increment(1, 1)
    assert t.array[1, 1] == 2.0
    t.decay(0.5)
    assert t.array[1, 1] == 1.0
    assert (t.array == 0.0).sum() == 8  # other cells stay 0


def test_tensor_reset_zeroes_everything():
    """reset() zeroes all cells; the cost returns to 1.0."""
    t = CongestionTensor.zeros(3, 3)
    t.increment(0, 0)
    t.increment(1, 1)
    assert t.cost(0, 0) > 1.0
    t.reset()
    assert (t.array == 0.0).all()
    assert t.cost(0, 0) == 1.0
    assert t.cost(2, 2) == 1.0


def test_tensor_max_cost_is_configurable():
    """Constructor accepts a custom ``max_cost``.  Use a small
    cap so the test can hit it without 1e43 increments."""
    t = CongestionTensor(
        np.zeros((2, 2), dtype=np.float32), max_cost=5.0
    )
    for _ in range(500):  # 500 > e^4 ≈ 54, so the cap kicks in
        t.increment(0, 0)
    assert t.cost(0, 0) == 5.0


def test_kernel_with_weight_zero_matches_no_tensor():
    """When ``congestion_weight=0`` the kernel should match
    the no-tensor path in time.  The U7 branch is gated on
    ``congestion_weight > 0.0`` in
    ``astar_core_numba._kernel`` so Numba prunes the dead
    per-neighbor arithmetic; the wall time at high iters must
    not regress.  This is the regression guard for the
    2026-06-23 full-pipeline profile that surfaced the
    1M-cap wall-time blowup.
    """
    import time
    from temper_placer.router_v6.astar_core_numba import (
        _astar_search_numba,
    )
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    grid = OccupancyGrid(
        "F.Cu", np.zeros((80, 80), dtype=np.int8), (0, 0), 1.0, 80, 80,
    )
    start = (5, 5)
    goal = (75, 75)
    flat = np.zeros((80, 80), dtype=np.float32).reshape(-1)

    # Warm-up: one throwaway call so the Numba JIT compile
    # is paid outside the timed region.  Numba specializes on
    # arg types so we also warm up both the no-tensor and
    # weight-zero signatures.
    _astar_search_numba(start, goal, grid, max_iterations=10_000)
    _astar_search_numba(
        start, goal, grid, max_iterations=10_000,
        congestion_flat=flat, congestion_weight=0.0,
        max_congestion_cost=100.0,
    )

    # Average over 3 runs to smooth out scheduler noise.
    no_tensor_runs = []
    for _ in range(3):
        t0 = time.perf_counter()
        _astar_search_numba(start, goal, grid, max_iterations=200_000)
        no_tensor_runs.append((time.perf_counter() - t0) * 1000.0)

    weight_zero_runs = []
    for _ in range(3):
        t0 = time.perf_counter()
        _astar_search_numba(
            start, goal, grid, max_iterations=200_000,
            congestion_flat=flat, congestion_weight=0.0,
            max_congestion_cost=100.0,
        )
        weight_zero_runs.append((time.perf_counter() - t0) * 1000.0)

    no_tensor_ms = min(no_tensor_runs)
    weight_zero_ms = min(weight_zero_runs)

    # Tolerance: weight=0 should match no-tensor (the kernel
    # branch is pruned by Numba).  A 50% slack absorbs the
    # remaining noise from CPython's GC and OS scheduling.
    ratio = weight_zero_ms / max(no_tensor_ms, 0.01)
    assert ratio < 1.50, (
        f"weight=0 took {weight_zero_ms:.1f}ms vs no-tensor "
        f"{no_tensor_ms:.1f}ms (ratio={ratio:.2f}); the U7 "
        f"branch is not pruned when weight=0"
    )
