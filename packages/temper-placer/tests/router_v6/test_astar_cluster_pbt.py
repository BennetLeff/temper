"""Property-based and metamorphic tests for the A*/Theta* cluster
(Wave 4) — the Rust-backed Theta* / Lazy Theta* search kernels in
``temper-rust-router-core`` (``theta_star.rs``), driven through the
``router_v6/_astar_theta_star`` shims.

Verification unit (contract G4, cluster reading): the migrated module
``_astar_theta_star.py`` (both search variants + the Bresenham LOS they
share).  Module-to-property map:

- Standard Theta* (``_astar_search_theta_star`` → ``theta_star_search_py``
  ``lazy=False``): P1 (endpoints), P2 (cells traversable), P3 (no
  redundant nodes), P4 (shortcut LOS validity — this is the property that
  reaches the Rust LOS kernel), P5 (Dijkstra completeness parity).
- Lazy Theta* (``_astar_search_lazy_theta_star`` → ``lazy=True``):
  P6 (reachability parity with standard), P7 (cells traversable),
  P8 (no redundant nodes).
- Both variants: P9 (max_iter=1 cap determinism).
- LOS (Bresenham, shared by both variants): reached inside the search by
  P4 (every standard-Theta* path edge is LOS-validated at push time).

Every property has a ``test_pN_fails_for_<mutant>`` vacuity guard: a
degenerate kernel is installed in place of the production shim and the
property is re-run via ``hypothesis.inner_test`` on a FIXED crafted input,
asserting ``AssertionError`` — a property a degenerate kernel cannot
violate is vacuous and must not ship.

All properties are implementation-agnostic invariants (they hold for the
pure-Python reference and the Rust kernel alike), so the suite is green
whether or not the extension is currently importable.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_placer.router_v6._astar_theta_star as ats
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from tests.router_v6.astar_oracle_utils import (
    DIJKSTRA_MAX_CELLS,
    dijkstra_shortest_path,
)
from tests.router_v6.astar_property_strategies import (
    grid_and_pair,
    grids,
    obstacle_perturbations,
    start_goal_pairs,
    unroutable_wall_grids,
)

# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def _line_of_sight(p1, p2, grid):
    """Production LOS (routes through the Rust LOS when available)."""
    return ats._line_of_sight_dispatch(p1, p2, grid, 0)


# P1 — standard Theta* endpoint + in-bounds correctness.  (Deliberately NOT
# an 8-connectivity claim: Theta* emits any-angle shortcuts, so consecutive
# path cells may be several cells apart — P4 is the property that pins the
# validity of those steps.)
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p1_theta_star_endpoints(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    if path is None:
        return
    assert path[0] == start, f"Theta* path must start at {start}: {path[0]}"
    assert path[-1] == goal, f"Theta* path must end at {goal}: {path[-1]}"
    for x, y in path:
        assert 0 <= x < grid.width_cells and 0 <= y < grid.height_cells, (
            f"Theta* path cell ({x},{y}) out of bounds on "
            f"{grid.width_cells}x{grid.height_cells}"
        )


# P2 — standard Theta* path cells are free (net_id=0 grids carry only 0/1).
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p2_theta_star_cells_free(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    if path is None:
        return
    for x, y in path:
        assert grid.grid[y, x] == 0, f"Theta* path cell ({x},{y}) blocked"


# P3 — standard Theta* has no consecutive duplicate cells and stays inside
# the grid.
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p3_theta_star_no_redundant_nodes(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    if path is None:
        return
    for i in range(len(path) - 1):
        assert path[i] != path[i + 1], "Theta* consecutive duplicate"
    assert len(path) <= grid.width_cells * grid.height_cells


# P4 — every edge of a standard-Theta* path has line-of-sight.  In standard
# Theta* every ``came_from`` assignment was LOS-validated at push time (the
# shortcut path only fires when ``los(parent, neighbor)`` holds), so every
# consecutive step — adjacent or a multi-cell shortcut — is LOS-clear.  This
# is the property that exercises the Rust LOS kernel inside the search.
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p4_theta_star_edges_have_los(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    if path is None or len(path) < 2:
        return
    for i in range(len(path) - 1):
        assert _line_of_sight(path[i], path[i + 1], grid), (
            f"Theta* shortcut without LOS: {path[i]} -> {path[i + 1]}"
        )


# P5 — standard Theta* (congestion-derivative OFF, so the search is
# complete) finds a path iff the independent Dijkstra oracle says the grid
# is reachable.
@given(gsp=grid_and_pair(2, 30, st.floats(0.0, 0.4)))
@settings(max_examples=100, deadline=30000)
def test_p5_theta_star_dijkstra_completeness(gsp):
    grid, start, goal = gsp
    if grid.width_cells * grid.height_cells > DIJKSTRA_MAX_CELLS:
        return
    path = ats._astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False
    )
    d_path, _ = dijkstra_shortest_path(start, goal, grid)
    assert (path is None) == (d_path is None), (
        f"Theta* completeness vs Dijkstra disagree on {grid.width_cells}x"
        f"{grid.height_cells} {start}->{goal}"
    )


# P6 — Lazy Theta* reachability parity with standard Theta* (both complete
# with the derivative off).
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p6_lazy_theta_star_reachability_parity(gsp):
    grid, start, goal = gsp
    theta = ats._astar_search_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False
    )
    lazy = ats._astar_search_lazy_theta_star(
        grid, start, goal, net_id=0, enable_congestion_derivative=False
    )
    assert (theta is None) == (lazy is None), (
        f"Lazy/standard Theta* reachability disagree on {start}->{goal}"
    )


# P7 — Lazy Theta* path cells are free.
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p7_lazy_theta_star_cells_free(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_lazy_theta_star(grid, start, goal, net_id=0)
    if path is None:
        return
    for x, y in path:
        assert grid.grid[y, x] == 0, f"Lazy Theta* path cell ({x},{y}) blocked"


# P8 — Lazy Theta* has no consecutive duplicate cells and stays inside the
# grid.
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p8_lazy_theta_star_no_redundant_nodes(gsp):
    grid, start, goal = gsp
    path = ats._astar_search_lazy_theta_star(grid, start, goal, net_id=0)
    if path is None:
        return
    for i in range(len(path) - 1):
        assert path[i] != path[i + 1], "Lazy Theta* consecutive duplicate"
    assert len(path) <= grid.width_cells * grid.height_cells


# P9 — a one-iteration budget is deterministic for both variants: with
# start != goal the first pop cannot be the goal, so the closed-count cap
# fires and both variants return None.  (The single-cell start==goal case
# returns the path before the cap check.)  This pins the interaction
# between the goal check and the max_iter check.
@given(gsp=grid_and_pair(2, 30, 0.3))
@settings(max_examples=100, deadline=30000)
def test_p9_max_iter_one_returns_none(gsp):
    grid, start, goal = gsp
    if start == goal:
        return
    assert ats._astar_search_theta_star(grid, start, goal, net_id=0, max_iter=1) is None
    assert ats._astar_search_lazy_theta_star(grid, start, goal, net_id=0, max_iter=1) is None


# ---------------------------------------------------------------------------
# Vacuity guards — every property above must be violated by a degenerate
# kernel.  Each guard installs a mutant in place of the production shim and
# re-runs the property on a FIXED crafted input via hypothesis.inner_test.
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    orig_theta = ats._astar_search_theta_star
    orig_lazy = ats._astar_search_lazy_theta_star
    yield
    ats._astar_search_theta_star = orig_theta
    ats._astar_search_lazy_theta_star = orig_lazy


def _open_grid(rows: int = 5, cols: int = 5) -> OccupancyGrid:
    return OccupancyGrid("Test", np.zeros((rows, cols), dtype=np.int8), (0.0, 0.0), 1.0, cols, rows)


def _grid_with_blocked(rows: int = 5, cols: int = 5, blocked=(2, 2)) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    arr[blocked[1], blocked[0]] = 1
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)


def _wall_grid() -> OccupancyGrid:
    arr = np.zeros((5, 9), dtype=np.int8)
    arr[:, 4] = 1  # full-height wall
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, 9, 5)


def test_p1_fails_for_single_cell_mutant(_restore_kernels) -> None:
    """A kernel that returns only [goal] violates the endpoint property."""
    ats._astar_search_theta_star = lambda grid, start, goal, **_k: [goal]
    with pytest.raises(AssertionError):
        test_p1_theta_star_endpoints.hypothesis.inner_test((_open_grid(), (0, 0), (4, 4)))
    # sanity: the mutant really is what ran (not a masked pass)
    assert ats._astar_search_theta_star(_open_grid(), (0, 0), (4, 4), net_id=0) == [(4, 4)]


def test_p2_fails_for_blocked_cell_mutant(_restore_kernels) -> None:
    """A kernel that routes through a blocked cell violates cell-freedom."""
    grid = _grid_with_blocked(5, 5, (2, 2))

    def blocked_mutant(_grid, start, goal, **_k):
        return [start, (2, 2), goal]

    ats._astar_search_theta_star = blocked_mutant
    with pytest.raises(AssertionError):
        test_p2_theta_star_cells_free.hypothesis.inner_test((grid, (0, 0), (4, 4)))


def test_p3_fails_for_duplicate_cell_mutant(_restore_kernels) -> None:
    """A kernel returning a consecutive duplicate violates P3."""
    ats._astar_search_theta_star = lambda grid, start, goal, **_k: [start, start, goal]
    with pytest.raises(AssertionError):
        test_p3_theta_star_no_redundant_nodes.hypothesis.inner_test((_open_grid(), (0, 0), (4, 4)))


def test_p4_fails_for_blocked_shortcut_mutant(_restore_kernels) -> None:
    """A kernel emitting a shortcut straight across a blocked cell violates
    the LOS property (the direct edge has a blocked cell on its line)."""
    grid = _grid_with_blocked(5, 5, (2, 2))

    def shortcut_mutant(_grid, start, goal, **_k):
        return [start, goal]

    ats._astar_search_theta_star = shortcut_mutant
    with pytest.raises(AssertionError):
        test_p4_theta_star_edges_have_los.hypothesis.inner_test((grid, (0, 0), (4, 4)))
    # sanity: the crafted grid genuinely blocks the direct line
    assert not _line_of_sight((0, 0), (4, 4), grid)


def test_p5_fails_for_always_none_mutant(_restore_kernels) -> None:
    """A kernel that never finds a path violates Dijkstra completeness on a
    reachable grid."""
    ats._astar_search_theta_star = lambda *a, **_k: None
    with pytest.raises(AssertionError):
        test_p5_theta_star_dijkstra_completeness.hypothesis.inner_test(
            (_open_grid(), (0, 0), (4, 4))
        )


def test_p6_fails_for_lazy_always_none_mutant(_restore_kernels) -> None:
    """A lazy kernel that never finds a path violates reachability parity
    when standard Theta* does."""
    ats._astar_search_lazy_theta_star = lambda *a, **_k: None
    with pytest.raises(AssertionError):
        test_p6_lazy_theta_star_reachability_parity.hypothesis.inner_test(
            (_open_grid(), (0, 0), (4, 4))
        )


def test_p7_fails_for_blocked_cell_mutant(_restore_kernels) -> None:
    """A lazy kernel that routes through a blocked cell violates P7."""
    grid = _grid_with_blocked(5, 5, (2, 2))

    def blocked_mutant(_grid, start, goal, **_k):
        return [start, (2, 2), goal]

    ats._astar_search_lazy_theta_star = blocked_mutant
    with pytest.raises(AssertionError):
        test_p7_lazy_theta_star_cells_free.hypothesis.inner_test((grid, (0, 0), (4, 4)))


def test_p8_fails_for_duplicate_cell_mutant(_restore_kernels) -> None:
    """A lazy kernel returning a consecutive duplicate violates P8."""
    ats._astar_search_lazy_theta_star = lambda grid, start, goal, **_k: [start, start, goal]
    with pytest.raises(AssertionError):
        test_p8_lazy_theta_star_no_redundant_nodes.hypothesis.inner_test((_open_grid(), (0, 0), (4, 4)))


def test_p9_fails_for_ignore_cap_mutant(_restore_kernels) -> None:
    """A kernel that ignores the max_iter=1 cap and returns a path violates
    the cap-determinism property."""
    ats._astar_search_theta_star = lambda grid, start, goal, **_k: [start, goal]
    with pytest.raises(AssertionError):
        test_p9_max_iter_one_returns_none.hypothesis.inner_test((_open_grid(), (0, 0), (4, 4)))


# ---------------------------------------------------------------------------
# Metamorphic relations (contract G5, >=3 per module; sectioned here).
# Exactness claims are stated per relation.
# ---------------------------------------------------------------------------

# MR1 — translation invariance (EXACT for integer cell translations with an
# impassable border).
#
# Shifting an occupancy grid (and start/goal) by an integer offset changes
# every coordinate by the same constant.  All search quantities — step cost,
# heuristic, LOS, heap ordering — are integer-coordinate-derived (Euclidean
# from integer deltas, LOS from integer cells), so the shifted search
# returns exactly the shifted path.  The offset grid is padded with a WALL
# (blocked) border: the padded cells are never traversable, so the search
# region is exactly the original grid under translation and every decision
# sequence is preserved.  (A FREE border would change the topology — the
# search could detour through the new free region — which is why the border
# is blocked.)
@given(
    gsp=grid_and_pair(3, 15, 0.2),
    dx=st.integers(1, 3),
    dy=st.integers(1, 3),
)
@settings(max_examples=60, deadline=30000)
def test_mr1_translation_invariance(gsp, dx, dy):
    grid, start, goal = gsp
    base = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    if base is None:
        return

    rows, cols = grid.grid.shape
    big = np.ones((rows + 2 * dy, cols + 2 * dx), dtype=np.int8)
    big[dy : dy + rows, dx : dx + cols] = grid.grid
    shifted = OccupancyGrid("Test", big, (0.0, 0.0), 1.0, cols + 2 * dx, rows + 2 * dy)
    moved = ats._astar_search_theta_star(
        shifted,
        (start[0] + dx, start[1] + dy),
        (goal[0] + dx, goal[1] + dy),
        net_id=0,
    )
    assert moved == [(x + dx, y + dy) for x, y in base]


# MR2 — obstacle perturbation monotonicity (EXACT, derivative off).
#
# Adding an obstacle only removes free cells, so it can never create a path;
# removing one only adds free cells, so it can never destroy a path.  The
# derivative must be OFF so the search is complete (the plateau abort is a
# heuristic and is not monotone under perturbation).


@st.composite
def _grid_pair_and_add_obstacle(draw):
    g = draw(grids(3, 20, st.just(0.25)))
    s, gl = draw(start_goal_pairs(g))
    g_plus = draw(obstacle_perturbations(g, s, gl, mode="add"))
    return g, g_plus, s, gl


@given(pair=_grid_pair_and_add_obstacle())
@settings(max_examples=60, deadline=30000)
def test_mr2_obstacle_monotonicity(pair):
    grid, grid_plus, start, goal = pair
    if (
        ats._astar_search_theta_star(
            grid, start, goal, net_id=0, enable_congestion_derivative=False
        )
        is None
    ):
        # no path in the base grid => no path after adding an obstacle
        assert (
            ats._astar_search_theta_star(
                grid_plus, start, goal, net_id=0, enable_congestion_derivative=False
            )
            is None
        ), "adding an obstacle created a path"


@st.composite
def _grid_pair_and_remove_obstacle(draw):
    g = draw(grids(3, 20, st.just(0.3)))
    s, gl = draw(start_goal_pairs(g))
    g_minus = draw(obstacle_perturbations(g, s, gl, mode="remove"))
    return g, g_minus, s, gl


@given(pair=_grid_pair_and_remove_obstacle())
@settings(max_examples=60, deadline=30000)
def test_mr2b_obstacle_removal_preserves_path(pair):
    grid, grid_minus, start, goal = pair
    if (
        ats._astar_search_theta_star(
            grid, start, goal, net_id=0, enable_congestion_derivative=False
        )
        is not None
    ):
        # a path in the base grid must survive removing an obstacle
        assert (
            ats._astar_search_theta_star(
                grid_minus, start, goal, net_id=0, enable_congestion_derivative=False
            )
            is not None
        ), "removing an obstacle destroyed a path"


# MR3 — start/goal swap reachability symmetry (EXACT).
#
# The grid is undirected, so a path s->g exists iff a path g->s exists.
@given(gsp=grid_and_pair(3, 20, 0.3))
@settings(max_examples=60, deadline=30000)
def test_mr3_start_goal_swap_reachability(gsp):
    grid, start, goal = gsp
    for fn in (
        ats._astar_search_theta_star,
        ats._astar_search_lazy_theta_star,
    ):
        fwd = fn(grid, start, goal, net_id=0, enable_congestion_derivative=False)
        rev = fn(grid, goal, start, net_id=0, enable_congestion_derivative=False)
        assert (fwd is None) == (rev is None), (
            f"start/goal swap reachability asymmetry for {fn.__name__}: {start}<->{goal}"
        )


# MR4 — re-execution determinism (EXACT): the same search twice returns the
# identical path.
@given(gsp=grid_and_pair(3, 20, 0.3))
@settings(max_examples=40, deadline=30000)
def test_mr4_reexecution_determinism(gsp):
    grid, start, goal = gsp
    first = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    second = ats._astar_search_theta_star(grid, start, goal, net_id=0)
    assert first == second
    first_l = ats._astar_search_lazy_theta_star(grid, start, goal, net_id=0)
    second_l = ats._astar_search_lazy_theta_star(grid, start, goal, net_id=0)
    assert first_l == second_l


# ---------------------------------------------------------------------------
# Wall-separated termination (supports P5/P9's "None on unroutable grid"
# direction with a guaranteed-unroutable input family).
# ---------------------------------------------------------------------------


@given(wg=unroutable_wall_grids())
@settings(max_examples=30, deadline=30000)
def test_unroutable_wall_returns_none_both_variants(wg):
    grid, start, goal = wg
    # the strategy yields world-coordinate floats; the searches take grid
    # cells (cell_size=1.0, origin=(0,0), so the cast is exact)
    s = (int(start[0]), int(start[1]))
    g = (int(goal[0]), int(goal[1]))
    assert ats._astar_search_theta_star(grid, s, g, net_id=0) is None
    assert ats._astar_search_lazy_theta_star(grid, s, g, net_id=0) is None
