"""Placement data structures for DRC checking."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
            # Overlapping
            return 0.0

        return math.sqrt(dx * dx + dy * dy)

    def overlaps(self, other: ComponentPlacement) -> bool:
        """Check if this component overlaps with another."""
        x1_min, y1_min, x1_max, y1_max = self.bounds
        x2_min, y2_min, x2_max, y2_max = other.bounds

        return not (
            x1_max < x2_min or
            x2_max < x1_min or
            y1_max < y2_min or
            y2_max < y1_min
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
