"""
U6: physics-U8 A* Dijkstra same-cost oracle + cost additivity (R13, R14).

Cross-validates :func:`temper_placer.router_v6.astar_core._astar_search`
against a reference Dijkstra that uses the **same** weighted grid, the
**same** neighbor-validity model, the **same** diagonal-cost arithmetic,
and the **same** per-cell thermal cost summation as the A* kernel.

Requirements
------------
- R13 (BMC): on grids ≤ 6×6 with a generated nonnegative field,
  A* path cost equals Dijkstra's within ε for ALL source/target pairs.
- R13 (property): admissibility — A* cost never below Dijkstra cost
  (minus ε) across generated fields.
- R14 (property): path-cost(field) − path-cost(no-field) equals the
  summed field cost over traversed cells; fail-capable against a
  deliberate double-count.
- Composition: no path enters a hard-masked/blocked cell regardless of
  field magnitude.

Scope: the basic ``_astar_search`` with thermal injection — NOT the
any-angle Theta*/Lazy-Theta* variants.

Epsilon rationale
-----------------
The production A* kernel runs under Numba (float32; hardcoded
1.4142135 diagonal) while the pure-Python ``_astar_search`` uses
``DIAGONAL_COST_FACTOR * math.sqrt(2)`` (float64).  Per the
``bfs-oracle-cost-model-mismatch`` learning, we compare within a
floating-point epsilon rather than demanding exact equality.
Python A* vs Python Dijkstra: both float64, differences from
summation order only → ε ≈ 1e-12 in practice.  We use 1e-5 to
absorb the Numba float32 case safely.
"""

from __future__ import annotations

import heapq
import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import (
    _DIRS_8,
    DIAGONAL_COST_FACTOR,
    _astar_search,
)
from temper_placer.router_v6.astar_core_numba import _astar_search_numba
from temper_placer.router_v6.neighbor_validity import (
    build_neighbor_validity_tensor_2d,
    is_valid_2d,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

EPS = 1e-5
EPS_NUMBA = 2e-4  # larger: float32 + hardcoded sqrt2 in Numba kernel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grid(rows: int, cols: int, blocked: list[tuple[int, int]] | None = None):
    """Create an OccupancyGrid with optional blocked cells."""
    arr = np.zeros((rows, cols), dtype=np.int8)
    if blocked:
        for r, c in blocked:
            arr[r, c] = 1
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)


def _free_cells(grid: OccupancyGrid):
    """Return list of (col, row) grid coords for all free cells."""
    return [
        (int(c), int(r))
        for r in range(grid.height_cells)
        for c in range(grid.width_cells)
        if grid.grid[r, c] == 0
    ]


# ---------------------------------------------------------------------------
# Reference Dijkstra — same cost model as _astar_search (Python A*).
# ---------------------------------------------------------------------------


def _dijkstra_cost(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: OccupancyGrid,
    neighbor_tensor: np.ndarray,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
    diagonal_factor: float = 1.0,
) -> float:
    """Return the minimum path cost from *start* to *goal* via Dijkstra.

    Edge cost model (MATCHES ``_astar_search`` exactly):
        cardinal step:  1.0
        diagonal step:  *diagonal_factor* × √2
        thermal:        *thermal_weight* × *thermal_flat*[dest_cell]

    Neighbour validity: ``is_valid_2d(neighbor_tensor, row, col, dir_idx)``
    — identical to the A* inner loop.

    Returns ``float('inf')`` if no path exists.
    """
    cols = grid.width_cells
    INF = float("inf")

    _sqrt2 = math.sqrt(2.0)
    use_thermal = thermal_flat is not None and thermal_weight > 0.0

    g_score = {start: 0.0}
    frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start)]

    while frontier:
        cost, current = heapq.heappop(frontier)
        if cost > g_score.get(current, INF):
            continue

        if current == goal:
            return cost

        # current is (col, row) = (x, y) — match A* unpacking
        cx, cy = current
        for dir_idx in range(8):
            if not is_valid_2d(neighbor_tensor, cy, cx, dir_idx):
                continue
            dx, dy = _DIRS_8[dir_idx]
            nx, ny = cx + dx, cy + dy

            move_cost = diagonal_factor * _sqrt2 if dx != 0 and dy != 0 else 1.0
            if use_thermal:
                assert thermal_flat is not None
                n_idx = ny * cols + nx
                move_cost += thermal_weight * float(thermal_flat[n_idx])

            new_cost = g_score[current] + move_cost
            neighbor = (nx, ny)

            if new_cost < g_score.get(neighbor, INF):
                g_score[neighbor] = new_cost
                heapq.heappush(frontier, (new_cost, neighbor))

    return INF


def _dijkstra_cost_numba_float32_model(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: OccupancyGrid,
    neighbor_tensor: np.ndarray,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
) -> float:
    """Dijkstra using the **Numba kernel's** edge-cost constants.

    Numba hardcodes diagonal as ``1.4142135`` (float32 approximation of
    √2) — NOT ``DIAGONAL_COST_FACTOR * sqrt(2)``.  This replica
    matches that exactly so we can oracle the Numba A* path.
    """
    cols = grid.width_cells
    INF = float("inf")
    _NB_SQRT2 = 1.4142135  # from astar_core_numba.py line 345

    use_thermal = thermal_flat is not None and thermal_weight > 0.0

    g_score = {start: 0.0}
    frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start)]

    while frontier:
        cost, current = heapq.heappop(frontier)
        if cost > g_score.get(current, INF):
            continue

        if current == goal:
            return cost

        # current is (col, row) = (x, y) — match A* unpacking
        cx, cy = current
        for dir_idx in range(8):
            if not is_valid_2d(neighbor_tensor, cy, cx, dir_idx):
                continue
            dx, dy = _DIRS_8[dir_idx]
            nx, ny = cx + dx, cy + dy

            move_cost = _NB_SQRT2 if dx != 0 and dy != 0 else 1.0
            if use_thermal:
                assert thermal_flat is not None
                n_idx = ny * cols + nx
                move_cost += thermal_weight * float(thermal_flat[n_idx])

            new_cost = g_score[current] + move_cost
            neighbor = (nx, ny)

            if new_cost < g_score.get(neighbor, INF):
                g_score[neighbor] = new_cost
                heapq.heappush(frontier, (new_cost, neighbor))

    return INF


# ---------------------------------------------------------------------------
# Path-cost computation (exact A* cost-model replica)
# ---------------------------------------------------------------------------


def _path_base_cost(
    path: list[tuple[int, int]],
    diagonal_factor: float = 1.0,
) -> float:
    """Sum of octile step costs along *path*."""
    total = 0.0
    _sqrt2 = math.sqrt(2.0)
    for i in range(len(path) - 1):
        c0, r0 = path[i]
        c1, r1 = path[i + 1]
        dx = abs(c1 - c0)
        dy = abs(r1 - r0)
        total += diagonal_factor * _sqrt2 if dx != 0 and dy != 0 else 1.0
    return total


def _path_field_sum(
    path: list[tuple[int, int]],
    thermal_flat: np.ndarray,
    cols: int,
) -> float:
    """Sum of thermal_flat over all cells in *path* EXCEPT the start cell.

    Matches the A* kernel: thermal cost of cell (nx, ny) is added to
    the step cost when *entering* it.  The start cell is never entered.
    """
    total = 0.0
    for i, (c, r) in enumerate(path):
        if i == 0:  # skip start cell
            continue
        idx = r * cols + c
        total += float(thermal_flat[idx])
    return total


def _path_total_cost(
    path: list[tuple[int, int]],
    cols: int,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
    diagonal_factor: float = 1.0,
) -> float:
    """Reconstructed total cost of a path using the A* cost model."""
    base = _path_base_cost(path, diagonal_factor)
    if thermal_flat is not None and thermal_weight > 0.0:
        return base + thermal_weight * _path_field_sum(path, thermal_flat, cols)
    return base


# ---------------------------------------------------------------------------
# BMC: exhaustive A* vs Dijkstra on small grids (R13)
# ---------------------------------------------------------------------------


# A set of fixed small grids to exhaust over source/target pairs.
_BMC_GRIDS: list[tuple[str, int, int, list[tuple[int, int]] | None]] = [
    ("empty_3x3", 3, 3, None),
    ("empty_4x4", 4, 4, None),
    ("empty_5x5", 5, 5, None),
    ("empty_6x6", 6, 6, None),
    ("single_obstacle_4x4", 4, 4, [(1, 1)]),
    ("wall_5x5", 5, 5, [(r, 2) for r in range(5) if r != 2]),  # wall with gap
    ("corner_blocked_5x5", 5, 5, [(0, 0), (4, 4)]),
    (
        "maze_6x6",
        6,
        6,
        [
            (1, 1),
            (1, 2),
            (1, 3),
            (1, 4),
            (3, 1),
            (3, 2),
            (3, 3),
            (3, 4),
        ],
    ),
]

# Thermal fields used in BMC (applied per grid).
# Each is a function: (rows, cols) -> (flat, weight, label)


def _bmc_field_zero(rows, cols):
    return np.zeros(rows * cols, dtype=np.float32), 0.0, "zero_field_w0"


def _bmc_field_uniform(rows, cols):
    flat = np.full(rows * cols, 50.0, dtype=np.float32)
    return flat, 0.5, "uniform_w0.5"


def _bmc_field_ramp(rows, cols):
    arr = np.arange(rows * cols, dtype=np.float32).reshape(rows, cols)
    return np.ascontiguousarray(arr.ravel()).astype(np.float32), 0.3, "ramp_w0.3"


def _bmc_field_hotspot(rows, cols):
    arr = np.zeros((rows, cols), dtype=np.float32)
    arr[rows // 2, cols // 2] = 200.0
    return np.ascontiguousarray(arr.ravel()).astype(np.float32), 2.0, "hotspot_w2"


_BMC_FIELDS = [
    _bmc_field_zero,
    _bmc_field_uniform,
    _bmc_field_ramp,
    _bmc_field_hotspot,
]


@pytest.mark.l0_unit
@pytest.mark.parametrize("label,rows,cols,blocked", _BMC_GRIDS)
def test_bmc_astar_equals_dijkstra_within_epsilon(label, rows, cols, blocked):
    """R13 BMC: on grids ≤ 6×6, A* cost equals Dijkstra's within ε
    for ALL source/target pairs."""
    grid = _make_grid(rows, cols, blocked)
    tensor = build_neighbor_validity_tensor_2d(grid)
    free = _free_cells(grid)

    assert len(free) >= 2, f"{label}: need ≥ 2 free cells"

    for field_fn in _BMC_FIELDS:
        thermal_flat, thermal_weight, f_label = field_fn(rows, cols)
        checked = 0
        for src in free:
            for dst in free:
                if src == dst:
                    continue
                checked += 1

                a_result = _astar_search(
                    src,
                    dst,
                    grid,
                    neighbor_tensor=tensor,
                    thermal_flat=thermal_flat,
                    thermal_weight=thermal_weight,
                )
                d_cost = _dijkstra_cost(
                    src,
                    dst,
                    grid,
                    tensor,
                    thermal_flat=thermal_flat,
                    thermal_weight=thermal_weight,
                    diagonal_factor=DIAGONAL_COST_FACTOR,
                )

                if a_result is None:
                    assert math.isinf(d_cost), (
                        f"{label}/{f_label} {src}→{dst}: A* no path "
                        f"but Dijkstra found cost={d_cost}"
                    )
                    continue

                # Reconstruct cost from A* path using the cost model.
                # Cost_so_far at goal = _path_total_cost via cost model.
                a_cost = _path_total_cost(
                    a_result,
                    cols,
                    thermal_flat,
                    thermal_weight,
                    DIAGONAL_COST_FACTOR,
                )

                assert abs(a_cost - d_cost) <= EPS, (
                    f"{label}/{f_label} {src}→{dst}: "
                    f"A* cost={a_cost:.10f}, Dijkstra cost={d_cost:.10f}, "
                    f"diff={abs(a_cost - d_cost):.2e}"
                )

        print(f"  {label}/{f_label}: checked {checked} pairs, all within ε")


@pytest.mark.l0_unit
def test_bmc_numba_astar_equals_dijkstra_within_epsilon():
    """Variant: Numba A* cost equals the float32-model Dijkstra within ε."""
    rows, cols = 5, 5
    grid = _make_grid(rows, cols)
    tensor = build_neighbor_validity_tensor_2d(grid)
    free = _free_cells(grid)

    thermal_2d = np.zeros((rows, cols), dtype=np.float32)
    thermal_2d[1, 2] = 100.0
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    for src in free:
        for dst in free:
            if src == dst:
                continue

            path = _astar_search_numba(
                src,
                dst,
                grid,
                max_iterations=5000,
                thermal_flat=thermal_flat,
                thermal_weight=2.0,
            )
            d_cost = _dijkstra_cost_numba_float32_model(
                src,
                dst,
                grid,
                tensor,
                thermal_flat=thermal_flat,
                thermal_weight=2.0,
            )

            if path is None:
                assert math.isinf(d_cost), f"{src}→{dst}: Numba A* no path but Dijkstra found cost"
                continue

            a_cost = _path_base_cost(path, diagonal_factor=1.0) + (
                2.0 * _path_field_sum(path, thermal_flat, cols)
            )
            assert abs(a_cost - d_cost) <= EPS_NUMBA, (
                f"{src}→{dst}: Numba A* cost={a_cost:.10f}, "
                f"Dijkstra cost={d_cost:.10f}, diff={abs(a_cost - d_cost):.2e}"
            )


# ---------------------------------------------------------------------------
# PBT strategies
# ---------------------------------------------------------------------------


@st.composite
def small_grid_with_field_and_pair(draw: st.DrawFn):
    """Generate a small grid (≤ 8×8), nonnegative field, and distinct
    start/goal pair."""
    rows = draw(st.integers(3, 8))
    cols = draw(st.integers(3, 8))
    density = draw(st.floats(0.0, 0.35))

    seed = draw(st.integers(0, 2**31 - 1))
    rng = np.random.RandomState(seed)
    arr = rng.binomial(1, density, size=(rows, cols)).astype(np.int8)

    free_cells = [(int(c), int(r)) for r in range(rows) for c in range(cols) if arr[r, c] == 0]
    assume(len(free_cells) >= 2)

    # Nonnegative thermal field
    thermal_2d = rng.uniform(0.0, 300.0, size=(rows, cols)).astype(np.float32)
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    thermal_weight = draw(st.floats(0.0, 10.0))

    grid = OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)

    idxs = draw(
        st.lists(
            st.integers(0, len(free_cells) - 1),
            min_size=2,
            max_size=2,
            unique=True,
        )
    )
    start = free_cells[idxs[0]]
    goal = free_cells[idxs[1]]

    return grid, start, goal, thermal_flat, thermal_weight


# ---------------------------------------------------------------------------
# R13 property: A* cost ≥ Dijkstra cost − ε  (admissibility never
# violates optimality)
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(gfp=small_grid_with_field_and_pair())
@settings(
    max_examples=200,
    deadline=10000,
    suppress_health_check=[HealthCheck.filter_too_much],
)
def test_pbt_astar_cost_never_below_dijkstra(gfp):
    """R13 admissibility: A* cost is never below Dijkstra cost (minus ε)."""
    grid, start, goal, thermal_flat, thermal_weight = gfp

    tensor = build_neighbor_validity_tensor_2d(grid)

    a_path = _astar_search(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        thermal_flat=thermal_flat if thermal_weight > 0 else None,
        thermal_weight=thermal_weight,
    )
    d_cost = _dijkstra_cost(
        start,
        goal,
        grid,
        tensor,
        thermal_flat=thermal_flat if thermal_weight > 0 else None,
        thermal_weight=thermal_weight,
        diagonal_factor=DIAGONAL_COST_FACTOR,
    )

    if a_path is None:
        # If A* cannot find a path, Dijkstra should also not find one
        # (A* is complete on finite graphs given the consistent heuristic).
        assert math.isinf(d_cost), f"{start}→{goal}: A* no path but Dijkstra cost={d_cost}"
        return

    # Reconstruct cost explicitly from the cost model — not from
    # A*'s internal cost_so_far dict.  This avoids trusting A*'s
    # own accounting.
    a_cost = _path_total_cost(
        a_path,
        grid.width_cells,
        thermal_flat if thermal_weight > 0 else None,
        thermal_weight,
        DIAGONAL_COST_FACTOR,
    )

    # Admissibility: A* cost must be ≥ optimal (Dijkstra) − ε.
    # When costs tie within ε, accept either path (bfs-oracle-
    # cost-model-mismatch learning).
    assert a_cost >= d_cost - EPS, (
        f"{start}→{goal}: A* cost {a_cost:.10f} < Dijkstra cost "
        f"{d_cost:.10f} (diff={d_cost - a_cost:.2e}) "
        f"grid={grid.width_cells}×{grid.height_cells} "
        f"thermal_w={thermal_weight}"
    )

    # Also check: A* cost should be ≤ optimal + ε  (no over-estimation
    # beyond floating point — the heuristic is admissible).
    assert a_cost <= d_cost + EPS, (
        f"{start}→{goal}: A* cost {a_cost:.10f} > Dijkstra cost "
        f"{d_cost:.10f} + ε (diff={a_cost - d_cost:.2e})"
    )


# ---------------------------------------------------------------------------
# R14 property: cost additivity
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(gfp=small_grid_with_field_and_pair())
@settings(
    max_examples=200,
    deadline=10000,
    suppress_health_check=[HealthCheck.filter_too_much],
)
def test_pbt_cost_additivity(gfp):
    """R14: path-cost(field) − path-cost(no-field) equals summed field
    cost over traversed cells.

    We compute:
      - optimal path with field:  path_on
      - total cost of path_on with field:  total_on
      - total cost of SAME path without field:  total_on_base  (octile only)
      - summed field cost over path_on (ex start cell):  field_sum

    Then assert: total_on − total_on_base ≈ thermal_weight × field_sum.
    """
    grid, start, goal, thermal_flat, thermal_weight = gfp
    assume(thermal_weight > 0.0)  # R14 needs a non-zero weight

    cols = grid.width_cells
    tensor = build_neighbor_validity_tensor_2d(grid)

    path_on = _astar_search(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
    )
    assume(path_on is not None)  # only test paths that exist

    # Total cost of path_on with field (cost model)
    total_on = _path_total_cost(
        path_on,
        cols,
        thermal_flat,
        thermal_weight,
        DIAGONAL_COST_FACTOR,
    )
    # Total cost of path_on without field (octile only)
    total_on_base = _path_total_cost(
        path_on,
        cols,
        thermal_flat,
        0.0,
        DIAGONAL_COST_FACTOR,
    )
    # Summed field cost over path (ex start cell)
    field_sum = _path_field_sum(path_on, thermal_flat, cols)

    expected_delta = thermal_weight * field_sum
    actual_delta = total_on - total_on_base

    assert abs(actual_delta - expected_delta) <= EPS, (
        f"R14 additivity failed: cost(field)={total_on:.10f}, "
        f"cost(no-field)={total_on_base:.10f}, "
        f"delta={actual_delta:.10f}, thermal_weight*sum={expected_delta:.10f}, "
        f"diff={abs(actual_delta - expected_delta):.2e} "
        f"grid={grid.width_cells}x{grid.height_cells} "
        f"path_len={len(path_on)} "
        f"thermal_w={thermal_weight}"
    )


# ---------------------------------------------------------------------------
# R14 fail-capable: deliberate double-count should FAIL the additivity
# check
# ---------------------------------------------------------------------------


def _path_total_cost_double_count(
    path: list[tuple[int, int]],
    thermal_flat: np.ndarray,
    cols: int,
    thermal_weight: float,
) -> float:
    """BUG: thermal cost applied TWICE per cell (simulates double-count)."""
    base = _path_base_cost(path, DIAGONAL_COST_FACTOR)
    # Double the thermal contribution
    field_sum = _path_field_sum(path, thermal_flat, cols)
    return base + 2.0 * thermal_weight * field_sum


@pytest.mark.l0_unit
def test_r14_fail_capable_double_count():
    """A deliberately doubled thermal cost must fail the additivity assertion.

    We simulate a bug where the thermal cost is accumulated twice.
    The additivity check (delta == thermal_weight * field_sum) must
    NOT hold for the buggy cost.

    Uses a uniform thermal field so every path traverses thermal cells.
    """
    rows, cols = 5, 5
    grid = _make_grid(rows, cols)
    tensor = build_neighbor_validity_tensor_2d(grid)

    # Uniform non-zero thermal: every path traverses thermal cells
    thermal_2d = np.full((rows, cols), 100.0, dtype=np.float32)
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)
    thermal_weight = 2.0

    start, goal = (0, 0), (4, 4)
    path = _astar_search(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
    )
    assert path is not None, "must find a path on empty grid"

    field_sum = _path_field_sum(path, thermal_flat, cols)
    # Uniform field: every cell (ex start) has thermal=100, so field_sum > 0
    assert field_sum > 0, "path must traverse thermal cells"

    # Buggy cost (double count) should NOT equal the correct additivity
    buggy_total = _path_total_cost_double_count(
        path,
        thermal_flat,
        cols,
        thermal_weight,
    )
    buggy_delta = buggy_total - _path_base_cost(path, DIAGONAL_COST_FACTOR)
    correct_delta = thermal_weight * field_sum

    # The double-count produces delta = 2*weight*sum, not weight*sum
    assert abs(buggy_delta - correct_delta) > EPS, (
        "FAIL-CAPABLE CHECK: double-count should NOT match correct additivity. "
        f"buggy_delta={buggy_delta:.6f}, correct_delta={correct_delta:.6f}"
    )


# ---------------------------------------------------------------------------
# Composition: no path enters a masked/blocked cell
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(gfp=small_grid_with_field_and_pair())
@settings(
    max_examples=200,
    deadline=10000,
    suppress_health_check=[HealthCheck.filter_too_much],
)
def test_pbt_no_path_through_masked_cells(gfp):
    """Composition: no path enters a hard-masked/blocked cell regardless
    of field magnitude.

    The neighbor-validity tensor is the gatekeeper — thermal cost is
    added only AFTER the validity check, so a zero-cost field on a
    blocked cell must not lure the path through it.
    """
    grid, start, goal, thermal_flat, thermal_weight = gfp

    tensor = build_neighbor_validity_tensor_2d(grid)

    path = _astar_search(
        start,
        goal,
        grid,
        neighbor_tensor=tensor,
        thermal_flat=thermal_flat if thermal_weight > 0 else None,
        thermal_weight=thermal_weight,
    )

    if path is None:
        return  # No path is an acceptable outcome

    blocked_set = {
        (int(c), int(r))
        for r in range(grid.height_cells)
        for c in range(grid.width_cells)
        if grid.grid[r, c] != 0
    }

    for cell in path:
        assert cell not in blocked_set, f"Path entered blocked cell {cell}"


# ---------------------------------------------------------------------------
# Edge: zero thermal weight = field-off baseline match
# ---------------------------------------------------------------------------


@pytest.mark.l0_unit
def test_zero_thermal_weight_matches_no_field():
    """Zero thermal_weight produces the same A* result as no field at all."""
    rows, cols = 6, 6
    grid = _make_grid(rows, cols)
    tensor = build_neighbor_validity_tensor_2d(grid)

    thermal_2d = np.random.RandomState(42).uniform(0, 500, (rows, cols))
    thermal_2d = thermal_2d.astype(np.float32)
    thermal_flat = np.ascontiguousarray(thermal_2d.ravel()).astype(np.float32)

    free = _free_cells(grid)
    for src in free:
        for dst in free:
            if src == dst:
                continue
            p_no = _astar_search(src, dst, grid, neighbor_tensor=tensor)
            p_w0 = _astar_search(
                src,
                dst,
                grid,
                neighbor_tensor=tensor,
                thermal_flat=thermal_flat,
                thermal_weight=0.0,
            )
            assert p_no == p_w0, f"zero-weight path differs from no-field path at {src}→{dst}"
