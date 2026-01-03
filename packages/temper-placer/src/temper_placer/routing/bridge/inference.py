"""
Inference engine for the Hypergraph Routing Bridge.

This module implements the rules-based logic that derives routing strategies
from the physical state of the PCB (placement, zones, and hypergraph attributes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import jax.numpy as jnp
from temper_placer.routing.bridge.types import (
    RoutingContext,
    RoutingStrategy,
    ZoneConflict,
    ZoneConflictType,
)

if TYPE_CHECKING:
    from jax import Array
    from temper_placer.core.board import Board
    from temper_placer.core.hypergraph import PhysicsHypergraph
    from temper_placer.core.netlist import Netlist


def detect_zone_conflicts(
    positions: Array,
    board: Board,
    netlist: Netlist,
) -> List[ZoneConflict]:
    """
    Identify physical components located in electrically incompatible zones.
    
    Rule: A net's class must be permitted by the zone containing its pins.
    Example: A 'Signal' net pin located in an 'HV_ZONE' (which only allows 'HighVoltage').
    """
    conflicts = []
    
    # 1. Iterate through all components
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        x, y = float(pos[0]), float(pos[1])
        
        # 2. Identify the physical zone of the component center
        zone = board.get_zone_for_point(x, y)
        if not zone:
            continue
            
        # 3. Check every pin/net on this component
        for pin in comp.pins:
            if not pin.net:
                continue
                
            try:
                net = netlist.get_net(pin.net)
            except (KeyError, ValueError):
                continue
                
            # 4. Validate if net class is allowed in this zone
            # Note: We use net class from netlist here.
            if net.net_class not in zone.net_classes:
                # Potential conflict found
                conflict_type = ZoneConflictType.LV_NET_IN_HV_ZONE
                if net.net_class == "HighVoltage":
                    conflict_type = ZoneConflictType.HV_NET_IN_LV_ZONE
                
                conflicts.append(
                    ZoneConflict(
                        net_id=net.name,
                        pin_id=f"{comp.ref}-{pin.number}",
                        conflict_type=conflict_type,
                        severity=1.0 # Simple linear severity for now
                    )
                )
                
    return conflicts


def infer_strategies(
    hypergraph: PhysicsHypergraph,
    conflicts: List[ZoneConflict],
    current_threshold: float = 2.0,
) -> Dict[str, RoutingStrategy]:
    """
    Derive routing strategies based on physical attributes and detected conflicts.
    """
    strategies = {}
    
    # 1. Start with standard strategy for all nets
    for net_name in hypergraph.hyperedge_names:
        strategies[net_name] = RoutingStrategy.STANDARD_A_STAR
        
    # 2. Rule: Current Capacity -> FLOOD_FILL
    # Access edge currents from hypergraph
    if hypergraph.edge_currents.size > 0:
        for i, net_name in enumerate(hypergraph.hyperedge_names):
            current = float(hypergraph.edge_currents[i])
            if current > current_threshold:
                strategies[net_name] = RoutingStrategy.FLOOD_FILL
                
    # 3. Rule: Zone Conflict -> EDGE_HUG
    # If a net has any conflict, it must be routed with extra care.
    for conflict in conflicts:
        # Conflicts override standard but not flood fill
        if strategies[conflict.net_id] != RoutingStrategy.FLOOD_FILL:
            strategies[conflict.net_id] = RoutingStrategy.EDGE_HUG
            
    return strategies


def analyze_placement(
    hypergraph: PhysicsHypergraph,
    positions: Array,
    board: Board,
    netlist: Netlist,
) -> RoutingContext:
    """
    Orchestrate the physical analysis of a placement to produce routing instructions.
    
    This is the primary entry point for the Hypergraph Routing Bridge.
    """
    # 1. Detect conflicts between physical placement and electrical zones
    conflicts = detect_zone_conflicts(positions, board, netlist)
    
    # 2. Infer strategies from hypergraph attributes and conflicts
    strategies = infer_strategies(hypergraph, conflicts)
    
    # 3. Calculate cost modifiers
    # (Placeholder: we could increase cost for critical paths or high-voltage nets)
    cost_modifiers = {}
    
    return RoutingContext(
        strategies=strategies,
        cost_modifiers=cost_modifiers,
        conflicts=conflicts,
    )
