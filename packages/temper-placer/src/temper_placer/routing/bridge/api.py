"""
Public API for the Hypergraph Routing Bridge.

This module provides the main entry point for generating routing contexts
from the physical design state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.routing.bridge.inference import analyze_placement

if TYPE_CHECKING:
    from jax import Array
    from temper_placer.core.board import Board
    from temper_placer.core.hypergraph import PhysicsHypergraph
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.bridge.types import RoutingContext


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
