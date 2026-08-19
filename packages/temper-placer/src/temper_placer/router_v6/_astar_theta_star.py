"""
Router V6: any-angle A* search (Theta* / Lazy Theta*) and their shared
line-of-sight primitive.

Part of temper-N6-U6 decomposition -- split from astar_core.py to bring
that module back under the repo's then-enforced 1000-line cap (the N6 LOC cap
gate, retired 2026-08-18; see ``docs/adr/2026-08-18-retire-loc-cap-gate.md``).

**One implementation, always.**  ``_astar_search_theta_star`` and
``_astar_search_lazy_theta_star`` run the Rust kernel
(``temper_rust_router.theta_star_search_py``) unconditionally, and
``_line_of_sight_dispatch`` runs ``line_of_sight_py`` unconditionally.  A
missing/stale extension raises
:class:`ThetaStarExtensionUnavailableError` -- it is a broken build, not a
runtime mode (same contract as the 2D kernel; see the module docstring of
``astar_core_rust``).

Two switches were removed on 2026-08-18 because both made "which code
routed this board?" unanswerable:

1. **The runtime monitor used to substitute the implementation.**  Both
   entry points read ``get_monitor_state() is None`` and, when a monitor
   was active, ran a *pure-Python* search instead of the Rust kernel.
   Measured on an empty 10x10 grid: monitor inactive -> 2 Rust kernel
   calls / 0 Python; inside ``astar_monitor()`` -> 0 Rust / 1
   ``_astar_search_theta_star_python`` / 1
   ``_astar_search_lazy_theta_star_python``.  So every number taken under
   the monitor described different code than a production run, and the act
   of measuring was what changed it.

   The monitor did not need that substitution.  The non-lazy Python
   reference contained **no monitor calls at all** -- substituting it
   observed nothing.  The lazy reference's single ``record_pop`` fed the
   f-cost-monotonicity check, which is not an invariant of Lazy Theta* in
   the first place: this repo's own
   ``test_monitor_lazy_theta_star_obstacle_grid`` documents that "Lazy
   Theta* naturally produces non-monotonic f-costs on obstacle grids ...
   The monitor should detect this", and wraps the call in
   ``try/except pytest.fail.Exception`` precisely because the check is
   expected to fire.  Monitoring now observes and never substitutes.

2. **Silent ``ImportError`` fallbacks** at the LOS dispatch and at both
   search entry points.  See ``_require_theta_star_extension``.

The two pure-Python search references that those switches reached are
deleted with this change (verified unreachable: nothing in ``packages/``,
``scripts/`` or ``benchmarks/`` referenced
``_astar_search_theta_star_python`` /
``_astar_search_lazy_theta_star_python`` outside this file).  They survive
as frozen, hermetic verbatim copies inside the differential suite
(``tests/router_v6/test_astar_cluster_rust_differential.py``:
``_oracle_astar_search_theta_star`` / ``_oracle_astar_search_lazy_theta_star``),
which is what pins the Rust kernel -- so the proof is untouched and the
proof and its subject are no longer the same object.

``_line_of_sight`` (the pure-Python Bresenham reference, with its
bounding-box shortcut and the ``_LOS_BB_*`` counters) is **kept**: it is
still reachable as the reference oracle for four test modules
(``test_los_rust_correctness``, ``test_los_bb_shortcut``,
``test_astar_metamorphic_pbt``, ``test_astar_perf_regression``).  It is no
longer on any production path -- see ``log_los_bb_stats``.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_core import in_bounds


class ThetaStarExtensionUnavailableError(RuntimeError):
    """``temper_rust_router`` is missing or stale.

    Raised instead of silently substituting a pure-Python search.  This
    mirrors the 2D kernel's contract: a missing extension is a **broken
    build**, not a runtime mode.

    The three ``except ImportError: -> pure Python`` fallbacks this
    replaces (the LOS dispatch and both search entry points) were unsafe
    for the same reason the 2D one was: nothing named which
    implementation had run, so a broken build laid copper on a
    mains-voltage board under a different algorithm and reported success.
    Recovery is ``make extensions`` (see AGENTS.md, "Build /
    environment"), never a fallback.
    """


_LOS_BB_HITS: list[int] = [0]
_LOS_BB_FALLS_THROUGH: list[int] = [0]


def _require_theta_star_extension():
    """Import ``temper_rust_router`` or fail closed.

    The single place this module turns "the extension is missing" into an
    error rather than into a *different algorithm*.  Verified 2026-08-18
    that no production caller can reach a pure-Python any-angle search:
    ``_astar_search._dispatch_search`` is the only src caller of either
    entry point, and it now has exactly one arm per variant.
    """
    try:
        import temper_rust_router as _trr
    except ImportError as exc:  # pragma: no cover -- extension missing/stale
        raise ThetaStarExtensionUnavailableError(
            "temper_rust_router.theta_star_search_py is unavailable, so the "
            "any-angle (Theta*/Lazy Theta*) search cannot run. Rebuild the "
            "extension (`make extensions`, and see "
            "`scripts/check_stale_extensions.py`); there is deliberately no "
            "pure-Python fallback."
        ) from exc
    return _trr


def _line_of_sight_dispatch(p1, p2, grid, net_id: int) -> bool:
    """Bresenham LOS via the Rust kernel (cleanup C1).

    **Fails closed.**  Until 2026-08-18 this caught ``ImportError`` and
    fell through to ``_line_of_sight``; a stale extension therefore
    silently swapped the any-angle shortcut decision for a different
    implementation with nothing in the output naming which one ran.
    """
    from temper_placer.router_v6.astar_core_rust import _line_of_sight_rust

    try:
        return _line_of_sight_rust(p1, p2, grid, net_id)
    except ImportError as exc:  # pragma: no cover -- extension missing/stale
        raise ThetaStarExtensionUnavailableError(
            "temper_rust_router.line_of_sight_py is unavailable, so the "
            "any-angle line-of-sight check cannot run. Rebuild the "
            "extension (`make extensions`); there is deliberately no "
            "pure-Python fallback."
        ) from exc


def reset_los_bb_stats() -> None:
    _LOS_BB_HITS[0] = 0
    _LOS_BB_FALLS_THROUGH[0] = 0


def get_los_bb_stats() -> tuple[int, int]:
    return (_LOS_BB_HITS[0], _LOS_BB_FALLS_THROUGH[0])


def log_los_bb_stats() -> None:
    """Report the bounding-box shortcut counters.

    These count calls into ``_line_of_sight`` (the pure-Python reference)
    only.  Production line-of-sight goes through
    ``_line_of_sight_dispatch`` -> the Rust ``line_of_sight_py`` kernel,
    which keeps no such counter, so on a production route this
    unconditionally reports zero.  ``_astar_reconstruct`` still calls it;
    the "not measured here" wording below exists so that zero is not read
    as "the shortcut never fired".
    """
    hits, falls = get_los_bb_stats()
    total = hits + falls
    if total > 0:
        rate = hits / total * 100
        print(f"LOS BB shortcut: {hits} hits / {total} total = {rate:.1f}% skip rate")
    else:
        print(
            "LOS BB shortcut: no calls recorded -- the pure-Python "
            "_line_of_sight reference did not run (production LOS is the "
            "Rust line_of_sight_py kernel, which keeps no BB counter). "
            "This is not evidence the shortcut never fires."
        )


def _line_of_sight(
    p1: tuple[int, int],
    p2: tuple[int, int],
    grid,
    net_id: int,
) -> bool:
    """
    Check if there's an unobstructed diagonal line between two grid points.

    Uses Bresenham's line algorithm to check all cells along the path.

    Args:
        p1: Start grid position (x, y)
        p2: End grid position (x, y)
        grid: Occupancy grid
        net_id: Net ID (cells with this ID are allowed)

    Returns:
        True if line is clear
    """
    x0, y0 = p1
    x1, y1 = p2

    # @req(2026-06-29-feat-los-bb, R1): BB empty shortcut
    #
    # Only take the shortcut when both endpoints are on-grid. A negative
    # coordinate makes ``min(...)``/``max(...)+1`` produce a negative slice
    # bound, which numpy interprets as counting from the end of the axis
    # rather than "off the front of the grid" -- silently sampling the
    # wrong region and reporting a false "clear" for an endpoint that is
    # actually out of bounds (see the p1=(0,0), p2=(0,-1) 2x2-grid repro
    # that motivated this guard). Deferring out-of-bounds endpoints to the
    # Bresenham loop below keeps a single source of truth for bounds
    # checking (``in_bounds()``) instead of duplicating that logic here.
    if in_bounds(x0, y0, grid.width_cells, grid.height_cells) and in_bounds(
        x1, y1, grid.width_cells, grid.height_cells
    ):
        bbox = grid.grid[min(y0, y1) : max(y0, y1) + 1, min(x0, x1) : max(x0, x1) + 1]
        if not np.any(bbox):
            _LOS_BB_HITS[0] += 1
            return True
        _LOS_BB_FALLS_THROUGH[0] += 1

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0

    while True:
        if not in_bounds(x, y, grid.width_cells, grid.height_cells):
            return False

        cell_value = grid.grid[y, x]
        if cell_value != 0 and cell_value != net_id:
            return False

        if x == x1 and y == y1:
            return True

        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


_CONGESTION_CHECK_INTERVAL: int = 1000
_CONGESTION_GROWTH_THRESHOLD: int = 5
_CONGESTION_PLATEAU_STRIKES: int = 3


# The congestion-derivative early-abort parameters above are the Rust
# kernel's, not a Python path's: ``theta_star_search_py`` implements the
# same "<5 new cells per 1000 expansions for 3 consecutive windows -> give
# up" rule. They stay here because they are the documented tuning surface
# and ``benchmarks/congestion_derivative_bench.py`` imports them by name.


# ---------------------------------------------------------------------------
# Rust-backed search entry points (Wave-4 migration of this module).
#
# The public names below delegate to the Rust kernel
# (``temper_rust_router.theta_star_search_py``, proven bit-identical to the
# pure-Python reference by the differential suite
# ``tests/router_v6/test_astar_cluster_rust_differential.py``).
#
# They take NO branch on anything.  Not on whether the extension imported,
# and not on whether anyone is watching: the monitor gate and the
# ImportError fallbacks that used to live here are gone (module docstring).
# Whatever runs here is the only thing that can run here, which is the
# whole point -- a measurement of this path is a measurement of production.
# ---------------------------------------------------------------------------


def _theta_star_search_rust_kernel(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None,
    max_iter: int | None,
    enable_congestion_derivative: bool,
    lazy: bool,
) -> list[tuple[int, int]] | None:
    """Run the Rust Theta* kernel (``theta_star_search_py``).

    Raises :class:`ThetaStarExtensionUnavailableError` when
    ``temper_rust_router`` is missing — there is no caller-side fallback,
    by design (see the class docstring).
    """
    _trr = _require_theta_star_extension()

    grid_contig = np.ascontiguousarray(grid.grid, dtype=np.int8)
    height, width = grid_contig.shape
    start_idx = start_grid[1] * width + start_grid[0]
    goal_idx = goal_grid[1] * width + goal_grid[0]
    came_from_init_arg = None
    if came_from_init:
        came_from_init_arg = [
            (child[1] * width + child[0], parent[1] * width + parent[0])
            for child, parent in came_from_init.items()
        ]
    path_idxs = _trr.theta_star_search_py(
        grid_contig.tobytes(),
        width,
        height,
        start_idx,
        goal_idx,
        net_id,
        came_from_init_arg,
        max_iter,
        enable_congestion_derivative,
        lazy,
    )
    if not path_idxs:
        return None
    return [(int(i % width), int(i // width)) for i in path_idxs]


def _astar_search_lazy_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
) -> list[tuple[int, int]] | None:
    """Lazy Theta* pathfinding (Rust-backed).

    Always the Rust kernel. Activating ``astar_monitor()`` around this call
    observes it; it does not change it.
    """
    return _theta_star_search_rust_kernel(
        grid,
        start_grid,
        goal_grid,
        net_id,
        came_from_init,
        max_iter,
        enable_congestion_derivative,
        lazy=True,
    )


def _astar_search_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
    enable_congestion_derivative: bool = True,
) -> list[tuple[int, int]] | None:
    """Theta* pathfinding with any-angle paths (Rust-backed).

    Always the Rust kernel. Activating ``astar_monitor()`` around this call
    observes it; it does not change it.
    """
    return _theta_star_search_rust_kernel(
        grid,
        start_grid,
        goal_grid,
        net_id,
        came_from_init,
        max_iter,
        enable_congestion_derivative,
        lazy=False,
    )
