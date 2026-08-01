"""
Router V6: A* search algorithms and shared route dataclasses.

Part of temper-N6-U6 decomposition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

import numpy as np

from temper_placer.core.board import STANDARD_LAYER_ORDER

# Lazy-import at module level so the A* inner loop doesn't pay import cost
from temper_placer.router_v6.astar_monitor import get_monitor_state  # noqa: E402

# A* search primitives (formerly in routing/heuristics.py)
OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0

# Configurable diagonal cost multiplier for the A* inner loop.
# 1.0 = standard octile (diagonal  1.414, cardinal  1.0).
# Lower values incentivise diagonals.  Set via
# :func:`temper_placer.router_v6.metrics.octilinear.add_diagonal_incentive`.
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


def _astar_search_3d(
    start: RouteNode3D,
    goal: RouteNode3D,
    grids: dict,
    via_cost: float = 10.0,
    via_diameter: float = 0.6,
    clearance: float = 0.2,
    net_id: int = 0,
    max_iter: int | None = None,
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
        net_id: Net ID for blocking. Also gates via-blocking: vias are
            only marked on the occupancy grid via ``mark_via_blocked()``
            when ``net_id > 0`` (see the loop body below) -- callers that
            want the search's own via placements to be protected against
            a later, different net's search MUST pass a real net_id, not
            the default 0.
        max_iter: Maximum frontier pops before giving up and returning
            None (safety net). Default ``None`` = unlimited
            (backward-compatible), mirroring ``_astar_search_theta_star``/
            ``_astar_search_lazy_theta_star``'s ``max_iter`` semantics.
            U1's production-scale spike (see
            ``test_astar_3d_production_scale_spike.py``) measured up to
            66s wall time on a degenerate long-distance segment with no
            cap -- callers that may hit pathological/unreachable
            segments (e.g. the fallback-tier call site in
            ``_astar_route_multilayer``) should pass an explicit bound.

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

    # U2 fix (docs/plans/2026-07-18-003-*): iteration safety valve.
    # Unlike the Theta*/Lazy Theta* variants, this search has no
    # closed-set-based expansion count -- count frontier pops instead,
    # which is a reasonable proxy for wall time given the per-pop work
    # below (neighbor generation over up to len(available_layers) grids).
    iterations = 0

    while frontier:
        iterations += 1
        if max_iter is not None and iterations > max_iter:
            return None

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
                move_cost = (
                    DIAGONAL_COST_FACTOR * _BASE_DIAGONAL_COST if dx != 0 and dy != 0 else 1.0
                )
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


# U2 fix (docs/plans/2026-07-18-003-*, informed by U1's spike): a sane,
# non-None default iteration cap for ``_route_segment_3d``. This function
# had zero production callers before U2, so changing its default from
# "unbounded" to "bounded" is not a behavior change for any existing
# caller -- it only affects the new fallback-tier call site (and any
# direct test call that doesn't override it). U1 measured short
# (waypoint-scale) fallback-tier calls completing in well under 1ms
# (tens to low hundreds of iterations); 200_000 leaves 3+ orders of
# magnitude of headroom for that call pattern while still bounding a
# pathological/unreachable segment's wall time to a small multiple of a
# second rather than U1's observed unbounded 66s worst case.
_ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER: Final[int] = 200_000


def _route_segment_3d(
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    start_layer: str,
    goal_layer: str,
    grids: dict,
    via_cost: float = 10.0,
    via_diameter: float = 0.6,
    clearance: float = 0.2,
    net_id: int = 0,
    max_iter: int | None = _ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER,
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
        via_diameter: Resolved netclass via diameter in mm used to reserve
            the candidate via's copper envelope on every spanned layer.
        clearance: Resolved netclass clearance in mm used with
            ``via_diameter`` when reserving that envelope.
        net_id: Net ID passed through to ``_astar_search_3d`` so any via
            placed by this call is actually blocked on the occupancy
            grid via ``mark_via_blocked()`` (which requires ``net_id >
            0``). U1's spike found this was previously silently dropped
            -- ``_astar_search_3d`` was always called with its
            ``net_id=0`` default, so via-blocking never fired through
            this entry point. Callers that want their via placements
            protected against a later net's search MUST pass a real
            (>0) net_id.
        max_iter: Maximum ``_astar_search_3d`` frontier pops before
            giving up (safety net against the 66s worst case U1
            measured). Defaults to ``_ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER``;
            pass ``None`` explicitly for the old unbounded behavior.

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

    result = _astar_search_3d(
        start_node,
        goal_node,
        grids,
        via_cost=via_cost,
        via_diameter=via_diameter,
        clearance=clearance,
        net_id=net_id,
        max_iter=max_iter,
    )

    if result is None:
        return None

    path_nodes, via_grid_positions = result

    # Convert bulk path to world coordinates (grid-to-world conversion)
    bulk_path = []
    for node in path_nodes:
        grid = grids[node.layer]
        world_x, world_y = grid.grid_to_world(node.x, node.y)
        bulk_path.append((world_x, world_y, node.layer))

    # Preserve the complete 3D bulk walk between exact pad anchors.  In
    # particular, do not discard the first or last bulk node: either can be
    # one half of a same-coordinate layer transition.  Removing it turns a
    # recorded via into an impossible cross-layer track at output time.
    # (``append_grid_path_point``/``append_exact_terminal_point`` only ever
    # merge same-layer points within grid quantization noise -- a real
    # layer transition, same (x, y) but different layer, is never merged.)
    tolerance = grid_quantization_tolerance(sample_grid.cell_size)
    world_path: list[tuple[float, float, str]] = []
    if bulk_path:
        world_path.append((start_world[0], start_world[1], start_layer))
        for point in bulk_path:
            append_grid_path_point(world_path, point, tolerance)

        goal_point = (goal_world[0], goal_world[1], goal_layer)
        append_exact_terminal_point(world_path, goal_point, tolerance)

    via_world_positions = []
    for gx, gy in via_grid_positions:
        wx, wy = sample_grid.grid_to_world(gx, gy)
        via_world_positions.append((wx, wy))

    return world_path, via_world_positions
