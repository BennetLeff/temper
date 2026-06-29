"""
PCL constraint to JAX loss function bridge - MVP implementation.

This module translates PCL constraints into differentiable JAX loss functions.
This is an MVP that focuses on tier mapping and basic constraint translation.

Tier Mapping:
- HARD (tier=1): weight=1e6
- STRONG (tier=2): weight=1e3
- SOFT (tier=3): weight=1e1

Note: Full constraint translation requires additional work to map all PCL
constraint types to appropriate loss functions with correct constructors.
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.losses.grouping import ProximityLoss, ProximityRule
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    ConstraintTier,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)


def tier_to_weight(tier: ConstraintTier) -> float:
    """
    Convert constraint tier to loss function weight.

    Weights are aligned with tiers.py for consistency.

    Args:
        tier: Constraint tier (HARD, STRONG, or SOFT).

    Returns:
        Weight multiplier for loss function.
    """
    weight_map = {
        ConstraintTier.HARD: 1000000.0,
        ConstraintTier.STRONG: 1000.0,
        ConstraintTier.SOFT: 10.0,
    }
    return weight_map[tier]


def _resolve_to_indices(
    name: str,
    netlist: Netlist,
    board: Board | None = None,
) -> list[int]:
    """
    Resolve a name (component ref or zone name) to component indices.

    Args:
        name: Component reference (e.g., 'Q1') or zone name (e.g., 'HV_ZONE').
        netlist: Netlist for component lookup.
        board: Optional board for zone component lookup.

    Returns:
        List of component indices.
    """
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # 1. Check if it's a direct component reference
    if name in ref_to_idx:
        return [ref_to_idx[name]]

    # 2. Check if it's a zone name in the board definition
    if board and board.zones:
        for zone in board.zones:
            if zone.name == name:
                indices = []
                for comp_ref in zone.components:
                    if comp_ref in ref_to_idx:
                        indices.append(ref_to_idx[comp_ref])
                return indices

    # 3. Handle fallback case (e.g., zone name not yet in board.zones)
    # This happens during early optimization phases
    if "_ZONE" in name:
        return []

    raise ValueError(f"Could not resolve '{name}' to any components in netlist or board zones")


def adjacent_to_proximity_loss(
    constraint: AdjacentConstraint,
    netlist: Netlist,
) -> LossFunction:
    """
    Convert Adjacent constraint to ProximityLoss.

    Args:
        constraint: Adjacent constraint specifying max distance.
        netlist: Netlist for component index lookup.

    Returns:
        ProximityLoss enforcing max distance.

    Raises:
        ValueError: If component references not found in netlist.
    """
    # Map component refs to indices
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    if constraint.a not in ref_to_idx:
        raise ValueError(f"Component {constraint.a} not found in netlist")
    if constraint.b not in ref_to_idx:
        raise ValueError(f"Component {constraint.b} not found in netlist")

    idx_a = ref_to_idx[constraint.a]
    idx_b = ref_to_idx[constraint.b]

    # Create ProximityRule
    rule = ProximityRule(
        idx_a=idx_a,
        idx_b=idx_b,
        max_distance_mm=constraint.max_distance_mm,
        weight=tier_to_weight(constraint.tier),
    )

    return ProximityLoss(proximity_rules=[rule])


def separated_to_separation_loss(
    constraint: SeparatedConstraint,
    netlist: Netlist,
    board: Board | None = None,
) -> LossFunction:
    """
    Convert Separated constraint to GroupSeparationLoss.

    Args:
        constraint: Separated constraint specifying min distance.
        netlist: Netlist for component/zone lookup.
        board: Optional board for zone lookup.

    Returns:
        GroupSeparationLoss enforcing min distance.
    """
    from temper_placer.losses.grouping import GroupConfig, GroupSeparationLoss

    indices_a = _resolve_to_indices(constraint.a, netlist, board)
    indices_b = _resolve_to_indices(constraint.b, netlist, board)

    if not indices_a or not indices_b:
        # Return empty loss if one group is empty (e.g., empty zone)
        return GroupSeparationLoss(separations=[])

    weight = tier_to_weight(constraint.tier)

    group_a = GroupConfig(
        name=constraint.a,
        component_indices=jnp.array(indices_a, dtype=jnp.int32),
        max_diameter_mm=0.0,
        weight=weight,
    )
    group_b = GroupConfig(
        name=constraint.b,
        component_indices=jnp.array(indices_b, dtype=jnp.int32),
        max_diameter_mm=0.0,
        weight=weight,
    )

    return GroupSeparationLoss(
        separations=[(group_a, group_b, constraint.min_distance_mm)],
    )


def enclosing_to_zone_loss(
    constraint: EnclosingConstraint,
    netlist: Netlist,
) -> LossFunction:
    """
    Convert Enclosing constraint to ZoneMembershipLoss.

    Args:
        constraint: Enclosing constraint (outer zone, inner components).
        netlist: Netlist for component lookup.

    Returns:
        ZoneMembershipLoss enforcing zone membership.
    """
    from temper_placer.losses.zone import ZoneMembershipLoss

    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    zone_assignments = {}
    for comp_ref in constraint.inner:
        if comp_ref not in ref_to_idx:
            raise ValueError(f"Component {comp_ref} not found in netlist")
        zone_assignments[comp_ref] = constraint.outer

    # Note: ZoneMembershipLoss weight scheduling is handled internally
    # but we could wrap it if we wanted to apply PCL tier weights here.
    # For now, we trust the internal schedule.
    return ZoneMembershipLoss(zone_assignments=zone_assignments)


def aligned_to_alignment_loss(
    constraint: AlignedConstraint,
    netlist: Netlist,
) -> LossFunction:
    """
    Convert Aligned constraint to AlignmentLoss.

    Args:
        constraint: Aligned constraint (components, axis, tolerance).
        netlist: Netlist for component lookup.

    Returns:
        AlignmentLoss enforcing alignment.
    """
    from temper_placer.losses.aesthetic import AlignmentLoss

    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    indices = []
    for comp_ref in constraint.components:
        if comp_ref not in ref_to_idx:
            raise ValueError(f"Component {comp_ref} not found in netlist")
        indices.append(ref_to_idx[comp_ref])

    # AlignmentLoss expects prefix_groups as (G, M) array where:
    # G = number of groups, M = max group size, padded with -1
    # For PCL, we have one group with the aligned components
    len(indices)
    prefix_groups_array = jnp.array(indices, dtype=jnp.int32).reshape(1, -1)

    return AlignmentLoss(prefix_groups=prefix_groups_array)


def onside_to_edge_loss(
    constraint: OnSideConstraint,
    netlist: Netlist,
    board: Board,
) -> LossFunction:
    """
    Convert OnSide constraint to EdgePreferenceLoss.

    Args:
        constraint: OnSide constraint (components, side, edge type).
        netlist: Netlist for component lookup.
        board: Board for edge position.

    Returns:
        EdgePreferenceLoss pulling components to board edge.
    """
    from temper_placer.losses.thermal import EdgePreferenceLoss

    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    indices = []
    for comp_ref in constraint.components:
        if comp_ref not in ref_to_idx:
            raise ValueError(f"Component {comp_ref} not found in netlist")
        indices.append(ref_to_idx[comp_ref])

    # EdgePreferenceLoss constructor signature:
    # (thermal_pad_indices, board_width, board_height, edge_preference_weight)
    return EdgePreferenceLoss(
        thermal_pad_indices=jnp.array(indices, dtype=jnp.int32),
        board_width=board.width,
        board_height=board.height,
        weight=tier_to_weight(constraint.tier),
    )


def anchored_to_positional_loss(
    constraint: AnchoredConstraint,
    netlist: Netlist,
) -> LossFunction:
    """
    Convert Anchored constraint to custom positional penalty.

    Args:
        constraint: Anchored constraint (component, region or position).
        netlist: Netlist for component lookup.

    Returns:
        Custom loss function penalizing deviation from target.
    """
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    if constraint.component not in ref_to_idx:
        raise ValueError(f"Component {constraint.component} not found in netlist")

    idx = ref_to_idx[constraint.component]
    weight = tier_to_weight(constraint.tier)

    if constraint.position is not None:
        target_pos = jnp.array(constraint.position, dtype=jnp.float32)

        class PositionalLossExact(LossFunction):
            @property
            def name(self) -> str:
                return f"anchored_{constraint.component}"

            def __call__(
                self,
                positions: Array,
                _rotations: Array,
                _context: LossContext,
                _epoch: int = 0,
                _total_epochs: int = 1,
                _net_virtual_nodes: Array | None = None,
            ) -> LossResult:
                delta = positions[idx] - target_pos
                distance = jnp.linalg.norm(delta)
                loss_value = weight * distance**2
                return LossResult(value=loss_value)

        return PositionalLossExact()

    elif constraint.region is not None:
        x_min, y_min, x_max, y_max = constraint.region
        target_pos = jnp.array([(x_min + x_max) / 2, (y_min + y_max) / 2], dtype=jnp.float32)

        class PositionalLossRegion(LossFunction):
            @property
            def name(self) -> str:
                return f"anchored_{constraint.component}_region"

            def __call__(
                self,
                positions: Array,
                _rotations: Array,
                _context: LossContext,
                _epoch: int = 0,
                _total_epochs: int = 1,
                _net_virtual_nodes: Array | None = None,
            ) -> LossResult:
                pos = positions[idx]
                x, y = pos[0], pos[1]

                # Distance from region center
                delta = pos - target_pos
                distance = jnp.linalg.norm(delta)

                # Additional penalty if outside bounds
                outside_x = jnp.maximum(0, x_min - x) + jnp.maximum(0, x - x_max)
                outside_y = jnp.maximum(0, y_min - y) + jnp.maximum(0, y - y_max)
                outside_penalty = (outside_x + outside_y) ** 2

                loss_value = weight * (distance**2 + 10.0 * outside_penalty)
                return LossResult(value=loss_value)

        return PositionalLossRegion()

    else:
        raise ValueError("AnchoredConstraint must have either position or region")


def loop_area_to_loop_loss(
    constraint: LoopAreaConstraint,
    netlist: Netlist,
    loops: dict[str, Any],
) -> LossFunction:
    """
    Convert LoopArea constraint to LoopAreaLoss.

    Args:
        constraint: LoopArea constraint (loop name, max area).
        netlist: Netlist for component lookup.
        loops: Loop definitions with component lists.

    Returns:
        LoopAreaLoss minimizing loop area.
    """
    from temper_placer.losses.loop_area import LoopAreaLoss

    if constraint.loop_name not in loops:
        raise ValueError(f"Loop {constraint.loop_name} not found in loop definitions")

    loop_def = loops[constraint.loop_name]
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    loop_indices = []
    for comp_ref in loop_def["components"]:
        if comp_ref not in ref_to_idx:
            raise ValueError(f"Component {comp_ref} in loop not found in netlist")
        loop_indices.append(ref_to_idx[comp_ref])

    # Create LoopConstraint with proper constructor signature
    # LoopAreaLoss gets constraints from LossContext, not constructor
    # For now, return basic loss with scaled penalty based on tier
    # TODO: Integrate with LossContext for proper loop constraint passing
    weight = tier_to_weight(constraint.tier)
    return LoopAreaLoss(
        area_penalty_scale=0.01 * weight,
        routing_factor=1.0,
    )


def constraint_to_loss(
    constraint: BaseConstraint,
    netlist: Netlist,
    board: Board | None = None,
    _zones: dict[str, Any] | None = None,
    loops: dict[str, Any] | None = None,
) -> LossFunction:
    """
    Unified dispatcher to convert any PCL constraint to a loss function.

    Args:
        constraint: PCL constraint to convert.
        netlist: Netlist for component lookup.
        board: Optional board for edge-based constraints.
        zones: Optional zone definitions for spatial constraints.
        loops: Optional loop definitions for loop area constraints.

    Returns:
        Loss function implementing the constraint.

    Raises:
        TypeError: If constraint type not recognized.
        ValueError: If constraint references invalid components/zones.
    """
    if isinstance(constraint, AdjacentConstraint):
        return adjacent_to_proximity_loss(constraint, netlist)

    elif isinstance(constraint, SeparatedConstraint):
        return separated_to_separation_loss(constraint, netlist, board)

    elif isinstance(constraint, EnclosingConstraint):
        return enclosing_to_zone_loss(constraint, netlist)

    elif isinstance(constraint, AlignedConstraint):
        return aligned_to_alignment_loss(constraint, netlist)

    elif isinstance(constraint, OnSideConstraint):
        if board is None:
            raise ValueError("board required for OnSideConstraint")
        return onside_to_edge_loss(constraint, netlist, board)

    elif isinstance(constraint, AnchoredConstraint):
        return anchored_to_positional_loss(constraint, netlist)

    elif isinstance(constraint, LoopAreaConstraint):
        if loops is None:
            raise ValueError("loops dict required for LoopAreaConstraint")
        return loop_area_to_loop_loss(constraint, netlist, loops)

    else:
        raise TypeError(f"Unknown constraint type: {type(constraint).__name__}")


def _backend_adapter(constraint: BaseConstraint, context) -> LossFunction:
    """Adapter: destructure CompilationContext for the loss bridge.

    Registered as BaseConstraint.backends["jax"] so ConstraintCollection.compile()
    can dispatch JAX compilation through the standard backend interface.
    """
    from temper_placer.pcl.constraints import CompilationContext
    return constraint_to_loss(
        constraint,
        netlist=context.netlist,
        board=context.board,
        zones=context.extra.get("zones"),
        loops=context.extra.get("loops"),
    )


# Register the JAX backend (R5, R21).
# Import-time registration: the loss bridge claims the "jax" key.
from temper_placer.pcl.constraints import BaseConstraint as _BaseConstraint
_BaseConstraint.backends["jax"] = _backend_adapter
