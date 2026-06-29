"""
Router V6 Stage 3.1: Build Constraint Model

Defines the variables and constraints for the SAT/SMT-based routing solver.
Part of temper-atsd (Stage 3 - Topological Routing)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from temper_placer.core.netlist import Net
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.router_v6.stage0_data import DesignRules, ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


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

    def esl(self):
        """Return an ESL predicate for this capacity constraint.

        The predicate is True iff at most *max_nets* of the term variables
        are True in the assignment, where *max_nets* = capacity * slack / min_width.
        """
        min_width = min(width for _, width in self.terms)
        max_nets = int(self.capacity * self.slack_factor / min_width)
        var_names = [var.name for var, _ in self.terms]
        return lambda ass: sum(1 for v in var_names if ass.get(v, False)) <= max_nets


@dataclass(kw_only=True)
class DiffPairConstraint(Constraint):
    """
    Constraint: uses[p_net, channel] == uses[n_net, channel]
    Ensures both nets of a differential pair follow the same path.
    """
    channel_id: str
    p_net_idx: int
    n_net_idx: int
    p_var: NetChannelVar
    n_var: NetChannelVar

    def esl(self):
        """Return an ESL predicate: p_var iff n_var (both True or both False)."""
        p_name = self.p_var.name
        n_name = self.n_var.name
        return lambda ass: ass.get(p_name, False) == ass.get(n_name, False)


@dataclass(kw_only=True)
class LayerConstraint(Constraint):
    """
    Constraint: uses[n, c] == value (usually 0 or 1)
    Restricts a net to a specific layer for a given channel.
    """
    net_idx: int
    channel_id: str
    allowed: bool

    def esl(self):
        """Return an ESL predicate: var == allowed."""
        var_name = f"uses_N{self.net_idx}_{self.channel_id}"
        return lambda ass: ass.get(var_name, False) == self.allowed


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
        design_rules: DesignRules | None = None,
        diff_pairs: list[DiffPair] | None = None,
        pcb: ParsedPCB | None = None,
        enable_bundling: bool = False,
        bundle_manifest: object | None = None,
    ):
        self.skeletons = skeletons
        self.nets = nets
        self.channel_widths = channel_widths or {}
        self.design_rules = design_rules
        self.diff_pairs = diff_pairs or []
        self.pcb = pcb
        self.model = ConstraintModel()
        self.enable_bundling = enable_bundling
        self.bundle_manifest = bundle_manifest

        # Build net name to index mapping for fast lookup
        self.net_to_idx = {net.name: i for i, net in enumerate(self.nets)}

    def build(self) -> ConstraintModel:
        """
        Generate all variables and constraints for the routing problem.
        """
        if self.enable_bundling and self.bundle_manifest is not None:
            self._create_class_channel_vars()
        else:
            self._create_channel_vars()
        self._create_via_vars()
        if self.enable_bundling and self.bundle_manifest is not None:
            self._create_bundled_capacity_constraints()
            self._create_bundled_layer_constraints()
        else:
            self._create_capacity_constraints()
            self._create_diff_pair_constraints()
            self._create_layer_constraints()
        return self.model

    def _create_channel_vars(self):
        """Create variables for net-channel assignment."""
        for net_idx, _net in enumerate(self.nets):
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

    def _create_class_channel_vars(self):
        """Create class-level channel variables for bundled nets.

        One `uses_B{bundle_id}_{channel_id}` per (bundle x skeleton edge).
        Non-bundled nets (singletons) get per-net vars as usual.
        """
        manifest = self.bundle_manifest
        bundle_id_for_net = getattr(manifest, "bundle_id_for_net", {})
        unbundled = set(getattr(manifest, "unbundled_net_indices", []))

        bundled_net_indices = set(bundle_id_for_net.keys())

        for layer_name, skeleton in self.skeletons.items():
            for i, (u, v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([u, v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

                seen_bundles: set[int] = set()
                for net_idx in sorted(bundled_net_indices):
                    bid = bundle_id_for_net.get(net_idx)
                    if bid is None or bid in seen_bundles:
                        continue
                    seen_bundles.add(bid)
                    var = NetChannelVar(
                        name=f"uses_B{bid}_{edge_id}",
                        net_idx=bid,
                        channel_id=edge_id,
                    )
                    var.var_type = "bundle"  # type: ignore[attr-defined]
                    self.model.add_variable(var)

                for net_idx in sorted(unbundled):
                    var = NetChannelVar(
                        name=f"uses_N{net_idx}_{edge_id}",
                        net_idx=net_idx,
                        channel_id=edge_id,
                    )
                    self.model.add_variable(var)

    def _create_bundled_capacity_constraints(self):
        """Create capacity constraints using class-level bundle variables.

        Safety-typed capacity constraints are encoded eagerly.  AtMostK
        bound uses the minimum width across all nets in the bundle.
        """
        if not self.channel_widths or not self.design_rules:
            return

        slack_factor = 0.8
        manifest = self.bundle_manifest
        bundle_id_for_net = getattr(manifest, "bundle_id_for_net", {})
        unbundled = set(getattr(manifest, "unbundled_net_indices", []))

        bid_to_nets: dict[int, list[int]] = {}
        for ni, bid in bundle_id_for_net.items():
            bid_to_nets.setdefault(bid, []).append(ni)

        for layer_name, skeleton in self.skeletons.items():
            widths_obj = self.channel_widths.get(layer_name)
            if not widths_obj:
                continue

            for i, (u, v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([u, v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

                capacity = widths_obj.edge_widths.get((u, v))
                if capacity is None:
                    capacity = widths_obj.edge_widths.get((v, u), 0.0)
                if capacity <= 0:
                    continue

                terms: list[tuple[NetChannelVar, float]] = []

                for bid, net_indices in sorted(bid_to_nets.items()):
                    var_key = (bid, edge_id)
                    if var_key in self.model.net_channel_vars:
                        min_width = float("inf")
                        for ni in net_indices:
                            rule = self.design_rules.get_rules_for_net(self.nets[ni].name)
                            w = rule.trace_width_mm + rule.clearance_mm
                            if w < min_width:
                                min_width = w
                        var = self.model.net_channel_vars[var_key]
                        terms.append((var, min_width))

                for net_idx in sorted(unbundled):
                    var_key = (net_idx, edge_id)
                    if var_key in self.model.net_channel_vars:
                        rule = self.design_rules.get_rules_for_net(self.nets[net_idx].name)
                        net_width = rule.trace_width_mm + rule.clearance_mm
                        var = self.model.net_channel_vars[var_key]
                        terms.append((var, net_width))

                if terms:
                    constraint = CapacityConstraint(
                        name=f"cap_{edge_id}",
                        channel_id=edge_id,
                        capacity=capacity,
                        slack_factor=slack_factor,
                        terms=terms,
                    )
                    self.model.add_constraint(constraint)

    def _create_bundled_layer_constraints(self):
        """Create layer constraints for bundled nets.

        SMD pin layer restrictions are always Safety constraints and must
        be encoded before the solver begins.
        """
        if not self.pcb:
            return

        manifest = self.bundle_manifest
        bundle_id_for_net = getattr(manifest, "bundle_id_for_net", {})

        for comp in self.pcb.components:
            comp_x, comp_y = comp.initial_position or (0.0, 0.0)
            for pin in comp.pins:
                if not pin.net or pin.net not in self.net_to_idx:
                    continue

                net_idx = self.net_to_idx[pin.net]
                if not pin.is_pth:
                    target_layer = pin.layer
                    pin_pos = pin_world_position(pin, comp)

                    for layer_name, skeleton in self.skeletons.items():
                        if layer_name == target_layer:
                            continue

                        for i, (u, v) in enumerate(skeleton.graph.edges):
                            match = False
                            for node in [u, v]:
                                if abs(node[0] - pin_pos[0]) < 0.01 and abs(
                                    node[1] - pin_pos[1]
                                ) < 0.01:
                                    match = True
                                    break

                            if match:
                                n1, n2 = sorted([u, v])
                                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

                                bid = bundle_id_for_net.get(net_idx)
                                if bid is not None:
                                    key = (bid, edge_id)
                                else:
                                    key = (net_idx, edge_id)

                                if key in self.model.net_channel_vars:
                                    var = self.model.net_channel_vars[key]
                                    constraint = LayerConstraint(
                                        name=f"layer_restr_N{net_idx}_{edge_id}",
                                        net_idx=net_idx,
                                        channel_id=edge_id,
                                        allowed=False,
                                    )
                                    self.model.add_constraint(constraint)

    def _create_via_vars(self):
        """Create variables for via placement."""
        # Collect all unique node locations across all skeletons
        all_nodes = set()
        for skeleton in self.skeletons.values():
            for node in skeleton.graph.nodes:
                all_nodes.add(node) # node is (x, y) tuple

        # Sort for stability
        sorted_nodes = sorted(all_nodes)

        for net_idx, _net in enumerate(self.nets):
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

    def _create_diff_pair_constraints(self):
        """
        Create constraints for differential pairs.
        uses[p_net, c] == uses[n_net, c]
        """
        for pair in self.diff_pairs:
            if pair.p_net not in self.net_to_idx or pair.n_net not in self.net_to_idx:
                continue

            p_idx = self.net_to_idx[pair.p_net]
            n_idx = self.net_to_idx[pair.n_net]

            for layer_name, skeleton in self.skeletons.items():
                for i, (u, v) in enumerate(skeleton.graph.edges):
                    n1, n2 = sorted([u, v])
                    edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

                    if (p_idx, edge_id) in self.model.net_channel_vars and \
                       (n_idx, edge_id) in self.model.net_channel_vars:

                        p_var = self.model.net_channel_vars[(p_idx, edge_id)]
                        n_var = self.model.net_channel_vars[(n_idx, edge_id)]

                        constraint = DiffPairConstraint(
                            name=f"diff_{pair.base_name}_{edge_id}",
                            channel_id=edge_id,
                            p_net_idx=p_idx,
                            n_net_idx=n_idx,
                            p_var=p_var,
                            n_var=n_var
                        )
                        self.model.add_constraint(constraint)

    def _create_layer_constraints(self):
        """
        Create layer constraints for pins.
        Ensures SMD pins only connect to their respective layer.
        """
        if not self.pcb:
            return

        for comp in self.pcb.components:
            comp_x, comp_y = comp.initial_position or (0.0, 0.0)
            float(comp.initial_rotation or 0) * math.pi / 2.0

            for pin in comp.pins:
                if not pin.net or pin.net not in self.net_to_idx:
                    continue

                net_idx = self.net_to_idx[pin.net]
                pin_pos = pin_world_position(pin, comp)

                # SMD pins are restricted to one layer
                if not pin.is_pth:
                    target_layer = pin.layer

                    # Find all breakout edges for this pin
                    # A breakout edge is an edge where one endpoint is the pin position
                    for layer_name, skeleton in self.skeletons.items():
                        if layer_name == target_layer:
                            continue # Allowed

                        # Restricted layer: for all edges connected to this pin position,
                        # set uses[net, edge] == 0
                        for i, (u, v) in enumerate(skeleton.graph.edges):
                            # Check if either endpoint matches pin position (with tolerance)
                            match = False
                            for node in [u, v]:
                                if abs(node[0] - pin_pos[0]) < 0.01 and abs(node[1] - pin_pos[1]) < 0.01:
                                    match = True
                                    break

                            if match:
                                n1, n2 = sorted([u, v])
                                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

                                if (net_idx, edge_id) in self.model.net_channel_vars:
                                    self.model.net_channel_vars[(net_idx, edge_id)]
                                    constraint = LayerConstraint(
                                        name=f"layer_restr_N{net_idx}_{edge_id}",
                                        net_idx=net_idx,
                                        channel_id=edge_id,
                                        allowed=False
                                    )
                                    self.model.add_constraint(constraint)


class ConstraintGenerationStage(Stage):
    """Stage 3.1: Build constraint model from skeletons and nets."""

    @property
    def name(self) -> str:
        return "ConstraintGeneration"

    def run(self, state: BoardState) -> BoardState:
        pcb: ParsedPCB = state._parsed_pcb
        skeletons = state.channel_skeletons
        channel_widths = state.channel_widths
        diff_pairs = infer_differential_pairs([net.name for net in pcb.nets])
        model_builder = ModelBuilder(
            skeletons=skeletons,
            nets=pcb.nets,
            channel_widths=channel_widths,
            design_rules=pcb.design_rules,
            diff_pairs=diff_pairs,
            pcb=pcb,
        )
        constraint_model = model_builder.build()
        return replace(state, constraint_model=constraint_model)


@register_validator("ConstraintGeneration")
def validate_constraint_generation(state: BoardState) -> list[StageDRCFailure]:
    failures: list[StageDRCFailure] = []
    cm = state.constraint_model
    if cm is None:
        failures.append(StageDRCFailure(
            field="constraint_model", value=None,
            reason="Constraint model not generated", stage="ConstraintGeneration",
        ))
        return failures
    if cm.variable_count == 0 and cm.constraint_count == 0:
        failures.append(StageDRCFailure(
            field="constraint_model", value=cm.variable_count,
            reason="Constraint model has zero variables and zero constraints",
            stage="ConstraintGeneration",
        ))
    channel_var_ids = set()
    for var in cm.variables:
        if hasattr(var, 'channel_id'):
            if var.channel_id in channel_var_ids:
                failures.append(StageDRCFailure(
                    field="net_channel_vars", value=var.channel_id,
                    reason=f"Duplicate channel variable name: {var.channel_id}",
                    stage="ConstraintGeneration",
                ))
            channel_var_ids.add(var.channel_id)
    return failures
