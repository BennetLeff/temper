"""
Geometry types shared between the deterministic pipeline and router_v6.

These are pure dataclass types with no dependencies on router_v6 or deterministic.
They serve as the lowest-level geometry vocabulary for pads, tracks, vias, and points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Point:
    """A 2D point."""

    x: float
    y: float

    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y])

    def distance_to(self, other: Point) -> float:
        """Euclidean distance to another point."""
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class Track:
    """A routed track segment."""

    start: Point
    end: Point
    width: float
    net: str
    layer: int
    id: str = ""
    diff_pair_companion: str | None = None

    def is_diff_pair_with(self, other: Track) -> bool:
        """Check if this track and another are companions in a differential pair."""
        return (
            self.diff_pair_companion is not None
            and self.diff_pair_companion == other.net
        )

    def midpoint(self) -> Point:
        """Get the midpoint of the track."""
        return Point(
            (self.start.x + self.end.x) / 2,
            (self.start.y + self.end.y) / 2,
        )


@dataclass
class Via:
    """A via connecting layers."""

    center: Point
    diameter: float
    drill: float
    net: str
    id: str = ""


@dataclass
class Pad:
    """A component pad for DRC/spatial queries."""

    center: Point
    shape: str  # "circle", "rect", "oval"
    size: tuple[float, float]  # (width, height) in mm
    net: str
    layer: int
    id: str = ""
    rotation: float = 0.0  # Degrees counter-clockwise
    mask_expansion: float = 0.1  # Solder mask clearance expansion
    is_pth: bool = False  # Plated Through-Hole flag (all layers)

    @property
    def radius(self) -> float:
        """Bounding radius for broad-phase checks."""
        w, h = self.size
        return (w**2 + h**2) ** 0.5 / 2
