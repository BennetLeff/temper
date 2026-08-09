"""
Geometry types shared between the deterministic pipeline and router_v6.

These are pure dataclass types with no dependencies on router_v6 or deterministic.
They serve as the lowest-level geometry vocabulary for pads, tracks, vias, and points.

Wave 4 (unit ``core_graph_cluster``): the scalar numeric methods are migrated
to ``packages/temper-geometry/src/core_graph_geometry.rs`` —
``Point.distance_to`` (CPython ``math.hypot``, the Dekker ``vector_norm``
replication), ``Track.midpoint``, and ``Pad.radius`` (``x**2`` / ``**0.5`` are
libm ``pow`` via host_math). String equality and numpy construction stay
Python. Bit-exact parity is pinned by
``tests/core/test_core_graph_cluster_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import temper_geometry as _tg


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
        return _tg.point_distance_py(self.x, self.y, other.x, other.y)


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
        return self.diff_pair_companion is not None and self.diff_pair_companion == other.net

    def midpoint(self) -> Point:
        """Get the midpoint of the track."""
        mx, my = _tg.track_midpoint_py(self.start.x, self.start.y, self.end.x, self.end.y)
        return Point(mx, my)


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
        return _tg.pad_radius_py(w, h)
