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
from typing import Any, Dict, List, Optional, Tuple

import yaml

from temper_placer.core.board import Board, Zone, GroundDomain, LayerStackup


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
    nets: List[str]
    max_area_mm2: Optional[float] = None
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
    pins: Optional[Tuple[str, str]] = None
    max_length_mm: float = 50.0
    priority: str = "normal"
    matched_length_group: Optional[str] = None


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
    sensitive_components: List[str]
    noise_sources: List[str]
    min_distance_mm: float = 10.0
    weight: float = 1.0


@dataclass
class ThermalConstraint:
    """Thermal placement constraint for heat-generating components."""

    components: List[str]  # Component refs
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
    high_power_components: List[str] = field(default_factory=list)
    power_dissipation_w: Dict[str, float] = field(default_factory=dict)
    min_separation_mm: float = 15.0  # Between high-power components

    # Heat-sensitive components (MCU, sensors)
    heat_sensitive_components: List[str] = field(default_factory=list)
    max_temp_rise_c: float = 20.0
    min_distance_from_heat_sources_mm: float = 20.0

    # Thermal pad components (for edge preference)
    thermal_pad_components: List[str] = field(default_factory=list)
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
class AestheticConstraints:
    """Aesthetic and professional layout constraints."""

    grid_size_mm: float = 0.5
    grid_weight: float = 1.0
    alignment_weight: float = 1.0
    rotation_consistency_weight: float = 1.0
    # Alignment groups: components with same prefix should align
    align_by_prefix: bool = True
    prefix_exceptions: List[str] = field(default_factory=list)
    # The maximum allowed wirelength increase for beauty (default 2.5x)
    max_wirelength_tax: float = 2.5
    # Enforcement of identical layouts for isomorphic groups
    consensus_weight: float = 1.0


@dataclass
class ComponentGroup:
    """Group of components that should be placed together."""

    name: str
    components: List[str]
    max_spread_mm: float = 30.0  # Maximum diameter of group bounding box
    zone: Optional[str] = None  # Required zone
    proximity_rules: List[ProximityRule] = field(default_factory=list)  # Proximity within group
    description: str = ""
    # Optional ID to force identical internal layouts with other groups sharing this ID
    template_group: Optional[str] = None
    # Optional pin number/name that defines the 'front' of the group for rotation
    primary_pin: Optional[str] = None


@dataclass
class PlacementConstraints:
    """Complete set of placement constraints."""

    # Board geometry
    board_width_mm: float = 100.0
    board_height_mm: float = 150.0
    board_margin_mm: float = 3.0

    # Zones
    zones: List[Zone] = field(default_factory=list)
    ground_domains: List[GroundDomain] = field(default_factory=list)

    # Clearance rules
    clearances: List[ClearanceRule] = field(default_factory=list)
    hv_clearance_mm: float = 10.0  # Default HV-LV clearance

    # Aesthetics
    aesthetics: AestheticConstraints = field(default_factory=AestheticConstraints)

    # Critical loops (EMI-sensitive)
    critical_loops: List[CriticalLoop] = field(default_factory=list)

    # Critical paths (signal integrity)
    critical_paths: List[CriticalPath] = field(default_factory=list)

    # Matched length groups
    matched_length_groups: List[MatchedLengthGroup] = field(default_factory=list)

    # Noise isolation rules
    noise_isolation: List[NoiseIsolationRule] = field(default_factory=list)

    # Thermal constraints (basic)
    thermal_constraints: List[ThermalConstraint] = field(default_factory=list)

    # Extended thermal properties (advanced)
    thermal_properties: Optional[ThermalProperties] = None

    # Component groups
    component_groups: List[ComponentGroup] = field(default_factory=list)

    # Group separation rules
    group_separations: List[GroupSeparation] = field(default_factory=list)

    # Fixed components (won't be optimized)
    fixed_components: List[str] = field(default_factory=list)

    # Zone assignments (component -> zone)
    zone_assignments: Dict[str, str] = field(default_factory=dict)

    # Net class assignments (net_name -> class)
    net_classes: Dict[str, str] = field(default_factory=dict)

    # Layer stackup
    layer_stackup: Optional[LayerStackup] = None

    def get_zone_for_component(self, ref: str) -> Optional[str]:
        """Get required zone for a component."""
        return self.zone_assignments.get(ref)

    def get_net_class(self, net_name: str) -> str:
        """Get net class for a net, with defaults based on name."""
        if net_name in self.net_classes:
            return self.net_classes[net_name]

        # Default rules based on net name
        upper = net_name.upper()
        if "GND" in upper or "VSS" in upper:
            return "Power"
        elif (
            "VCC" in upper or "VDD" in upper or "+3V3" in upper or "+5V" in upper or "+15V" in upper
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
    with open(config_path, "r") as f:
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
