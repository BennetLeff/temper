"""
Router V6: A* search algorithms and shared route dataclasses.

Part of temper-N6-U6 decomposition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from temper_placer.core.board import STANDARD_LAYER_ORDER

# Lazy-import at module level so the A* inner loop doesn't pay import cost
enable_numba_los = False  # Numba JIT LoS not merged; temper-N6-U8
from temper_placer.router_v6.astar_monitor import get_monitor_state  # noqa: E402

# A* search primitives (formerly in routing/heuristics.py)
OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0

_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 0), (0, -1), (-1, 0),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
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
    (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1),
)


@dataclass
class RoutePath:
    """A routed path for a net."""

    net_name: str
    coordinates: list[tuple[float, float]]  # (x, y) path coordinates
    layer_name: str
    path_length: float  # Total length in mm
    forced_segment_count: int = 0  # Number of segments using force routing (fallback)

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
        )


def _astar_search(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid,
    neighbor_tensor: np.ndarray | None = None,
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

    Returns:
        List of cells or None if no path found
    """
    from heapq import heappop, heappush

    # Backward-compat: if no tensor was passed, build one on the
    # fly.  This is the same cost as the inlined check (one pass
    # over the grid) but keeps the inner loop on the tensor path.
    # New callers should build the tensor once at A* pass start
    # (outside the per-net A* loop) and pass it in.
    if neighbor_tensor is None:
        from temper_placer.router_v6.neighbor_validity import (
            build_neighbor_validity_tensor_2d,
        )
        neighbor_tensor = build_neighbor_validity_tensor_2d(grid)

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
            if not _tensor_is_valid(neighbor_tensor, cy, cx, dir_idx):
                continue
            dx, dy = _DIRS_8[dir_idx]
            nx, ny = cx + dx, cy + dy

            # Diagonal cost = 1.414, Cardinal = 1.0
            move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
            new_cost = cost_so_far[current] + move_cost
            neighbor = (nx, ny)

            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = float(new_cost)  # type: ignore[assignment]
                priority = new_cost + _heuristic(neighbor, goal)
                heappush(frontier, (priority, neighbor))
                came_from[neighbor] = current

    return None  # No path found


_LOS_BB_HITS: list[int] = [0]
_LOS_BB_FALLS_THROUGH: list[int] = [0]


def reset_los_bb_stats() -> None:
    _LOS_BB_HITS[0] = 0
    _LOS_BB_FALLS_THROUGH[0] = 0


def get_los_bb_stats() -> tuple[int, int]:
    return (_LOS_BB_HITS[0], _LOS_BB_FALLS_THROUGH[0])


def log_los_bb_stats() -> None:
    hits, falls = get_los_bb_stats()
    total = hits + falls
    if total > 0:
        rate = hits / total * 100
        print(f"LOS BB shortcut: {hits} hits / {total} total = {rate:.1f}% skip rate")
    else:
        print("LOS BB shortcut: no calls recorded")


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Octile distance heuristic for 8-connected grid search."""
    return octile_distance(a, b)


def _line_of_sight(
    p1: tuple[int, int], p2: tuple[int, int], grid, net_id: int,
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
    bbox = grid.grid[min(y0, y1):max(y0, y1) + 1, min(x0, x1):max(x0, x1) + 1]
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


def _astar_search_lazy_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
) -> list[tuple[int, int]] | None:
    """
    Lazy Theta* pathfinding.

    Optimizes Theta* by delaying the line-of-sight check until a node is expanded.
    This significantly reduces the number of geometric checks.

    Args:
        grid: Occupancy grid
        start_grid: Start position (grid coordinates)
        goal_grid: Goal position (grid coordinates)
        net_id: Net ID for unblocking own cells
        came_from_init: Optional initial came_from for warm-starting
        max_iter: Maximum node expansions before returning None (safety net).
            Default ``None`` = unlimited (backward-compatible).

    Returns:
        Path as list of (x, y) grid cells, or None if no path
    """
    import math
    from heapq import heappop, heappush

    if enable_numba_los:
        from temper_placer.router_v6.astar_core_numba import _line_of_sight_numba
        los_fn = _line_of_sight_numba
    else:
        los_fn = _line_of_sight

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set: list = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            # Handle start node case (came_from[start] not in came_from)
            if current == start_grid:
                break
            path.append(current)
        path.reverse()
        return path

    while open_set:
        f_cost, _, current = heappop(open_set)

        if current in closed_set:
            continue

        # LAZY CHECK: Validate LOS only when expanding
        parent = came_from.get(current)

        # Runtime monitor: f-cost monotonicity for Lazy Theta*
        _mon_lazy = get_monitor_state()
        if _mon_lazy is not None:
            _mon_lazy.record_pop(current, float(f_cost))
        if parent and not los_fn(parent, current, grid, net_id):
            # LOS Failed.
            # Standard Lazy Theta* strategy: find a valid parent from closed neighbors
            # This is "Vertex A adjustment" from the paper.
            # However, since we populate using optimistic parents, the 'current'
            # node might not have a valid parent in the closed set that reaches it
            # directly via LOS.
            # Simplified strategy: If LOS from parent fails, treat it as an A* node
            # (but we didn't store the A* parent).
            # Re-evaluate parent from neighbors in closed set.

            best_parent = None
            best_g = float("inf")

            # Check 8-connected neighbors
            cx, cy = current
            for dx, dy in _SAME_LAYER_DELTAS:
                nx, ny = cx + dx, cy + dy
                neighbor = (nx, ny)

                if neighbor in closed_set and neighbor in g_score:
                    # Cost is just distance (1 or 1.414)
                    step_cost = euclidean_dist(neighbor, current)
                    new_g = g_score[neighbor] + step_cost
                    if new_g < best_g:
                        best_g = new_g
                        best_parent = neighbor

            if best_parent:
                came_from[current] = best_parent
                g_score[current] = best_g
                # Continue expansion with corrected parent
            else:
                # Should not happen if we reached 'current'
                continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        if max_iter is not None and len(closed_set) >= max_iter:
            return None

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in _SAME_LAYER_DELTAS:
            nx, ny = cx + dx, cy + dy
            if in_bounds(nx, ny, grid.width_cells, grid.height_cells):
                cell_value = grid.grid[ny, nx]
                if cell_value == 0 or cell_value == net_id:
                    neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # LAZY OPTIMIZATION: Always assume LOS from parent(current) to neighbor
            # This makes the "parent" pointer jump multiple steps.
            # parent(neighbor) = parent(current)

            grandparent = came_from.get(current)

            # Path 1: Optimistic (grandparent -> neighbor)
            if grandparent:
                tentative_g_lazy = g_score[grandparent] + euclidean_dist(grandparent, neighbor)
                path_source_lazy = grandparent
            else:
                # Start node has no parent
                tentative_g_lazy = float("inf")
                path_source_lazy = None

            # Path 2: A* (current -> neighbor) - always valid if adjacent
            tentative_g_astar = g_score[current] + euclidean_dist(current, neighbor)

            # Choose best (usually optimistic)
            # Standard Lazy Theta* typically just picks the optimistic one if better.
            # But we must ensure g-values are consistent.

            if grandparent and tentative_g_lazy < tentative_g_astar:
                tentative_g = tentative_g_lazy
                path_source = path_source_lazy
            else:
                tentative_g = tentative_g_astar
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                f_score = tentative_g + euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None


def _astar_search_theta_star(
    grid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    max_iter: int | None = None,
) -> list[tuple[int, int]] | None:
    """
    Theta* pathfinding with any-angle paths.

    Key difference from A*: When expanding a neighbor, checks if parent
    of current has line-of-sight to neighbor. If yes, connects parent
    directly to neighbor (skipping current), creating diagonal shortcuts.

    Args:
        grid: Occupancy grid
        start_grid: Start position (grid coordinates)
        goal_grid: Goal position (grid coordinates)
        net_id: Net ID for unblocking own cells
        came_from_init: Optional initial came_from for warm-starting
        max_iter: Maximum node expansions before returning None (safety net).
            Default ``None`` = unlimited (backward-compatible).

    Returns:
        Path as list of (x, y) grid cells, or None if no path
    """
    import math
    from heapq import heappop, heappush

    if enable_numba_los:
        from temper_placer.router_v6.astar_core_numba import _line_of_sight_numba
        los_fn = _line_of_sight_numba
    else:
        los_fn = _line_of_sight

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set: list = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    while open_set:
        _, _, current = heappop(open_set)

        if current in closed_set:
            continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        if max_iter is not None and len(closed_set) >= max_iter:
            return None

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in _SAME_LAYER_DELTAS:
            nx, ny = cx + dx, cy + dy
            if in_bounds(nx, ny, grid.width_cells, grid.height_cells):
                cell_value = grid.grid[ny, nx]
                if cell_value == 0 or cell_value == net_id:
                    neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # THETA* OPTIMIZATION: Check line-of-sight from parent
            parent = came_from.get(current)
            if parent and los_fn(parent, neighbor, grid, net_id):
                # Path 2: parent -> neighbor (shortcut)
                tentative_g = g_score[parent] + euclidean_dist(parent, neighbor)
                path_source = parent
            else:
                # Path 1: current -> neighbor (standard A*)
                tentative_g = g_score[current] + euclidean_dist(current, neighbor)
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                f_score = tentative_g + euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None  # No path found


def _astar_search_3d(
    start: RouteNode3D,
    goal: RouteNode3D,
    grids: dict,
    via_cost: float = 10.0,
    via_diameter: float = 0.6,
    clearance: float = 0.2,
    net_id: int = 0,
) -> tuple[list, list[tuple[int, int]]] | None:
    """
    3D A* search with layer transitions (via insertion).

    Via insertion is a valid move with associated cost. This allows
    routing to escape congestion by switching layers.

    After path is found, vias are blocked on ALL layers they span.

    Args:
        start: Start node (x, y, layer)
        goal: Goal node (x, y, layer)
        grids: Dictionary of OccupancyGrid per layer
        via_cost: Cost multiplier for layer transitions (default 10x step)
        via_diameter: Via annular ring diameter in mm
        clearance: Via clearance in mm
        net_id: Net ID for blocking

    Returns:
        (path, via_positions) or None if no path found
        - path: List of RouteNode3D
        - via_positions: List of (x, y) where layer changes occur
    """
    from heapq import heappop, heappush

    # Validate layers exist
    if start.layer not in grids or goal.layer not in grids:
        return None

    # Available layers for transitions (dynamic from grids)
    # Prefer standard PCB layer order if possible
    standard_order = [str(idx) for idx in STANDARD_LAYER_ORDER]
    available_layers = [layer for layer in standard_order if layer in grids]
    # Add any non-standard layers from grids
    for layer in grids:
        if layer not in available_layers:
            available_layers.append(layer)

    # A* frontier: (priority, node)
    frontier: list = []
    heappush(frontier, (0, (start.x, start.y, start.layer)))

    # Tracking
    came_from: dict[tuple[int, int, str], tuple[int, int, str] | None] = {
        (start.x, start.y, start.layer): None
    }
    cost_so_far: dict[tuple[int, int, str], float] = {(start.x, start.y, start.layer): 0}

    goal_key = (goal.x, goal.y, goal.layer)

    while frontier:
        _, current_key = heappop(frontier)
        x, y, layer = current_key

        # Runtime monitor: f-cost monotonicity
        _mon_theta = get_monitor_state()
        if _mon_theta is not None:
            _mon_theta.record_pop((x, y), float(cost_so_far[current_key]))

        if current_key == goal_key:
            # Reconstruct path and find via positions
            path = []
            vias = []
            current = current_key
            prev_layer = None

            while current is not None:
                cx, cy, cl = current
                path.append(RouteNode3D(cx, cy, cl))

                # Detect layer transition
                if prev_layer is not None and prev_layer != cl:
                    vias.append((cx, cy))
                prev_layer = cl

                current = came_from[current]

            # Block vias on ALL layers (they span the full stackup)
            if vias and net_id > 0:
                sample_grid = next(iter(grids.values()))
                for via_gx, via_gy in vias:
                    via_wx, via_wy = sample_grid.grid_to_world(via_gx, via_gy)
                    for layer_grid in grids.values():
                        layer_grid.mark_via_blocked(via_wx, via_wy, via_diameter, clearance, net_id)

            # Runtime monitor: validate path integrity
            if _mon_theta is not None:
                path_2d = [(node.x, node.y) for node in path]
                start_2d = (start.x, start.y)
                goal_2d = (goal.x, goal.y)
                # Check path adjacency and endpoint correctness
                _mon_theta.validate_path_completeness(path_2d, start_2d, goal_2d)

            return list(reversed(path)), vias

        grid = grids[layer]

        # Generate neighbors: 8-direction moves + layer transitions
        moves = []

        # Same-layer moves (8-connected)
        for dx, dy in _SAME_LAYER_DELTAS:
            nx, ny = x + dx, y + dy
            if grid.is_free(nx, ny):
                move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                moves.append(((nx, ny, layer), move_cost))

        # Layer transition moves (via insertion)
        for other_layer in available_layers:
            if other_layer != layer:
                other_grid = grids[other_layer]
                # Can place via if current cell is free on other layer
                if other_grid.is_free(x, y):
                    # Via cost discourages excessive transitions
                    moves.append(((x, y, other_layer), via_cost))

        for neighbor_key, move_cost in moves:
            new_cost = cost_so_far[current_key] + move_cost

            if neighbor_key not in cost_so_far or new_cost < cost_so_far[neighbor_key]:
                cost_so_far[neighbor_key] = new_cost
                # Heuristic: 2D distance to goal
                heuristic = _heuristic((neighbor_key[0], neighbor_key[1]), (goal.x, goal.y))
                # Add layer mismatch penalty
                if neighbor_key[2] != goal.layer:
                    heuristic += via_cost  # Will need at least one more via

                priority = new_cost + heuristic
                heappush(frontier, (priority, neighbor_key))
                came_from[neighbor_key] = current_key

    return None  # No path found


def _route_segment_3d(
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    start_layer: str,
    goal_layer: str,
    grids: dict,
    via_cost: float = 10.0,
) -> tuple[list[tuple[float, float, str]], list[tuple[float, float]]] | None:
    """
    Route a single segment using 3D A* with via insertion.

    IMPORTANT: Preserves exact start/goal positions (pad centers) in the final path.
    Only the bulk routing happens on-grid; fanout to pads is off-grid.

    Args:
        start_world: Start position in mm (x, y) - exact pad center
        goal_world: Goal position in mm (x, y) - exact pad center
        start_layer: Starting layer name
        goal_layer: Goal layer name
        grids: Dictionary of OccupancyGrid per layer
        via_cost: Cost for layer transitions

    Returns:
        (world_path, via_positions) or None
        - world_path: List of (x, y, layer) in ABSOLUTE board coordinates
        - via_positions: List of (x, y) where vias are placed
    """
    if not grids:
        return None

    # Get a grid for coordinate conversion
    sample_grid = next(iter(grids.values()))

    # Find nearest grid cells to start/goal (for bulk routing)
    start_grid = sample_grid.world_to_grid(start_world[0], start_world[1])
    goal_grid = sample_grid.world_to_grid(goal_world[0], goal_world[1])

    # Bounds check
    for _layer, grid in grids.items():
        if not in_bounds(start_grid[0], start_grid[1], grid.width_cells, grid.height_cells):
            continue
        if not in_bounds(goal_grid[0], goal_grid[1], grid.width_cells, grid.height_cells):
            continue

    start_node = RouteNode3D(start_grid[0], start_grid[1], start_layer)
    goal_node = RouteNode3D(goal_grid[0], goal_grid[1], goal_layer)

    result = _astar_search_3d(start_node, goal_node, grids, via_cost)

    if result is None:
        return None

    path_nodes, via_grid_positions = result

    # Convert bulk path to world coordinates (grid-to-world conversion)
    bulk_path = []
    for node in path_nodes:
        grid = grids[node.layer]
        world_x, world_y = grid.grid_to_world(node.x, node.y)
        bulk_path.append((world_x, world_y, node.layer))

    # **KEY FIX**: Replace first and last points with exact pad positions
    # This ensures routes connect directly to pad centers, not grid-snapped approximations
    world_path = []

    if len(bulk_path) > 0:
        # Start with exact pad center
        world_path.append((start_world[0], start_world[1], start_layer))

        # Add bulk path (excluding first and last if they're the same as pads)
        # Keep middle segments
        if len(bulk_path) > 2:
            world_path.extend(bulk_path[1:-1])

        # End with exact pad center (if different from start)
        if len(bulk_path) == 1:
            # Single-cell path: just start and end at pads
            if (start_world[0], start_world[1]) != (goal_world[0], goal_world[1]):
                world_path.append((goal_world[0], goal_world[1], goal_layer))
        else:
            world_path.append((goal_world[0], goal_world[1], goal_layer))

    via_world_positions = []
    for gx, gy in via_grid_positions:
        wx, wy = sample_grid.grid_to_world(gx, gy)
        via_world_positions.append((wx, wy))

    return world_path, via_world_positions
