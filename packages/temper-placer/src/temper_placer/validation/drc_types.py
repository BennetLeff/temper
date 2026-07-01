"""
DRC type definitions — Placement, constraints, and geometric types.

Moved from the now-removed ``temper-drc`` Python package.  All DRC
execution is delegated to the Rust crate ``temper-drc-rs``; these
types remain for backward-compatible data construction and are
consumed by the ``CheckRunner`` adapter in ``drc_runner.py``.

Former locations (unified after temper-drc deletion):
  - ``temper_drc.input.placement`` → Placement, ComponentPlacement
  - ``temper_drc.input.constraints`` → ConstraintSet, ClearanceRule, …
  - ``temper_drc.types`` → Via, ViaPlacement, TracePlacement, TraceSegment
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


# =========================================================================
#  Component / Placement  (was temper_drc.input.placement)
# =========================================================================


@dataclass
class ComponentPlacement:
    """
    Single component placement on the PCB.

    Attributes:
        ref: Reference designator (e.g., "Q1", "U_MCU").
        footprint: Footprint name.
        x: Center X position in mm.
        y: Center Y position in mm.
        rotation: Rotation angle in degrees.
        layer: PCB layer ("F.Cu" or "B.Cu").
        width: Component width in mm.
        height: Component height in mm.
        net_class: Assigned net class (default: "Signal").
        voltage_domain: Voltage domain (optional).
    """

    ref: str
    footprint: str
    x: float
    y: float
    rotation: float
    layer: str
    width: float
    height: float
    net_class: str = "Signal"
    voltage_domain: str | None = None

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Get bounding box (x_min, y_min, x_max, y_max)."""
        hw, hh = self.width / 2, self.height / 2
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)

    @property
    def center(self) -> tuple[float, float]:
        """Get center point."""
        return (self.x, self.y)

    def distance_to(self, other: ComponentPlacement) -> float:
        """Calculate center-to-center distance to another component."""
        dx = self.x - other.x
        dy = self.y - other.y
        return math.sqrt(dx * dx + dy * dy)

    def edge_distance_to(self, other: ComponentPlacement) -> float:
        """Calculate edge-to-edge distance (minimum clearance)."""
        x1_min, y1_min, x1_max, y1_max = self.bounds
        x2_min, y2_min, x2_max, y2_max = other.bounds

        # Calculate gap in each direction
        dx = max(0, max(x1_min - x2_max, x2_min - x1_max))
        dy = max(0, max(y1_min - y2_max, y2_min - y1_max))

        if dx == 0 and dy == 0:
            return 0.0

        return math.sqrt(dx * dx + dy * dy)

    def overlaps(self, other: ComponentPlacement) -> bool:
        """Check if this component overlaps with another."""
        x1_min, y1_min, x1_max, y1_max = self.bounds
        x2_min, y2_min, x2_max, y2_max = other.bounds

        return not (
            x1_max < x2_min
            or x2_max < x1_min
            or y1_max < y2_min
            or y2_max < y1_min
        )

    def overlap_area(self, other: ComponentPlacement) -> float:
        """Calculate overlap area with another component."""
        x1_min, y1_min, x1_max, y1_max = self.bounds
        x2_min, y2_min, x2_max, y2_max = other.bounds

        x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
        y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))

        return x_overlap * y_overlap

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ref": self.ref,
            "footprint": self.footprint,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            "layer": self.layer,
            "width": self.width,
            "height": self.height,
            "net_class": self.net_class,
            "voltage_domain": self.voltage_domain,
        }


@dataclass
class Placement:
    """
    Complete placement data for DRC checking.

    Attributes:
        components: Map of ref -> ComponentPlacement.
        nets: Map of net_name -> list of component refs.
        zones: Map of zone_name -> (x_min, y_min, x_max, y_max).
        board_width: Board width in mm.
        board_height: Board height in mm.
        net_classes: Map of net_name -> net_class.
        voltage_domains: Map of net_name -> voltage_domain.
    """

    components: dict[str, ComponentPlacement] = field(default_factory=dict)
    nets: dict[str, list[str]] = field(default_factory=dict)
    zones: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    board_width: float = 100.0
    board_height: float = 100.0
    net_classes: dict[str, str] = field(default_factory=dict)
    voltage_domains: dict[str, str] = field(default_factory=dict)
    via_placement: Any = None
    trace_placement: Any = None

    def get_component(self, ref: str) -> ComponentPlacement | None:
        """Get a component by reference."""
        return self.components.get(ref)

    def components_in_zone(self, zone_name: str) -> list[str]:
        """Get all component refs in a zone."""
        if zone_name not in self.zones:
            return []

        x_min, y_min, x_max, y_max = self.zones[zone_name]
        refs = []

        for ref, comp in self.components.items():
            if x_min <= comp.x <= x_max and y_min <= comp.y <= y_max:
                refs.append(ref)

        return refs

    def distance_between(self, ref_a: str, ref_b: str) -> float | None:
        """Get center-to-center distance between two components."""
        a = self.components.get(ref_a)
        b = self.components.get(ref_b)
        if a is None or b is None:
            return None
        return a.distance_to(b)

    def edge_distance_between(self, ref_a: str, ref_b: str) -> float | None:
        """Get edge-to-edge distance between two components."""
        a = self.components.get(ref_a)
        b = self.components.get(ref_b)
        if a is None or b is None:
            return None
        return a.edge_distance_to(b)

    def get_net_class(self, net_name: str) -> str:
        """Get net class for a net, defaulting to 'Signal'."""
        return self.net_classes.get(net_name, "Signal")

    def get_voltage_domain(self, net_name: str) -> str | None:
        """Get voltage domain for a net."""
        return self.voltage_domains.get(net_name)

    def all_pairs(self) -> list[tuple[str, str]]:
        """Generate all unique component pairs."""
        refs = list(self.components.keys())
        pairs = []
        for i, ref_a in enumerate(refs):
            for ref_b in refs[i + 1:]:
                pairs.append((ref_a, ref_b))
        return pairs

    @classmethod
    def from_yaml(cls, path: Path) -> Placement:
        """Load placement from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Placement:
        """Create placement from dictionary."""
        components = {}
        for comp_data in data.get("components", []):
            comp = ComponentPlacement(
                ref=comp_data["ref"],
                footprint=comp_data.get("footprint", ""),
                x=comp_data["x"],
                y=comp_data["y"],
                rotation=comp_data.get("rotation", 0.0),
                layer=comp_data.get("layer", "F.Cu"),
                width=comp_data.get("width", 1.0),
                height=comp_data.get("height", 1.0),
                net_class=comp_data.get("net_class", "Signal"),
                voltage_domain=comp_data.get("voltage_domain"),
            )
            components[comp.ref] = comp

        zones = {}
        for zone_data in data.get("zones", []):
            bounds = zone_data.get("bounds", [0, 0, 100, 100])
            zones[zone_data["name"]] = tuple(bounds)

        return cls(
            components=components,
            nets=data.get("nets", {}),
            zones=zones,
            board_width=data.get("board_width", 100.0),
            board_height=data.get("board_height", 100.0),
            net_classes=data.get("net_classes", {}),
            voltage_domains=data.get("voltage_domains", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "components": [c.to_dict() for c in self.components.values()],
            "nets": self.nets,
            "zones": [
                {"name": name, "bounds": list(bounds)}
                for name, bounds in self.zones.items()
            ],
            "board_width": self.board_width,
            "board_height": self.board_height,
            "net_classes": self.net_classes,
            "voltage_domains": self.voltage_domains,
        }


# =========================================================================
#  Constraints  (was temper_drc.input.constraints)
# =========================================================================


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
        return (self.from_class == class_a and self.to_class == class_b) or (
            self.from_class == class_b and self.to_class == class_a
        )


@dataclass
class ZoneDefinition:
    """Zone definition from PCL."""

    name: str
    bounds: tuple[float, float, float, float]
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
        return 0.0

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
        clearances = []
        clearances_data = data.get("clearances", [])

        if isinstance(clearances_data, dict):
            for key, value in clearances_data.items():
                parts = key.split("-")
                if len(parts) == 2:
                    clearances.append(
                        ClearanceRule(
                            from_class=parts[0],
                            to_class=parts[1],
                            min_mm=float(value),
                            description="",
                        )
                    )
        elif isinstance(clearances_data, list):
            for rule in clearances_data:
                clearances.append(
                    ClearanceRule(
                        from_class=rule.get("from", "*"),
                        to_class=rule.get("to", "*"),
                        min_mm=rule.get("clearance_mm", 0.0),
                        description=rule.get("description", ""),
                    )
                )

        zones = []
        for zone_data in data.get("zones", []):
            bounds = zone_data.get("bounds", [0, 0, 100, 100])
            zones.append(
                ZoneDefinition(
                    name=zone_data["name"],
                    bounds=tuple(bounds),
                    net_classes=zone_data.get("net_classes", []),
                    components=zone_data.get("components", []),
                )
            )

        loops = []
        for loop_data in data.get("critical_loops", []):
            loops.append(
                LoopConstraint(
                    name=loop_data["name"],
                    nets=loop_data.get("nets", []),
                    max_area_mm2=loop_data.get("max_area_mm2", 100.0),
                    weight=loop_data.get("weight", 1.0),
                    description=loop_data.get("description", ""),
                )
            )

        thermal = []
        for t_data in data.get("thermal", []):
            thermal.append(
                ThermalConstraint(
                    components=t_data.get("components", []),
                    prefer_edge=t_data.get("prefer_edge", False),
                    min_spacing_mm=t_data.get("min_spacing_mm", 0.0),
                    max_distance_from_edge_mm=t_data.get("max_distance_from_edge_mm", 100.0),
                    description=t_data.get("description", ""),
                )
            )

        groups = []
        for g_data in data.get("groups", []):
            groups.append(
                GroupConstraint(
                    name=g_data["name"],
                    components=g_data.get("components", []),
                    max_spread_mm=g_data.get("max_spread_mm", 100.0),
                    zone=g_data.get("zone"),
                    proximity_rules=g_data.get("proximity", []),
                    description=g_data.get("description", ""),
                )
            )

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


# =========================================================================
#  Via / Trace types  (was temper_drc.types)
# =========================================================================


@dataclass
class Via:
    """A single via for DRC clearance and annular ring checks."""

    position: tuple[float, float]
    from_layer: str
    to_layer: str
    diameter: float
    drill: float
    net_name: str

    @property
    def radius(self) -> float:
        return self.diameter / 2.0


@dataclass
class ViaPlacement:
    """Collection of placed vias for DRC checking."""

    vias: list[Via] = field(default_factory=list)

    @property
    def via_count(self) -> int:
        return len(self.vias)

    def get_vias_for_net(self, net_name: str) -> list[Via]:
        return [v for v in self.vias if v.net_name == net_name]


@dataclass
class TraceSegment:
    """A single trace segment for DRC clearance checks."""

    net_name: str
    layer: str
    width: float
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def length(self) -> float:
        return math.sqrt(
            (self.end[0] - self.start[0]) ** 2
            + (self.end[1] - self.start[1]) ** 2
        )

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        hw = self.width / 2.0
        return (
            min(self.start[0], self.end[0]) - hw,
            min(self.start[1], self.end[1]) - hw,
            max(self.start[0], self.end[0]) + hw,
            max(self.start[1], self.end[1]) + hw,
        )


@dataclass
class TracePlacement:
    """Collection of routed trace segments for DRC checking."""

    segments: list[TraceSegment] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def get_segments_for_net(self, net_name: str) -> list[TraceSegment]:
        return [s for s in self.segments if s.net_name == net_name]
