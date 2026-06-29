"""
Compact loss set factory for temper-placer.

This module provides the 'Core 8' consolidated loss suite, replacing the
40+ individual loss functions with high-level categories.
"""

from __future__ import annotations

import contextlib
from typing import Any

from temper_placer.losses.aesthetic import AlignmentLoss, get_prefix_groups
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.channel_capacity import ChannelCapacityLoss
from temper_placer.losses.consolidated import (
    UnifiedAestheticLoss,
    UnifiedGroupingLoss,
    UnifiedLoopLoss,
    UnifiedStarPointLoss,
    UnifiedThermalLoss,
)
from temper_placer.losses.grid import GridAlignmentLoss
from temper_placer.losses.ground_crossing import GroundCrossingLoss
from temper_placer.losses.grouping import create_grouping_losses_from_constraints
from temper_placer.losses.loop_area import LoopAreaLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.planarity import EdgeCrossingLoss
from temper_placer.losses.power_path import PowerPathLoss, create_power_path_loss
from temper_placer.losses.return_path import create_return_path_loss
from temper_placer.losses.star_point import StarPointLoss
from temper_placer.losses.thermal import (
    ThermalLoss,
    ThermalSpreadLoss,
    create_temper_thermal_losses,
)
from temper_placer.losses.wirelength import WirelengthLoss


def create_compact_loss_set(
    weights: dict[str, float],
    context: LossContext,
    constraints: Any = None,
) -> CompositeLoss:
    """
    Create the consolidated 8-core loss set.

    Args:
        weights: Dictionary of override weights.
        context: LossContext for resolving constraints.
        constraints: PlacementConstraints object (for resolving grouping/thermal rules).

    Returns:
        CompositeLoss containing the 8 core losses.
    """
    loss_list = []

    # 1. Overlap (Hard)
    overlap_weight = weights.get("overlap", 100.0)
    loss_list.append(WeightedLoss(OverlapLoss(margin=0.3), overlap_weight))

    # 2. Boundary (Hard)
    boundary_weight = weights.get("boundary", 50.0)
    loss_list.append(WeightedLoss(BoundaryLoss(), boundary_weight))

    # 3. Routability (Combined Wirelength + Capacity)
    routability_weight = weights.get("routability", 10.0)
    # 30% HPWL, 70% Channel Capacity
    routability_composite = CompositeLoss([
        WeightedLoss(WirelengthLoss(), weight=0.3),
        WeightedLoss(ChannelCapacityLoss(), weight=0.7)
    ])
    loss_list.append(WeightedLoss(routability_composite, routability_weight))

    # 4. Thermal
    thermal_weight = weights.get("thermal", 5.0)
    thermal_losses = []
    if constraints:
        # Try to use existing factory logic
        try:
            t_spread, t_edge = create_temper_thermal_losses(constraints, context.netlist)
            thermal_losses.append(t_spread)
            thermal_losses.append(t_edge)
        except Exception:
            pass

    # Add power path if defined
    try:
        if constraints and hasattr(constraints, 'high_current_paths'):
            pp_loss = create_power_path_loss(constraints, context.netlist)
            thermal_losses.append(pp_loss)
    except Exception:
        pass

    if thermal_losses:
        unified_thermal = UnifiedThermalLoss(
            spread_loss=next((loss for loss in thermal_losses if isinstance(loss, ThermalSpreadLoss)), None),
            edge_loss=next((loss for loss in thermal_losses if isinstance(loss, ThermalLoss)), None),
            power_path_loss=next((loss for loss in thermal_losses if isinstance(loss, PowerPathLoss)), None),
        )
        loss_list.append(WeightedLoss(unified_thermal, thermal_weight))

    # 5. Grouping
    grouping_weight = weights.get("grouping", 3.0)
    if constraints:
        c_loss, p_loss, s_loss, sym_loss = create_grouping_losses_from_constraints(constraints, context.netlist)
        unified_grouping = UnifiedGroupingLoss(
            cluster_loss=c_loss,
            proximity_loss=p_loss,
            separation_loss=s_loss
        )
        loss_list.append(WeightedLoss(unified_grouping, grouping_weight))
        if sym_loss:
            # Symmetry is specialized grouping, part of Aesthetic in some views, but Grouping here
            loss_list.append(WeightedLoss(sym_loss, grouping_weight * 0.5))

    # 6. Loop Area
    loop_weight = weights.get("loop", 2.0)
    loop_area = LoopAreaLoss()
    return_path = None
    if constraints and hasattr(constraints, 'return_path_constraints'):
        with contextlib.suppress(Exception):
            return_path = create_return_path_loss(context.netlist, constraints.return_path_constraints)
    unified_loop = UnifiedLoopLoss(loop_area_loss=loop_area, return_path_loss=return_path)
    loss_list.append(WeightedLoss(unified_loop, loop_weight))

    # 7. Star Point
    star_weight = weights.get("star_point", 1.0)
    star_point = StarPointLoss()
    crossing = GroundCrossingLoss()
    unified_star = UnifiedStarPointLoss(star_point_loss=star_point, crossing_loss=crossing)
    loss_list.append(WeightedLoss(unified_star, star_weight))

    # 8. Aesthetic
    aesthetic_weight = weights.get("aesthetic", 0.5)

    # Prefix alignment
    prefix_groups = get_prefix_groups(context.netlist)
    aes = AlignmentLoss(prefix_groups=prefix_groups) if prefix_groups.shape[0] > 0 else None

    grid = GridAlignmentLoss()
    planarity = EdgeCrossingLoss()

    unified_aes = UnifiedAestheticLoss(aesthetic_loss=aes, grid_loss=grid, planarity_loss=planarity)
    loss_list.append(WeightedLoss(unified_aes, aesthetic_weight))

    return CompositeLoss(loss_list)
