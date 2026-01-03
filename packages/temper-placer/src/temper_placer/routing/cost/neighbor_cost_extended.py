"""Extended neighbor cost calculation for maze routing.

Provides a complete neighbor cost calculation that combines all extracted
modules: blocked checking, net isolation, sharing penalty, and total move cost.
"""

from typing import TYPE_CHECKING

import numpy as np

from temper_placer.routing.cost.neighbor_cost import (
    BLOCKED_COST,
    check_blocked,
    check_net_isolation,
    compute_sharing_penalty,
    compute_base_cost,
    compute_congestion_multiplier,
    get_strategy_multiplier,
)
from temper_placer.routing.cost.layer_cost import (
    compute_layer_preference_penalty,
    compute_wrong_way_penalty,
    compute_layer_balance_penalty,
    compute_via_cost,
    compute_total_move_cost,
)

if TYPE_CHECKING:
    from temper_placer.routing.heuristics import GridCell
    from temper_placer.routing.layer_assignment import LayerAssignment


def compute_neighbor_cost(
    current: "GridCell",
    neighbor: "GridCell",
    history_np: np.ndarray | None,
    history: np.ndarray | None,
    congestion_np: np.ndarray | None,
    congestion: np.ndarray | None,
    occupancy_np: np.ndarray | None,
    occupancy: np.ndarray | None,
    soft_c_space_np: np.ndarray | None,
    soft_c_space: np.ndarray | None,
    c_space_grid_np: np.ndarray | None,
    cell_owner: dict,
    current_net: str | None,
    layer_usage: np.ndarray,
    cost_map: np.ndarray | None,
    assignment: "LayerAssignment | None",
    difficulty: float,
    via_cost: float = 1.0,
    wrong_way_penalty: float = 2.0,
    layer_balance_weight: float = 0.1,
    congestion_via_discount: float = 0.5,
    soft_blocking: bool = True,
    p_scale: float = 1.0,
) -> float:
    """Compute complete cost to move from current to neighbor cell.

    Combines all cost factors:
    - Base movement cost
    - Layer preference penalty
    - Wrong-way penalty
    - History cost
    - Sharing penalty
    - Difficulty
    - C-space cost
    - Strategy multiplier
    - Layer balance penalty
    - Via cost

    Args:
        current: Current cell position
        neighbor: Neighbor cell position
        history_np: Cached history cost array (preferred)
        history: Fallback history cost array
        congestion_np: Cached congestion array (preferred)
        congestion: Fallback congestion array
        occupancy_np: Cached occupancy array (preferred)
        occupancy: Fallback occupancy array
        soft_c_space_np: Cached soft C-space array (preferred)
        soft_c_space: Fallback soft C-space array
        c_space_grid_np: Cached C-space grid array
        cell_owner: Dictionary mapping cells to owning net
        current_net: The net currently being routed
        layer_usage: Array of usage counts per layer
        cost_map: Optional cost map with strategy multipliers
        assignment: Current layer assignment
        difficulty: Routing difficulty at neighbor cell
        via_cost: Base cost for a via
        wrong_way_penalty: Penalty for wrong-way routing
        layer_balance_weight: Weight for layer balance penalty
        congestion_via_discount: Discount for vias in congested areas
        soft_blocking: Whether soft blocking is enabled
        p_scale: Congestion scaling factor

    Returns:
        Total cost for this move, or BLOCKED_COST if movement is blocked
    """
    blocked, occupied, c_space_cost = check_blocked(
        neighbor.x,
        neighbor.y,
        neighbor.layer,
        occupancy_np,
        soft_c_space_np,
        c_space_grid_np,
        occupancy,
        soft_c_space,
    )

    if blocked:
        return BLOCKED_COST

    is_different_net = check_net_isolation(
        neighbor.x, neighbor.y, neighbor.layer, cell_owner, current_net
    )

    if is_different_net:
        return BLOCKED_COST

    congestion_val = 0.0
    if congestion_np is not None:
        congestion_val = float(congestion_np[neighbor.x, neighbor.y, neighbor.layer])
    elif congestion is not None:
        congestion_val = float(congestion[neighbor.x, neighbor.y, neighbor.layer])

    history_val = compute_base_cost(neighbor.x, neighbor.y, neighbor.layer, history_np, history)

    sharing_penalty = compute_sharing_penalty(occupied, congestion_val, soft_blocking)

    if sharing_penalty >= BLOCKED_COST:
        return BLOCKED_COST

    strategy_mult = get_strategy_multiplier(cost_map, neighbor.x, neighbor.y, neighbor.layer)

    return compute_total_move_cost(
        current_x=current.x,
        current_y=current.y,
        neighbor_x=neighbor.x,
        neighbor_y=neighbor.y,
        neighbor_layer=neighbor.layer,
        layer_usage=layer_usage,
        cost_map=cost_map,
        congestion=congestion_val,
        history_cost=history_val,
        sharing_penalty=sharing_penalty,
        difficulty=difficulty,
        c_space_cost=c_space_cost,
        assignment=assignment,
        via_cost=via_cost,
        wrong_way_penalty=wrong_way_penalty,
        layer_balance_weight=layer_balance_weight,
        congestion_via_discount=congestion_via_discount,
        soft_blocking=soft_blocking,
        p_scale=p_scale,
    )
