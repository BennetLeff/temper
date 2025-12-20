"""Constraint data structures loaded from PCL YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ClearanceRule:
    """Clearance rule between net classes."""

    from_class: str
    to_class: str
    min_mm: float
    description: str = ""

    def applies_to(self, class_a: str, class_b: str) -> bool:
        """Check if this rule applies to two net classes."""
        if self.from_class == "*" or self.to_class == "*":
            return True
        return (
            (self.from_class == class_a and self.to_class == class_b) or
            (self.from_class == class_b and self.to_class == class_a)
        )


@dataclass
class ZoneDefinition:
    """Zone definition from PCL."""

    name: str
    bounds: tuple[float, float, float, float]  # x_min, y_min, x_max, y_max
    net_classes: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)


@dataclass
class LoopConstraint:
    """Critical loop constraint from PCL."""

    name: str
    nets: list[str]
    max_area_mm2: float
    weight: float = 1.0
    description: str = ""


@dataclass
class ThermalConstraint:
    """Thermal constraint from PCL."""

    components: list[str]
    prefer_edge: bool = False
    min_spacing_mm: float = 0.0
    max_distance_from_edge_mm: float = 100.0
    description: str = ""


@dataclass
class GroupConstraint:
    """Component group constraint from PCL."""

    name: str
    components: list[str]
    max_spread_mm: float = 100.0
    zone: str | None = None
    proximity_rules: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""


@dataclass
class ConstraintSet:
    """
    Complete set of constraints loaded from PCL YAML.

    This is the primary input to checks, containing all rules and
    constraints defined in the PCL file.
    """

    clearances: list[ClearanceRule] = field(default_factory=list)
    zones: list[ZoneDefinition] = field(default_factory=list)
    critical_loops: list[LoopConstraint] = field(default_factory=list)
    thermal_constraints: list[ThermalConstraint] = field(default_factory=list)
    component_groups: list[GroupConstraint] = field(default_factory=list)
    net_classes: dict[str, str] = field(default_factory=dict)
    voltage_domains: dict[str, str] = field(default_factory=dict)
    hv_clearance_mm: float = 10.0
    board_width: float = 100.0
    board_height: float = 100.0

    def get_clearance(self, class_a: str, class_b: str) -> float:
        """Get required clearance between two net classes."""
        for rule in self.clearances:
            if rule.applies_to(class_a, class_b):
                return rule.min_mm
        return 0.0  # Default: no clearance requirement

    def get_zone(self, name: str) -> ZoneDefinition | None:
        """Get zone by name."""
        for zone in self.zones:
            if zone.name == name:
                return zone
        return None

    def get_loop(self, name: str) -> LoopConstraint | None:
        """Get critical loop by name."""
        for loop in self.critical_loops:
            if loop.name == name:
                return loop
        return None

    def get_group(self, name: str) -> GroupConstraint | None:
        """Get component group by name."""
        for group in self.component_groups:
            if group.name == name:
                return group
        return None

    @classmethod
    def from_yaml(cls, path: Path) -> ConstraintSet:
        """Load constraints from PCL YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstraintSet:
        """Create constraints from dictionary."""
        # Parse clearances
        clearances = []
        for rule in data.get("clearances", []):
            clearances.append(ClearanceRule(
                from_class=rule.get("from", "*"),
                to_class=rule.get("to", "*"),
                min_mm=rule.get("clearance_mm", 0.0),
                description=rule.get("description", ""),
            ))

        # Parse zones
        zones = []
        for zone_data in data.get("zones", []):
            bounds = zone_data.get("bounds", [0, 0, 100, 100])
            zones.append(ZoneDefinition(
                name=zone_data["name"],
                bounds=tuple(bounds),
                net_classes=zone_data.get("net_classes", []),
                components=zone_data.get("components", []),
            ))

        # Parse critical loops
        loops = []
        for loop_data in data.get("critical_loops", []):
            loops.append(LoopConstraint(
                name=loop_data["name"],
                nets=loop_data.get("nets", []),
                max_area_mm2=loop_data.get("max_area_mm2", 100.0),
                weight=loop_data.get("weight", 1.0),
                description=loop_data.get("description", ""),
            ))

        # Parse thermal constraints
        thermal = []
        for t_data in data.get("thermal", []):
            thermal.append(ThermalConstraint(
                components=t_data.get("components", []),
                prefer_edge=t_data.get("prefer_edge", False),
                min_spacing_mm=t_data.get("min_spacing_mm", 0.0),
                max_distance_from_edge_mm=t_data.get("max_distance_from_edge_mm", 100.0),
                description=t_data.get("description", ""),
            ))

        # Parse groups
        groups = []
        for g_data in data.get("groups", []):
            groups.append(GroupConstraint(
                name=g_data["name"],
                components=g_data.get("components", []),
                max_spread_mm=g_data.get("max_spread_mm", 100.0),
                zone=g_data.get("zone"),
                proximity_rules=g_data.get("proximity", []),
                description=g_data.get("description", ""),
            ))

        # Board dimensions
        board = data.get("board", {})

        return cls(
            clearances=clearances,
            zones=zones,
            critical_loops=loops,
            thermal_constraints=thermal,
            component_groups=groups,
            net_classes=data.get("net_classes", {}),
            voltage_domains=data.get("voltage_domains", {}),
            hv_clearance_mm=data.get("hv_clearance_mm", 10.0),
            board_width=board.get("width_mm", 100.0),
            board_height=board.get("height_mm", 100.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "clearances": [
                {
                    "from": r.from_class,
                    "to": r.to_class,
                    "clearance_mm": r.min_mm,
                    "description": r.description,
                }
                for r in self.clearances
            ],
            "zones": [
                {
                    "name": z.name,
                    "bounds": list(z.bounds),
                    "net_classes": z.net_classes,
                    "components": z.components,
                }
                for z in self.zones
            ],
            "critical_loops": [
                {
                    "name": loop.name,
                    "nets": loop.nets,
                    "max_area_mm2": loop.max_area_mm2,
                    "weight": loop.weight,
                    "description": loop.description,
                }
                for loop in self.critical_loops
            ],
            "net_classes": self.net_classes,
            "voltage_domains": self.voltage_domains,
            "hv_clearance_mm": self.hv_clearance_mm,
            "board": {
                "width_mm": self.board_width,
                "height_mm": self.board_height,
            },
        }
