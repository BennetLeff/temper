"""
Router V6: A* search algorithms and shared route dataclasses.

Part of temper-N6-U6 decomposition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

import numpy as np

# Lazy-import at module level so the A* inner loop doesn't pay import cost
from temper_placer.router_v6.astar_monitor import get_monitor_state  # noqa: E402

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


# ---------------------------------------------------------------------------
# Grid-quantization-aware path-point de-duplication.
#
# Root cause of docs/evidence/2026-07-27-acid-trap-elimination.md: pad,
# via, and waypoint coordinates are exact floats from the netlist/footprint
# layout; the routing grid is a fixed-pitch lattice.  ``grid_to_world``
# returns a cell's CENTER, so converting the A* path's grid cells back to
# world coordinates and then separately appending the exact terminal
# (``start_world``/``goal_world``) at each waypoint boundary produced two
# almost-but-not-quite-coincident points -- a near-zero-length "spur"
# whose direction is essentially arbitrary relative to the grid-aligned
# approach direction.  That spur's vertex reliably registers as an acute
# angle (`acid_trap_detection.py`), on very nearly every routed net,
# independent of any real routing decision.  These helpers collapse that
# spur at the three call sites that build path geometry from a grid+exact
# terminal pair (`_astar_route`, `_astar_route_multilayer`,
# `_route_segment_3d`) instead of leaving it for a general corner-mitring
# pass to paper over -- the double-vertex is never generated in the first
# place.
# ---------------------------------------------------------------------------


def grid_quantization_tolerance(cell_size: float) -> float:
    """Max distance between a world point and its grid cell's center.

    ``OccupancyGrid.grid_to_world`` returns a cell's center; any point
    inside that cell (e.g. an off-grid pad whose nearest cell is this
    one) is at most half the cell's diagonal away from that center. Two
    path points closer together than this cannot represent a real
    direction change -- they are the same physical location to within
    the grid's own quantization error, not a routing decision.
    """
    return cell_size * math.sqrt(2.0) / 2.0


def _same_path_layer(a: tuple, b: tuple) -> bool:
    """True if two path-point tuples share a layer.

    Points are ``(x, y)`` (single-layer paths) or ``(x, y, layer)``
    (multi-layer paths). 2-tuples are always same-layer by definition.
    Never merge two 3-tuples on different layers -- that would erase a
    real via transition, not a quantization artifact.
    """
    if len(a) > 2 and len(b) > 2:
        return a[2] == b[2]
    return True


def append_grid_path_point(points: list[tuple], point: tuple, tolerance: float) -> None:
    """Append a grid-derived ``point`` unless it duplicates ``points[-1]``
    to within grid quantization noise.

    Used while walking an A* grid path's cells. Keeps the existing last
    point (typically an exact terminal appended just before this loop
    started) rather than the new, merely-approximate grid-cell center.
    """
    if points and _same_path_layer(points[-1], point):
        last = points[-1]
        if math.hypot(point[0] - last[0], point[1] - last[1]) <= tolerance:
            return
    points.append(point)


def append_exact_terminal_point(points: list[tuple], point: tuple, tolerance: float) -> None:
    """Append an exact terminal ``point`` (pad/via/waypoint location),
    replacing ``points[-1]`` instead of duplicating it when the two are
    within grid quantization noise of each other.

    Used when closing out a segment onto its exact goal coordinate: the
    exact terminal is more authoritative than the grid-cell-center point
    that preceded it, so it replaces rather than merely follows it.
    """
    if points and _same_path_layer(points[-1], point):
        last = points[-1]
        if math.hypot(point[0] - last[0], point[1] - last[1]) <= tolerance:
            points[-1] = point
            return
    points.append(point)


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


@dataclass
class RoutePath:
    """A routed path for a net."""

    net_name: str
    coordinates: list[tuple[float, float]]  # (x, y) path coordinates
    layer_name: str
    path_length: float  # Total length in mm
    forced_segment_count: int = 0  # Number of segments using force routing (fallback)
    # Waypoint indices whose incoming edge was not found by A*.  Kept so a
    # multi-terminal caller can fail closed and name the unresolved terminal.
    failed_waypoint_indices: list[int] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.coordinates) - 1)

    @property
    def success(self) -> bool:
        """Whether the route was successfully found."""
        return len(self.coordinates) >= 2


@dataclass
class RouteNode3D:
    """3D routing state for multi-layer A* pathfinding."""

    x: int  # Grid x coordinate
    y: int  # Grid y coordinate
    layer: str  # Layer name (e.g., "F.Cu", "B.Cu")

    def __hash__(self):
        return hash((self.x, self.y, self.layer))

    def __eq__(self, other):
        if not isinstance(other, RouteNode3D):
            return False
        return self.x == other.x and self.y == other.y and self.layer == other.layer


@dataclass
class RoutePath3D:
    """A routed path with explicit layer information per segment."""

    net_name: str
    segments: list[tuple[float, float, str]]  # (x, y, layer) coordinates
    via_positions: list[tuple[float, float]]  # Positions where layer changes occur
    path_length: float  # Total length in mm
    via_count: int = 0
    forced_segment_count: int = 0
    failed_waypoint_indices: list[int] = field(default_factory=list)
    # Diagnostic carrier only: Rust decides whether the failed Tier-3 search
    # stopped at its cap. None means this path did not carry that failure.
    failure_hit_iteration_cap: bool | None = None

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.segments) - 1)

    def to_route_path(self, default_layer: str = "F.Cu") -> RoutePath:
        """Convert to legacy RoutePath format."""
        coords = [(s[0], s[1]) for s in self.segments]
        return RoutePath(
            net_name=self.net_name,
            coordinates=coords,
            layer_name=default_layer,
            path_length=self.path_length,
            forced_segment_count=self.forced_segment_count,
            failed_waypoint_indices=self.failed_waypoint_indices,
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

