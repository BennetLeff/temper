"""
Template-based component placement structures.
"""

from __future__ import annotations

import math
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ComponentPosition:
    """Relative position of a component within a template."""
    ref: str
    x: float
    y: float
    rotation: int = 0


@dataclass
class ParametricComponentPosition:
    """Relative position within a parametric template."""
    ref: str
    x_ratio: float
    y_ratio: float
    rotation: int = 0


@dataclass
class ComponentTemplate:
    """A template defining relative positions of components."""
    name: str
    components: list[ComponentPosition]
    anchor_point: str | None = None
    width: float = 0.0
    height: float = 0.0
    description: str = ""

    def __post_init__(self):
        if self.anchor_point is None and self.components:
            self.anchor_point = self.components[0].ref

    def get_anchor_position(self) -> ComponentPosition | None:
        for comp in self.components:
            if comp.ref == self.anchor_point:
                return comp
        return None

    def apply(self, anchor_x: float, anchor_y: float, rotation: int = 0) -> dict[str, tuple[float, float, int]]:
        anchor = self.get_anchor_position()
        if anchor is None: raise ValueError(f"Anchor point {self.anchor_point} not found")
        ax, ay = anchor.x, anchor.y
        placements = {}
        rad = math.radians(rotation)
        for comp in self.components:
            rx, ry = comp.x - ax, comp.y - ay
            if rotation != 0:
                rotated_x = rx * math.cos(rad) - ry * math.sin(rad)
                rotated_y = rx * math.sin(rad) + ry * math.cos(rad)
            else:
                rotated_x, rotated_y = rx, ry
            placements[comp.ref] = (anchor_x + rotated_x, anchor_y + rotated_y, (rotation + comp.rotation) % 360)
        return placements


@dataclass
class ParametricTemplate:
    """A template that scales based on target dimensions."""
    name: str
    components: list[ParametricComponentPosition]
    anchor_ref: str
    description: str = ""

    def apply(self, anchor_x: float, anchor_y: float, width: float, height: float, rotation: int = 0) -> dict[str, tuple[float, float, int]]:
        anchor = next((c for c in self.components if c.ref == self.anchor_ref), self.components[0])
        ax, ay = anchor.x_ratio * width, anchor.y_ratio * height
        placements = {}
        rad = math.radians(rotation)
        for comp in self.components:
            rx, ry = comp.x_ratio * width - ax, comp.y_ratio * height - ay
            if rotation != 0:
                rotated_x = rx * math.cos(rad) - ry * math.sin(rad)
                rotated_y = rx * math.sin(rad) + ry * math.cos(rad)
            else:
                rotated_x, rotated_y = rx, ry
            placements[comp.ref] = (anchor_x + rotated_x, anchor_y + rotated_y, (rotation + comp.rotation) % 360)
        return placements

    @classmethod
    def create_half_bridge(cls, q1="Q1", q2="Q2", d1="D1", d2="D2", c1="C_BUS1", c2="C_BUS2"):
        components = [
            ParametricComponentPosition(q1, 0.2, 0.8),
            ParametricComponentPosition(q2, 0.2, 0.2),
            ParametricComponentPosition(d1, 0.5, 0.8),
            ParametricComponentPosition(d2, 0.5, 0.2),
            ParametricComponentPosition(c1, 0.8, 0.5),
            ParametricComponentPosition(c2, 0.8, 0.1),
        ]
        return cls("half_bridge_parametric", components, q1, "Parametric half-bridge layout")


@dataclass
class HalfBridgeTemplate(ComponentTemplate):
    """Legacy vertical half-bridge template."""
    @classmethod
    def create_vertical(cls, q1="Q1", q2="Q2", d1="D1", d2="D2", c1="C_BUS1", c2="C_BUS2", spacing=25.0, diode_off=18.0, cap_off=28.0):
        components = [
            ComponentPosition(q1, 0.0, 0.0),
            ComponentPosition(q2, 0.0, -spacing),
            ComponentPosition(d1, diode_off, 0.0),
            ComponentPosition(d2, diode_off, -spacing),
            ComponentPosition(c1, cap_off, -spacing * 0.25),
            ComponentPosition(c2, cap_off, -spacing * 0.75),
        ]
        return cls("half_bridge_vertical", components, q1, cap_off + 15, spacing + 15, "Vertical half-bridge")


def load_template_from_yaml(path: Path) -> ComponentTemplate:
    """Load a component template from YAML."""
    with open(path) as f:
        data = yaml.safe_load(f)
    components = [ComponentPosition(c["ref"], float(c["x"]), float(c["y"]), int(c.get("rotation", 0))) for c in data["components"]]
    return ComponentTemplate(data["name"], components, data.get("anchor_point"), float(data.get("width", 0)), float(data.get("height", 0)), data.get("description", ""))
