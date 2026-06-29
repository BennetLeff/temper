"""
Hypothesis strategies for A* pathfinding property tests.

Composable strategies for generating occupancy grids, start/goal pairs,
obstacle perturbations, and grid translations. Follows the conventions
established in ``dfm_property_strategies.py``.

Strategies
----------
* ``grids`` -- generated OccupancyGrid with Bernoulli obstacle placement
* ``start_goal_pairs`` -- two distinct free cells from a grid
* ``obstacle_perturbations`` -- add/remove a single obstacle on a grid
* ``grid_translations`` -- shift grid contents by (dx, dy) into a larger grid

Per Q4: separate module from oracle utils to keep the oracle clean of
Hypothesis imports.
"""

from __future__ import annotations

import numpy as np
from hypothesis import assume
from hypothesis import strategies as st

from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _default_rows(rows):
    """Coerce rows parameter to a strategy."""
    if isinstance(rows, st.SearchStrategy):
        return rows
    return st.just(rows)


def _default_cols(cols):
    """Coerce cols parameter to a strategy."""
    if isinstance(cols, st.SearchStrategy):
        return cols
    return st.just(cols)


def _default_density(p_obstacle):
    """Coerce p_obstacle to a strategy."""
    if isinstance(p_obstacle, st.SearchStrategy):
        return p_obstacle
    return st.just(p_obstacle)


# @req(2026-06-28-001, R6): Hypothesis strategies for A* grids
@st.composite
def grids(
    draw: st.DrawFn,
    rows: int | st.SearchStrategy = st.integers(2, 30),
    cols: int | st.SearchStrategy | None = None,
    p_obstacle: float | st.SearchStrategy = st.floats(0.0, 0.6),
) -> OccupancyGrid:
    """Generate an OccupancyGrid with Bernoulli(p_obstacle) obstacle placement.

    ``rows`` and ``cols`` may be integers or Hypothesis strategies.
    At least one free cell is guaranteed by rejection sampling.

    Returns an OccupancyGrid with layer_name="Test", origin=(0,0),
    cell_size=1.0.
    """
    r = draw(_default_rows(rows))
    c = draw(_default_cols(rows)) if cols is None else draw(_default_cols(cols))
    p = draw(_default_density(p_obstacle))

    seed = draw(st.integers(0, 2**31 - 1))
    rng = np.random.RandomState(seed)
    arr = rng.binomial(1, p, size=(r, c)).astype(np.int8)
    assume(np.any(arr == 0))  # at least one free cell

    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, c, r)


# @req(2026-06-28-001, R6): start/goal pair strategy
@st.composite
def start_goal_pairs(
    draw: st.DrawFn,
    grid: OccupancyGrid,
    same_layer: bool = True,  # noqa: ARG001 -- reserved for future 3D
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Draw two distinct free cells from *grid*.

    Returns ``((sx, sy), (gx, gy))`` in grid coordinates.
    """
    arr = grid.grid
    free_cells = [(int(x), int(y)) for y in range(arr.shape[0]) for x in range(arr.shape[1]) if arr[y, x] == 0]
    assume(len(free_cells) >= 2)
    start_idx = draw(st.integers(0, len(free_cells) - 1))
    goal_indices = [i for i in range(len(free_cells)) if i != start_idx]
    goal_idx = draw(st.sampled_from(goal_indices))
    return (free_cells[start_idx], free_cells[goal_idx])


# @req(2026-06-28-001, R6): obstacle perturbation strategy
@st.composite
def obstacle_perturbations(
    draw: st.DrawFn,
    grid: OccupancyGrid,
    start: tuple[int, int] | None = None,
    goal: tuple[int, int] | None = None,
    mode: str = "add",
) -> OccupancyGrid:
    """Perturb *grid* by adding or removing a single obstacle.

    ``mode='add'`` (default): block a free cell (not start/goal).
    ``mode='remove'``: free a blocked cell.
    ``mode='either'``: randomly pick add or remove.

    Returns a copy of the grid with the perturbation applied.  The
    original grid is not mutated.
    """
    import copy

    new_arr = copy.deepcopy(grid.grid)
    rows, cols = int(new_arr.shape[0]), int(new_arr.shape[1])

    if mode == "either":
        mode = draw(st.sampled_from(["add", "remove"]))

    if mode == "add":
        free_not_sg = [
            (x, y) for y in range(rows) for x in range(cols)
            if new_arr[y, x] == 0 and (x, y) != start and (x, y) != goal
        ]
        assume(len(free_not_sg) >= 1)
        ex, ey = draw(st.sampled_from(free_not_sg))
        new_arr[ey, ex] = 1
    else:
        blocked = [
            (x, y) for y in range(rows) for x in range(cols)
            if new_arr[y, x] != 0 and (x, y) != start and (x, y) != goal
        ]
        assume(len(blocked) >= 1)
        ex, ey = draw(st.sampled_from(blocked))
        new_arr[ey, ex] = 0

    return OccupancyGrid(grid.layer_name, new_arr, grid.origin, grid.cell_size, cols, rows)


# @req(2026-06-28-001, R6): grid translation strategy
@st.composite
def grid_translations(
    draw: st.DrawFn,
    grid: OccupancyGrid,
    max_shift: tuple[int, int] | None = None,
) -> tuple[OccupancyGrid, int, int]:
    """Shift *grid* contents by (dx, dy) into a larger padded grid.

    Returns ``(translated_grid, dx, dy)``.  The new grid is 2x larger in
    each dimension unless *max_shift* is provided.
    """
    rows, cols = int(grid.grid.shape[0]), int(grid.grid.shape[1])

    if max_shift is not None:
        max_dx, max_dy = max_shift
    else:
        max_dx, max_dy = cols, rows

    dx = draw(st.integers(0, max(0, max_dx)))
    dy = draw(st.integers(0, max(0, max_dy)))

    new_rows = rows + max_dy + 1
    new_cols = cols + max_dx + 1
    new_arr = np.ones((new_rows, new_cols), dtype=grid.grid.dtype)
    new_arr[dy : dy + rows, dx : dx + cols] = grid.grid

    t_grid = OccupancyGrid(grid.layer_name, new_arr, grid.origin, grid.cell_size, new_cols, new_rows)
    return t_grid, dx, dy


# @req(2026-06-28-001, R6): combined grid-and-pair strategy for convenience
@st.composite
def grid_and_pair(
    draw: st.DrawFn,
    rows: int | st.SearchStrategy = st.integers(2, 30),
    cols: int | st.SearchStrategy | None = None,
    p_obstacle: float | st.SearchStrategy = st.floats(0.0, 0.6),
) -> tuple[OccupancyGrid, tuple[int, int], tuple[int, int]]:
    """Draw a grid and a start/goal pair in one composite.

    Returns ``(grid, start, goal)``.
    """
    g = draw(grids(rows, cols, p_obstacle))
    s, gl = draw(start_goal_pairs(g))
    return g, s, gl
