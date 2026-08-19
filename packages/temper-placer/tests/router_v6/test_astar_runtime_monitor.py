# ruff: noqa: F841  # state variable from the retired JIT backend
"""
Tests for A* Runtime Invariant Monitor.

Verifies the context-manager-activated monitor checks four structural
invariants during ``_astar_search`` execution. Zero overhead when the
context manager is not active (SC6).
"""

from __future__ import annotations

import statistics
import time

import numpy as np
import pytest

from temper_placer.router_v6.astar_core import _astar_search
from temper_placer.router_v6.astar_monitor import astar_monitor, get_monitor_state
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for r, c in blocked or set():
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


# Overhead-measurement parameters. N=11 samples follows the median-and-range
# discipline in docs/METHODOLOGY.md Sec 5 ("a single before/after measurement
# is not evidence when the oracle is noisy").
_OVERHEAD_ITERS = 100
_OVERHEAD_SAMPLES = 11

# Floor on the timed region. The ratio below is only evidence if the region
# it divides by is far larger than the clock's resolution; the perf gate's own
# noise analysis puts sub-microsecond regions at 24%+ variance and ~600us
# regions at 3.7%. The measured baseline here is ~13ms, so this floor is ~13x
# below the operating point and cannot cause a spurious failure -- it exists
# because the previous spelling ended in ``if t_baseline > 0 else 0.0``, i.e.
# a zero-length measurement reported *zero overhead* and the gate passed by
# measuring nothing. A gate that cannot fail is worse than one that flakes.
_MIN_BASELINE_S = 1e-3


def _paired_overhead_sample(grid: OccupancyGrid, iters: int) -> float:
    """One interleaved (baseline, monitored) CPU-time pair -> overhead ratio.

    The two halves are measured adjacently so that common-mode drift in
    machine load affects both and largely cancels in the ratio. Measuring
    all baselines first and all monitored runs second does *not* cancel:
    load that ramps up midway is charged entirely to the monitored half.
    """
    start, goal = (0, 0), (19, 19)

    t0 = time.thread_time()
    for _ in range(iters):
        _astar_search(start, goal, grid)
    t_baseline = time.thread_time() - t0

    t1 = time.thread_time()
    for _ in range(iters):
        with astar_monitor():
            _astar_search(start, goal, grid)
    t_monitored = time.thread_time() - t1

    assert t_baseline >= _MIN_BASELINE_S, (
        f"baseline CPU time {t_baseline * 1e3:.4f}ms over {iters} iterations is "
        f"below the {_MIN_BASELINE_S * 1e3:.1f}ms floor -- the overhead ratio "
        "would be measuring clock granularity, not the monitor. Raise "
        "_OVERHEAD_ITERS rather than removing this check."
    )
    return (t_monitored - t_baseline) / t_baseline


def test_monitor_no_overhead_when_inactive():
    """The monitor must not materially slow A*: CPU overhead stays under 50%.

    Instrument (2026-08-04). The claim is about *CPU work the monitor adds*,
    so it is measured with ``time.thread_time()``, not ``time.perf_counter()``.
    Wall clock also counts time the process spent descheduled, which on a
    saturated runner is unbounded and unrelated to the monitor -- and this job
    runs under ``pytest -n auto``, so sibling xdist workers contend for CPU by
    construction.

    Measured on a 12-core host under 2x CPU oversubscription:

    ==============================================  ==============  =========
    form                                            overhead        fail rate
    ==============================================  ==============  =========
    perf_counter, single sample (old)               median -15.1%,   7/30
                                                    max +630.2%
    thread_time, single sample                      max +49.6%       0/30
    thread_time, median of 11 (this test)           median +5.4%,    0/25
                                                    max +20.9%
    ==============================================  ==============  =========

    Head-to-head at the pytest level, 20 invocations of each form under that
    same load: the old form failed 7/20, this form 0/20.

    The true CPU overhead is ~+5%, so the 50% threshold retains ~2.4x margin
    over the worst observed sample. A single CPU-time sample is *not* enough:
    it still reached +49.6% against a 50% threshold. Timer granularity was
    never the problem (1us tick vs a ~13ms baseline, ~13000 ticks), so the
    workload is deliberately left unchanged.

    The threshold is unchanged at 50%. The gate still bites: injecting
    redundant work into ``MonitorState.record_pop`` moves the measured
    overhead monotonically (+12.9% / +17.7% / +28.2% / +46.2% / +87.3% for
    5 / 10 / 20 / 40 / 80 extra ops per pop) and trips the assertion, both
    idle and under the same 2x load.

    Re-verified 2026-08-05, after the 51-PR backlog triage (#778) listed this
    test as a live ``main`` breakage. It is not one: the triage measured
    ``c60825861`` (2026-08-04T08:32-0600) and PR #697's run
    (2026-08-04T18:33Z), both of which predate the instrument above -- it
    landed in ``aece7c372`` at 2026-08-04T19:54Z, and #697's failure text
    (``Monitor overhead 55.6% ... Baseline: 0.0184s``) is the *old*
    single-wall-clock-sample message, not this one. Since then: the
    ``router_v6 group 3`` job is green on the 10 most recent ``Python Tests``
    runs on ``main``, and 25/25 local invocations pass under 24 busy loops on
    a 12-core host. The threshold is deliberately still 50% and the workload
    is deliberately unchanged; the only addition is the ``_MIN_BASELINE_S``
    floor, which closes the one way this gate could have passed vacuously.
    """
    grid = _make_grid(20, 20)

    # SC6: no monitor state leaks outside the context manager.
    assert get_monitor_state() is None

    ratios = sorted(
        _paired_overhead_sample(grid, _OVERHEAD_ITERS) for _ in range(_OVERHEAD_SAMPLES)
    )
    overhead_ratio = statistics.median(ratios)

    assert get_monitor_state() is None

    assert overhead_ratio < 0.5, (
        f"Monitor CPU overhead median {overhead_ratio:.1%} exceeds 50% threshold "
        f"over {_OVERHEAD_SAMPLES} samples "
        f"(range {ratios[0]:.1%}..{ratios[-1]:.1%})."
    )


def test_monitor_theta_star_no_single_expansion_check():
    """Theta* with monitor active -> single-expansion check is disabled by default."""
    from temper_placer.router_v6._astar_theta_star import _astar_search_theta_star

    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search_theta_star(grid, (0, 0), (9, 9), net_id=0)
        assert path is not None
    # No single-expansion violations because check is disabled by default
    single_exp_violations = [v for v in state.violations if v.invariant == "single_expansion"]
    assert len(single_exp_violations) == 0


def test_monitor_path_completeness_ok():
    """Monitor validates path starts/ends correctly and is adjacent."""
    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search((0, 0), (9, 9), grid)
        assert path is not None
    path_violations = [v for v in state.violations if v.invariant == "path_completeness"]
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
    from temper_placer.router_v6._astar_theta_star import _astar_search_lazy_theta_star

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
    from temper_placer.router_v6._astar_theta_star import _astar_search_lazy_theta_star

    blocked = {(5, y) for y in range(9)} | {(5, 5)}
    grid = _make_grid(10, 10, blocked)
    try:
        with astar_monitor():
            path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
            assert path is not None, "Should find path on obstacle grid"
    except pytest.fail.Exception as e:
        # Expected: f_cost_monotonicity violations from optimistic parent
        assert "f_cost_monotonicity" in str(e), f"Unexpected monitor failure: {e}"
    # Verify path is actually findable (without monitor interference)
    path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
    assert path is not None, "Should find path on obstacle grid"


def test_monitor_lazy_theta_star_blocked_grid():
    """Lazy Theta* on blocked grid triggers f_cost_monotonicity.

    Same as above — f_cost_monotonicity violations are expected due
    to optimistic parent corrections on blocked grids.
    """
    from temper_placer.router_v6._astar_theta_star import _astar_search_lazy_theta_star

    blocked = {(5, y) for y in range(10)}
    grid = _make_grid(10, 10, blocked)
    try:
        with astar_monitor() as state:
            path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
            assert path is None
    except pytest.fail.Exception as e:
        # Expected: f_cost_monotonicity violations from optimistic parent
        assert "f_cost_monotonicity" in str(e), f"Unexpected monitor failure: {e}"


def test_monitor_lazy_theta_star_path_completeness_ok():
    """Monitor validates Lazy Theta* path starts/ends correctly."""
    from temper_placer.router_v6._astar_theta_star import _astar_search_lazy_theta_star

    grid = _make_grid(10, 10)
    with astar_monitor() as state:
        path = _astar_search_lazy_theta_star(grid, (0, 0), (9, 9), net_id=0)
        assert path is not None
    path_violations = [v for v in state.violations if v.invariant == "path_completeness"]
    assert len(path_violations) == 0


# ---------------------------------------------------------------------------
# Observation must not substitute (2026-08-18)
# ---------------------------------------------------------------------------
#
# Until this date, both any-angle entry points read
# ``get_monitor_state() is None`` and ran a *pure-Python* search whenever a
# monitor was active. Measured on an empty 10x10 grid before the fix:
# monitor inactive -> 2 Rust kernel calls / 0 Python; inside
# ``astar_monitor()`` -> 0 Rust / 1 ``_astar_search_theta_star_python`` /
# 1 ``_astar_search_lazy_theta_star_python``. Every number taken under the
# monitor therefore described different code than a production run.


def _count_theta_kernel_calls(fn, *args, **kwargs):
    """Run ``fn`` and return ``(result, rust_kernel_call_count)``."""
    import temper_placer.router_v6._astar_theta_star as ats

    original = ats._theta_star_search_rust_kernel
    calls = [0]

    def counting(*a, **k):
        calls[0] += 1
        return original(*a, **k)

    ats._theta_star_search_rust_kernel = counting
    try:
        return fn(*args, **kwargs), calls[0]
    finally:
        ats._theta_star_search_rust_kernel = original


@pytest.mark.parametrize("variant", ["theta_star", "lazy_theta_star"])
@pytest.mark.parametrize("blocked", [False, True])
def test_monitor_does_not_substitute_the_implementation(variant, blocked):
    """The Rust kernel runs whether or not a monitor is watching.

    Both halves must report exactly one kernel call. A zero on the
    monitored half is the original defect: the monitor swapped in a
    different implementation, so anything measured under it (time, call
    counts, profiler output) was about code production never runs.
    """
    from temper_placer.router_v6._astar_theta_star import (
        _astar_search_lazy_theta_star,
        _astar_search_theta_star,
    )

    search = (
        _astar_search_theta_star if variant == "theta_star" else (_astar_search_lazy_theta_star)
    )
    grid = _make_grid(10, 10, {(5, y) for y in range(9)} | {(5, 5)} if blocked else None)

    unobserved, unobserved_calls = _count_theta_kernel_calls(search, grid, (0, 0), (9, 9), net_id=0)

    # The monitor's own f-cost check is not an invariant of Lazy Theta*
    # (see test_monitor_lazy_theta_star_obstacle_grid), and __exit__ turns
    # violations into pytest.fail under PYTEST_CURRENT_TEST -- so the
    # context is exited before asserting, and a fired check is tolerated.
    # The sentinel makes a *skipped body* (rather than a fired check on
    # exit) fail loudly instead of silently passing the assertion below.
    observed, observed_calls = object(), -1
    try:
        with astar_monitor():
            observed, observed_calls = _count_theta_kernel_calls(
                search, grid, (0, 0), (9, 9), net_id=0
            )
    except pytest.fail.Exception as exc:  # pragma: no cover -- variant-dependent
        assert "f_cost_monotonicity" in str(exc), exc

    assert unobserved_calls == 1, (
        f"{variant}: expected exactly 1 Rust kernel call with no monitor, got {unobserved_calls}"
    )
    assert observed_calls == 1, (
        f"{variant}: the Rust kernel must still run under astar_monitor(); "
        f"got {observed_calls} kernel calls. Observing must never substitute "
        "the implementation."
    )
    assert observed == unobserved, (
        f"{variant}: path differed between the observed and unobserved runs"
    )


def test_no_pure_python_any_angle_search_survives_in_src():
    """The substituted-in Python searches are gone, not merely bypassed.

    Leaving them importable would keep "which implementation routed this?"
    answerable only by reading a branch. The frozen verbatim copies live
    in ``tests/router_v6/test_astar_cluster_rust_differential.py``
    (``_oracle_astar_search_theta_star`` /
    ``_oracle_astar_search_lazy_theta_star``), which is what pins the Rust
    kernel -- so the proof is intact and is no longer the same object as
    its subject.
    """
    import temper_placer.router_v6._astar_theta_star as ats

    for name in (
        "_astar_search_theta_star_python",
        "_astar_search_lazy_theta_star_python",
    ):
        assert not hasattr(ats, name), (
            f"{name} is reachable again. If a Python any-angle search is "
            "genuinely needed, it must be selected explicitly and logged -- "
            "never implicitly on a monitor-state check."
        )


def test_theta_star_fails_closed_when_the_extension_is_missing():
    """A missing extension raises; it never routes with something else.

    Same contract as the 2D kernel: a missing ``temper_rust_router`` is a
    broken build, not a runtime mode.
    """
    import builtins

    from temper_placer.router_v6._astar_theta_star import (
        ThetaStarExtensionUnavailableError,
        _require_theta_star_extension,
    )

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "temper_rust_router":
            raise ImportError("simulated missing extension")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = refuse
    try:
        with pytest.raises(ThetaStarExtensionUnavailableError):
            _require_theta_star_extension()
    finally:
        builtins.__import__ = real_import
