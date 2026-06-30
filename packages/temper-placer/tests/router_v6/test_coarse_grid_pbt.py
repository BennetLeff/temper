"""Property-based tests for coarse-to-fine downsampling correctness."""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.occupancy_grid import CellState, OccupancyGrid


def _make_grid(w: int, h: int, values: np.ndarray) -> OccupancyGrid:
    return OccupancyGrid(
        layer_name="test",
        grid=values.copy(),
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=w,
        height_cells=h,
    )


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_all_free_is_free(w, h):
    """All-free fine grid: coarse cells fully inside board are FREE."""
    fine = np.zeros((h, w), dtype=np.int8)
    og = _make_grid(w, h, fine)
    for factor in (2, 3, 4, 8):
        coarse = og.downsample(factor=factor)
        assert coarse.grid.size > 0
        # Coarse cells that are entirely within the fine grid bounds
        # (not padded) should be FREE.
        complete_cx = w // factor
        complete_cy = h // factor
        if complete_cx > 0 and complete_cy > 0:
            free_in_complete = np.sum(coarse.grid[:complete_cy, :complete_cx] == CellState.FREE.value)
            assert free_in_complete == complete_cx * complete_cy


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_all_blocked_is_blocked(w, h):
    """All-blocked fine grid: all complete coarse blocks are blocked."""
    fine = np.full((h, w), CellState.BLOCKED.value, dtype=np.int8)
    og = _make_grid(w, h, fine)
    for factor in (2, 3, 4, 8):
        coarse = og.downsample(factor=factor)
        assert coarse.grid.size > 0
        assert int(np.sum(coarse.grid != 0)) >= (w // factor) * (h // factor)


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_one_blocked_per_block(w, h):
    """One blocked cell per non-padded block => that coarse cell blocked."""
    fine = np.zeros((h, w), dtype=np.int8)
    for fy in range(h):
        for fx in range(w):
            fine[fy, fx] = 1
    og = _make_grid(w, h, fine)
    for factor in (2, 3, 4):
        coarse = og.downsample(factor=factor)
        assert coarse.grid.size > 0
        # All coarse cells that correspond to actual fine cells should be blocked
        complete_cy = h // factor
        complete_cx = w // factor
        if complete_cx > 0 and complete_cy > 0:
            free = np.sum(coarse.grid[:complete_cy, :complete_cx] == CellState.FREE.value)
            assert free == 0


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
    factor=st.integers(min_value=2, max_value=8),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_dimension_consistency(w, h, factor):
    """Coarse grid dimensions are ceil(fine_dims / factor)."""
    fine = np.zeros((h, w), dtype=np.int8)
    og = _make_grid(w, h, fine)
    coarse = og.downsample(factor=factor)
    import math
    assert coarse.width_cells == max(1, math.ceil(w / factor))
    assert coarse.height_cells == max(1, math.ceil(h / factor))
    assert coarse.cell_size == og.cell_size * factor
    assert coarse.origin == og.origin


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
    factor=st.integers(min_value=2, max_value=8),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_implication_fine_blocked_coarse_blocked(w, h, factor):
    """For every blocked fine cell, its coarse cell is also blocked."""
    fine = np.zeros((h, w), dtype=np.int8)
    rng = np.random.RandomState(42)
    # Scatter some blocked cells
    for _ in range(max(1, w * h // 4)):
        fx = rng.randint(0, w)
        fy = rng.randint(0, h)
        fine[fy, fx] = CellState.BLOCKED.value
    og = _make_grid(w, h, fine)
    coarse = og.downsample(factor=factor)
    for fy in range(h):
        for fx in range(w):
            if fine[fy, fx] != 0:
                cx, cy = fx // factor, fy // factor
                # The coarse cell may be out of bounds if the fine grid
                # was trimmed; but with ceil + padding, coarse covers all
                # fine cells
                if cx < coarse.width_cells and cy < coarse.height_cells:
                    assert (
                        coarse.grid[cy, cx] != 0
                    ), f"Fine ({fx},{fy}) blocked -> coarse ({cx},{cy}) FREE"


@given(
    w=st.integers(min_value=1, max_value=50),
    h=st.integers(min_value=1, max_value=50),
    factor=st.integers(min_value=2, max_value=8),
)
@settings(max_examples=200, deadline=30000)
def test_downsample_contrapositive_coarse_free_implies_fine_free(w, h, factor):
    """If a coarse cell is FREE, all its fine sub-cells are FREE."""
    fine = np.zeros((h, w), dtype=np.int8)
    rng = np.random.RandomState(123)
    for _ in range(max(1, w * h // 4)):
        fx = rng.randint(0, w)
        fy = rng.randint(0, h)
        fine[fy, fx] = CellState.BLOCKED.value
    og = _make_grid(w, h, fine)
    coarse = og.downsample(factor=factor)

    for cy in range(coarse.height_cells):
        for cx in range(coarse.width_cells):
            if coarse.grid[cy, cx] == CellState.FREE.value:
                fy0, fy1 = cy * factor, (cy + 1) * factor
                fx0, fx1 = cx * factor, (cx + 1) * factor
                block = fine[fy0:fy1, fx0:fx1]
                assert not np.any(block), (
                    f"Coarse ({cx},{cy}) FREE but fine block "
                    f"[{fy0}:{fy1},{fx0}:{fx1}] has blocked cells"
                )
