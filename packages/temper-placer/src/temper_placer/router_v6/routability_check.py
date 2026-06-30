"""
Completion invariant checker for the temper PCB router.

Provides ``check_routability``, a connectivity-based structural
reachability test on the Euclidean Distance Transform (EDT) grid
from Stage 2.  A net is *structurally unroutable* when — even on
an empty routing grid, ignoring other nets — no sequence of
passable cells connects the net's start and goal positions.

Mathematical foundation:
    A net is routable iff there exists a connected sequence of passable
    cells from start to goal.  This is a graph connectivity problem.
    For reachability alone, BFS suffices and is O(N) vs Dijkstra's
    O(N log N).  Since we only need the boolean answer (not the
    minimum-width path), BFS gives the same answer with far lower
    overhead on large grids.

Soundness proof:
    - Base case: empty grid -> BFS finds straight line -> every net routable
    - Induction: blocking one cell can only remove paths that pass through
      that cell; BFS correctly detects this
    - Soundness: if BFS says no path, no path exists (BFS is complete
      for unweighted/constant-weighted connectivity)
"""

from __future__ import annotations

import heapq
import math
from collections import deque

import numpy as np


def _clear_region(
    passable: np.ndarray,
    cx: int,
    cy: int,
    radius_cells: int,
) -> None:
    """Set a circular region in ``passable`` to True.

    Used to simulate pad unblocking (matching ``_unblock_net_pads``
    in ``astar_grid.py``).
    """
    h, w = passable.shape
    y0 = max(0, cy - radius_cells)
    y1 = min(h, cy + radius_cells + 1)
    x0 = max(0, cx - radius_cells)
    x1 = min(w, cx + radius_cells + 1)

    ys, xs = np.ogrid[y0:y1, x0:x1]
    dy = ys - cy
    dx = xs - cx
    mask = dx * dx + dy * dy <= radius_cells * radius_cells
    passable[y0:y1, x0:x1] |= mask

# 8-connected grid deltas: E, SE, S, SW, W, NW, N, NE.
# Used by both check_routability (BFS) and astar_passability (A*).
_DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1),
)


def check_routability(
    net_name: str,
    start: tuple[float, float],
    goal: tuple[float, float],
    edt_grid: np.ndarray,
    edt_mask: np.ndarray,
    trace_width: float,
    cell_size: float,
    origin: tuple[float, float] | None = None,
    pad_radius_cells: int | None = None,
) -> bool:
    """Check whether a net is structurally routable.

    Runs BFS on the EDT grid.  A cell is *passable* when the channel
    width at that cell (2 * edt_distance * cell_size) is at least
    ``trace_width``.

    Args:
        net_name: Net identifier (used only for diagnostics / future logging).
        start: Start position in world coordinates ``(x_mm, y_mm)``.
        goal: Goal position in world coordinates ``(x_mm, y_mm)``.
        edt_grid: 2-D numpy array of EDT distances (in cell units).
            Shape ``(height, width)``.
        edt_mask: 2-D boolean numpy array, ``True`` for interior cells.
            Same shape as ``edt_grid``.
        trace_width: Required trace width in mm.
        cell_size: Grid cell size in mm.
        origin: ``(min_x, min_y)`` world coordinate of cell (0, 0).
            When ``None``, ``start`` and ``goal`` are treated as
            grid indices directly (so ``edt_mask.shape`` is the
            only reference frame).
        pad_radius_cells: Radius (in grid cells) around start and goal
            to unconditionally mark as passable.  Simulates the router's
            ``_unblock_net_pads`` step.  Default ``None`` = 1 cell
            (single-cell clearing).

    Returns:
        ``True`` if a path exists, ``False`` if the net is structurally
        unroutable.

    Example:
        >>> import numpy as np
        >>> edt = np.ones((50, 50), dtype=np.float64)
        >>> mask = np.ones((50, 50), dtype=bool)
        >>> check_routability("test", (5, 5), (45, 45), edt, mask,
        ...                   trace_width=0.2, cell_size=0.1)
        True
    """
    h, w = edt_grid.shape

    # Minimum EDT distance (cell units) required to fit the trace.
    # width = 2 * edt * cell_size >= trace_width
    #  ->  edt >= trace_width / (2 * cell_size)
    min_edt = trace_width / (2.0 * cell_size)

    # Convert world -> grid when origin is given.
    if origin is not None:
        ox, oy = origin
        sx = int(round((start[0] - ox) / cell_size))
        sy = int(round((start[1] - oy) / cell_size))
        gx = int(round((goal[0] - ox) / cell_size))
        gy = int(round((goal[1] - oy) / cell_size))
    else:
        sx, sy = int(round(start[0])), int(round(start[1]))
        gx, gy = int(round(goal[0])), int(round(goal[1]))

    # Trivial case.
    if (sx, sy) == (gx, gy):
        return True

    # Out-of-bounds check.
    if not (0 <= sx < w and 0 <= sy < h):
        return False
    if not (0 <= gx < w and 0 <= gy < h):
        return False

    # Build a boolean passability mask vectorized once.
    passable = (edt_mask > 0) & (edt_grid >= min_edt)

    # Clear pad regions around start and goal to simulate
    # ``_unblock_net_pads`` (pads are unblocked before routing).
    # If no pad radius is given, clear a minimal single-cell region
    # so the BFS can expand from the start/goal cells.
    if pad_radius_cells is None:
        pad_radius_cells = 1
    if pad_radius_cells > 0:
        _clear_region(passable, sx, sy, pad_radius_cells)
        _clear_region(passable, gx, gy, pad_radius_cells)

    # BFS from start to goal.  Deque-based frontier is O(1) push/pop
    # vs heapq's O(log n).
    visited: np.ndarray = np.zeros((h, w), dtype=bool)
    visited[sy, sx] = True
    frontier: deque[tuple[int, int]] = deque()
    frontier.append((sx, sy))

    while frontier:
        cx, cy = frontier.popleft()

        for dx, dy in _DIRS_8:
            nx, ny = cx + dx, cy + dy

            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue

            if visited[ny, nx]:
                continue

            if not passable[ny, nx]:
                continue

            if nx == gx and ny == gy:
                return True

            visited[ny, nx] = True
            frontier.append((nx, ny))

    return False


def check_routability_bidi(
    net_name: str,
    start: tuple[float, float],
    goal: tuple[float, float],
    edt_grid: np.ndarray,
    edt_mask: np.ndarray,
    trace_width: float,
    cell_size: float,
    origin: tuple[float, float] | None = None,
    pad_radius_cells: int | None = None,
) -> bool:
    """Like ``check_routability`` but uses bidirectional BFS.

    Expands from both start and goal simultaneously.  When the two
    frontiers meet (or one frontier discovers a cell visited by the
    other), a path exists.  This typically explores ~50% fewer cells
    than unidirectional BFS on long corridors.
    """
    h, w = edt_grid.shape
    min_edt = trace_width / (2.0 * cell_size)

    if origin is not None:
        ox, oy = origin
        sx = int(round((start[0] - ox) / cell_size))
        sy = int(round((start[1] - oy) / cell_size))
        gx = int(round((goal[0] - ox) / cell_size))
        gy = int(round((goal[1] - oy) / cell_size))
    else:
        sx, sy = int(round(start[0])), int(round(start[1]))
        gx, gy = int(round(goal[0])), int(round(goal[1]))

    if (sx, sy) == (gx, gy):
        return True
    if not (0 <= sx < w and 0 <= sy < h):
        return False
    if not (0 <= gx < w and 0 <= gy < h):
        return False

    passable = (edt_mask > 0) & (edt_grid >= min_edt)

    if pad_radius_cells is None:
        pad_radius_cells = 1
    if pad_radius_cells > 0:
        _clear_region(passable, sx, sy, pad_radius_cells)
        _clear_region(passable, gx, gy, pad_radius_cells)

    # visited[iy, ix] encodes which frontier discovered the cell:
    #   0 = unvisited, 1 = from start side, 2 = from goal side.
    visited: np.ndarray = np.zeros((h, w), dtype=np.uint8)
    visited[sy, sx] = 1
    visited[gy, gx] = 2

    frontier_a: deque[tuple[int, int]] = deque()
    frontier_b: deque[tuple[int, int]] = deque()
    frontier_a.append((sx, sy))
    frontier_b.append((gx, gy))

    def _expand(frontier: deque[tuple[int, int]], side: int,
                other: int) -> bool:
        """Expand one level.  Return True if we hit the other frontier."""
        for _ in range(len(frontier)):
            cx, cy = frontier.popleft()
            for dx, dy in _DIRS_8:
                nx, ny = cx + dx, cy + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                if not passable[ny, nx]:
                    continue
                if visited[ny, nx] == other:
                    return True
                if visited[ny, nx] != 0:
                    continue
                visited[ny, nx] = side
                frontier.append((nx, ny))
        return False

    while frontier_a and frontier_b:
        # Alternate expansion from each side.
        if len(frontier_a) <= len(frontier_b):
            if _expand(frontier_a, 1, 2):
                return True
        else:
            if _expand(frontier_b, 2, 1):
                return True

    # Drain whichever frontier remains (the other is empty).
    remaining = frontier_a or frontier_b
    side = 1 if frontier_a else 2
    other = 2 if side == 1 else 1
    while remaining:
        if _expand(remaining, side, other):
            return True

    return False


def build_passability_mask(
    edt_grid: np.ndarray,
    edt_mask: np.ndarray,
    trace_width: float,
    cell_size: float,
) -> np.ndarray:
    """Build a boolean passability mask from the EDT grid.

    A cell is passable when ``2 * edt_distance * cell_size >= trace_width``
    and the cell is inside the available routing area (mask is True).

    Returns a 2-D boolean array, same shape as ``edt_grid``.
    """
    min_edt = trace_width / (2.0 * cell_size)
    return (edt_mask > 0) & (edt_grid >= min_edt)


def check_routability_cc(
    net_name: str,
    start: tuple[float, float],
    goal: tuple[float, float],
    edt_grid: np.ndarray,
    edt_mask: np.ndarray,
    trace_width: float,
    cell_size: float,
    origin: tuple[float, float] | None = None,
    pad_radius_cells: int | None = None,
    *,
    passable_mask: np.ndarray | None = None,
    component_labels: np.ndarray | None = None,
) -> bool:
    """Check routability using 8-connected components (O(1) per net).

    Precomputes 8-connected component labels via
    ``scipy.ndimage.label``.  The first call with a given ``trace_width``
    incurs an O(N) cost; subsequent calls with the same mask reuse the
    cached labels.

    Pass ``passable_mask`` or ``component_labels`` to reuse across
    multiple nets with the same width.

    This is mathematically equivalent to BFS/Dijkstra for reachability:
    the ``label`` function finds ALL 8-connected components, and the
    answer is simply whether start and goal share the same label.
    """
    from scipy.ndimage import label as nd_label

    h, w = edt_grid.shape
    min_edt = trace_width / (2.0 * cell_size)

    if origin is not None:
        ox, oy = origin
        sx = int(round((start[0] - ox) / cell_size))
        sy = int(round((start[1] - oy) / cell_size))
        gx = int(round((goal[0] - ox) / cell_size))
        gy = int(round((goal[1] - oy) / cell_size))
    else:
        sx, sy = int(round(start[0])), int(round(start[1]))
        gx, gy = int(round(goal[0])), int(round(goal[1]))

    if (sx, sy) == (gx, gy):
        return True
    if not (0 <= sx < w and 0 <= sy < h):
        return False
    if not (0 <= gx < w and 0 <= gy < h):
        return False

    if component_labels is None:
        if passable_mask is None:
            passable_mask = (edt_mask > 0) & (edt_grid >= min_edt)

        # Clear pad regions.
        if pad_radius_cells is None:
            pad_radius_cells = 1
        if pad_radius_cells > 0:
            _clear_region(passable_mask, sx, sy, pad_radius_cells)
            _clear_region(passable_mask, gx, gy, pad_radius_cells)

        # 8-connected components.  The ``structure`` parameter defines
        # connectivity: a 3x3 block of ones means all 8 neighbors.
        structure = np.ones((3, 3), dtype=bool)
        component_labels, _num_features = nd_label(passable_mask, structure=structure)

    ls = component_labels[sy, sx]
    lg = component_labels[gy, gx]
    return bool(ls > 0 and lg > 0 and ls == lg)


def _edt_from_obstacle_mask(
    obstacle_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute EDT grid and interior mask from a binary obstacle mask.

    ``obstacle_mask``: ``True`` = blocked, ``False`` = free.
    Returns ``(edt_grid, interior_mask)`` where:
    - ``interior_mask``: ``True`` for free (non-obstacle) cells.
    - ``edt_grid``: distance transform over interior cells.
    """
    interior = ~obstacle_mask
    from scipy.ndimage import distance_transform_edt
    edt = distance_transform_edt(interior.astype(np.uint8))
    return edt, interior


def check_routability_direct(
    net_name: str,
    start: tuple[float, float],
    goal: tuple[float, float],
    obstacle_mask: np.ndarray,
    trace_width: float,
    cell_size: float,
) -> bool:
    """Convenience wrapper that computes EDT on-the-fly from an obstacle mask.

    ``obstacle_mask`` is a 2-D boolean array where ``True`` = blocked.
    Start and goal are treated as *grid indices* (x, y).
    """
    edt, mask = _edt_from_obstacle_mask(obstacle_mask)
    return check_routability(
        net_name=net_name,
        start=start,
        goal=goal,
        edt_grid=edt,
        edt_mask=mask,
        trace_width=trace_width,
        cell_size=cell_size,
    )


def astar_passability(
    start: tuple[int, int],
    goal: tuple[int, int],
    obstacle_mask: np.ndarray,
) -> list[tuple[int, int]] | None:
    """Standard A* search on a binary obstacle grid.

    Used as the ground-truth oracle for PBT verification.
    ``obstacle_mask``: ``True`` = blocked.
    Returns a path (list of grid cells) or ``None``.
    """
    h, w = obstacle_mask.shape

    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)

    frontier: list[tuple[float, int, tuple[int, int]]] = [
        (0.0, 0, start)
    ]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}
    counter = 1

    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current == goal:
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        cx, cy = current
        for dx, dy in _DIRS_8:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            if obstacle_mask[ny, nx]:
                continue
            move_cost = math.sqrt(dx * dx + dy * dy)
            new_cost = cost_so_far[current] + move_cost
            neighbor = (nx, ny)
            if new_cost < cost_so_far.get(neighbor, float("inf")):
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(neighbor, goal)
                heapq.heappush(frontier, (priority, counter, neighbor))
                counter += 1
                came_from[neighbor] = current

    return None
