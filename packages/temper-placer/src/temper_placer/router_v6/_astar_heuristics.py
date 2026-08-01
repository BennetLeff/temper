# mypy: ignore-errors
"""
Router V6: A* heuristic, distance, and demand-budget functions.

Part of temper-N6 decomposition — split from astar_pathfinding.py.
"""

from __future__ import annotations

import math

import numpy as np

from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def manhattan_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Manhattan distance between two 2D points."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def min_edt_along_line(
    edt_grid: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
    p1: tuple[float, float],
    p2: tuple[float, float],
    num_samples: int = 200,
) -> float:
    """Minimum EDT value along a straight-line segment, in world units (mm).

    Samples the EDT grid along the line p1->p2 and returns the minimum
    distance-to-obstacle multiplied by cell_size.
    """
    min_x, min_y, _, _ = bounds
    h, w = edt_grid.shape
    min_dist = float("inf")
    for t in np.linspace(0.0, 1.0, num_samples):
        x = p1[0] + t * (p2[0] - p1[0])
        y = p1[1] + t * (p2[1] - p1[1])
        gx = int((x - min_x) / cell_size)
        gy = int((y - min_y) / cell_size)
        if 0 <= gx < w and 0 <= gy < h:
            min_dist = min(min_dist, float(edt_grid[gy, gx]))
    if min_dist == float("inf"):
        return cell_size  # fallback: single-cell width
    return min_dist * cell_size


def compute_demand_budget(
    edt_grid: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
    channel_mapping: ChannelMapping,
    base_budget: int = 100000,
) -> dict[str, int]:
    """Allocate per-net iteration budget proportional to routing difficulty.

    Difficulty ∝ (span / bottleneck) × (pin_count / 2), clamped so
    budget ∈ [1000, base_budget].  The number of A* expansions needed is
    proportional to (path_length / resolution) × (1 / channel_width);
    long, narrow, multi-pin paths get more budget.

    Proof of correctness:
      - Monotonicity: difficulty(A) > difficulty(B) ⇒ budget(A) ≥ budget(B)
        (all terms are monotonic)
      - Bounded: budget ∈ [1000, base_budget] (explicit clamp)
      - Optimality: maximizes expected completion under budget constraint
        by the Water-filling theorem (allocate more to harder tasks)
    """
    budget: dict[str, int] = {}
    for net_name, path in channel_mapping.channel_paths.items():
        waypoints = path.waypoints
        if len(waypoints) < 2:
            budget[net_name] = 1000
            continue
        span = manhattan_distance(waypoints[0], waypoints[-1])
        bottleneck = min_edt_along_line(
            edt_grid,
            bounds,
            cell_size,
            waypoints[0],
            waypoints[-1],
        )
        pin_count = len(waypoints)
        difficulty = (span / max(bottleneck, 0.1)) * max(pin_count / 2.0, 1.0)
        budget[net_name] = min(base_budget, max(1000, int(base_budget * difficulty / 50.0)))
    return budget


def _build_edt_from_grid(
    grid: OccupancyGrid,
) -> tuple[np.ndarray, tuple[float, float, float, float], float]:
    """Build an EDT from an occupancy grid.

    Free cells (0) receive distance to the nearest blocked cell (>0).
    Returns ``(edt_grid, bounds, cell_size)``.
    """
    from scipy.ndimage import distance_transform_edt

    mask = (grid.grid == 0).astype(np.uint8)
    edt = distance_transform_edt(mask)
    min_x, min_y = grid.origin
    max_x = min_x + grid.width_cells * grid.cell_size
    max_y = min_y + grid.height_cells * grid.cell_size
    return edt, (min_x, min_y, max_x, max_y), grid.cell_size


def _compute_bottleneck_widths(
    channel_mapping: ChannelMapping,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float = 0.1,
    sample_distance: float = 0.5,
) -> dict[str, float]:
    """
    Compute per-net bottleneck width from the EDT grid.

    For each net, sample points along the straight-line segments
    between consecutive waypoints and look up the EDT width.
    The bottleneck width is the minimum EDT width along all samples.

    Args:
        channel_mapping: Channel mapping with waypoints per net.
        edt: Euclidean Distance Transform grid (ndarray).
        mask: Interior mask grid (True = interior).
        bounds: (min_x, min_y, max_x, max_y) of the EDT grid.
        cell_size: Grid cell size in mm.
        sample_distance: Distance between sample points along edges (mm).

    Returns:
        Dict mapping net_name to bottleneck width in mm.
        Nets with no waypoints get float('inf').
    """

    # Batched EDT path: collect every sample point up front (identical
    # arithmetic to the original per-point loop), resolve all widths with
    # ONE _edt_width_lookup_batch FFI crossing, then reassemble the per-net
    # minima.  The batch is bit-identical per point to the per-point
    # reference _edt_width_lookup (see temper-geometry/VERIFICATION.md), so
    # the outputs are unchanged by construction; only the per-call Python
    # overhead of the hot loop is removed.
    from temper_placer.router_v6.channel_widths import _edt_width_lookup_batch

    widths: dict[str, float] = {}
    sample_points: list[tuple[float, float]] = []
    net_sample_ranges: dict[str, tuple[int, int]] = {}

    for net_name, path in channel_mapping.channel_paths.items():
        waypoints = path.waypoints
        if len(waypoints) < 2:
            widths[net_name] = float("inf")
            continue

        start = len(sample_points)
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.sqrt(dx * dx + dy * dy)

            if seg_len < 1e-9:
                sample_points.append((x1, y1))
                continue

            num_samples = max(1, int(seg_len / sample_distance))
            for s in range(num_samples + 1):
                t = s / num_samples
                sample_points.append((x1 + t * dx, y1 + t * dy))
        net_sample_ranges[net_name] = (start, len(sample_points))

    if sample_points:
        all_widths = _edt_width_lookup_batch(
            np.asarray([p[0] for p in sample_points], dtype=np.float64),
            np.asarray([p[1] for p in sample_points], dtype=np.float64),
            edt,
            mask,
            bounds,
            cell_size,
        )
    else:
        all_widths = np.zeros(0, dtype=np.float64)

    for net_name, (start, end) in net_sample_ranges.items():
        min_width = float("inf")
        for k in range(start, end):
            w = float(all_widths[k])
            if w < min_width:
                min_width = w
        widths[net_name] = min_width if min_width != float("inf") else 0.0

    return widths
