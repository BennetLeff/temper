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
from temper_placer.core.decision import Alternative, Decision, DecisionTrace
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
from temper_placer.core.manufacturing import FabPreset, inflated_clearance, inflated_width
from temper_placer.core.net_types import (
    ConnectivityStrategy,
    NetClassification,
    NetType,
    NetTypeSpec,
    VoltageClass,
)
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.core.topology import ComponentCluster, TopologicalGraph, TopologicalSolution

# Units
from temper_placer.core.units import (
    CellIndex,
    Degrees,
    DegreesArray,
    LayerIndex,
    Millimeters,
    NetId,
    Radians,
    RadiansArray,
    mm_to_cell,
)

# IPC-2221 PCB design standards
from temper_placer.core.ipc2221 import estimate_current_from_net_class

# Net graph utilities
from temper_placer.core.net_graph import NetGraph, SubNetEdge

# Hypergraph utilities
from temper_placer.core.hypergraph import HypergraphIncidence, PhysicsHypergraph

# Net priority classification
from temper_placer.core.priority import PlacementPriority, PriorityConfig, RoutingPriority

# Differential pair constraints
from temper_placer.core.differential_pair import DifferentialPairConstraint

# Bus cohort routing constraints
from temper_placer.core.bus_cohort import BusCohortConstraint, BusRegistry

# Physical design specifications
from temper_placer.core.specification import EMISpec, PcbSpecification, ThermalSpec

# Design rules and net class rules
from temper_placer.core.design_rules import DesignRules, NetClassRules

# Component community detection
from temper_placer.core.community import Community, detect_communities

__all__ = [
    # State
    "PlacementState",
    # Topology
    "TopologicalGraph",
    "TopologicalSolution",
    "ComponentCluster",
    # Decisions
    "Decision",
    "DecisionTrace",
    "Alternative",
    # Manufacturing
    "FabPreset",
    "inflated_clearance",
    "inflated_width",
    # Components and nets
    "Component",
    "Pin",
    "Net",
    "Netlist",
    # Net type classification
    "NetType",
    "ConnectivityStrategy",
    "VoltageClass",
    "NetTypeSpec",
    "NetClassification",
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
    # Units
    "CellIndex",
    "Degrees",
    "DegreesArray",
    "LayerIndex",
    "Millimeters",
    "NetId",
    "Radians",
    "RadiansArray",
    "mm_to_cell",
    # IPC-2221
    "estimate_current_from_net_class",
    # Net graph
    "NetGraph",
    "SubNetEdge",
    # Hypergraph
    "HypergraphIncidence",
    "PhysicsHypergraph",
    # Priority
    "PlacementPriority",
    "RoutingPriority",
    "PriorityConfig",
    # Differential pair
    "DifferentialPairConstraint",
    # Bus cohort
    "BusCohortConstraint",
    "BusRegistry",
    # Specifications
    "EMISpec",
    "PcbSpecification",
    "ThermalSpec",
    # Design rules
    "DesignRules",
    "NetClassRules",
    # Community
    "Community",
    "detect_communities",
]
