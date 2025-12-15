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
class ThermalConstraint:
    """Thermal placement constraint for heat-generating components."""

    components: List[str]  # Component refs
    prefer_edge: bool = True  # Place near board edge
    min_spacing_mm: float = 5.0  # Minimum spacing between thermal components
    max_distance_from_edge_mm: float = 20.0
    description: str = ""


@dataclass
class ComponentGroup:
    """Group of components that should be placed together."""

    name: str
    components: List[str]
    max_spread_mm: float = 30.0  # Maximum spread of group centroid
    zone: Optional[str] = None  # Required zone
    description: str = ""


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

    # Critical loops (EMI-sensitive)
    critical_loops: List[CriticalLoop] = field(default_factory=list)

    # Thermal constraints
    thermal_constraints: List[ThermalConstraint] = field(default_factory=list)

    # Component groups
    component_groups: List[ComponentGroup] = field(default_factory=list)

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

    # Parse component groups
    if "groups" in config:
        for group_cfg in config["groups"]:
            group = ComponentGroup(
                name=group_cfg["name"],
                components=group_cfg["components"],
                max_spread_mm=group_cfg.get("max_spread_mm", 30.0),
                zone=group_cfg.get("zone"),
                description=group_cfg.get("description", ""),
            )
            constraints.component_groups.append(group)

    # Parse fixed components
    if "fixed_components" in config:
        constraints.fixed_components = config["fixed_components"]

    # Parse zone assignments
    if "zone_assignments" in config:
        constraints.zone_assignments = config["zone_assignments"]

    # Parse net classes
    if "net_classes" in config:
        constraints.net_classes = config["net_classes"]

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
