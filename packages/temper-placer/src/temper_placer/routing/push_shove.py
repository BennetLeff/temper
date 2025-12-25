"""
Push-and-shove router with functional state management.

This module implements a push-and-shove router using:
- Immutable Grid and Path dataclasses
- Signed Distance Functions (SDF) for collision detection
- A* pathfinding with functional state
- Push/shove operations that return new state

The router is designed for PCB trace routing with the ability to
push existing traces aside to make room for new connections.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from heapq import heappop, heappush

import jax.numpy as jnp

from temper_placer.routing.heuristics import GridCell, manhattan_heuristic

# =============================================================================
# Core Data Structures
# =============================================================================


@dataclass(frozen=True)
class Segment:
    """Immutable path segment from start to end."""

    start: tuple[float, float]
    end: tuple[float, float]

    def __hash__(self):
        return hash((self.start, self.end))


@dataclass(frozen=True)
class Path:
    """Immutable path representation with segments, width, and clearance."""

    segments: tuple[Segment, ...]  # Tuple for immutability and hashing
    width: float  # Trace width in mm
    clearance: float  # Clearance around trace in mm
    net: str  # Net name

    def __init__(self, segments, width, clearance, net):
        # Convert list to tuple for immutability
        if isinstance(segments, list):
            segments = tuple(segments)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "clearance", clearance)
        object.__setattr__(self, "net", net)

    def __hash__(self):
        return hash((self.segments, self.width, self.clearance, self.net))


@dataclass(frozen=True)
class Grid:
    """Immutable routing grid with occupancy state."""

    width: int  # Grid width in cells
    height: int  # Grid height in cells
    layers: int  # Number of routing layers
    occupancy: jnp.ndarray = field(default=None, compare=False)
    path_map: dict[tuple[int, int, int], str] = field(default_factory=dict)

    def __init__(self, width, height, layers, occupancy=None, path_map=None):
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "layers", layers)

        if occupancy is None:
            occupancy = jnp.zeros((width, height, layers), dtype=jnp.int32)
        object.__setattr__(self, "occupancy", occupancy)

        if path_map is None:
            path_map = {}
        object.__setattr__(self, "path_map", path_map)

    def with_obstacle(self, cell: GridCell) -> "Grid":
        """Return new grid with obstacle at cell."""
        new_occupancy = self.occupancy.at[cell.x, cell.y, cell.layer].set(1)
        return Grid(self.width, self.height, self.layers, new_occupancy, self.path_map)

    def with_path(self, cell: GridCell, net: str) -> "Grid":
        """Return new grid with path at cell."""
        new_occupancy = self.occupancy.at[cell.x, cell.y, cell.layer].set(2)
        new_path_map = dict(self.path_map)
        new_path_map[(cell.x, cell.y, cell.layer)] = net
        return Grid(self.width, self.height, self.layers, new_occupancy, new_path_map)

    def without_path(self, cell: GridCell) -> "Grid":
        """Return new grid with path removed from cell."""
        new_occupancy = self.occupancy.at[cell.x, cell.y, cell.layer].set(0)
        new_path_map = dict(self.path_map)
        new_path_map.pop((cell.x, cell.y, cell.layer), None)
        return Grid(self.width, self.height, self.layers, new_occupancy, new_path_map)


@dataclass(frozen=True)
class PathResult:
    """Result of pathfinding operation."""

    success: bool
    path: list[GridCell]
    cost: float = 0.0

    def __init__(self, success, path, cost=0.0):
        object.__setattr__(self, "success", success)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "cost", cost)


@dataclass(frozen=True)
class ShoveResult:
    """Result of shove operation."""

    success: bool
    paths: list[Path]
    iterations: int = 0

    def __init__(self, success, paths, iterations=0):
        object.__setattr__(self, "success", success)
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "iterations", iterations)


# =============================================================================
# Pure Grid Query Functions
# =============================================================================


def get_cell(grid: Grid, pos: tuple[int, int], layer: int = 0) -> GridCell:
    """Get grid cell at position (pure function)."""
    return GridCell(pos[0], pos[1], layer)


def is_occupied(grid: Grid, pos: tuple[int, int], layer: int = 0) -> bool:
    """Check if cell is occupied (pure function)."""
    x, y = pos

    # Out of bounds is treated as occupied
    if not (0 <= x < grid.width and 0 <= y < grid.height):
        return True

    return int(grid.occupancy[x, y, layer]) != 0


def get_neighbors(grid: Grid, cell: GridCell, allow_layer_change: bool = True) -> list[GridCell]:
    """Get valid neighbor cells (pure function)."""
    neighbors = []

    # 4-connected neighbors on same layer
    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
        nx, ny = cell.x + dx, cell.y + dy
        if 0 <= nx < grid.width and 0 <= ny < grid.height:
            if not is_occupied(grid, (nx, ny), cell.layer):
                neighbors.append(GridCell(nx, ny, cell.layer))

    # Layer changes (vias)
    if allow_layer_change and grid.layers > 1:
        for layer in range(grid.layers):
            if layer != cell.layer:
                if not is_occupied(grid, (cell.x, cell.y), layer):
                    neighbors.append(GridCell(cell.x, cell.y, layer))

    return neighbors


# =============================================================================
# A* Pathfinding
# =============================================================================


def find_path(
    grid: Grid, start: GridCell, end: GridCell, allow_layer_change: bool = False
) -> PathResult:
    """
    Find path using A* algorithm (functional, returns new PathResult).

    Args:
        grid: Current grid state
        start: Start cell
        end: End cell
        allow_layer_change: Whether to allow vias

    Returns:
        PathResult with success flag and path
    """
    # Priority queue: (f_score, counter, current, g_score)
    counter = 0
    open_set = [(0.0, counter, start, 0.0)]
    closed_set: set[GridCell] = set()
    came_from: dict[GridCell, GridCell] = {}
    g_score: dict[GridCell, float] = {start: 0.0}

    while open_set:
        _, _, current, current_g = heappop(open_set)

        if current in closed_set:
            continue

        if current == end:
            # Reconstruct path
            path = []
            node = current
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.append(start)
            path.reverse()
            return PathResult(success=True, path=path, cost=current_g)

        closed_set.add(current)

        # Explore neighbors
        for neighbor in get_neighbors(grid, current, allow_layer_change):
            if neighbor in closed_set:
                continue

            # Cost: 1.0 for movement, 10.0 for via
            move_cost = 10.0 if neighbor.layer != current.layer else 1.0
            tentative_g = current_g + move_cost

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + manhattan_heuristic(neighbor, end)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor, tentative_g))

    # No path found
    return PathResult(success=False, path=[])


# =============================================================================
# SDF (Signed Distance Function) for Collision Detection
# =============================================================================


def segment_sdf(point: tuple[float, float], seg: Segment, radius: float) -> float:
    """
    Signed distance from point to line segment with radius.

    Negative = inside, zero = on boundary, positive = outside.
    """
    px, py = point
    ax, ay = seg.start
    bx, by = seg.end

    # Vector from A to B
    bax = bx - ax
    bay = by - ay

    # Vector from A to point
    pax = px - ax
    pay = py - ay

    # Project point onto line AB
    ba_length_sq = bax * bax + bay * bay

    if ba_length_sq < 1e-10:
        # Degenerate segment (point)
        dist = math.sqrt(pax * pax + pay * pay)
        return dist - radius

    t = (pax * bax + pay * bay) / ba_length_sq
    t = max(0.0, min(1.0, t))  # Clamp to segment

    # Closest point on segment
    closest_x = ax + t * bax
    closest_y = ay + t * bay

    # Distance to closest point
    dx = px - closest_x
    dy = py - closest_y
    dist = math.sqrt(dx * dx + dy * dy)

    return dist - radius


def to_sdf(path: Path) -> Callable[[tuple[float, float]], float]:
    """
    Convert path to signed distance function.

    Returns a function that computes SDF at any point.
    """
    # Total radius = width/2 + clearance/2
    radius = (path.width + path.clearance) / 2.0

    def sdf_func(point: tuple[float, float]) -> float:
        """SDF function for this path."""
        # Union of all segments (min distance)
        min_dist = float("inf")
        for seg in path.segments:
            dist = segment_sdf(point, seg, radius)
            min_dist = min(min_dist, dist)
        return min_dist

    return sdf_func


def detect_collision(path1: Path, path2: Path, num_samples: int = 21) -> bool:
    """
    Detect collision between two paths using SDF sampling.

    Args:
        path1: First path
        path2: Second path
        num_samples: Number of sample points per segment

    Returns:
        True if paths collide (violate clearance)
    """
    # Same net = no collision
    if path1.net == path2.net:
        return False

    # Total required separation between center lines
    # (W1/2 + C1/2) + (W2/2 + C2/2)
    required_dist = (path1.width + path1.clearance + path2.width + path2.clearance) / 2.0

    # Sample points along path2 and check against path1's segments
    for seg2 in path2.segments:
        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0.5
            px = seg2.start[0] + t * (seg2.end[0] - seg2.start[0])
            py = seg2.start[1] + t * (seg2.end[1] - seg2.start[1])

            # Check distance to all segments in path1
            for seg1 in path1.segments:
                # Segment SDF with 0 radius gives distance to segment
                dist = segment_sdf((px, py), seg1, 0.0)
                if dist < required_dist - 1e-6:  # Small epsilon for stability
                    return True

    # Sample points along path1 and check against path2's segments
    for seg1 in path1.segments:
        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0.5
            px = seg1.start[0] + t * (seg1.end[0] - seg1.start[0])
            py = seg1.start[1] + t * (seg1.end[1] - seg1.start[1])

            for seg2 in path2.segments:
                dist = segment_sdf((px, py), seg2, 0.0)
                if dist < required_dist - 1e-6:
                    return True

    return False


# =============================================================================
# Push and Shove Operations
# =============================================================================


def push_path(
    path: Path,
    direction: tuple[float, float],
    distance: float,
    preserve_endpoints: bool = True,
) -> Path:
    """
    Push path in direction by distance (returns new Path).

    Args:
        path: Original path
        direction: Normalized direction vector
        distance: Distance to push
        preserve_endpoints: If True, keep first segment's start and last segment's
            end fixed at original positions (pad locations). Adds transition
            segments to reconnect pushed middle portion. Defaults to True.

    Returns:
        New path pushed by distance, with endpoints preserved if requested
    """
    dx = direction[0] * distance
    dy = direction[1] * distance

    segments = list(path.segments)
    n = len(segments)

    if not preserve_endpoints or n == 0:
        # Simple case: push everything (backwards compatibility)
        new_segments = [
            Segment(
                (seg.start[0] + dx, seg.start[1] + dy),
                (seg.end[0] + dx, seg.end[1] + dy),
            )
            for seg in segments
        ]
    elif n == 1:
        # Single segment: keep both endpoints fixed, insert pushed middle point
        seg = segments[0]
        start_anchor = seg.start
        end_anchor = seg.end

        # Compute midpoint and push it
        mid_x = (seg.start[0] + seg.end[0]) / 2 + dx
        mid_y = (seg.start[1] + seg.end[1]) / 2 + dy
        mid_pushed = (mid_x, mid_y)

        # Create two segments: start->mid, mid->end
        new_segments = [
            Segment(start_anchor, mid_pushed),
            Segment(mid_pushed, end_anchor),
        ]
    else:
        # Multi-segment path: preserve first start and last end
        start_anchor = segments[0].start  # First pad location
        end_anchor = segments[-1].end  # Last pad location

        new_segments = []

        # First segment: anchor start, push end
        first_seg = segments[0]
        pushed_first_end = (first_seg.end[0] + dx, first_seg.end[1] + dy)
        new_segments.append(Segment(start_anchor, pushed_first_end))

        # Middle segments: push both endpoints
        for i in range(1, n - 1):
            seg = segments[i]
            new_start = (seg.start[0] + dx, seg.start[1] + dy)
            new_end = (seg.end[0] + dx, seg.end[1] + dy)
            new_segments.append(Segment(new_start, new_end))

        # Last segment: push start, anchor end
        last_seg = segments[-1]
        pushed_last_start = (last_seg.start[0] + dx, last_seg.start[1] + dy)
        new_segments.append(Segment(pushed_last_start, end_anchor))

    return Path(
        segments=tuple(new_segments), width=path.width, clearance=path.clearance, net=path.net
    )


def compute_push_direction(path: Path, new_path: Path) -> tuple[float, float]:
    """
    Compute direction to push path away from new_path.

    Returns normalized direction vector.
    """
    # Use midpoint of first segment
    seg1 = path.segments[0]
    seg2 = new_path.segments[0]

    # Centers of segments
    c1x = (seg1.start[0] + seg1.end[0]) / 2.0
    c1y = (seg1.start[1] + seg1.end[1]) / 2.0
    c2x = (seg2.start[0] + seg2.end[0]) / 2.0
    c2y = (seg2.start[1] + seg2.end[1]) / 2.0

    # Direction from new_path to path
    dx = c1x - c2x
    dy = c1y - c2y

    # Normalize
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        # Default to upward
        return (0.0, 1.0)

    return (dx / length, dy / length)


def shove_paths(
    existing_paths: list[Path],
    new_path: Path,
    board_bounds: tuple[float, float] | None = None,
    max_iterations: int = 10,
) -> ShoveResult:
    """
    Shove existing paths to make room for new path.

    Args:
        existing_paths: Paths that may need shoving
        new_path: New path to route
        board_bounds: Optional (width, height) board bounds
        max_iterations: Maximum shove iterations

    Returns:
        ShoveResult with success flag and updated paths
    """
    current_paths = list(existing_paths)

    for iteration in range(max_iterations):
        colliding_indices = []

        # Find colliding paths
        for i, path in enumerate(current_paths):
            if detect_collision(path, new_path):
                colliding_indices.append(i)

        # If no collisions, success
        if not colliding_indices:
            return ShoveResult(success=True, paths=current_paths, iterations=iteration)

        # Shove colliding paths
        for i in colliding_indices:
            path = current_paths[i]

            # Compute push direction
            direction = compute_push_direction(path, new_path)

            # Minimum push distance = clearance requirement
            min_distance = (
                path.width + path.clearance + new_path.width + new_path.clearance
            ) / 2.0 + 1e-3

            # Push by minimum distance
            pushed_path = push_path(path, direction, min_distance)

            # Check if pushed path is within bounds
            if board_bounds is not None:
                width, height = board_bounds
                valid = True
                for seg in pushed_path.segments:
                    if (
                        seg.start[0] < 0
                        or seg.start[0] > width
                        or seg.start[1] < 0
                        or seg.start[1] > height
                        or seg.end[0] < 0
                        or seg.end[0] > width
                        or seg.end[1] < 0
                        or seg.end[1] > height
                    ):
                        valid = False
                        break

                if not valid:
                    # Cannot shove - would go out of bounds
                    return ShoveResult(success=False, paths=existing_paths, iterations=iteration)

            current_paths[i] = pushed_path

    # Max iterations exceeded
    return ShoveResult(success=False, paths=existing_paths, iterations=max_iterations)


# =============================================================================
# Convenience Functions
# =============================================================================


def grid_from_paths(
    width: int, height: int, layers: int, paths: list[Path], cell_size: float = 1.0
) -> Grid:
    """
    Create grid from existing paths.

    Args:
        width: Grid width in cells
        height: Grid height in cells
        layers: Number of layers
        paths: Existing paths to mark as occupied
        cell_size: Size of each grid cell in mm

    Returns:
        Grid with paths marked as occupied
    """
    grid = Grid(width, height, layers)

    # Mark cells occupied by paths
    for path in paths:
        for seg in path.segments:
            # Sample segment and mark grid cells
            num_samples = (
                int(
                    math.ceil(
                        math.sqrt(
                            (seg.end[0] - seg.start[0]) ** 2 + (seg.end[1] - seg.start[1]) ** 2
                        )
                        / cell_size
                    )
                )
                + 1
            )

            for i in range(num_samples):
                t = i / max(1, num_samples - 1)
                x = seg.start[0] + t * (seg.end[0] - seg.start[0])
                y = seg.start[1] + t * (seg.end[1] - seg.start[1])

                # Convert to grid coordinates
                gx = int(x / cell_size)
                gy = int(y / cell_size)

                if 0 <= gx < width and 0 <= gy < height:
                    grid = grid.with_path(GridCell(gx, gy, 0), path.net)

    return grid
