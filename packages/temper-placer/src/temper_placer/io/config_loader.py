"""
YAML constraint configuration parser.

This module loads placement constraints from YAML files, defining:
- Zone assignments
- Net class clearances
- Critical nets and loops
- Thermal constraints
- Component groupings
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from temper_placer.core.board import Board, GroundDomain, LayerStackup, Zone


@dataclass
class ClearanceRule:
    """Clearance rule between net classes or components."""

    from_class: str
    to_class: str
    clearance_mm: float
    description: str = ""


@dataclass
class CriticalLoop:
    """Definition of a critical current loop to minimize."""

    name: str
    nets: list[str]
    max_area_mm2: float | None = None
    weight: float = 1.0
    description: str = ""


@dataclass
class CriticalPath:
    """
    Definition of a critical signal path between two components.

    Attributes:
        name: Unique name for the path.
        from_comp: Starting component reference.
        to_comp: Ending component reference.
        pins: Optional tuple of (from_pin, to_pin) names.
        max_length_mm: Maximum allowed length in mm.
        priority: Priority level ('critical', 'high', 'normal').
        matched_length_group: Optional name of matched length group.
    """

    name: str
    from_comp: str
    to_comp: str
    pins: tuple[str, str] | None = None
    max_length_mm: float = 50.0
    priority: str = "normal"
    matched_length_group: str | None = None


@dataclass
class MatchedLengthGroup:
    """
    Group of signal paths that must have matched lengths.

    Attributes:
        name: Unique name for the group.
        tolerance_mm: Maximum difference in length between any two paths in group.
    """

    name: str
    tolerance_mm: float = 5.0


@dataclass
class NoiseIsolationRule:
    """
    Rule for physical isolation between sensitive components and noise sources.

    Attributes:
        name: Unique name for the rule.
        sensitive_components: List of component refs (supports globs).
        noise_sources: List of component refs (supports globs).
        min_distance_mm: Minimum required separation.
        weight: Importance of this rule.
    """

    name: str
    sensitive_components: list[str]
    noise_sources: list[str]
    min_distance_mm: float = 10.0
    weight: float = 1.0


@dataclass
class StarGroundConfig:
    """Definition of a star ground constraint."""

    net: str
    weight: float = 1.0
    anchor: tuple[float, float] | None = None
    description: str = ""


@dataclass
class ThermalConstraint:
    """Thermal placement constraint for heat-generating components."""

    components: list[str]  # Component refs
    prefer_edge: bool = True  # Place near board edge
    min_spacing_mm: float = 5.0  # Minimum spacing between thermal components
    max_distance_from_edge_mm: float = 20.0
    description: str = ""


@dataclass
class ThermalProperties:
    """
    Extended thermal properties for comprehensive thermal management.

    This extends the basic ThermalConstraint with:
    - Power dissipation values for heat spreading calculations
    - Heat-sensitive component specifications
    - Thermal pad component identification
    """

    # High-power heat sources
    high_power_components: list[str] = field(default_factory=list)
    power_dissipation_w: dict[str, float] = field(default_factory=dict)
    min_separation_mm: float = 15.0  # Between high-power components

    # Heat-sensitive components (MCU, sensors)
    heat_sensitive_components: list[str] = field(default_factory=list)
    max_temp_rise_c: float = 20.0
    min_distance_from_heat_sources_mm: float = 20.0

    # Thermal pad components (for edge preference)
    thermal_pad_components: list[str] = field(default_factory=list)
    prefer_edge: bool = True
    preferred_edge_margin_mm: float = 10.0


@dataclass
class ProximityRule:
    """Proximity constraint between two components."""

    component_a: str
    component_b: str
    max_distance_mm: float = 10.0
    description: str = ""


@dataclass
class GroupSeparation:
    """Minimum separation between two groups."""

    group_a: str
    group_b: str
    min_distance_mm: float = 20.0
    description: str = ""


@dataclass
class LossConfig:
    """Configuration for a single loss function.

    Attributes:
        weight: Weight/importance of this loss in the composite (default: 1.0)
        enabled: Whether this loss is active (default: True)
        margin: Optional margin parameter (for overlap/boundary losses)
    """

    weight: float = 1.0
    enabled: bool = True
    margin: float | None = None


@dataclass
class LossesConfig:
    """Configuration for all loss functions.

    Only losses explicitly specified here will be used by the optimizer.
    Unspecified losses are NOT included (no hardcoded defaults).

    Example YAML:
        losses:
          overlap:
            weight: 100.0
          boundary:
            weight: 50.0
          wirelength:
            weight: 10.0
    """

    overlap: LossConfig | None = None
    boundary: LossConfig | None = None
    wirelength: LossConfig | None = None
    spread: LossConfig | None = None
    edge_avoidance: LossConfig | None = None
    group_cluster: LossConfig | None = None
    thermal: LossConfig | None = None
    zone: LossConfig | None = None
    clearance: LossConfig | None = None
    loop_area: LossConfig | None = None
    star_point: LossConfig | None = None

    def get_active_losses(self) -> dict[str, LossConfig]:
        """Return dict of loss_name -> LossConfig for all enabled losses."""
        result = {}
        for name in [
            "overlap",
            "boundary",
            "wirelength",
            "spread",
            "edge_avoidance",
            "group_cluster",
            "thermal",
            "zone",
            "clearance",
            "loop_area",
            "star_point",
        ]:
            config = getattr(self, name)
            if config is not None and config.enabled:
                result[name] = config
        return result

    def get_weights(self) -> dict[str, float]:
        """Return dict of loss_name -> weight for all enabled losses."""
        return {name: cfg.weight for name, cfg in self.get_active_losses().items()}


@dataclass
class AestheticConstraints:
    """Aesthetic and professional layout constraints."""

    grid_size_mm: float = 0.5
    grid_weight: float = 1.0
    alignment_weight: float = 1.0
    rotation_consistency_weight: float = 1.0
    # Alignment groups: components with same prefix should align
    align_by_prefix: bool = True
    prefix_exceptions: list[str] = field(default_factory=list)
    # The maximum allowed wirelength increase for beauty (default 2.5x)
    max_wirelength_tax: float = 2.5
    # Enforcement of identical layouts for isomorphic groups
    consensus_weight: float = 1.0
    # Professional whitespace distribution
    whitespace_weight: float = 0.0
    # Visual grouping and separation
    grouping_weight: float = 0.0
    # Symmetry enforcement
    symmetry_weight: float = 0.0


@dataclass
class ManufacturingConstraints:
    """Manufacturing margin and variability constraints."""

    target_margin_mm: float = 0.1
    margin_weight: float = 0.0
    etch_tolerance_mm: float = 0.02


@dataclass
class ComponentGroup:
    """Group of components that should be placed together."""

    name: str
    components: list[str]
    max_spread_mm: float = 30.0  # Maximum diameter of group bounding box
    zone: str | None = None  # Required zone
    proximity_rules: list[ProximityRule] = field(default_factory=list)  # Proximity within group
    description: str = ""
    # Optional ID to force identical internal layouts with other groups sharing this ID
    template_group: str | None = None
    # Optional pin number/name that defines the 'front' of the group for rotation
    primary_pin: str | None = None
    # Whether to organize the group in a 2D matrix with dynamic gutters
    stacked_layout: bool = False


@dataclass
class PlacementConstraints:
    """Complete set of placement constraints."""

    # Board geometry
    board_width_mm: float = 100.0
    board_height_mm: float = 150.0
    board_margin_mm: float = 3.0

    # Zones
    zones: list[Zone] = field(default_factory=list)
    ground_domains: list[GroundDomain] = field(default_factory=list)

    # Clearance rules
    clearances: list[ClearanceRule] = field(default_factory=list)
    hv_clearance_mm: float = 10.0  # Default HV-LV clearance

    # Aesthetics
    aesthetics: AestheticConstraints = field(default_factory=AestheticConstraints)

    # Manufacturing
    manufacturing: ManufacturingConstraints = field(default_factory=ManufacturingConstraints)

    # Critical loops (EMI-sensitive)
    critical_loops: list[CriticalLoop] = field(default_factory=list)

    # Critical paths (signal integrity)
    critical_paths: list[CriticalPath] = field(default_factory=list)

    # Matched length groups
    matched_length_groups: list[MatchedLengthGroup] = field(default_factory=list)

    # Noise isolation rules
    noise_isolation: list[NoiseIsolationRule] = field(default_factory=list)

    # Star grounds
    star_grounds: list[StarGroundConfig] = field(default_factory=list)

    # Thermal constraints (basic)
    thermal_constraints: list[ThermalConstraint] = field(default_factory=list)

    # Extended thermal properties (advanced)
    thermal_properties: ThermalProperties | None = None

    # Component groups
    component_groups: list[ComponentGroup] = field(default_factory=list)

    # Group separation rules
    group_separations: list[GroupSeparation] = field(default_factory=list)

    # Fixed components (won't be optimized)
    fixed_components: list[str] = field(default_factory=list)
    
    # Fixed positions (component ref -> (x, y) in mm)
    # Components in this dict will be placed at exact coordinates and marked as fixed
    fixed_positions: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Zone assignments (component -> zone)
    zone_assignments: dict[str, str] = field(default_factory=dict)

    # Net class assignments (net_name -> class)
    net_classes: dict[str, str] = field(default_factory=dict)

    # Layer stackup
    layer_stackup: LayerStackup | None = None

    # Loss function configuration (explicit control over which losses are used)
    losses: LossesConfig | None = None

    def get_zone_for_component(self, ref: str) -> str | None:
        """Get required zone for a component."""
        return self.zone_assignments.get(ref)

    def get_net_class(self, net_name: str) -> str:
        """Get net class for a net, with defaults based on name."""
        if net_name in self.net_classes:
            return self.net_classes[net_name]

        # Default rules based on net name
        upper = net_name.upper()
        if (
            "GND" in upper
            or "VSS" in upper
            or (
                "VCC" in upper
                or "VDD" in upper
                or "+3V3" in upper
                or "+5V" in upper
                or "+15V" in upper
            )
        ):
            return "Power"
        elif "HV" in upper or "BUS" in upper or "DC_BUS" in upper:
            return "HighVoltage"
        else:
            return "Signal"


def load_constraints(config_path: Path) -> PlacementConstraints:
    """
    Load placement constraints from a YAML configuration file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        PlacementConstraints object with all loaded constraints.

    Example YAML format:

    ```yaml
    board:
      width_mm: 100
      height_mm: 150
      margin_mm: 3

    zones:
      - name: HV_ZONE
        bounds: [0, 0, 50, 80]
        net_classes: [HighVoltage, Power]
      - name: LV_ZONE
        bounds: [50, 0, 100, 80]
        net_classes: [Signal, Power]

    clearances:
      - from: HighVoltage
        to: Signal
        clearance_mm: 10

    critical_loops:
      - name: gate_drive
        nets: [GATE_H, SW_NODE, VCC_15V]
        max_area_mm2: 100
        weight: 2.0

    thermal:
      - components: [Q1, Q2]
        prefer_edge: true
        min_spacing_mm: 10

    groups:
      - name: mcu_decoupling
        components: [U1, C1, C2, C3]
        max_spread_mm: 20
        zone: LV_ZONE
    ```
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    constraints = PlacementConstraints()

    # Parse board geometry
    if "board" in config:
        board = config["board"]
        constraints.board_width_mm = board.get("width_mm", 100.0)
        constraints.board_height_mm = board.get("height_mm", 150.0)
        constraints.board_margin_mm = board.get("margin_mm", 3.0)

    # Parse zones
    if "zones" in config:
        for zone_cfg in config["zones"]:
            zone = Zone(
                name=zone_cfg["name"],
                bounds=tuple(zone_cfg["bounds"]),
                net_classes=zone_cfg.get("net_classes", ["Signal"]),
                components=zone_cfg.get("components", []),
            )
            constraints.zones.append(zone)

    # Parse ground domains
    if "ground_domains" in config:
        for domain_cfg in config["ground_domains"]:
            domain = GroundDomain(
                name=domain_cfg["name"],
                bounds=tuple(domain_cfg["bounds"]),
                star_point=tuple(domain_cfg["star_point"]) if "star_point" in domain_cfg else None,
            )
            constraints.ground_domains.append(domain)

    # Parse clearance rules
    if "clearances" in config:
        for rule_cfg in config["clearances"]:
            rule = ClearanceRule(
                from_class=rule_cfg["from"],
                to_class=rule_cfg["to"],
                clearance_mm=rule_cfg["clearance_mm"],
                description=rule_cfg.get("description", ""),
            )
            constraints.clearances.append(rule)

    # Parse HV clearance default
    if "hv_clearance_mm" in config:
        constraints.hv_clearance_mm = config["hv_clearance_mm"]

    # Parse critical loops
    if "critical_loops" in config:
        for loop_cfg in config["critical_loops"]:
            loop = CriticalLoop(
                name=loop_cfg["name"],
                nets=loop_cfg["nets"],
                max_area_mm2=loop_cfg.get("max_area_mm2"),
                weight=loop_cfg.get("weight", 1.0),
                description=loop_cfg.get("description", ""),
            )
            constraints.critical_loops.append(loop)

    # Parse critical paths
    if "critical_paths" in config:
        for name, path_cfg in config["critical_paths"].items():
            pins = path_cfg.get("pins")
            path = CriticalPath(
                name=name,
                from_comp=path_cfg["from"],
                to_comp=path_cfg["to"],
                pins=tuple(pins) if pins and len(pins) >= 2 else None,
                max_length_mm=path_cfg.get("max_length_mm", 50.0),
                priority=path_cfg.get("priority", "normal"),
                matched_length_group=path_cfg.get("matched_length_group"),
            )
            constraints.critical_paths.append(path)

    # Parse matched length groups
    if "matched_length_groups" in config:
        for name, group_cfg in config["matched_length_groups"].items():
            group = MatchedLengthGroup(
                name=name,
                tolerance_mm=group_cfg.get("tolerance_mm", 5.0),
            )
            constraints.matched_length_groups.append(group)

    # Parse noise isolation
    if "noise_isolation" in config:
        for name, rule_cfg in config["noise_isolation"].items():
            rule = NoiseIsolationRule(
                name=name,
                sensitive_components=rule_cfg["sensitive_components"],
                noise_sources=rule_cfg["noise_sources"],
                min_distance_mm=rule_cfg.get("min_distance_mm", 10.0),
                weight=rule_cfg.get("weight", 1.0),
            )
            constraints.noise_isolation.append(rule)

    # Parse star grounds
    if "star_grounds" in config:
        for sg_cfg in config["star_grounds"]:
            anchor = tuple(sg_cfg["anchor"]) if "anchor" in sg_cfg else None
            sg = StarGroundConfig(
                net=sg_cfg["net"],
                weight=sg_cfg.get("weight", 1.0),
                anchor=anchor,
                description=sg_cfg.get("description", ""),
            )
            constraints.star_grounds.append(sg)

    # Parse thermal constraints
    if "thermal" in config:
        for thermal_cfg in config["thermal"]:
            thermal = ThermalConstraint(
                components=thermal_cfg["components"],
                prefer_edge=thermal_cfg.get("prefer_edge", True),
                min_spacing_mm=thermal_cfg.get("min_spacing_mm", 5.0),
                max_distance_from_edge_mm=thermal_cfg.get("max_distance_from_edge_mm", 20.0),
                description=thermal_cfg.get("description", ""),
            )
            constraints.thermal_constraints.append(thermal)

    # Parse extended thermal properties
    if "thermal_properties" in config:
        tp_cfg = config["thermal_properties"]

        # Parse high-power section
        high_power = tp_cfg.get("high_power", {})
        hp_components = high_power.get("components", [])
        hp_power = high_power.get("power_dissipation_w", {})
        hp_min_sep = high_power.get("min_separation_mm", 15.0)

        # Parse heat-sensitive section
        heat_sensitive = tp_cfg.get("heat_sensitive", {})
        hs_components = heat_sensitive.get("components", [])
        hs_max_temp = heat_sensitive.get("max_temp_rise_c", 20.0)
        hs_min_dist = heat_sensitive.get("min_distance_from_heat_sources_mm", 20.0)

        # Parse thermal pads section
        thermal_pads = tp_cfg.get("thermal_pads", {})
        pad_components = thermal_pads.get("components", [])
        prefer_edge = thermal_pads.get("prefer_edge", True)
        edge_margin = thermal_pads.get("preferred_edge_margin_mm", 10.0)

        constraints.thermal_properties = ThermalProperties(
            high_power_components=hp_components,
            power_dissipation_w=hp_power,
            min_separation_mm=hp_min_sep,
            heat_sensitive_components=hs_components,
            max_temp_rise_c=hs_max_temp,
            min_distance_from_heat_sources_mm=hs_min_dist,
            thermal_pad_components=pad_components,
            prefer_edge=prefer_edge,
            preferred_edge_margin_mm=edge_margin,
        )

    # Parse component groups
    if "groups" in config:
        for group_cfg in config["groups"]:
            # Parse proximity rules within group
            proximity_rules = []
            if "proximity" in group_cfg:
                for prox_cfg in group_cfg["proximity"]:
                    # Format: [[comp_a, comp_b], max_distance] or {pair: [a, b], max_distance_mm: X}
                    if isinstance(prox_cfg, dict):
                        pair = prox_cfg.get("pair", prox_cfg.get("components", []))
                        max_dist = prox_cfg.get("max_distance_mm", 10.0)
                    else:
                        # Legacy format: [[a, b], dist]
                        pair = prox_cfg[0] if len(prox_cfg) > 0 else []
                        max_dist = prox_cfg[1] if len(prox_cfg) > 1 else 10.0
                    if len(pair) >= 2:
                        proximity_rules.append(
                            ProximityRule(
                                component_a=pair[0],
                                component_b=pair[1],
                                max_distance_mm=max_dist,
                            )
                        )

            group = ComponentGroup(
                name=group_cfg["name"],
                components=group_cfg["components"],
                max_spread_mm=group_cfg.get("max_spread_mm", 30.0),
                zone=group_cfg.get("zone"),
                proximity_rules=proximity_rules,
                description=group_cfg.get("description", ""),
                template_group=group_cfg.get("template_group"),
                primary_pin=group_cfg.get("primary_pin"),
                stacked_layout=group_cfg.get("stacked_layout", False),
            )
            constraints.component_groups.append(group)

    # Parse group separation rules
    if "group_separation" in config:
        for sep_cfg in config["group_separation"]:
            groups = sep_cfg.get("groups", [])
            if len(groups) >= 2:
                separation = GroupSeparation(
                    group_a=groups[0],
                    group_b=groups[1],
                    min_distance_mm=sep_cfg.get("min_distance_mm", 20.0),
                    description=sep_cfg.get("description", ""),
                )
                constraints.group_separations.append(separation)

    # Parse fixed components
    if "fixed_components" in config:
        constraints.fixed_components = config["fixed_components"]
    
    # Parse fixed positions (component ref -> [x, y] in mm)
    if "fixed_positions" in config:
        for ref, pos in config["fixed_positions"].items():
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                constraints.fixed_positions[ref] = (float(pos[0]), float(pos[1]))
                # Also add to fixed_components list if not already there
                if ref not in constraints.fixed_components:
                    constraints.fixed_components.append(ref)

    # Parse zone assignments
    if "zone_assignments" in config:
        constraints.zone_assignments = config["zone_assignments"]

    # Parse net classes
    if "net_classes" in config:
        constraints.net_classes = config["net_classes"]

    # Parse aesthetics
    if "aesthetics" in config:
        aes = config["aesthetics"]
        constraints.aesthetics.grid_size_mm = aes.get("grid_size_mm", 0.5)
        constraints.aesthetics.grid_weight = aes.get("grid_weight", 1.0)
        constraints.aesthetics.alignment_weight = aes.get("alignment_weight", 1.0)
        constraints.aesthetics.rotation_consistency_weight = aes.get(
            "rotation_consistency_weight", 1.0
        )
        constraints.aesthetics.align_by_prefix = aes.get("align_by_prefix", True)
        constraints.aesthetics.prefix_exceptions = aes.get("prefix_exceptions", [])
        constraints.aesthetics.max_wirelength_tax = aes.get("max_wirelength_tax", 2.5)
        constraints.aesthetics.consensus_weight = aes.get("consensus_weight", 1.0)
        constraints.aesthetics.whitespace_weight = aes.get("whitespace_weight", 0.0)
        constraints.aesthetics.grouping_weight = aes.get("grouping_weight", 0.0)
        constraints.aesthetics.symmetry_weight = aes.get("symmetry_weight", 0.0)

    # Parse manufacturing
    if "manufacturing" in config:
        mfg = config["manufacturing"]
        constraints.manufacturing.target_margin_mm = mfg.get("target_margin_mm", 0.1)
        constraints.manufacturing.margin_weight = mfg.get("margin_weight", 0.0)
        constraints.manufacturing.etch_tolerance_mm = mfg.get("etch_tolerance_mm", 0.02)

    # Parse losses configuration
    if "losses" in config:
        losses_cfg = config["losses"]
        if losses_cfg:  # Not None or empty dict
            losses_config = LossesConfig()

            # Parse each loss type
            for loss_name in [
                "overlap",
                "boundary",
                "wirelength",
                "spread",
                "edge_avoidance",
                "group_cluster",
                "thermal",
                "zone",
                "clearance",
                "loop_area",
                "star_point",
            ]:
                if loss_name in losses_cfg:
                    loss_data = losses_cfg[loss_name]
                    if loss_data is None:
                        # Explicit null = disabled
                        continue
                    elif isinstance(loss_data, dict):
                        loss_config = LossConfig(
                            weight=loss_data.get("weight", 1.0),
                            enabled=loss_data.get("enabled", True),
                            margin=loss_data.get("margin"),
                        )
                    else:
                        # Simple value = just the weight
                        loss_config = LossConfig(weight=float(loss_data))

                    setattr(losses_config, loss_name, loss_config)

            constraints.losses = losses_config

    return constraints


def create_board_from_constraints(constraints: PlacementConstraints) -> Board:
    """
    Create a Board object from constraints configuration.

    Args:
        constraints: Loaded placement constraints.

    Returns:
        Board object with zones, ground domains, etc.
    """
    return Board(
        width=constraints.board_width_mm,
        height=constraints.board_height_mm,
        origin=(0.0, 0.0),
        zones=constraints.zones,
        ground_domains=constraints.ground_domains,
        layer_stackup=constraints.layer_stackup or LayerStackup.default_4layer(),
    )


def apply_zones_to_netlist(
    netlist: Netlist, constraints: PlacementConstraints
) -> None:
    """
    Apply zone assignments from component groups to components in the netlist.
    
    For each component group that has a zone assignment, sets the corresponding
    component's zone field. This is required for ZoneLoss to work.
    
    Args:
        netlist: The netlist to modify.
        constraints: Placement constraints containing component groups with zones.
    """
    for group in constraints.component_groups:
        if group.zone:
            for comp_ref in group.components:
                comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                if comp:
                    comp.zone = group.zone


def apply_fixed_components_to_netlist(netlist, constraints: PlacementConstraints) -> None:
    """
    Apply fixed_components list from constraints to netlist.
    
    Sets Component.fixed = True for all components whose ref appears
    in constraints.fixed_components.
    
    Args:
    args:
        netlist: Netlist object with components to mark as fixed.
        constraints: Placement constraints containing fixed_components list.
    """
    if not constraints.fixed_components and not constraints.fixed_positions:
        return
    
    fixed_set = set(constraints.fixed_components)
    for comp in netlist.components:
        if comp.ref in fixed_set:
            comp.fixed = True
        
        # Apply fixed position if defined
        if comp.ref in constraints.fixed_positions:
            pos = constraints.fixed_positions[comp.ref]
            comp.initial_position = pos
            comp.fixed = True  # Ensure it's marked fixed
