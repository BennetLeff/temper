"""Pinned Python oracle for ``router_v6/astar_core.py``'s 2D A* search.

DO NOT EDIT -- THIS IS THE REFERENCE.
=====================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``9019da63fe1f8cfccb98c53fafbbf0a8537ee7a6`` (``origin/main``,
2026-08-18) of ``temper_placer/router_v6/astar_core.py``:
``OCTILE_DIAG``, ``DIAGONAL_COST_FACTOR``, ``_BASE_DIAGONAL_COST``,
``_SAME_NET_COST_DISCOUNT``, ``octile_distance``, ``in_bounds``,
``_DIRS_8``, ``_astar_search`` and ``_heuristic`` -- i.e. exactly the
transitive closure of what ``_astar_search`` needs, and nothing else.

Nothing has been cleaned up, refactored, or fixed.

Why this oracle exists (2026-08-18)
-----------------------------------
``astar_core_rust._astar_search_rust`` used to catch ``ImportError`` on
``temper_rust_router`` and silently fall through to
``astar_core._astar_search``. That fallback was **not** behaviour-equivalent
-- the Rust kernel computes in f32 and carries a closed set and a congestion
term, the Python reference computes in f64, re-expands, and has neither --
so a missing extension quietly laid *different copper on a mains board* with
nothing in the output naming which implementation ran. The fallback was
deleted; a missing extension is now a loud, immediate failure.

Deleting the fallback removed the *only* reason the runtime router needed
``astar_core._astar_search``. But the differential suite that proves the
Rust kernel correct
(``test_astar_kernel_rust_differential.py::test_same_net_bit_exact_vs_oracle``
and friends) was importing that same live ``src/`` function as its oracle --
so the proof and the subject were the same object. This file breaks that
circularity: the differential now reads a frozen copy, pinned by
``scripts/oracle_hashes.json`` and gated by ``scripts/check_oracle_hashes.py``,
which cannot drift when ``src/`` changes.

Scope note -- this is the **2D** search only. ``_astar_search_3d`` /
``_route_segment_3d`` (Tier 3) are still pure Python with no Rust
equivalent yet and are deliberately NOT pinned here.

What the differential does and does not assert
----------------------------------------------
``test_same_net_bit_exact_vs_oracle``'s own docstring concedes that Rust and
Python may differ in *cell sequence* (the f64->f32 heuristic cast changes
heap tie-breaking when costs are close). It asserts invariants -- both reach
the goal, both respect occupancy, both are connected -- not path equality.
That is the honest strength of this differential and moving it onto a pinned
oracle does not change it either way.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from temper_placer.router_v6.astar_monitor import get_monitor_state

# A* search primitives (formerly in routing/heuristics.py)
OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0

# Configurable diagonal cost multiplier for the A* inner loop.
# 1.0 = standard octile (diagonal  1.414, cardinal  1.0).
# Lower values incentivise diagonals.  Assign to this module attribute
# directly; the former `metrics.octilinear.add_diagonal_incentive` setter was
# retired along with that module (it had no callers).
DIAGONAL_COST_FACTOR: float = 1.0
_BASE_DIAGONAL_COST: Final[float] = math.sqrt(2.0)
# Cost multiplier for cells already occupied by the same net.
# < 1.0 incentivises tree branches to share copper space rather than
# spreading out, reducing the overall footprint and leaving more free
# cells available for cross-net routes.
_SAME_NET_COST_DISCOUNT: Final[float] = 0.25


def octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + OCTILE_DIAG * min(dx, dy)


def in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool:
    return 0 <= x < width_cells and 0 <= y < height_cells


# 8-move direction encoding shared with neighbor_validity.DIRS_8.
# Order: E, SE, S, SW, W, NW, N, NE.
_DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
)


def _astar_search(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid,
    neighbor_tensor: np.ndarray | None = None,
    thermal_flat: np.ndarray | None = None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
    corridor_mask: np.ndarray | None = None,
) -> list[tuple[int, int]] | None:
    """
    A* search algorithm for pathfinding.

    Args:
        start: Start cell (x, y)
        goal: Goal cell (x, y)
        grid: Occupancy grid
        neighbor_tensor: Pre-baked (rows, cols, 8) boolean tensor from
            ``neighbor_validity.build_neighbor_validity_tensor_2d``.
            When ``None`` (the default for back-compat with existing
            callers), the inner loop falls back to the inlined
            bounds + numpy check.  When supplied, the inner loop
            uses a single bit read per neighbor.
        thermal_flat: U8 optional ``(height_cells*width_cells,)``
            float32 cost field.  Added to step-cost alongside
            congestion.
        thermal_weight: U8 multiplier on per-cell thermal cost.
        corridor_mask: Optional ``(height_cells, width_cells)`` boolean
            mask (e.g. ``corridor_erosion.corridor_mask_for_net``) --
            when supplied AND ``net_id >= 0``, a destination cell outside
            the corridor is invalid regardless of raw occupancy. This is
            the ``net_id >= 0`` inline-occupancy-check counterpart of
            ``neighbor_tensor``'s existing ``corridor_mask`` support: the
            ``net_id >= 0`` branch below does its own occupancy check
            rather than consulting ``neighbor_tensor`` (see the branch
            below), so a corridor constraint for a real, net-aware search
            has to be threaded through here directly. Spike:
            docs/evidence/2026-08-11-corridor-aware-astar-spike.md.

    Returns:
        List of cells or None if no path found
    """
    from heapq import heappop, heappush

    use_thermal = thermal_flat is not None and thermal_weight > 0.0

    # Backward-compat: if no tensor was passed, build one on the
    # fly.  This is the same cost as the inlined check (one pass
    # over the grid) but keeps the inner loop on the tensor path.
    # New callers should build the tensor once at A* pass start
    # (outside the per-net A* loop) and pass it in.
    if neighbor_tensor is None and net_id < 0:
        from temper_placer.router_v6.neighbor_validity import (
            build_neighbor_validity_tensor_2d,
        )

        neighbor_tensor = build_neighbor_validity_tensor_2d(grid)

    cols = grid.width_cells

    # A* frontier (priority queue)
    frontier: list = []
    heappush(frontier, (0, start))

    # Came from and cost tracking
    came_from = {start: None}
    cost_so_far = {start: 0}

    while frontier:
        current_f, current = heappop(frontier)

        # Runtime monitor: record f-cost monotonicity and single-expansion
        _mon = get_monitor_state()
        if _mon is not None:
            _mon.record_pop(current, float(current_f))

        if current == goal:
            # Reconstruct path
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            path = list(reversed(path))

            # Runtime monitor: validate cost lower bound and path completeness
            if _mon is not None:
                _mon.validate_cost_lower_bound(path, cost_so_far, came_from)
                _mon.validate_path_completeness(path, start, goal)

            return path

        # Explore neighbors (8-connected).  U5: the validity tensor is
        # pre-baked once at A* pass start so the inner loop is a
        # single bit read per (cell, direction).  See
        # neighbor_validity.build_neighbor_validity_tensor_2d.
        from temper_placer.router_v6.neighbor_validity import (
            is_valid_2d as _tensor_is_valid,
        )

        cx, cy = current  # current is (x, y) tuple; rename for tensor indexing

        for dir_idx in range(8):
            dx, dy = _DIRS_8[dir_idx]
            nx, ny = cx + dx, cy + dy
            is_same_net = False
            if net_id >= 0:
                if not in_bounds(nx, ny, grid.width_cells, grid.height_cells):
                    continue
                if corridor_mask is not None and not corridor_mask[ny, nx]:
                    continue
                cell_value = grid.grid[ny, nx]
                if cell_value != 0 and cell_value != net_id:
                    continue
                is_same_net = cell_value == net_id
            else:
                # net_id < 0 guarantees neighbor_tensor was built at line 168.
                assert neighbor_tensor is not None
                if not _tensor_is_valid(neighbor_tensor, cy, cx, dir_idx):
                    continue

            # Diagonal cost uses configurable multiplier
            move_cost = DIAGONAL_COST_FACTOR * _BASE_DIAGONAL_COST if dx != 0 and dy != 0 else 1.0
            # Same-net occupancy: cells already committed for this net cost a
            # fraction of free cells so tree branches preferentially share
            # copper space, reducing overall footprint for cross-net routes.
            if is_same_net:
                move_cost *= _SAME_NET_COST_DISCOUNT
            # U8: additive thermal cost
            if use_thermal and thermal_flat is not None:
                n_idx = ny * cols + nx
                move_cost += float(thermal_weight) * float(thermal_flat[n_idx])
            new_cost = cost_so_far[current] + move_cost
            neighbor = (nx, ny)

            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = float(new_cost)  # type: ignore[assignment]
                priority = new_cost + _heuristic(neighbor, goal)
                heappush(frontier, (priority, neighbor))
                came_from[neighbor] = current

    return None  # No path found


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Octile distance heuristic for 8-connected grid search."""
    return octile_distance(a, b)
