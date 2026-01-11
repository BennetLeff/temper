"""
Router V6 Stage 3.1: Build Constraint Model

Defines the variables and constraints for the SAT/SMT-based routing solver.
Part of temper-atsd (Stage 3 - Topological Routing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.stage0_data import DesignRules


@dataclass(kw_only=True)
class Variable:
    """Base class for routing variables."""
    name: str
    var_type: str  # "bool", "int", "continuous"


@dataclass(kw_only=True)
class NetChannelVar(Variable):
    """
    Variable representing if a net uses a specific channel segment.
    uses[net_id, channel_id]
    """
    net_idx: int
    channel_id: str  # Unique ID for channel edge (e.g. "L1_E5")
    var_type: str = "bool"


@dataclass(kw_only=True)
class NetLayerVar(Variable):
    """
    Variable representing the layer assignment of a net segment.
    layer[net_id, segment_id]
    """
    net_idx: int
    segment_id: str
    var_type: str = "int"  # Layer index


@dataclass(kw_only=True)
class ViaVar(Variable):
    """
    Variable representing if a via exists for a net at a specific location.
    via[net_id, location_id]
    """
    net_idx: int
    location_id: str  # Unique ID for potential via location (node)
    var_type: str = "bool"


@dataclass(kw_only=True)
class OrderVar(Variable):
    """
    Variable representing relative ordering of two nets in a channel.
    order[net1_idx, net2_idx, channel_id]
    True if net1 is "before" net2 in channel.
    """
    net1_idx: int
    net2_idx: int
    channel_id: str
    var_type: str = "bool"


@dataclass(kw_only=True)
class Constraint:
    """Base class for routing constraints."""
    name: str
    description: str = ""


@dataclass(kw_only=True)
class CapacityConstraint(Constraint):
    """
    Constraint: sum(uses[n,c] * width[n]) <= capacity[c] * slack
    """
    channel_id: str
    capacity: float
    slack_factor: float
    terms: list[tuple[NetChannelVar, float]]  # (variable, coefficient/width)


@dataclass
class ConstraintModel:
    """
    SAT/SMT Constraint Model for Topological Routing.
    
    Holds all variables and constraints (in abstract form).
    """
    variables: list[Variable] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    net_channel_vars: dict[tuple[int, str], NetChannelVar] = field(default_factory=dict)
    via_vars: dict[tuple[int, str], ViaVar] = field(default_factory=dict)
    
    def add_variable(self, var: Variable) -> None:
        self.variables.append(var)
        if isinstance(var, NetChannelVar):
            self.net_channel_vars[(var.net_idx, var.channel_id)] = var
        elif isinstance(var, ViaVar):
            self.via_vars[(var.net_idx, var.location_id)] = var

    def add_constraint(self, constraint: Constraint) -> None:
        self.constraints.append(constraint)

    @property
    def variable_count(self) -> int:
        return len(self.variables)

    @property
    def constraint_count(self) -> int:
        return len(self.constraints)


class ModelBuilder:
    """Builder for generating the constraint model from skeletons and nets."""
    
    def __init__(
        self, 
        skeletons: dict[str, ChannelSkeleton], 
        nets: list[Net],
        channel_widths: dict[str, ChannelWidths] | None = None,
        design_rules: DesignRules | None = None
    ):
        self.skeletons = skeletons
        self.nets = nets
        self.channel_widths = channel_widths or {}
        self.design_rules = design_rules
        self.model = ConstraintModel()
        
    def build(self) -> ConstraintModel:
        """
        Generate all variables and constraints for the routing problem.
        """
        self._create_channel_vars()
        self._create_via_vars()
        self._create_capacity_constraints()
        return self.model
        
    def _create_channel_vars(self):
        """Create variables for net-channel assignment."""
        for net_idx, net in enumerate(self.nets):
            # For each layer skeleton
            for layer_name, skeleton in self.skeletons.items():
                # For each edge in the skeleton
                # We need a stable ID for edges. 
                # nx edges are (u, v). We can sort nodes to canonicalize.
                for i, (u, v) in enumerate(skeleton.graph.edges):
                    # Sort nodes by coordinate to ensure stable ID
                    n1, n2 = sorted([u, v])
                    edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                    
                    var = NetChannelVar(
                        name=f"uses_N{net_idx}_{edge_id}",
                        net_idx=net_idx,
                        channel_id=edge_id
                    )
                    self.model.add_variable(var)

    def _create_via_vars(self):
        """Create variables for via placement."""
        # Vias can exist at skeleton nodes (intersections)
        # We assume vias connect adjacent layers or all layers.
        # For simplicity, we create potential via vars at every skeleton node
        # that exists in multiple layers (or just spatially).
        
        # Collect all unique node locations across all skeletons
        all_nodes = set()
        for skeleton in self.skeletons.values():
            for node in skeleton.graph.nodes:
                all_nodes.add(node) # node is (x, y) tuple
        
        # Sort for stability
        sorted_nodes = sorted(list(all_nodes))
        
        for net_idx, net in enumerate(self.nets):
            for i, node in enumerate(sorted_nodes):
                node_id = f"VIA_N{i}_{node[0]:.2f}_{node[1]:.2f}"
                
                var = ViaVar(
                    name=f"via_N{net_idx}_{node_id}",
                    net_idx=net_idx,
                    location_id=node_id
                )
                self.model.add_variable(var)

    def _create_capacity_constraints(self):
        """
        Create capacity constraints for each channel.
        sum(uses[n, c] * width[n]) <= capacity[c] * 0.8
        """
        if not self.channel_widths or not self.design_rules:
            return

        slack_factor = 0.8

        for layer_name, skeleton in self.skeletons.items():
            widths = self.channel_widths.get(layer_name)
            if not widths:
                continue

            for i, (u, v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([u, v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                
                # Get capacity (min width of edge)
                # Try both directions
                capacity = widths.edge_widths.get((u, v))
                if capacity is None:
                    capacity = widths.edge_widths.get((v, u), 0.0)
                
                if capacity <= 0:
                    continue

                terms = []
                for net_idx, net in enumerate(self.nets):
                    # Get net width from design rules
                    rule = self.design_rules.get_rules_for_net(net.name)
                    net_width = rule.trace_width_mm + rule.clearance_mm # width + spacing
                    
                    # Find variable
                    if (net_idx, edge_id) in self.model.net_channel_vars:
                        var = self.model.net_channel_vars[(net_idx, edge_id)]
                        terms.append((var, net_width))
                
                if terms:
                    constraint = CapacityConstraint(
                        name=f"cap_{edge_id}",
                        channel_id=edge_id,
                        capacity=capacity,
                        slack_factor=slack_factor,
                        terms=terms
                    )
                    self.model.add_constraint(constraint)
