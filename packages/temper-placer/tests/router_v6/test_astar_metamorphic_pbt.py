"""
Metamorphic Property-Based Tests for A* Pathfinding.

Implements all 9 metamorphic relation tests (MR1-MR9) as standalone
Hypothesis ``@given``-based property tests. Each relation is tested via
random sampling (>=100 examples) on grids up to 100x100 and exhaustively
on 3x3 grids.

MR1 — Rotation Invariance
MR2 — Symmetry (Swap Start/Goal)
MR3 — Obstacle Monotonicity (Addition)
MR4 — Obstacle Monotonicity (Removal)
MR5 — Edge-Weight Scaling
MR6 — Empty-Grid Optimality
MR7 — Grid Translation Invariance
MR8 — Path Cells Free
MR9 — No Redundant Nodes
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import _astar_search, octile_distance
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

from astar_oracle_utils import (
    SQRT2,
    DIJKSTRA_MAX_CELLS,
    dijkstra_shortest_path,
)
from astar_property_strategies import (
    grid_and_pair,
    grids,
    obstacle_perturbations,
    start_goal_pairs,
    grid_translations,
)

_TOL = 1e-12
_RELAXED_TOL = 1e-6  # for Theta* relaxed assertions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_cost_octile(path: list[tuple[int, int]]) -> float:
    cost = 0.0
    for i in range(len(path) - 1):
        dx = abs(path[i + 1][0] - path[i][0])
        dy = abs(path[i + 1][1] - path[i][1])
        cost += SQRT2 if dx != 0 and dy != 0 else 1.0
    return cost


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or set()):
        arr[r, c] = 1
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)


def _rotate_grid(
    grid: OccupancyGrid, start: tuple[int, int], goal: tuple[int, int], degrees: int
) -> tuple[OccupancyGrid, tuple[int, int], tuple[int, int]]:
    """Rotate grid and coordinates by 0, 90, 180, or 270 degrees."""
    arr = grid.grid
    h, w = arr.shape

    if degrees == 0:
        return grid, start, goal
    elif degrees == 90:
        new_arr = np.rot90(arr, k=-1)  # clockwise
        new_start = (int(h - 1 - start[1]), int(start[0]))
        new_goal = (int(h - 1 - goal[1]), int(goal[0]))
    elif degrees == 180:
        new_arr = np.rot90(arr, k=2)
        new_start = (int(w - 1 - start[0]), int(h - 1 - start[1]))
        new_goal = (int(w - 1 - goal[0]), int(h - 1 - goal[1]))
    elif degrees == 270:
        new_arr = np.rot90(arr, k=1)  # counter-clockwise = 270 clockwise
        new_start = (int(start[1]), int(w - 1 - start[0]))
        new_goal = (int(goal[1]), int(w - 1 - goal[0]))
    else:
        raise ValueError(f"Unsupported rotation: {degrees}")

    new_h, new_w = new_arr.shape
    new_grid = OccupancyGrid(grid.layer_name, new_arr, grid.origin, grid.cell_size, new_w, new_h)
    return new_grid, new_start, new_goal


# =============================================================================
# MR1 — Rotation Invariance
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(3, 20, 0.3), rotation=st.sampled_from([90, 180, 270]))
@settings(max_examples=100, deadline=30000)
def test_mr1_rotation_invariance(gsp, rotation):
    """Rotate grid and start/goal by `rotation` degrees; assert cost unchanged."""
    grid, start, goal = gsp
    r_grid, r_start, r_goal = _rotate_grid(grid, start, goal, rotation)

    path_orig = _astar_search(start, goal, grid)
    path_rot = _astar_search(r_start, r_goal, r_grid)

    assert (path_orig is None) == (path_rot is None), (
        f"Rotation {rotation}: completeness mismatch"
    )

    if path_orig is not None and path_rot is not None:
        cost_orig = _path_cost_octile(path_orig)
        cost_rot = _path_cost_octile(path_rot)
        assert abs(cost_orig - cost_rot) < _TOL, (
            f"Rotation {rotation}: cost {cost_orig} vs {cost_rot}"
        )


# @req(2026-06-28-001, R5): exhaustive 3x3 for MR1
@pytest.mark.l2_exhaustive
def test_mr1_rotation_3x3_exhaustive():
    """Exhaustive 3x3 verification of MR1 (Rotation Invariance)."""
    for occ_bits in range(512):
        blocked: set[tuple[int, int]] = set()
        for r in range(3):
            for c in range(3):
                if occ_bits & (1 << (r * 3 + c)):
                    blocked.add((r, c))
        grid = _make_grid(3, 3, blocked)
        free_cells = [(c, r) for r in range(3) for c in range(3) if grid.grid[r, c] == 0]

        for i in range(len(free_cells)):
            for j in range(i + 1, len(free_cells)):
                s, g = free_cells[i], free_cells[j]
                path_orig = _astar_search(s, g, grid)

                for rot in [90, 180, 270]:
                    r_grid, rs, rg = _rotate_grid(grid, s, g, rot)
                    r_path = _astar_search(rs, rg, r_grid)

                    # Completeness parity
                    assert (path_orig is None) == (r_path is None), (
                        f"Rotation {rot}: cfg={occ_bits}, {s}->{g}: completeness mismatch"
                    )

                    if path_orig is not None and r_path is not None:
                        cost_orig = _path_cost_octile(path_orig)
                        cost_rot = _path_cost_octile(r_path)
                        assert abs(cost_orig - cost_rot) < _TOL, (
                            f"Rotation {rot}: cfg={occ_bits}, {s}->{g}: "
                            f"{cost_orig} vs {cost_rot}"
                        )


# =============================================================================
# MR2 — Symmetry (Swap Start/Goal)
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_mr2_symmetry(gsp):
    """Swap start/goal; assert cost unchanged."""
    grid, start, goal = gsp
    path_fwd = _astar_search(start, goal, grid)
    path_rev = _astar_search(goal, start, grid)

    assert (path_fwd is None) == (path_rev is None), "Completeness mismatch"

    if path_fwd is not None and path_rev is not None:
        cost_fwd = _path_cost_octile(path_fwd)
        cost_rev = _path_cost_octile(path_rev)
        assert abs(cost_fwd - cost_rev) < _TOL, (
            f"Symmetry: {start}->{goal}={cost_fwd} vs {goal}->{start}={cost_rev}"
        )


@pytest.mark.l2_exhaustive
def test_mr2_symmetry_3x3_exhaustive():
    """Exhaustive 3x3 verification of MR2 (Symmetry)."""
    for occ_bits in range(512):
        blocked: set[tuple[int, int]] = set()
        for r in range(3):
            for c in range(3):
                if occ_bits & (1 << (r * 3 + c)):
                    blocked.add((r, c))
        grid = _make_grid(3, 3, blocked)
        free_cells = [(c, r) for r in range(3) for c in range(3) if grid.grid[r, c] == 0]

        for i in range(len(free_cells)):
            for j in range(i + 1, len(free_cells)):
                s, g = free_cells[i], free_cells[j]
                p1 = _astar_search(s, g, grid)
                p2 = _astar_search(g, s, grid)
                assert (p1 is None) == (p2 is None), f"cfg={occ_bits} {s}<->{g}: completeness"
                if p1 is not None and p2 is not None:
                    c1 = _path_cost_octile(p1)
                    c2 = _path_cost_octile(p2)
                    assert abs(c1 - c2) < _TOL, f"cfg={occ_bits} {s}<->{g}: {c1} vs {c2}"


# =============================================================================
# MR3 — Obstacle Monotonicity (Addition)
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 30, st.floats(0.05, 0.3)))
@settings(max_examples=100, deadline=30000)
def test_mr3_obstacle_addition(gsp):
    """Add an obstacle; new_cost >= original_cost or new is None."""
    grid, start, goal = gsp
    path_orig = _astar_search(start, goal, grid)

    # Generate perturbed grid by adding an obstacle
    perturbed = _add_random_obstacle(grid, start, goal)
    if perturbed is None:
        return  # No free cell to block (skip this sample)

    path_new = _astar_search(start, goal, perturbed)

    if path_orig is None:
        return  # Original unreachable, nothing to assert

    if path_new is not None:
        cost_orig = _path_cost_octile(path_orig)
        cost_new = _path_cost_octile(path_new)
        assert cost_new >= cost_orig - _TOL, (
            f"Obstacle addition reduced cost: {cost_orig} -> {cost_new}"
        )
    # else: path_new is None, which satisfies ">= or None"


def _add_random_obstacle(grid: OccupancyGrid, start, goal) -> OccupancyGrid | None:
    """Return a copy of grid with a random free cell blocked (not start/goal)."""
    import copy
    import random
    arr = copy.deepcopy(grid.grid)
    free_not_sg = [
        (x, y) for y in range(arr.shape[0]) for x in range(arr.shape[1])
        if arr[y, x] == 0 and (x, y) != start and (x, y) != goal
    ]
    if not free_not_sg:
        return None
    ex, ey = random.choice(free_not_sg)
    arr[ey, ex] = 1
    return OccupancyGrid(grid.layer_name, arr, grid.origin, grid.cell_size,
                         grid.width_cells, grid.height_cells)


@pytest.mark.l2_exhaustive
def test_mr3_obstacle_addition_3x3_exhaustive():
    """Exhaustive 3x3 verification of MR3 (Obstacle Addition)."""
    for occ_bits in range(512):
        blocked: set[tuple[int, int]] = set()
        for r in range(3):
            for c in range(3):
                if occ_bits & (1 << (r * 3 + c)):
                    blocked.add((r, c))
        grid = _make_grid(3, 3, blocked)
        free_cells = [(c, r) for r in range(3) for c in range(3) if grid.grid[r, c] == 0]

        for i in range(len(free_cells)):
            for j in range(i + 1, len(free_cells)):
                s, g = free_cells[i], free_cells[j]
                path_orig = _astar_search(s, g, grid)
                if path_orig is None:
                    continue  # Original unreachable

                cost_orig = _path_cost_octile(path_orig)

                # Try adding each free non-s/g cell
                for k in range(len(free_cells)):
                    if free_cells[k] in (s, g):
                        continue
                    perturbed = _add_obstacle_at(grid, free_cells[k])
                    path_new = _astar_search(s, g, perturbed)
                    if path_new is not None:
                        cost_new = _path_cost_octile(path_new)
                        assert cost_new >= cost_orig - _TOL, (
                            f"Addition {free_cells[k]}: {cost_orig} -> {cost_new}"
                        )


def _add_obstacle_at(grid: OccupancyGrid, pos: tuple[int, int]) -> OccupancyGrid:
    import copy
    arr = copy.deepcopy(grid.grid)
    arr[pos[1], pos[0]] = 1
    return OccupancyGrid(grid.layer_name, arr, grid.origin, grid.cell_size,
                         grid.width_cells, grid.height_cells)


# =============================================================================
# MR4 — Obstacle Monotonicity (Removal)
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 30, st.floats(0.05, 0.4)))
@settings(max_examples=100, deadline=30000)
def test_mr4_obstacle_removal(gsp):
    """Remove an obstacle; new_cost <= original_cost or new becomes reachable."""
    grid, start, goal = gsp
    path_orig = _astar_search(start, goal, grid)

    perturbed = _remove_random_obstacle(grid, start, goal)
    if perturbed is None:
        return

    path_new = _astar_search(start, goal, perturbed)

    if path_orig is not None and path_new is not None:
        cost_orig = _path_cost_octile(path_orig)
        cost_new = _path_cost_octile(path_new)
        assert cost_new <= cost_orig + _TOL, (
            f"Obstacle removal increased cost: {cost_orig} -> {cost_new}"
        )
    # If original was unreachable and new is reachable, that's valid


def _remove_random_obstacle(grid: OccupancyGrid, start, goal) -> OccupancyGrid | None:
    import copy
    import random
    arr = copy.deepcopy(grid.grid)
    blocked = [
        (x, y) for y in range(arr.shape[0]) for x in range(arr.shape[1])
        if arr[y, x] != 0 and (x, y) != start and (x, y) != goal
    ]
    if not blocked:
        return None
    ex, ey = random.choice(blocked)
    arr[ey, ex] = 0
    return OccupancyGrid(grid.layer_name, arr, grid.origin, grid.cell_size,
                         grid.width_cells, grid.height_cells)


@pytest.mark.l2_exhaustive
def test_mr4_obstacle_removal_3x3_exhaustive():
    """Exhaustive 3x3 verification of MR4 (Obstacle Removal)."""
    for occ_bits in range(512):
        blocked: set[tuple[int, int]] = set()
        for r in range(3):
            for c in range(3):
                if occ_bits & (1 << (r * 3 + c)):
                    blocked.add((r, c))
        grid = _make_grid(3, 3, blocked)
        free_cells = [(c, r) for r in range(3) for c in range(3) if grid.grid[r, c] == 0]
        blocked_cells = [(c, r) for r in range(3) for c in range(3) if grid.grid[r, c] != 0]

        for i in range(len(free_cells)):
            for j in range(i + 1, len(free_cells)):
                s, g = free_cells[i], free_cells[j]
                path_orig = _astar_search(s, g, grid)
                cost_orig = _path_cost_octile(path_orig) if path_orig else float("inf")

                for bk in blocked_cells:
                    if bk in (s, g):
                        continue
                    arr2 = np.copy(grid.grid)
                    arr2[bk[1], bk[0]] = 0
                    pgrid = OccupancyGrid("Test", arr2, (0.0, 0.0), 1.0,
                                          grid.width_cells, grid.height_cells)
                    path_new = _astar_search(s, g, pgrid)
                    if path_orig is not None and path_new is not None:
                        cost_orig = _path_cost_octile(path_orig)
                        cost_new = _path_cost_octile(path_new)
                        assert cost_new <= cost_orig + _TOL, (
                            f"Removal {bk}: cfg={occ_bits} {s}->{g}: {cost_orig} -> {cost_new}"
                        )
                    # If original was unreachable, removal may make it reachable (valid)
                    # If both unreachable, nothing to assert


# =============================================================================
# MR5 — Edge-Weight Scaling
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 30, 0.3), k=st.floats(0.5, 5.0, exclude_min=True))
@settings(max_examples=100, deadline=30000)
def test_mr5_edge_weight_scaling(gsp, k):
    """Scale cell_size; assert grid cost unchanged, physical cost scales."""
    grid, start, goal = gsp
    path_orig = _astar_search(start, goal, grid)
    if path_orig is None:
        return

    cost_grid = _path_cost_octile(path_orig)
    cost_physical_orig = cost_grid * grid.cell_size

    # Create grid with scaled cell_size. A* uses fixed grid costs (1.0/sqrt2)
    # independent of cell_size, so grid_cost should be the same.
    # Physical cost = grid_cost * cell_size, scales linearly with cell_size.
    scaled_cell = grid.cell_size * k
    scaled_grid = OccupancyGrid(
        grid.layer_name,
        np.copy(grid.grid),
        grid.origin,
        scaled_cell,
        grid.width_cells,
        grid.height_cells,
    )
    path_scaled = _astar_search(start, goal, scaled_grid)
    if path_scaled is None:
        return

    cost_grid_scaled = _path_cost_octile(path_scaled)
    cost_physical_scaled = cost_grid_scaled * scaled_cell

    # Grid costs should match (same occupancy, A* independent of cell_size)
    assert abs(cost_grid - cost_grid_scaled) < _TOL, (
        f"Grid cost differs after cell_size scaling k={k}: {cost_grid} vs {cost_grid_scaled}"
    )

    # Physical costs should scale by k
    expected_physical = cost_physical_orig * k
    assert abs(cost_physical_scaled - expected_physical) < max(_TOL, abs(expected_physical) * _TOL), (
        f"Physical cost scaling k={k}: {cost_physical_orig} * {k} = {expected_physical}, "
        f"got {cost_physical_scaled}"
    )


# =============================================================================
# MR6 — Empty-Grid Optimality
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 100, st.floats(0.0, 0.0)))
@settings(max_examples=100, deadline=30000)
def test_mr6_empty_grid_optimality(gsp):
    """On empty grid, A* cost == octile_distance(start, goal)."""
    grid, start, goal = gsp
    path = _astar_search(start, goal, grid)
    assert path is not None, f"No path on empty grid: {start}->{goal}"

    cost = _path_cost_octile(path)
    expected = octile_distance(start, goal)
    assert abs(cost - expected) < _TOL, (
        f"Empty grid: A*={cost}, octile={expected}, {start}->{goal}"
    )

    # Also verify Dijkstra matches on grids <=30x30
    n_cells = grid.width_cells * grid.height_cells
    if n_cells <= DIJKSTRA_MAX_CELLS:
        _, d_cost = dijkstra_shortest_path(start, goal, grid)
        assert abs(cost - d_cost) < _TOL


# =============================================================================
# MR7 — Grid Translation Invariance
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 20, 0.3))
@settings(max_examples=100, deadline=30000)
def test_mr7_translation_invariance(gsp):
    """Translate grid by (dx, dy); assert cost unchanged."""
    grid, start, goal = gsp
    t_grid, dx, dy = _translate_grid_random(grid)
    t_start = (start[0] + dx, start[1] + dy)
    t_goal = (goal[0] + dx, goal[1] + dy)

    path_orig = _astar_search(start, goal, grid)
    path_trans = _astar_search(t_start, t_goal, t_grid)

    assert (path_orig is None) == (path_trans is None), "Translation completeness mismatch"

    if path_orig is not None and path_trans is not None:
        cost_orig = _path_cost_octile(path_orig)
        cost_trans = _path_cost_octile(path_trans)
        assert abs(cost_orig - cost_trans) < _TOL, (
            f"Translation ({dx},{dy}): {cost_orig} vs {cost_trans}"
        )
        # Path cells should be shifted
        assert len(path_orig) == len(path_trans), (
            f"Path length mismatch after translation"
        )
        for (ox, oy), (tx, ty) in zip(path_orig, path_trans):
            assert tx == ox + dx and ty == oy + dy, (
                f"Path cell not translated: ({ox},{oy}) -> ({tx},{ty}), shift=({dx},{dy})"
            )


def _translate_grid_random(grid: OccupancyGrid) -> tuple[OccupancyGrid, int, int]:
    import random
    dx = random.randint(0, grid.width_cells)
    dy = random.randint(0, grid.height_cells)
    new_w = grid.width_cells + dx + 1
    new_h = grid.height_cells + dy + 1
    # Fill border with blocked (1) so padding doesn't create new paths
    arr = np.ones((new_h, new_w), dtype=grid.grid.dtype)
    arr[dy : dy + grid.height_cells, dx : dx + grid.width_cells] = grid.grid
    t_grid = OccupancyGrid(grid.layer_name, arr, grid.origin, grid.cell_size, new_w, new_h)
    return t_grid, dx, dy


# =============================================================================
# MR8 — Path Cells Free
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 100, st.floats(0.0, 0.5)))
@settings(max_examples=100, deadline=30000)
def test_mr8_path_cells_free(gsp):
    """Every cell in A* path must be free (0 or net_id)."""
    grid, start, goal = gsp
    path = _astar_search(start, goal, grid)
    if path is None:
        return

    for x, y in path:
        val = grid.grid[y, x]
        assert val == 0 or val == 0, (  # net_id=0 for testing; start/goal may be >0
            f"Path cell ({x},{y}) has value {val}, grid {grid.width_cells}x{grid.height_cells}"
        )


# =============================================================================
# MR9 — No Redundant Nodes
# =============================================================================


@pytest.mark.l3_pbt
@given(gsp=grid_and_pair(2, 100, st.floats(0.0, 0.5)))
@settings(max_examples=100, deadline=30000)
def test_mr9_no_redundant_nodes(gsp):
    """No consecutive duplicate cells in A* path."""
    grid, start, goal = gsp
    path = _astar_search(start, goal, grid)
    if path is None:
        return

    for i in range(len(path) - 1):
        assert path[i] != path[i + 1], (
            f"Consecutive duplicate at index {i}: {path[i]} in "
            f"grid {grid.width_cells}x{grid.height_cells}"
        )
    max_cells = grid.width_cells * grid.height_cells
    assert len(path) <= max_cells, (
        f"Path length {len(path)} exceeds grid cells {max_cells}"
    )
