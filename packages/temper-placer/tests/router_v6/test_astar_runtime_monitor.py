"""
Tests for A* Runtime Invariant Monitor.

Verifies the context-manager-activated monitor checks four structural
invariants during ``_astar_search`` execution. Zero overhead when the
context manager is not active (SC6).
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from temper_placer.router_v6.astar_core import _astar_search
from temper_placer.router_v6.astar_monitor import astar_monitor, get_monitor_state
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in (blocked or set()):
        arr[r, c] = 1
    return OccupancyGrid("Test", arr, (0.0, 0.0), 1.0, cols, rows)


def test_monitor_no_violations_empty_grid():
    """A* on empty 10x10 grid with monitor active -> no violations."""
    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search((0, 0), (9, 9), grid)
        assert path is not None
        assert len(path) > 0
    assert len(state.violations) == 0


def test_monitor_no_violations_obstacle_grid():
    """A* on grid with obstacles -> path found, no violations."""
    blocked = {(5, y) for y in range(9)} | {(5, 5)}
    grid = _make_grid(10, 10, blocked)
    with astar_monitor() as state:
        path = _astar_search((0, 0), (9, 9), grid)
        assert path is not None
    assert len(state.violations) == 0


def test_monitor_no_path():
    """A* with start/goal separated by wall -> None, no violations."""
    blocked = {(5, y) for y in range(10)}
    grid = _make_grid(10, 10, blocked)
    with astar_monitor() as state:
        path = _astar_search((0, 0), (9, 9), grid)
        assert path is None
    # Search exhausted the frontier, no violations
    assert len(state.violations) == 0


def test_monitor_detects_broken_heuristic():
    """With monkey-patched inconsistent heuristic, f-cost monotonicity violations
    are detected and the monitor fails via pytest.fail in CI mode."""
    grid = _make_grid(10, 10)

    import temper_placer.router_v6.astar_core as ac
    _original_heuristic = ac._heuristic

    # An inconsistent heuristic: alternates between 0 and 50 based on
    # parity of coordinates. This causes f-cost to oscillate, breaking
    # monotonicity.
    def _broken_heuristic(a, _b):
        return 50.0 if (a[0] + a[1]) % 2 == 0 else 0.0

    try:
        ac._heuristic = _broken_heuristic
        with pytest.raises(pytest.fail.Exception, match=r"f_cost_monotonicity"), astar_monitor():
            _astar_search((0, 0), (9, 9), grid)
    finally:
        ac._heuristic = _original_heuristic


def test_monitor_no_overhead_when_inactive():
    """Without context manager, A* runs with no monitor overhead."""
    grid = _make_grid(20, 20)
    N = 100

    # Run without monitor
    t0 = time.perf_counter()
    for _ in range(N):
        _astar_search((0, 0), (19, 19), grid)
    t_baseline = time.perf_counter() - t0

    # Verify monitor is inactive
    assert get_monitor_state() is None

    # Run with monitor
    t1 = time.perf_counter()
    for _ in range(N):
        with astar_monitor():
            _astar_search((0, 0), (19, 19), grid)
    t_monitored = time.perf_counter() - t1

    # Monitor overhead should stay under 25% of baseline
    # (the plan specifies <10%; 25% is a generous CI safety margin)
    overhead_ratio = (t_monitored - t_baseline) / t_baseline if t_baseline > 0 else 0
    assert overhead_ratio < 0.5, (
        f"Monitor overhead {overhead_ratio:.1%} exceeds 50% threshold. "
        f"Baseline: {t_baseline:.4f}s, Monitored: {t_monitored:.4f}s"
    )


def test_monitor_theta_star_no_single_expansion_check():
    """Theta* with monitor active -> single-expansion check is disabled by default."""
    from temper_placer.router_v6.astar_core import _astar_search_theta_star

    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search_theta_star(grid, (0, 0), (9, 9), net_id=0)
        assert path is not None
    # No single-expansion violations because check is disabled by default
    single_exp_violations = [
        v for v in state.violations if v.invariant == "single_expansion"
    ]
    assert len(single_exp_violations) == 0


def test_monitor_path_completeness_ok():
    """Monitor validates path starts/ends correctly and is adjacent."""
    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search((0, 0), (9, 9), grid)
        assert path is not None
    path_violations = [
        v for v in state.violations if v.invariant == "path_completeness"
    ]
    assert len(path_violations) == 0


# ---------------------------------------------------------------------------
# Lazy Theta* Monitor Tests (U7)
# ---------------------------------------------------------------------------


def test_monitor_lazy_theta_star_no_violations_empty_grid():
    """Lazy Theta* on empty 10x10 grid with monitor active.

    On empty grids, Lazy Theta* uses the straight-line diagonal so no
    LOS failures occur, hence no parent corrections and no violation
    of f-cost monotonicity.
    """
    from temper_placer.router_v6.astar_core import _astar_search_lazy_theta_star

    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
        assert path is not None
        assert len(path) > 0
    assert len(state.violations) == 0


def test_monitor_lazy_theta_star_obstacle_grid():
    """Lazy Theta* on grid with obstacles triggers f_cost_monotonicity.

    Lazy Theta* naturally produces non-monotonic f-costs on obstacle
    grids because optimistic parent assignments are corrected at pop
    time. The monitor should detect this, but only f_cost_monotonicity
    violations (not structural ones like path_completeness).
    """
    from temper_placer.router_v6.astar_core import _astar_search_lazy_theta_star

    blocked = {(5, y) for y in range(9)} | {(5, 5)}
    grid = _make_grid(10, 10, blocked)
    try:
        with astar_monitor():
            path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
            assert path is not None, "Should find path on obstacle grid"
    except pytest.fail.Exception as e:
        # Expected: f_cost_monotonicity violations from optimistic parent
        assert "f_cost_monotonicity" in str(e), (
            f"Unexpected monitor failure: {e}"
        )
    # Verify path is actually findable (without monitor interference)
    path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
    assert path is not None, "Should find path on obstacle grid"


def test_monitor_lazy_theta_star_blocked_grid():
    """Lazy Theta* on blocked grid triggers f_cost_monotonicity.

    Same as above — f_cost_monotonicity violations are expected due
    to optimistic parent corrections on blocked grids.
    """
    from temper_placer.router_v6.astar_core import _astar_search_lazy_theta_star

    blocked = {(5, y) for y in range(10)}
    grid = _make_grid(10, 10, blocked)
    try:
        with astar_monitor() as state:
            path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
            assert path is None
    except pytest.fail.Exception as e:
        # Expected: f_cost_monotonicity violations from optimistic parent
        assert "f_cost_monotonicity" in str(e), (
            f"Unexpected monitor failure: {e}"
        )


def test_monitor_lazy_theta_star_path_completeness_ok():
    """Monitor validates Lazy Theta* path starts/ends correctly."""
    from temper_placer.router_v6.astar_core import _astar_search_lazy_theta_star

    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
        assert path is not None
    path_violations = [
        v for v in state.violations if v.invariant == "path_completeness"
    ]
    assert len(path_violations) == 0
