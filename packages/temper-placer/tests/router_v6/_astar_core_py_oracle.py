"""Pinned Python oracle for ``router_v6/astar_core.py``'s ``_astar_search``.

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Every line below the ``BEGIN VERBATIM EXTRACTION`` marker is a **verbatim**
``git show`` extraction from commit ``9bf6e5df797cf93e0122b742ab87661bf097dd81``
of ``packages/temper-placer/src/temper_placer/router_v6/astar_core.py``, concatenating these
line ranges in file order:

  - lines 18-53
  - lines 136-147
  - lines 221-366

Nothing below the marker has been reformatted, renamed, cleaned up, or
"fixed". ``test_oracle_is_verbatim_copy`` (in
``test_astar_search2d_rust_differential.py``) re-runs the identical extraction
and compares the result to this file's text character for character, so any
drift -- in this file or in the ranges' meaning -- fails closed.

Why this oracle exists
----------------------
``astar_core._astar_search`` was the last live pure-Python search kernel in
the router. Its single production call site was
``_corridor_backbone.route_edge_astar`` (``_corridor_backbone.py:523``),
reached for ``gnd`` via ``_ground_plane`` and for ``+3V3``/``vcc``/``+15V``/
``V_BUS_SENSE`` via ``_power_islands``. This file pins its pre-migration
behaviour so ``temper_rust_router_core::astar_search2d`` can be proven to
reproduce it bit-exactly -- on the real corridor-backbone grids the
production call site actually sees -- before the Python is deleted.

It is emphatically NOT the same function as the Rust
``astar_kernel_3d`` behind ``astar_core_rust._astar_search_rust``: that
kernel keeps a **closed set**, computes in **f32**, and hardcodes ``SQRT_2``
with no counterpart to the runtime-mutable ``DIAGONAL_COST_FACTOR``
multiplied in below. Those are three independent ways to move an argmin, so
it was not a usable base for this port and is left untouched.

What is NOT pinned here
-----------------------
The imports below the docstring are NOT part of the verbatim extraction --
they are this file's own standalone-runnability preamble. One name is
imported from a live module rather than copied, because it is stable
infrastructure the migration does not touch:

  - ``get_monitor_state`` (``router_v6.astar_monitor``) -- the runtime
    monitor hook, inert (returns ``None``) unless a monitor is installed.

``neighbor_validity``'s ``is_valid_2d`` and
``build_neighbor_validity_tensor_2d`` are likewise imported live, from
inside the extracted function body itself (that is how the original spells
them). ``OccupancyGrid`` is not copied either: the oracle operates on
whatever grid object it is handed, using only its ``grid`` /
``width_cells`` / ``height_cells`` surface.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from temper_placer.router_v6.astar_monitor import get_monitor_state

# --- BEGIN VERBATIM EXTRACTION ---

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

_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


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
