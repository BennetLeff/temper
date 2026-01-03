"""Neighbor cost calculation for maze routing."""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import GridCell


BLOCKED_COST = 1e9


def check_blocked(
    x: int,
    y: int,
    layer: int,
    occupancy_np: np.ndarray | None,
    soft_c_space_np: np.ndarray | None,
    c_space_grid_np: np.ndarray | None,
    occupancy: np.ndarray | None = None,
    soft_c_space: np.ndarray | None = None,
) -> tuple[bool, bool, float]:
    """Check if a cell is blocked and return occupancy status.

    Args:
        x, y, layer: Cell coordinates
        occupancy_np: Cached occupancy array (preferred)
        soft_c_space_np: Cached soft C-space array (preferred)
        c_space_grid_np: Cached C-space grid array
        occupancy: Fallback occupancy array
        soft_c_space: Fallback soft C-space array

    Returns:
        Tuple of (is_blocked, is_occupied, c_space_cost)
    """
    use_numpy = occupancy_np is not None

    if use_numpy:
        occ_value = int(occupancy_np[x, y, layer])
        blocked = occ_value == -1
        occupied = occ_value == 2

        c_space_cost = 0.0
        if soft_c_space_np is not None:
            if soft_c_space_np.ndim == 2:
                c_space_cost = float(soft_c_space_np[x, y])
            else:
                c_space_cost = float(soft_c_space_np[x, y, layer])

            if c_space_cost == np.inf:
                blocked = True

        if c_space_grid_np is not None:
            if c_space_grid_np.ndim == 2:
                if bool(c_space_grid_np[x, y]):
                    blocked = True
            else:
                if bool(c_space_grid_np[x, y, layer]):
                    blocked = True
    elif occupancy is not None:
        occ_value = int(occupancy[x, y, layer])
        blocked = occ_value == -1
        occupied = occ_value == 2

        c_space_cost = 0.0
        if soft_c_space is not None:
            if soft_c_space.ndim == 2:
                c_space_cost = float(soft_c_space[x, y])
            else:
                c_space_cost = float(soft_c_space[x, y, layer])

            if c_space_cost == np.inf:
                blocked = True

        if c_space_grid_np is not None:
            if c_space_grid_np.ndim == 2:
                if bool(c_space_grid_np[x, y]):
                    blocked = True
            else:
                if bool(c_space_grid_np[x, y, layer]):
                    blocked = True
    else:
        blocked = False
        occupied = False
        c_space_cost = 0.0

    return blocked, occupied, c_space_cost


def check_net_isolation(
    x: int,
    y: int,
    layer: int,
    cell_owner: dict,
    current_net: str | None,
) -> bool:
    """Check if cell is owned by a different net (DRC-1: net isolation).

    Args:
        x, y, layer: Cell coordinates
        cell_owner: Dictionary mapping cells to owning net
        current_net: The net currently being routed

    Returns:
        True if cell is owned by a different net (should be blocked)
    """
    if current_net is None:
        return False

    key = (x, y, layer)
    owner = cell_owner.get(key)
    if owner is not None and owner != current_net:
        return True

    return False


def compute_sharing_penalty(
    occupied: bool,
    congestion: float,
    soft_blocking: bool,
) -> float:
    """Compute penalty for sharing a cell with other routes.

    Args:
        occupied: Whether cell is occupied by another route
        congestion: Current congestion level at cell
        soft_blocking: Whether soft blocking is enabled

    Returns:
        Sharing penalty (0 if not occupied or in strict mode)
    """
    if not occupied:
        return 0.0

    if not soft_blocking:
        return BLOCKED_COST

    return 50.0 * (1.0 + congestion)


def get_strategy_multiplier(
    cost_map: np.ndarray | None,
    x: int,
    y: int,
    layer: int,
) -> float:
    """Get routing strategy cost multiplier.

    Args:
        cost_map: Optional cost map with strategy multipliers
        x, y, layer: Cell coordinates

    Returns:
        Strategy multiplier (1.0 if no cost map)
    """
    if cost_map is None:
        return 1.0

    if cost_map.ndim == 2:
        return float(cost_map[x, y])
    else:
        return float(cost_map[x, y, layer])


def compute_layer_balance_cost(
    layer_usage: np.ndarray,
    target_layer: int,
    layer_balance_weight: float,
) -> float:
    """Compute penalty for layer imbalance.

    Args:
        layer_usage: Array of usage counts per layer
        target_layer: Layer being evaluated
        layer_balance_weight: Weight factor for penalty

    Returns:
        Layer balance penalty (0 if balanced or weight is 0)
    """
    if layer_balance_weight <= 0:
        return 0.0

    total_usage = np.sum(layer_usage)
    if total_usage <= 0:
        return 0.0

    mean_usage = np.mean(layer_usage)
    usage = layer_usage[target_layer]

    if usage > mean_usage:
        imbalance_penalty = (usage - mean_usage) / max(1.0, mean_usage)
        return layer_balance_weight * imbalance_penalty

    return 0.0


def compute_base_cost(
    x: int,
    y: int,
    layer: int,
    history_np: np.ndarray | None,
    history: np.ndarray | None = None,
) -> float:
    """Get history cost for a cell.

    Args:
        x, y, layer: Cell coordinates
        history_np: Cached history array (preferred)
        history: Fallback history array

    Returns:
        History cost value
    """
    if history_np is not None:
        return float(history_np[x, y, layer])
    elif history is not None:
        return float(history[x, y, layer])
    else:
        return 0.0


def compute_congestion_multiplier(
    congestion: float,
    p_scale: float = 1.0,
) -> float:
    """Compute congestion multiplier for cost calculation.

    Args:
        congestion: Congestion level at cell
        p_scale: Scaling factor for congestion

    Returns:
        Congestion multiplier
    """
    return 1.0 + congestion * p_scale
