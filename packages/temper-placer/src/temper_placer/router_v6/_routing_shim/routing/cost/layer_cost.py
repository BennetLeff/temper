"""Layer cost calculations for maze routing."""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.layer_assignment import LayerAssignment


def compute_layer_balance_penalty(
    layer_usage: np.ndarray,
    neighbor_layer: int,
    layer_balance_weight: float = 0.1,
) -> float:
    """Compute penalty for layer imbalance.

    Encourages even distribution of routing across layers by penalizing
    moves to layers with above-average usage.

    Args:
        layer_usage: Array of usage counts per layer
        neighbor_layer: The layer being considered
        layer_balance_weight: Weight factor for imbalance penalty

    Returns:
        Penalty value to add to cost (0 if layer is below average or weight is 0)
    """
    if layer_balance_weight <= 0:
        return 0.0

    total_usage = np.sum(layer_usage)
    if total_usage <= 0:
        return 0.0

    mean_usage = np.mean(layer_usage)
    usage = layer_usage[neighbor_layer]

    if usage > mean_usage:
        imbalance_penalty = (usage - mean_usage) / max(1.0, mean_usage)
        return layer_balance_weight * imbalance_penalty

    return 0.0


def compute_via_cost(
    is_layer_change: bool,
    congestion: float,
    via_cost: float = 1.0,
    congestion_via_discount: float = 0.5,
    soft_blocking: bool = True,
) -> float:
    """Compute cost for layer transition (via placement).

    Applies dynamic via cost that encourages layer escape in congested areas.

    Args:
        is_layer_change: True if this move changes layers
        congestion: Current congestion level at the cell
        via_cost: Base cost for a via
        congestion_via_discount: Discount factor for vias in congested areas
        soft_blocking: Whether soft blocking is enabled

    Returns:
        Via cost to add to total (0 if not a layer change)
    """
    if not is_layer_change:
        return 0.0

    if soft_blocking and congestion > 2.0:
        return via_cost * congestion_via_discount

    return via_cost


def compute_wrong_way_penalty(
    current_x: int,
    current_y: int,
    neighbor_x: int,
    neighbor_y: int,
    layer: int,
    wrong_way_penalty: float = 2.0,
) -> float:
    """Compute penalty for routing against layer preference.

    Layer 0 (L1) prefers horizontal routing, Layer 1 (L4) prefers vertical.

    Args:
        current_x, current_y: Current cell coordinates
        neighbor_x, neighbor_y: Neighbor cell coordinates
        layer: Current layer index
        wrong_way_penalty: Penalty for wrong-way routing

    Returns:
        Penalty value (0 if routing aligns with layer preference)
    """
    if wrong_way_penalty <= 0:
        return 0.0

    if layer == 0:
        if neighbor_y != current_y:
            return wrong_way_penalty
    elif layer == 1:
        if neighbor_x != current_x:
            return wrong_way_penalty

    return 0.0


def compute_layer_preference_penalty(
    neighbor_layer: int,
    assignment: "LayerAssignment | None",
    base_penalty: float = 5.0,
) -> float:
    """Compute penalty for using non-primary layer.

    When a layer assignment exists, penalize routes that don't use
    the primary layer unless necessary.

    Args:
        neighbor_layer: The layer being considered
        assignment: Current layer assignment (None if not assigned)
        base_penalty: Penalty for using non-primary layer

    Returns:
        Penalty value (0 if using primary layer or no assignment)
    """
    if assignment is None:
        return 0.0

    primary_idx = assignment.primary_layer.value - 1
    if neighbor_layer == primary_idx:
        return 0.0

    return base_penalty


def compute_strategy_multiplier(
    cost_map: np.ndarray | None,
    x: int,
    y: int,
    layer: int,
) -> float:
    """Get strategy multiplier from cost map.

    Applies routing strategy preferences encoded in the cost map.

    Args:
        cost_map: Optional cost map with strategy multipliers
        x, y, layer: Cell coordinates

    Returns:
        Multiplier value (1.0 if no cost map)
    """
    if cost_map is None:
        return 1.0

    if cost_map.ndim == 2:
        return float(cost_map[x, y])
    else:
        return float(cost_map[x, y, layer])


def compute_congestion_cost(
    base_cost: float,
    history_cost: float,
    sharing_penalty: float,
    difficulty: float,
    c_space_cost: float,
    congestion: float,
    strategy_multiplier: float = 1.0,
    p_scale: float = 1.0,
) -> float:
    """Compute congestion-aware cost.

    Combines base costs with congestion multipliers and strategy.

    Args:
        base_cost: Base movement cost (1.0)
        history_cost: Historical congestion cost
        sharing_penalty: Penalty for sharing cell with other routes
        difficulty: Routing difficulty at cell
        c_space_cost: Soft C-space cost
        congestion: Current congestion level
        strategy_multiplier: Strategy cost multiplier
        p_scale: Congestion scaling factor

    Returns:
        Congestion-adjusted cost
    """
    raw_cost = base_cost + history_cost + sharing_penalty + difficulty + c_space_cost
    congestion_multiplier = 1.0 + congestion * p_scale
    return strategy_multiplier * raw_cost * congestion_multiplier


def compute_total_move_cost(
    current_x: int,
    current_y: int,
    neighbor_x: int,
    neighbor_y: int,
    neighbor_layer: int,
    layer_usage: np.ndarray,
    cost_map: np.ndarray | None,
    congestion: float,
    history_cost: float,
    sharing_penalty: float,
    difficulty: float,
    c_space_cost: float,
    assignment: "LayerAssignment | None",
    via_cost: float = 1.0,
    wrong_way_penalty: float = 2.0,
    layer_balance_weight: float = 0.1,
    congestion_via_discount: float = 0.5,
    soft_blocking: bool = True,
    p_scale: float = 1.0,
) -> float:
    """Compute total cost for moving to a neighbor cell.

    Combines all cost factors: base, layer preference, wrong-way,
    history, congestion, difficulty, sharing, strategy, and via.

    Args:
        current_x, current_y: Current cell coordinates
        neighbor_x, neighbor_y, neighbor_layer: Neighbor cell
        layer_usage: Array of usage counts per layer
        cost_map: Optional cost map with strategy multipliers
        congestion: Current congestion level
        history_cost: Historical congestion cost
        sharing_penalty: Penalty for sharing cell
        difficulty: Routing difficulty at cell
        c_space_cost: Soft C-space cost
        assignment: Current layer assignment
        via_cost: Base cost for a via
        wrong_way_penalty: Penalty for wrong-way routing
        layer_balance_weight: Weight for layer balance penalty
        congestion_via_discount: Discount for vias in congested areas
        soft_blocking: Whether soft blocking is enabled
        p_scale: Congestion scaling factor

    Returns:
        Total cost for this move
    """
    base_cost = 1.0

    layer_pref_penalty = compute_layer_preference_penalty(neighbor_layer, assignment)
    wrong_way = compute_wrong_way_penalty(
        current_x, current_y, neighbor_x, neighbor_y, neighbor_layer, wrong_way_penalty
    )
    layer_balance = compute_layer_balance_penalty(layer_usage, neighbor_layer, layer_balance_weight)
    strategy_mult = compute_strategy_multiplier(cost_map, neighbor_x, neighbor_y, neighbor_layer)

    raw_cost = (
        base_cost
        + layer_pref_penalty
        + wrong_way
        + sharing_penalty
        + history_cost
        + difficulty
        + c_space_cost
    )
    congestion_multiplier = 1.0 + congestion * p_scale
    congestion_cost = strategy_mult * raw_cost * congestion_multiplier

    via = compute_via_cost(
        current_y != neighbor_y or current_x != neighbor_x,
        congestion,
        via_cost,
        congestion_via_discount,
        soft_blocking,
    )

    return congestion_cost + layer_balance + via
