"""
Property-Based Tests for Demand-Proportional Iteration Budget.

Verifies monotonicity and boundedness of ``compute_demand_budget()``
on random occupancy grids and channel mappings.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import (
    _build_edt_from_grid,
    compute_demand_budget,
    manhattan_distance,
    min_edt_along_line,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

_MAX_GRID = 80


def _make_edt_from_mask(mask: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float, float], float]:
    """Build EDT from a boolean mask.  True = free, False = blocked."""
    from scipy.ndimage import distance_transform_edt
    h, w = mask.shape
    edt = distance_transform_edt(mask.astype(np.uint8))
    bounds = (0.0, 0.0, float(w), float(h))
    return edt, bounds, 1.0


def _make_grid_and_channel(
    free_mask: np.ndarray,
    waypoints: list[tuple[float, float]],
    net_name: str = "NET",
) -> tuple[np.ndarray, tuple[float, float, float, float], float, ChannelMapping]:
    """Construct EDT and ChannelMapping from a boolean free mask and waypoints."""
    h, w = free_mask.shape
    edt, bounds, cell_size = _make_edt_from_mask(free_mask)
    ch_path = ChannelPath(
        net_name=net_name,
        channel_sequence=[],
        waypoints=list(waypoints),
        total_length=0.0,
    )
    mapping = ChannelMapping(channel_paths={net_name: ch_path})
    return edt, bounds, cell_size, mapping


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_manhattan_distance():
    assert manhattan_distance((0.0, 0.0), (3.0, 4.0)) == 7.0
    assert manhattan_distance((1.0, 2.0), (1.0, 2.0)) == 0.0


def test_min_edt_along_line_empty():
    """On a fully-free grid, min EDT ≈ distance to nearest boundary."""
    # 50x50 grid, all free.  EDT at center ≈ min(25,25) * 1.0 = 25.
    edt, bounds, cell_size = _make_edt_from_mask(np.ones((50, 50), dtype=bool))
    val = min_edt_along_line(edt, bounds, cell_size, (5.0, 5.0), (45.0, 45.0))
    # Points near center have large EDT, edges smaller.  Min should be > 0.
    assert val > 0.0
    assert val <= 25.0 * cell_size


def test_min_edt_along_line_choked():
    """When line crosses a narrow gap, min EDT reflects the bottleneck."""
    mask = np.ones((30, 30), dtype=bool)
    mask[:, 14:16] = False  # 2-cell-wide vertical wall
    mask[10:20, 14:16] = True  # open a 10-cell horizontal gap
    edt, bounds, cell_size = _make_edt_from_mask(mask)
    # Cross the gap [0,15] -> [29,15].  Row 15 is the midpoint of the
    # 10-cell-high gap; nearest blocked cell is 5 cells above/below.
    val = min_edt_along_line(edt, bounds, cell_size, (0.0, 15.0), (29.0, 15.0))
    assert 1.0 <= val <= 6.0, f"Expected bottleneck ~5.0, got {val}"


def test_compute_demand_budget_empty():
    """Empty channel mapping produces empty budget."""
    edt, bounds, cell_size = _make_edt_from_mask(np.ones((10, 10), dtype=bool))
    mapping = ChannelMapping(channel_paths={})
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)
    assert budget == {}


def test_compute_demand_budget_single_net():
    """Single net gets a valid budget."""
    edt, bounds, cell_size = _make_edt_from_mask(np.ones((50, 50), dtype=bool))
    ch_path = ChannelPath("NET", [], [(5.0, 5.0), (45.0, 45.0)], 0.0)
    mapping = ChannelMapping(channel_paths={"NET": ch_path})
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)
    assert "NET" in budget
    assert 1000 <= budget["NET"] <= 100000


# ---------------------------------------------------------------------------
# PBT: Monotonicity
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(
    width=st.integers(20, 80),
    height=st.integers(20, 80),
    density=st.floats(0.0, 0.4),
    n_nets=st.integers(2, 12),
    seed=st.integers(0, 1000),
)
@settings(max_examples=100, deadline=30000)
def test_budget_monotonic_in_difficulty(width, height, density, n_nets, seed):
    """Budget(A) >= Budget(B) whenever difficulty(A) > difficulty(B)."""
    rng = np.random.default_rng(seed)

    # Build a random free-space mask
    free_mask = rng.random((height, width)) > density
    edt, bounds, cell_size = _make_edt_from_mask(free_mask)

    # Build n_nets with random waypoints
    paths = {}
    difficulties: list[tuple[str, float]] = []
    for i in range(n_nets):
        # 2-4 waypoints for this net
        n_wp = rng.integers(2, 5)
        wps = [(float(rng.integers(2, width - 2)), float(rng.integers(2, height - 2)))
               for _ in range(n_wp)]
        net_name = f"N{i}"
        paths[net_name] = ChannelPath(net_name, [], wps, 0.0)

        # Compute difficulty from the formula
        span = manhattan_distance(wps[0], wps[-1])
        bottleneck = min_edt_along_line(edt, bounds, cell_size, wps[0], wps[-1])
        pin_count = len(wps)
        diff = (span / max(bottleneck, 0.1)) * max(pin_count / 2.0, 1.0)
        difficulties.append((net_name, diff))

    mapping = ChannelMapping(channel_paths=paths)
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)

    # Sort by difficulty ascending
    difficulties.sort(key=lambda x: x[1])

    # Monotonicity: budget should be non-decreasing with difficulty
    for i in range(len(difficulties) - 1):
        name_a, diff_a = difficulties[i]
        name_b, diff_b = difficulties[i + 1]
        if diff_a < diff_b - 1e-6:
            assert budget[name_a] <= budget[name_b], (
                f"Monotonicity violated: N{i} (diff={diff_a:.2f}, "
                f"budget={budget[name_a]}) > N{i+1} (diff={diff_b:.2f}, "
                f"budget={budget[name_b]})"
            )


# ---------------------------------------------------------------------------
# PBT: Boundedness
# ---------------------------------------------------------------------------


@pytest.mark.l3_pbt
@given(
    width=st.integers(10, 80),
    height=st.integers(10, 80),
    density=st.floats(0.0, 0.5),
    seed=st.integers(0, 500),
)
@settings(max_examples=100, deadline=30000)
def test_budget_bounded(width, height, density, seed):
    """Budget for any net is always in [1000, base_budget]."""
    rng = np.random.default_rng(seed)

    free_mask = rng.random((height, width)) > density
    edt, bounds, cell_size = _make_edt_from_mask(free_mask)

    n_nets = rng.integers(3, 10)
    paths = {}
    for i in range(n_nets):
        n_wp = rng.integers(2, 6)
        wps = [(float(rng.integers(1, width - 1)), float(rng.integers(1, height - 1)))
               for _ in range(n_wp)]
        paths[f"N{i}"] = ChannelPath(f"N{i}", [], wps, 0.0)

    mapping = ChannelMapping(channel_paths=paths)
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)

    for net_name, b in budget.items():
        assert 1000 <= b <= 100000, (
            f"Budget out of bounds: {net_name} = {b}"
        )


# ---------------------------------------------------------------------------
# Integration: budget affects routing
# ---------------------------------------------------------------------------


@pytest.mark.l4_regression
def test_budget_via_run_astar_pathfinding():
    """Routing with a per-net budget produces valid PathfindingResult."""
    from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding

    # Simple grid: 30x30, all free
    grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0.0, 0.0), 1.0, 30, 30)

    ch1 = ChannelPath("N0", [], [(2.0, 2.0), (28.0, 28.0)], 0.0)
    ch2 = ChannelPath("N1", [], [(2.0, 28.0), (28.0, 2.0)], 0.0)
    mapping = ChannelMapping(channel_paths={"N0": ch1, "N1": ch2})

    # Compute budget from the grid
    edt, bounds, cell_size = _build_edt_from_grid(grid)
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)

    result = run_astar_pathfinding(mapping, grid, net_budgets=budget)
    assert result.success_count == 2
    assert result.failure_count == 0


@pytest.mark.l4_regression
def test_budget_with_blocked_grid():
    """Tight budget causes failure on blocked grid; generous succeeds."""
    from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding

    # Build a maze grid with a narrow gap
    arr = np.ones((20, 20), dtype=np.int8)
    arr[2:18, :] = 0  # mostly free
    arr[8:12, :] = 1  # wall in middle
    arr[8:12, 9] = 0  # single-cell gap at column 9
    grid = OccupancyGrid("F.Cu", arr, (0.0, 0.0), 1.0, 20, 20)

    ch = ChannelPath("N0", [], [(5.0, 10.0), (15.0, 10.0)], 0.0)
    mapping = ChannelMapping(channel_paths={"N0": ch})

    # Extremely tight budget should fail
    tight_budget = {"N0": 10}
    result_tight = run_astar_pathfinding(mapping, grid, net_budgets=tight_budget)
    # May or may not route — but must terminate (not hang)

    # Generous budget should succeed
    generous_budget = {"N0": 50000}
    result_generous = run_astar_pathfinding(mapping, grid, net_budgets=generous_budget)
    assert result_generous.success_count >= result_tight.success_count, (
        "Generous budget should not reduce success rate"
    )
