"""
Core data structures for temper-placer.

This module contains the fundamental data structures that all other modules depend on:
- PlacementState: JAX-compatible state holding positions and rotation logits
- Component, Pin: Individual component and pin representations
- Net, Netlist: Connectivity information
- Board, Zone: Board geometry and placement zones
- Loop, LoopEvent, LoopCollection: Loop-centric modeling for power electronics

All position arrays use jax.Array for differentiability.
"""

from temper_placer.core.board import Board, LayerStackup, Zone
from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)
from temper_placer.core.loop_extractor import (
    auto_extract_loops,
    classify_component,
    merge_loops,
)
from temper_placer.core.loop_ownership import (
    ComponentLoopInfo,
    LoopMembership,
    LoopOwnershipMap,
    build_ownership_map,
)
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState

__all__ = [
    # State
    "PlacementState",
    # Components and nets
    "Component",
    "Pin",
    "Net",
    "Netlist",
    # Board geometry
    "Board",
    "Zone",
    "LayerStackup",
    # Loop-centric modeling
    "Loop",
    "LoopCollection",
    "LoopEvent",
    "LoopPin",
    "LoopPriority",
    "LoopType",
    # Loop extraction
    "auto_extract_loops",
    "classify_component",
    "merge_loops",
    # Loop ownership
    "ComponentLoopInfo",
    "LoopMembership",
    "LoopOwnershipMap",
    "build_ownership_map",
]
