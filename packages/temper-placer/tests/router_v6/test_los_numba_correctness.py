"""Property-based tests: Numba LOS == Python LOS for random inputs."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import _line_of_sight
from temper_placer.router_v6.astar_core_numba import _line_of_sight_numba


@st.composite
def random_los_input(draw):
    w = draw(st.integers(2, 70))
    h = draw(st.integers(2, 70))
    n_cells = w * h
    flat = draw(st.lists(
        st.sampled_from([0, 1, 2]),
        min_size=n_cells, max_size=n_cells,
    ))
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


@given(random_los_input())
@settings(max_examples=1_000)
def test_numba_los_matches_python(input_data):
    p1, p2, grid_arr, net_id = input_data
    grid = FakeGrid(grid_arr)

    python_result = _line_of_sight(p1, p2, grid, net_id)
    numba_result = _line_of_sight_numba(p1, p2, grid, net_id)
    assert python_result == numba_result, (
        f"Mismatch: Python={python_result}, Numba={numba_result}\n"
        f"p1={p1}, p2={p2}, grid shape={grid_arr.shape}, net_id={net_id}")


def test_los_empty_grid():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((0, 0), (9, 9), grid, 0) is True
    assert _line_of_sight_numba((0, 0), (9, 9), grid, -1) is True


def test_los_fully_blocked():
    grid_arr = np.ones((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((0, 0), (9, 9), grid, 0) is False


def test_los_same_cell():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((5, 5), (5, 5), grid, 0) is True

    grid_arr[5, 5] = 1
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((5, 5), (5, 5), grid, 0) is False

    grid_arr[5, 5] = 2
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((5, 5), (5, 5), grid, 2) is True


def test_los_diagonal_vs_straight():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid_arr[:, 5] = 1
    grid = FakeGrid(grid_arr)
    # Both lines should return the same result in Python and Numba
    assert _line_of_sight_numba((0, 0), (9, 4), grid, 0) == \
           _line_of_sight((0, 0), (9, 4), grid, 0)
    assert _line_of_sight_numba((0, 0), (9, 6), grid, 0) == \
           _line_of_sight((0, 0), (9, 6), grid, 0)


def test_los_out_of_bounds():
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((-1, 5), (5, 5), grid, 0) is False
    assert _line_of_sight_numba((5, 5), (5, 10), grid, 0) is False
    assert _line_of_sight_numba((10, 0), (5, 5), grid, 0) is False


def test_los_own_net_unblocked():
    grid_arr = np.ones((5, 5), dtype=np.int32)
    grid_arr[0, 0] = 0
    grid_arr[1, 1] = 2
    grid_arr[2, 2] = 0
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((0, 0), (2, 2), grid, 2) == \
           _line_of_sight((0, 0), (2, 2), grid, 2)


def test_los_net_id_negative_one():
    grid_arr = np.ones((5, 5), dtype=np.int32)
    grid = FakeGrid(grid_arr)
    assert _line_of_sight_numba((0, 0), (4, 4), grid, -1) is False


@pytest.mark.skipif(
    not __import__("importlib").import_module(
        "temper_placer.router_v6.astar_core_numba"
    )._HAVE_NUMBA,
    reason="Numba not installed",
)
def test_los_numba_compiles():
    from temper_placer.router_v6.astar_core_numba import _get_los_kernel
    kernel = _get_los_kernel()
    assert kernel is not None
    grid_arr = np.zeros((10, 10), dtype=np.int32)
    result = kernel(0, 0, 9, 9, np.ascontiguousarray(grid_arr), 10, 10, 0)
    assert result is True or result is False
