"""Differential tests: Rust corridor mask vs the original pure-numpy
implementation.

The pre-migration implementation is pinned here as ``_NumpyOracle`` —
the differential target for the wrapper in
``temper_placer.router_v6.corridor``.  Any change to the Rust
implementation or the wrapper that disagrees with the oracle fails
here.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from temper_placer.router_v6.corridor import extract_corridor_mask


def _numpy_oracle(
    coarse_path: list[tuple[int, int]],
    coarse_factor: int,
    buffer_cells: int,
    fine_rows: int,
    fine_cols: int,
) -> np.ndarray:
    """The pre-migration implementation, verbatim semantics."""
    mask = np.zeros((fine_rows, fine_cols), dtype=np.bool_)
    for cx, cy in coarse_path:
        r0 = max(0, cy * coarse_factor - buffer_cells)
        r1 = min(fine_rows, (cy + 1) * coarse_factor + buffer_cells)
        c0 = max(0, cx * coarse_factor - buffer_cells)
        c1 = min(fine_cols, (cx + 1) * coarse_factor + buffer_cells)
        mask[r0:r1, c0:c1] = True
    return mask


def _random_path(rng: random.Random, max_cx: int, max_cy: int, length: int) -> list[tuple[int, int]]:
    return [(rng.randrange(max_cx), rng.randrange(max_cy)) for _ in range(length)]


@pytest.mark.parametrize(
    "rows,cols,factor",
    [
        (100, 200, 4),
        (64, 64, 2),
        (33, 17, 3),
        (10, 10, 4),
        (256, 128, 8),
        (7, 9, 1),
    ],
)
def test_matches_numpy_oracle_on_random_corpus(rows: int, cols: int, factor: int) -> None:
    rng = random.Random(rows * 1000 + cols)
    for _ in range(40):
        path = _random_path(rng, max(1, cols // factor), max(1, rows // factor), rng.randrange(0, 30))
        buffer_cells = rng.randrange(0, factor * 2 + 3)
        rust = extract_corridor_mask(path, factor, buffer_cells, rows, cols)
        python = _numpy_oracle(path, factor, buffer_cells, rows, cols)
        np.testing.assert_array_equal(rust, python)


def test_matches_oracle_with_negative_buffer() -> None:
    path = [(0, 0), (1, 1)]
    rust = extract_corridor_mask(path, 4, -1, 20, 20)
    python = _numpy_oracle(path, 4, -1, 20, 20)
    np.testing.assert_array_equal(rust, python)


def test_matches_oracle_with_underflow_negative_buffer() -> None:
    # buffer below -(cy+1)*factor: numpy wraps negative slice bounds
    # (mask[r0:-1]); the Rust wrap_clamp must reproduce it bit-for-bit.
    for buffer in (-5, -8, -12, -20):
        path = [(0, 0), (1, 1)]
        rust = extract_corridor_mask(path, 4, buffer, 10, 10)
        python = _numpy_oracle(path, 4, buffer, 10, 10)
        np.testing.assert_array_equal(rust, python)


def test_matches_oracle_with_huge_buffer() -> None:
    path = [(0, 0)]
    rust = extract_corridor_mask(path, 4, 100, 12, 12)
    python = _numpy_oracle(path, 4, 100, 12, 12)
    np.testing.assert_array_equal(rust, python)


def test_matches_oracle_with_path_touching_all_edges() -> None:
    path = [(0, 0), (3, 0), (0, 4), (3, 4), (1, 2)]
    rust = extract_corridor_mask(path, 2, 1, 10, 8)
    python = _numpy_oracle(path, 2, 1, 10, 8)
    np.testing.assert_array_equal(rust, python)


def test_shape_and_dtype_contract() -> None:
    mask = extract_corridor_mask([(1, 2)], 4, 2, 100, 200)
    assert mask.shape == (100, 200)
    assert mask.dtype == np.bool_


def test_empty_path_contract() -> None:
    mask = extract_corridor_mask([], 4, 2, 100, 200)
    assert not np.any(mask)
