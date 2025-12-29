"""
Public API for the Hypergraph Routing Bridge.

This module provides the main entry point for generating routing contexts
from the physical design state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jax.numpy as jnp
from temper_placer.routing.bridge.inference import analyze_placement
from temper_placer.routing.bridge.types import RoutingStrategy, RoutingContext
from temper_placer.routing.bridge.cost_map import generate_edge_hug_field

if TYPE_CHECKING:
    from jax import Array
    from temper_placer.core.board import Board
    from temper_placer.core.hypergraph import PhysicsHypergraph
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.maze_router import MazeRouter


def get_routing_context(
    hypergraph: PhysicsHypergraph,
    positions: Array,
    board: Board,
    netlist: Netlist,
) -> RoutingContext:
    """
    Generate a semantic routing context from the current placement and hypergraph.
    
    This function should be called after placement optimization but before routing.
    """
    return analyze_placement(hypergraph, positions, board, netlist)


def get_cost_map_for_net(
    grid_size: tuple[int, int],
    cell_size_mm: float,
    context: RoutingContext,
    net_id: str,
) -> Array | None:
    """
    Generate a 2D cost map for a specific net based on the semantic context.
    
    Returns:
        (W, H) Array or None if standard routing is requested.
    """
    strategy = context.get_strategy(net_id)
    
    if strategy == RoutingStrategy.EDGE_HUG:
        return generate_edge_hug_field(
            grid_size=grid_size,
            cell_size_mm=cell_size_mm,
            target_width_mm=5.0
        )
    
    if strategy == RoutingStrategy.FLOOD_FILL:
        # High cost everywhere to discourage trace routing (effectively blocking)
        return jnp.full(grid_size, 1000.0)
        
    return None
