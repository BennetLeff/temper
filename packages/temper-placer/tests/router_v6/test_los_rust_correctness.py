"""Property-based tests: Rust LOS == Python LOS for random inputs.

Reworked from ``test_los_numba_correctness.py`` (cleanup C1, 2026-07-31):
the Numba LOS kernel was removed with the rest of the Numba backend; the
Rust kernel (``_line_of_sight_rust``) is the sole accelerated LOS and the
pure-Python ``_line_of_sight`` remains the reference oracle.  The
numba-vs-python parity evidence recorded by the retired suite is
preserved here as rust-vs-python, which is the stronger property now
that the Rust kernel is what production Theta* routing runs.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6._astar_theta_star import _line_of_sight
from temper_placer.router_v6.astar_core_numba import _line_of_sight_rust


@st.composite
def random_los_input(draw):
    w = draw(st.integers(2, 70))
    h = draw(st.integers(2, 70))
    n_cells = w * h
    flat = draw(
        st.lists(
            st.sampled_from([0, 1, 2]),
            min_size=n_cells,
            max_size=n_cells,
        )
    )
    grid_arr = np.array(flat, dtype=np.int32).reshape(h, w)
    net_id = draw(st.integers(-1, 2))
    x0 = draw(st.integers(-1, w))
    y0 = draw(st.integers(-1, h))
    x1 = draw(st.integers(-1, w))
    y1 = draw(st.integers(-1, h))
    return (x0, y0), (x1, y1), grid_arr, net_id


class FakeGrid:
    def __init__(self, grid_arr):
        self.grid = grid_arr
        self.width_cells = int(grid_arr.shape[1])
        self.height_cells = int(grid_arr.shape[0])


@pytest.fixture(autouse=True)
def rust_los_engaged():
    """Fail loudly instead of silently testing the Python fallback when
    ``temper_rust_router`` is missing/stale."""
    from temper_placer.router_v6.astar_core_numba import _select_astar_backend

    assert _select_astar_backend() == "rust", (
        "temper_rust_router did not resolve — run `make extensions` "
        "(extension missing or stale)"
    )


@given(random_los_input())
@settings(max_examples=1_000)
def test_rust_los_matches_python(input_data):
    p1, p2, grid_arr, net_id = input_data
    grid = FakeGrid(grid_arr)

    python_result = _line_of_sight(p1, p2, grid, net_id)
    rust_result = _line_of_sight_rust(p1, p2, grid, net_id)
    assert python_result == rust_result, (
        f"Mismatch: Python={python_result}, Rust={rust_result}\n"
        f"p1={p1}, p2={p2}, grid shape={grid_arr.shape}, net_id={net_id}"
    )


def test_los_empty_grid():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((0, 0), (9, 9), grid, 0) is True
    assert _line_of_sight_rust((0, 0), (9, 9), grid, -1) is True


def test_los_fully_blocked():
    grid_arr = np.ones((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((0, 0), (9, 9), grid, 0) is False


def test_los_same_cell():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((5, 5), (5, 5), grid, 0) is True

    grid_arr[5, 5] = 1
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((5, 5), (5, 5), grid, 0) is False

    grid_arr[5, 5] = 2
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((5, 5), (5, 5), grid, 2) is True


def test_los_diagonal_vs_straight():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid_arr[:, 5] = 1
    grid = FakeGrid(grid_arr)
    # Both lines should return the same result in Rust and Python
    assert _line_of_sight_rust((0, 0), (9, 4), grid, 0) == _line_of_sight((0, 0), (9, 4), grid, 0)
    assert _line_of_sight_rust((0, 0), (9, 6), grid, 0) == _line_of_sight((0, 0), (9, 6), grid, 0)


def test_los_out_of_bounds():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((-1, 5), (5, 5), grid, 0) is False
    assert _line_of_sight_rust((5, 5), (5, 10), grid, 0) is False
    assert _line_of_sight_rust((10, 0), (5, 5), grid, 0) is False


def test_los_own_net_unblocked():
    grid_arr = np.ones((5, 5), dtype=np.int32)
    grid_arr[0, 0] = 0
    grid_arr[1, 1] = 2
    grid_arr[2, 2] = 0
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((0, 0), (2, 2), grid, 2) == _line_of_sight((0, 0), (2, 2), grid, 2)


def test_los_net_id_negative_one():
    grid_arr = np.ones((5, 5), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_rust((0, 0), (4, 4), grid, -1) is False


def test_los_python_negative_coordinate_bb_shortcut_bug():
    """Regression for the BB-shortcut negative-index-wrap defect.

    ``_line_of_sight``'s bounding-box shortcut sliced
    ``grid.grid[min(y0, y1) : max(y0, y1) + 1, ...]`` directly off the
    raw (possibly negative) endpoint coordinates. Numpy treats a
    negative slice bound as counting from the end of the axis rather
    than "off the front of the grid", so on a 2x2 all-zero grid,
    ``p1=(0, 0), p2=(0, -1)`` produced the slice ``grid[-1:1, 0:1]`` --
    empty, hence "no obstruction" -- and the shortcut returned True for
    an endpoint that is actually out of bounds. The Bresenham loop's
    own ``in_bounds()`` check would (and now does) correctly reject it.

    This is the minimal repro that was failing
    ``test_numba_los_matches_python`` before the fix: Python returned
    True, the kernel (which has no BB shortcut, only the Bresenham loop)
    correctly returned False. The Rust kernel inherits the Bresenham-only
    semantics; this pins both to False.
    """
    grid_arr = np.zeros((2, 2), dtype=np.int32)
    grid = FakeGrid(grid_arr)

    p1, p2 = (0, 0), (0, -1)
    python_result = _line_of_sight(p1, p2, grid, 0)
    rust_result = _line_of_sight_rust(p1, p2, grid, 0)

    assert python_result is False
    assert rust_result is False
    assert python_result == rust_result


@pytest.mark.parametrize(
    "p1,p2",
    [
        ((0, 0), (0, -1)),  # negative y endpoint, minimal repro
        ((0, 0), (-1, 0)),  # negative x endpoint
        ((-1, -1), (0, 0)),  # negative start point
        ((0, 0), (5, 5)),  # x1 past width_cells (grid is 5x5, cols 0-4)
        ((0, 0), (0, 5)),  # y1 past height_cells
        ((-1, 0), (5, 5)),  # both endpoints out of bounds, opposite corners
    ],
)
def test_los_python_matches_rust_out_of_bounds(p1, p2):
    """Differential coverage for negative and past-the-edge endpoints.

    ``test_rust_los_matches_python`` above is a property test over a
    Hypothesis-generated input space that includes out-of-bounds
    coordinates, but a shrunk failing example is not committed
    anywhere -- this pins the specific negative/out-of-bounds shapes
    that previously diverged as an explicit, always-run regression.
    """
    grid_arr = np.zeros((5, 5), dtype=np.int32)
    grid = FakeGrid(grid_arr)

    python_result = _line_of_sight(p1, p2, grid, 0)
    rust_result = _line_of_sight_rust(p1, p2, grid, 0)
    assert python_result == rust_result, (
        f"Mismatch: Python={python_result}, Rust={rust_result}, p1={p1}, p2={p2}"
    )
