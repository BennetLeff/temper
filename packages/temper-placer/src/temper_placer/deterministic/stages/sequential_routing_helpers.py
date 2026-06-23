from typing import List, Optional, Tuple

from ...routing.layer_assignment import Layer as LayerEnum


# Layer enum to index mapping
LAYER_ENUM_TO_IDX = {
    LayerEnum.L1_TOP: 0,
    LayerEnum.L2_GND: 1,
    LayerEnum.L3_PWR: 2,
    LayerEnum.L4_BOT: 3,
}


def _compute_endpoint_tolerance(
    is_pth: bool,
    pad_size: Optional[Tuple[float, float]],
    grid_cell_size: float,
) -> float:
    """Compute endpoint tolerance for A* pathfinding.

    For PTH pads, traces can land anywhere within the pad boundary.
    For SMD pads, traces must hit closer to center.

    Args:
        is_pth: True if plated through-hole
        pad_size: (width, height) of pad or None
        grid_cell_size: Grid cell size in mm

    Returns:
        Tolerance in mm - A* accepts endpoints within this radius
    """
    if not is_pth or not pad_size:
        return grid_cell_size  # Default: one grid cell

    # PTH pads: allow landing anywhere within pad
    # Use half the smaller dimension as tolerance
    min_dim = min(pad_size[0], pad_size[1])
    return max(min_dim / 2.0, grid_cell_size)


def _compute_mst(points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
    """Compute Minimum Spanning Tree using Prim's algorithm."""
    n = len(points)
    if n < 2:
        return []

    visited = {0}
    edges = []

    while len(visited) < n:
        min_dist_sq = float("inf")
        u_min, v_min = -1, -1

        # Find shortest edge from visited to unvisited
        for u in visited:
            for v in range(n):
                if v in visited:
                    continue

                # Squared Euclidean distance
                dist_sq = (points[u][0] - points[v][0]) ** 2 + (
                    points[u][1] - points[v][1]
                ) ** 2

                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    u_min = u
                    v_min = v

        if u_min != -1 and v_min != -1:
            visited.add(v_min)
            edges.append((u_min, v_min))
        else:
            break

    return edges
