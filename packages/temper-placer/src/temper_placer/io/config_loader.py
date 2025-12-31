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

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    nets: list[str] = field(default_factory=list)
    pins: list[tuple[str, str]] | None = None
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
class ComponentSpacingRule:
    """Minimum edge-to-edge spacing between specific component pairs."""

    component_a: str
    component_b: str
    min_separation_mm: float
    description: str = ""
    weight: float = 1.0


@dataclass
class ManufacturingConstraint:
    """Manufacturing constraint for orientations and assembly side."""

    components: list[str]
    allowed_orientations: list[float] | None = None
    side: str | None = None  # "top", "bottom", "both"
    tier: str = "hard"
    because: str = ""
    weight: float = 1.0


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
    weight: float = 1.0  # Importance weight (higher = stronger clustering)
    description: str = ""
    # Optional ID to force identical internal layouts with other groups sharing this ID
    template_group: str | None = None
    # Optional pin number/name that defines the 'front' of the group for rotation
    primary_pin: str | None = None
    # Whether to organize the group in a 2D matrix with dynamic gutters
    stacked_layout: bool = False


@dataclass
class NetClassRule:
    """Design rules for a specific net class."""

    name: str # e.g. "HighVoltage"
    trace_width_mm: float = 0.2
    clearance_mm: float = 0.2
    via_size_mm: float = 0.6
    via_drill_mm: float = 0.3
    creepage_mm: float = 0.0
    allow_neckdown: bool = True
    description: str = ""


@dataclass
class PlacementConstraints:
    """Complete set of placement constraints."""

    # Board geometry
    board_width_mm: float = 100.0
    board_height_mm: float = 150.0
    board_margin_mm: float = 3.0
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)

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

    # Component spacing rules (minimum edge-to-edge distances)
    component_spacing_rules: list[ComponentSpacingRule] = field(default_factory=list)

    # Manufacturing orientation and side constraints
    manufacturing_constraints: list[ManufacturingConstraint] = field(default_factory=list)

    # Fixed components (won't be optimized)
    fixed_components: list[str] = field(default_factory=list)
    
    # Fixed positions (component ref -> (x, y) in mm)
    fixed_positions: dict[str, tuple[float, float]] = field(default_factory=dict)

    # Zone assignments (component -> zone)
    zone_assignments: dict[str, str] = field(default_factory=dict)

    # Net class assignments (net_name -> class)
    net_classes: dict[str, str] = field(default_factory=dict)

    # Net class design rules (class_name -> NetClassRule)
    net_class_rules: dict[str, NetClassRule] = field(default_factory=dict)


    # Layer stackup
    layer_stackup: LayerStackup | None = None

    # Loss function configuration
    losses: LossesConfig | None = None

    # Priority-based placement and routing configuration
    placement_priority: dict = field(default_factory=dict)
    routing_priority: dict = field(default_factory=dict)

    def get_zone_for_component(self, ref: str) -> str | None:
        """Get required zone for a component."""
        return self.zone_assignments.get(ref)

    def get_net_class(self, net_name: str) -> str:
        """Get net class for a net, with defaults based on name."""
        if net_name in self.net_classes:
            return self.net_classes[net_name]

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


def _validate_weight(weight: float, name: str) -> None:
    """Validate that loss weight is within acceptable bounds."""
    if not math.isfinite(weight):
        raise ValueError(f"Loss weight for '{name}' must be finite (got {weight}).")
    if weight < 0:
        raise ValueError(f"Loss weight for '{name}' must be positive (got {weight}).")
    if weight > 1e6:
        raise ValueError(f"Loss weight for '{name}' must be less than 1e6 (got {weight}).")


def load_constraints(config_path: Path) -> PlacementConstraints:
    """Load placement constraints from a YAML configuration file."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    constraints = PlacementConstraints()

    if "board" in config:
        board = config["board"]
        constraints.board_width_mm = board.get("width_mm", 100.0)
        constraints.board_height_mm = board.get("height_mm", 150.0)
        constraints.board_margin_mm = board.get("margin_mm", 3.0)
        
        if "keepouts" in board:
            for ko in board["keepouts"]:
                if isinstance(ko, (list, tuple)) and len(ko) >= 4:
                    constraints.keepouts.append(tuple(ko))

    if "zones" in config:
        for zone_cfg in config["zones"]:
            if "bounds_ratio" in zone_cfg:
                ratio = zone_cfg["bounds_ratio"]
                bounds = (
                    ratio[0] * constraints.board_width_mm,
                    ratio[1] * constraints.board_height_mm,
                    ratio[2] * constraints.board_width_mm,
                    ratio[3] * constraints.board_height_mm,
                )
            else:
                bounds = tuple(zone_cfg["bounds"])

            zone = Zone(
                name=zone_cfg["name"],
                bounds=bounds,
                net_classes=zone_cfg.get("net_classes", ["Signal"]),
                components=zone_cfg.get("components", []),
            )
            constraints.zones.append(zone)

    if "ground_domains" in config:
        for domain_cfg in config["ground_domains"]:
            domain = GroundDomain(
                name=domain_cfg["name"],
                bounds=tuple(domain_cfg["bounds"]),
                star_point=tuple(domain_cfg["star_point"]) if "star_point" in domain_cfg else None,
            )
            constraints.ground_domains.append(domain)

    if "clearances" in config:
        for rule_cfg in config["clearances"]:
            rule = ClearanceRule(
                from_class=rule_cfg["from"],
                to_class=rule_cfg["to"],
                clearance_mm=rule_cfg["clearance_mm"],
                description=rule_cfg.get("description", ""),
            )
            constraints.clearances.append(rule)

    if "hv_clearance_mm" in config:
        constraints.hv_clearance_mm = config["hv_clearance_mm"]

    if "critical_loops" in config:
        for loop_cfg in config["critical_loops"]:
            pins_raw = loop_cfg.get("pins")
            pins = None
            if pins_raw:
                pins = [tuple(p) for p in pins_raw if len(p) >= 2]

            loop = CriticalLoop(
                name=loop_cfg["name"],
                nets=loop_cfg.get("nets", []),
                pins=pins,
                max_area_mm2=loop_cfg.get("max_area_mm2"),
                weight=loop_cfg.get("weight", 1.0),
                description=loop_cfg.get("description", ""),
            )
            constraints.critical_loops.append(loop)

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

    if "matched_length_groups" in config:
        for name, group_cfg in config["matched_length_groups"].items():
            group = MatchedLengthGroup(
                name=name,
                tolerance_mm=group_cfg.get("tolerance_mm", 5.0),
            )
            constraints.matched_length_groups.append(group)

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

    if "thermal" in config:
        for thermal_cfg in config["thermal"]:
            min_spacing = thermal_cfg.get("min_spacing_mm", thermal_cfg.get("min_separation_mm", 5.0))
            thermal = ThermalConstraint(
                components=thermal_cfg["components"],
                prefer_edge=thermal_cfg.get("prefer_edge", True),
                min_spacing_mm=min_spacing,
                max_distance_from_edge_mm=thermal_cfg.get("max_distance_from_edge_mm", 20.0),
                description=thermal_cfg.get("description", ""),
            )
            constraints.thermal_constraints.append(thermal)

    if "thermal_properties" in config:
        tp_cfg = config["thermal_properties"]
        high_power = tp_cfg.get("high_power", {})
        heat_sensitive = tp_cfg.get("heat_sensitive", {})
        thermal_pads = tp_cfg.get("thermal_pads", {})

        constraints.thermal_properties = ThermalProperties(
            high_power_components=high_power.get("components", []),
            power_dissipation_w=high_power.get("power_dissipation_w", {}),
            min_separation_mm=high_power.get("min_separation_mm", 15.0),
            heat_sensitive_components=heat_sensitive.get("components", []),
            max_temp_rise_c=heat_sensitive.get("max_temp_rise_c", 20.0),
            min_distance_from_heat_sources_mm=heat_sensitive.get("min_distance_from_heat_sources_mm", 20.0),
            thermal_pad_components=thermal_pads.get("components", []),
            prefer_edge=thermal_pads.get("prefer_edge", True),
            preferred_edge_margin_mm=thermal_pads.get("preferred_edge_margin_mm", 10.0),
        )

    if "groups" in config:
        for group_cfg in config["groups"]:
            proximity_rules = []
            if "proximity" in group_cfg:
                for prox_cfg in group_cfg["proximity"]:
                    if isinstance(prox_cfg, dict):
                        pair = prox_cfg.get("pair", prox_cfg.get("components", []))
                        max_dist = prox_cfg.get("max_distance_mm", 10.0)
                    else:
                        pair = prox_cfg[0] if len(prox_cfg) > 0 else []
                        max_dist = prox_cfg[1] if len(prox_cfg) > 1 else 10.0
                    if len(pair) >= 2:
                        proximity_rules.append(ProximityRule(pair[0], pair[1], max_dist))

            group = ComponentGroup(
                name=group_cfg["name"],
                components=group_cfg["components"],
                max_spread_mm=group_cfg.get("max_spread_mm", 30.0),
                zone=group_cfg.get("zone"),
                proximity_rules=proximity_rules,
                weight=group_cfg.get("weight", 1.0),
                description=group_cfg.get("description", ""),
                template_group=group_cfg.get("template_group"),
                primary_pin=group_cfg.get("primary_pin"),
                stacked_layout=group_cfg.get("stacked_layout", False),
            )
            constraints.component_groups.append(group)

    if "component_groups" in config:
        for group_cfg in config["component_groups"]:
            leader = group_cfg.get("leader")
            followers = group_cfg.get("followers", [])
            components = []
            if leader: components.append(leader)
            components.extend(followers)
            if components:
                group = ComponentGroup(
                    name=group_cfg["name"],
                    components=components,
                    max_spread_mm=group_cfg.get("max_distance", 30.0),
                    zone=group_cfg.get("zone"),
                    proximity_rules=[],
                    weight=group_cfg.get("weight", 1.0),
                    description=group_cfg.get("description", ""),
                )
                constraints.component_groups.append(group)

    if "group_separation" in config:
        for sep_cfg in config["group_separation"]:
            groups = sep_cfg.get("groups", [])
            if len(groups) >= 2:
                separation = GroupSeparation(
                    group_a=groups[0], group_b=groups[1],
                    min_distance_mm=sep_cfg.get("min_distance_mm", 20.0),
                    description=sep_cfg.get("description", ""),
                )
                constraints.group_separations.append(separation)

    if "minimum_spacing" in config:
        for spacing_cfg in config["minimum_spacing"]:
            components = spacing_cfg.get("components", [])
            if len(components) >= 2:
                rule = ComponentSpacingRule(
                    component_a=components[0],
                    component_b=components[1],
                    min_separation_mm=spacing_cfg.get("min_separation_mm", 2.0),
                    description=spacing_cfg.get("description", ""),
                    weight=spacing_cfg.get("weight", 1.0),
                )
                constraints.component_spacing_rules.append(rule)

    if "manufacturing_constraints" in config:
        for mfg_cfg in config["manufacturing_constraints"]:
            mfg = ManufacturingConstraint(
                components=mfg_cfg["components"],
                allowed_orientations=mfg_cfg.get("allowed_orientations"),
                side=mfg_cfg.get("side"),
                tier=mfg_cfg.get("tier", "hard"),
                because=mfg_cfg.get("because", ""),
                weight=mfg_cfg.get("weight", 1.0),
            )
            constraints.manufacturing_constraints.append(mfg)

    if "fixed_components" in config:
        constraints.fixed_components = config["fixed_components"]
    
    if "fixed_positions" in config:
        for ref, pos in config["fixed_positions"].items():
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                constraints.fixed_positions[ref] = (float(pos[0]), float(pos[1]))
                if ref not in constraints.fixed_components:
                    constraints.fixed_components.append(ref)

    if "zone_assignments" in config:
        constraints.zone_assignments = config["zone_assignments"]

    if "net_classes" in config:
        constraints.net_classes = config["net_classes"]

    if "net_class_rules" in config:
        for name, rule_cfg in config["net_class_rules"].items():
            rule = NetClassRule(
                name=name,
                trace_width_mm=rule_cfg.get("trace_width_mm", 0.2),
                clearance_mm=rule_cfg.get("clearance_mm", 0.2),
                via_size_mm=rule_cfg.get("via_size_mm", 0.6),
                via_drill_mm=rule_cfg.get("via_drill_mm", 0.3),
                allow_neckdown=rule_cfg.get("allow_neckdown", True),
                description=rule_cfg.get("description", ""),
            )
            constraints.net_class_rules[name] = rule



    if "aesthetics" in config:
        aes = config["aesthetics"]
        constraints.aesthetics.grid_size_mm = aes.get("grid_size_mm", 0.5)
        constraints.aesthetics.grid_weight = aes.get("grid_weight", 1.0)
        constraints.aesthetics.alignment_weight = aes.get("alignment_weight", 1.0)
        constraints.aesthetics.rotation_consistency_weight = aes.get("rotation_consistency_weight", 1.0)
        constraints.aesthetics.align_by_prefix = aes.get("align_by_prefix", True)
        constraints.aesthetics.prefix_exceptions = aes.get("prefix_exceptions", [])
        constraints.aesthetics.max_wirelength_tax = aes.get("max_wirelength_tax", 2.5)
        constraints.aesthetics.consensus_weight = aes.get("consensus_weight", 1.0)
        constraints.aesthetics.whitespace_weight = aes.get("whitespace_weight", 0.0)
        constraints.aesthetics.grouping_weight = aes.get("grouping_weight", 0.0)
        constraints.aesthetics.symmetry_weight = aes.get("symmetry_weight", 0.0)

    if "manufacturing" in config:
        mfg = config["manufacturing"]
        constraints.manufacturing.target_margin_mm = mfg.get("target_margin_mm", 0.1)
        constraints.manufacturing.margin_weight = mfg.get("margin_weight", 0.0)
        constraints.manufacturing.etch_tolerance_mm = mfg.get("etch_tolerance_mm", 0.02)

    if "losses" in config:
        losses_cfg = config["losses"]
        if losses_cfg:
            losses_config = LossesConfig()
            for loss_name in [
                "overlap", "boundary", "wirelength", "spread", "edge_avoidance",
                "group_cluster", "thermal", "zone", "clearance", "loop_area", "star_point"
            ]:
                if loss_name in losses_cfg:
                    loss_data = losses_cfg[loss_name]
                    if loss_data is None: continue
                    elif isinstance(loss_data, dict):
                        w = float(loss_data.get("weight", 1.0))
                        _validate_weight(w, loss_name)
                        loss_config = LossConfig(weight=w, enabled=loss_data.get("enabled", True), margin=loss_data.get("margin"))
                    else:
                        w = float(loss_data)
                        _validate_weight(w, loss_name)
                        loss_config = LossConfig(weight=w)
                    setattr(losses_config, loss_name, loss_config)
            constraints.losses = losses_config
    
    if "loss_weights" in config and constraints.losses is None:
        loss_weights = config["loss_weights"]
        if loss_weights:
            losses_config = LossesConfig()
            weight_name_map = {
                "zone_membership": "zone", "zone": "zone", "overlap": "overlap", "boundary": "boundary",
                "wirelength": "wirelength", "spread": "spread", "edge_avoidance": "edge_avoidance",
                "group_cluster": "group_cluster", "thermal": "thermal", "clearance": "clearance",
                "loop_area": "loop_area", "star_point": "star_point",
            }
            for weight_key, weight_value in loss_weights.items():
                loss_name = weight_name_map.get(weight_key, weight_key)
                if loss_name in [
                    "overlap", "boundary", "wirelength", "spread", "edge_avoidance",
                    "group_cluster", "thermal", "zone", "clearance", "loop_area", "star_point"
                ]:
                    w = float(weight_value)
                    _validate_weight(w, loss_name)
                    loss_config = LossConfig(weight=w)
                    setattr(losses_config, loss_name, loss_config)
            constraints.losses = losses_config

    if "placement_priority" in config:
        constraints.placement_priority = config["placement_priority"]

    if "routing_priority" in config:
        constraints.routing_priority = config["routing_priority"]
    return constraints


def constraints_to_design_rules(constraints: PlacementConstraints) -> "DesignRules":
    """Convert placement constraints to routing design rules."""
    from temper_placer.core.design_rules import DesignRules, NetClassRules as CoreNetClassRules

    rules = DesignRules()

    # Copy net class assignments
    rules.net_class_assignments = constraints.net_classes.copy()

    # Copy net class definitions
    for name, rule in constraints.net_class_rules.items():
        # Map fields (note: allow_neckdown currently not supported in Core NetClassRules)
        rules.net_classes[name] = CoreNetClassRules(
            name=rule.name,
            trace_width=rule.trace_width_mm,
            clearance=rule.clearance_mm,
            via_diameter=rule.via_size_mm,
            via_drill=rule.via_drill_mm,
            creepage_mm=rule.creepage_mm,
        )

    return rules


def create_board_from_constraints(constraints: PlacementConstraints) -> Board:
    """Create a Board object from constraints configuration."""
    return Board(
        width=constraints.board_width_mm,
        height=constraints.board_height_mm,
        origin=(0.0, 0.0),
        zones=constraints.zones,
        ground_domains=constraints.ground_domains,
        keepouts=constraints.keepouts,
        layer_stackup=constraints.layer_stackup or LayerStackup.default_4layer(),
    )


def apply_zones_to_netlist(
    netlist: Netlist, constraints: PlacementConstraints
) -> None:
    """Apply zone assignments from component groups to components."""
    for group in constraints.component_groups:
        if group.zone:
            for comp_ref in group.components:
                comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                if comp:
                    comp.zone = group.zone


def apply_fixed_components_to_netlist(netlist, constraints: PlacementConstraints) -> None:
    """Apply fixed_components list from constraints to netlist."""
    if not constraints.fixed_components and not constraints.fixed_positions:
        return
    
    fixed_set = set(constraints.fixed_components)
    for comp in netlist.components:
        if comp.ref in fixed_set:
            comp.fixed = True
        
        if comp.ref in constraints.fixed_positions:
            pos = constraints.fixed_positions[comp.ref]
            comp.initial_position = pos
            comp.fixed = True