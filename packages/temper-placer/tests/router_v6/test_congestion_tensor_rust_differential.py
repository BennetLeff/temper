"""Differential tests: Rust-backed CongestionTensor vs the original
pure-numpy implementation.

The pre-migration implementation (float32 numpy storage, f64 cost math)
is pinned here as ``_NumpyOracle`` — the differential target for the
wrapper in ``temper_placer.router_v6.congestion_tensor``.  Any change
to the Rust implementation or the wrapper that disagrees with the
oracle fails here, not in a routed board one day.

Three-way parity: the router's production consumer of congestion cost
is the Rust kernel in ``astar_core_rust.py``, which computes
``np.float32(1.0) + np.log(np.float32(1.0) + raw)`` — a *different*
formula from both the oracle (f64 log1p) and the Rust cost (f64 log1p
cast to f32).  ``test_kernel_formula_relation`` pins that relationship
explicitly so it cannot silently drift.
"""

from __future__ import annotations

import math
import random

import numpy as np

from temper_placer.router_v6.congestion_tensor import (
    DECAY_FACTOR,
    MAX_COST,
    CongestionTensor,
)


class _NumpyOracle:
    """The pre-migration pure-numpy implementation, verbatim semantics."""

    def __init__(self, rows: int, cols: int, max_cost: float = MAX_COST, weight: float = 1.0):
        self.array = np.zeros((rows, cols), dtype=np.float32)
        self.max_cost = max_cost
        self.weight = weight

    def increment(self, row: int, col: int, weight: float = 1.0) -> None:
        self.array[row, col] = self.array[row, col] + weight

    def increment_path(self, coords, grid, weight: float = 1.0) -> None:
        for x, y in coords:
            gx, gy = grid.world_to_grid(x, y)
            if 0 <= gx < self.array.shape[1] and 0 <= gy < self.array.shape[0]:
                self.array[gy, gx] = self.array[gy, gx] + weight

    def cost(self, row: int, col: int) -> float:
        raw = float(self.array[row, col])
        if raw <= 0.0:
            return 1.0
        return min(self.max_cost, 1.0 + math.log1p(raw))

    def decay(self, factor: float = DECAY_FACTOR) -> None:
        self.array *= factor

    def reset(self) -> None:
        self.array.fill(0.0)


class _StubGrid:
    """Minimal grid exposing the ``world_to_grid`` contract."""

    def __init__(self, rows: int, cols: int, cell_mm: float = 1.0):
        self.rows = rows
        self.cols = cols
        self.cell_mm = cell_mm

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_mm), int(y // self.cell_mm)


def _random_usage(rng: random.Random, rows: int, cols: int) -> np.ndarray:
    """Usage counts in the range real routing produces."""
    arr = np.zeros((rows, cols), dtype=np.float32)
    for i in range(rows):
        for j in range(cols):
            arr[i, j] = rng.random() * 40.0
    return arr


# ---------------------------------------------------------------------------
# cost() parity
# ---------------------------------------------------------------------------


def test_cost_bit_identical_over_random_usages():
    rng = random.Random(20260731)
    rows, cols = 16, 16
    rust = CongestionTensor.zeros(rows, cols)
    oracle = _NumpyOracle(rows, cols)
    oracle.array = _random_usage(rng, rows, cols)
    for i in range(rows):
        for j in range(cols):
            rust.increment(i, j, float(oracle.array[i, j]))
    for i in range(rows):
        for j in range(cols):
            expect = np.float32(oracle.cost(i, j))
            assert rust.cost(i, j) == expect, f"mismatch at ({i},{j}) usage={oracle.array[i, j]}"


def test_cost_bit_identical_with_clamped_max_cost():
    # The f32/f64 clamp band: with max_cost=2.0, usage counts that push
    # 1.0 + log1p(raw) across the cap are routine (raw ~1.72).
    rng = random.Random(7)
    rows, cols = 8, 8
    rust = CongestionTensor.zeros(rows, cols, max_cost=2.0)
    oracle = _NumpyOracle(rows, cols, max_cost=2.0)
    oracle.array = _random_usage(rng, rows, cols)
    # force values straddling the clamp
    oracle.array[0, 0] = 1.71828
    oracle.array[0, 1] = 1.7183
    oracle.array[0, 2] = 2.0
    oracle.array[0, 3] = 1e6
    for i in range(rows):
        for j in range(cols):
            rust.increment(i, j, float(oracle.array[i, j]))
            expect = np.float32(oracle.cost(i, j))
            assert rust.cost(i, j) == expect, f"clamp-band mismatch at ({i},{j})"


def test_cost_floor_is_one_at_zero_and_negative_usage():
    rust = CongestionTensor.zeros(3, 3)
    for (i, j) in [(0, 0), (1, 2), (2, 1)]:
        assert rust.cost(i, j) == 1.0
    rust.increment(1, 1, -5.0)
    assert rust.cost(1, 1) == 1.0
    # out-of-bounds reads sanitize to the cost floor (the Python original
    # raised IndexError; the wrapper sanitizes instead — see
    # test_out_of_bounds_sanitized_not_folded for the fold-guard case)


def test_out_of_bounds_sanitized_not_folded():
    # (0, 2) on a 2x2 grid must NOT fold onto cell (1, 0) via a flat-index
    # check — the Python original raised IndexError; the wrapper sanitizes
    # to a no-op / cost floor.
    rust = CongestionTensor.zeros(2, 2)
    rust.increment(0, 0, 3.0)
    rust.increment(0, 2, 1.0)
    rust.increment(2, 0, 1.0)
    assert rust.array[1, 0] == 0.0  # col-OOB did not land here
    assert rust.array[0, 1] == 0.0  # row-OOB did not land here
    assert rust.cost(0, 0) == np.float32(1.0 + math.log1p(3.0))
    assert rust.cost(0, 2) == np.float32(1.0)  # sanitized floor
    assert rust.cost(99, 99) == np.float32(1.0)


def test_kernel_formula_relation():
    # The production consumer (astar_core_rust kernel) computes
    # np.float32(1.0) + np.log(np.float32(1.0) + raw) with an f32 cap.
    # It differs from the Rust/oracle f64 log1p in the last ulp for
    # raw >= ~1e-7, and collapses to exactly 1.0 for raw below half an
    # ulp of 1.0 (where log1p does not). Pin both behaviors.
    rng = random.Random(11)
    rust = CongestionTensor.zeros(1, 512)
    for j in range(512):
        raw = 10.0 ** (-8.0 + 10.0 * rng.random())
        rust.increment(0, j, raw)
        kernel = np.float32(1.0) + np.log(np.float32(1.0) + np.float32(raw))
        if kernel > np.float32(100.0):
            kernel = np.float32(100.0)
        assert rust.cost(0, j) == kernel or (
            np.abs(np.float32(rust.cost(0, j)) - kernel) <= np.spacing(np.float32(rust.cost(0, j)))
        ), f"kernel relation broken at raw={raw!r}: rust={rust.cost(0, j)!r} kernel={kernel!r}"
    raw = 1e-8
    fresh = CongestionTensor.zeros(1, 1)
    fresh.increment(0, 0, raw)
    kernel = np.float32(1.0) + np.log(np.float32(1.0) + np.float32(raw))
    assert kernel == np.float32(1.0)  # f32 1+raw collapses
    # Rust follows the f64 log1p oracle (also rounds to 1.0 at this raw) —
    # the meaningful three-way claim is kernel-collapse vs oracle-follow.
    assert fresh.cost(0, 0) == np.float32(1.0 + math.log1p(np.float64(raw)))


# ---------------------------------------------------------------------------
# increment / increment_path parity
# ---------------------------------------------------------------------------


def test_increment_matches_oracle_bit_exact():
    rng = random.Random(3)
    rows, cols = 12, 12
    rust = CongestionTensor.zeros(rows, cols)
    oracle = _NumpyOracle(rows, cols)
    for _ in range(500):
        i, j = rng.randrange(rows), rng.randrange(cols)
        w = rng.random() * 3.0
        rust.increment(i, j, w)
        oracle.increment(i, j, w)
    np.testing.assert_array_equal(rust.array, oracle.array)


def test_increment_path_matches_oracle_with_grid_mapping():
    rng = random.Random(5)
    rows, cols, cell = 20, 30, 1.0
    rust = CongestionTensor.zeros(rows, cols)
    oracle = _NumpyOracle(rows, cols)
    grid = _StubGrid(rows, cols, cell_mm=cell)
    coords = [(rng.random() * 40 - 5, rng.random() * 40 - 5) for _ in range(800)]
    rust.increment_path(coords, grid, weight=0.7)
    oracle.increment_path(coords, grid, weight=0.7)
    np.testing.assert_array_equal(rust.array, oracle.array)


def test_increment_path_skips_out_of_bounds_like_oracle():
    grid = _StubGrid(5, 5)
    rust = CongestionTensor.zeros(5, 5)
    oracle = _NumpyOracle(5, 5)
    coords = [(2.5, 2.5), (-1.0, 0.0), (0.0, -1.0), (100.0, 0.0), (0.0, 100.0), (4.9, 4.9)]
    rust.increment_path(coords, grid)
    oracle.increment_path(coords, grid)
    np.testing.assert_array_equal(rust.array, oracle.array)
    assert rust.array[2, 2] == 1.0
    assert rust.array[4, 4] == 1.0
    assert rust.array.sum() == 2.0


def test_decay_and_reset_match_oracle():
    rng = random.Random(9)
    rows, cols = 8, 8
    rust = CongestionTensor.zeros(rows, cols)
    oracle = _NumpyOracle(rows, cols)
    oracle.array = _random_usage(rng, rows, cols)
    for i in range(rows):
        for j in range(cols):
            rust.increment(i, j, float(oracle.array[i, j]))
    rust.decay(0.95)
    oracle.decay(0.95)
    np.testing.assert_array_equal(rust.array, oracle.array)
    rust.reset()
    oracle.reset()
    np.testing.assert_array_equal(rust.array, oracle.array)


def test_weight_and_max_cost_passthrough():
    # weight/max_cost live in f32 Rust storage; the kernel consumes them as
    # np.float32, so the f32 round-trip is the parity contract.
    rust = CongestionTensor.zeros(2, 2, max_cost=42.0, weight=0.3)
    assert rust.max_cost == np.float32(42.0)
    assert rust.weight == np.float32(0.3)
    rust.weight = 0.1
    rust.max_cost = 7.5
    assert rust.weight == np.float32(0.1)
    assert rust.max_cost == np.float32(7.5)


def test_array_shape_dtype_and_readonly():
    rust = CongestionTensor.zeros(3, 5)
    arr = rust.array
    assert arr.shape == (3, 5)
    assert arr.dtype == np.float32
    assert not arr.flags.writeable  # fresh copy per access; never cache
    rust.increment(1, 2, 4.0)
    assert rust.array[1, 2] == 4.0  # fresh copy sees the mutation
    assert arr[1, 2] == 0.0  # the earlier view is stale by design
