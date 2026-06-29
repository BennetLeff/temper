"""
Spatial indexing for efficient DRC queries.

Uses scipy cKDTree for O(log n) nearest-neighbor queries on PCB geometry.

Part of temper-lueu.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial import cKDTree

from temper_placer.router_v6.constraints_geometry import LineSegment, Point, RotatedRect

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass
class Track:
    """A routed track segment."""

    start: Point
    end: Point
    width: float
    net: str
    layer: int
    id: str = ""
    diff_pair_companion: str | None = None  # Companion net if part of a differential pair

    def is_diff_pair_with(self, other: Track) -> bool:
        """Check if this track and another are companions in a differential pair."""
        return (
            self.diff_pair_companion is not None
            and self.diff_pair_companion == other.net
        )

    def to_segment(self) -> LineSegment:
        """Convert to LineSegment for geometric operations."""
        return LineSegment(self.start, self.end)

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
    """A component pad."""

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
    def rot_rect(self) -> RotatedRect:
        """Get geometric representation."""
        return RotatedRect(self.center, self.size, self.rotation)

    @property
    def radius(self) -> float:
        """Bounding radius for broad-phase checks."""
        # Use circumscribed circle radius for safety
        w, h = self.size
        return (w**2 + h**2)**0.5 / 2


@dataclass
class PCBGeometry:
    """Indexed collection of all PCB geometry.

    Provides O(log n) spatial queries using cKDTree.
    """

    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)

    # Internal indices
    _track_index: cKDTree | None = field(default=None, repr=False)
    _via_index: cKDTree | None = field(default=None, repr=False)
    _pad_index: cKDTree | None = field(default=None, repr=False)
    _track_midpoints: NDArray | None = field(default=None, repr=False)
    _via_centers: NDArray | None = field(default=None, repr=False)
    _pad_centers: NDArray | None = field(default=None, repr=False)

    # ID counters
    _next_track_id: int = field(default=0, repr=False)
    _next_via_id: int = field(default=0, repr=False)
    _next_pad_id: int = field(default=0, repr=False)

    # ID lookups
    _track_map: dict[str, Track] = field(default_factory=dict, repr=False)
    _via_map: dict[str, Via] = field(default_factory=dict, repr=False)
    _pad_map: dict[str, Pad] = field(default_factory=dict, repr=False)

    def add_track(self, track: Track) -> str:
        """Add a track and return its ID.

        Note: rebuild_index() must be called after adding geometry for
        efficient queries.
        """
        if not track.id:
            track.id = f"track_{self._next_track_id}"
            self._next_track_id += 1
        self.tracks.append(track)
        self._track_map[track.id] = track
        self._track_index = None  # Invalidate index
        return track.id

    def add_via(self, via: Via) -> str:
        """Add a via and return its ID."""
        if not via.id:
            via.id = f"via_{self._next_via_id}"
            self._next_via_id += 1
        self.vias.append(via)
        self._via_map[via.id] = via
        self._via_index = None
        return via.id

    def add_pad(self, pad: Pad) -> str:
        """Add a pad and return its ID."""
        if not pad.id:
            pad.id = f"pad_{self._next_pad_id}"
            self._next_pad_id += 1
        self.pads.append(pad)
        self._pad_map[pad.id] = pad
        self._pad_index = None
        return pad.id

    def get_geometry_by_id(self, item_id: str) -> Track | Via | Pad | None:
        """Get geometry item by ID."""
        if item_id.startswith("track_"):
            return self._track_map.get(item_id)
        if item_id.startswith("via_"):
            return self._via_map.get(item_id)
        if item_id.startswith("pad_"):
            return self._pad_map.get(item_id)
        return None

    def rebuild_index(self) -> None:
        """Rebuild spatial indices for efficient queries.

        Call this after adding a batch of geometry.
        """
        # Track index using midpoints
        if self.tracks:
            midpoints = np.array(
                [[t.midpoint().x, t.midpoint().y] for t in self.tracks]
            )
            self._track_midpoints = midpoints
            self._track_index = cKDTree(midpoints)
        else:
            self._track_index = None
            self._track_midpoints = None

        # Via index
        if self.vias:
            centers = np.array([[v.center.x, v.center.y] for v in self.vias])
            self._via_centers = centers
            self._via_index = cKDTree(centers)
        else:
            self._via_index = None
            self._via_centers = None

        # Pad index
        if self.pads:
            centers = np.array([[p.center.x, p.center.y] for p in self.pads])
            self._pad_centers = centers
            self._pad_index = cKDTree(centers)
        else:
            self._pad_index = None
            self._pad_centers = None

    def query_tracks_near(
        self, point: Point, radius: float, layer: int | None = None
    ) -> list[Track]:
        """Find tracks within radius of a point.

        Args:
            point: Query point
            radius: Search radius in mm
            layer: Optional layer filter

        Returns:
            List of tracks within radius
        """
        if self._track_index is None:
            if self.tracks:
                self.rebuild_index()
            else:
                return []

        if self._track_index is None:
            return []

        indices = self._track_index.query_ball_point([point.x, point.y], radius)
        tracks = [self.tracks[i] for i in indices]

        if layer is not None:
            tracks = [t for t in tracks if t.layer == layer]

        return tracks

    def query_vias_near(self, point: Point, radius: float) -> list[Via]:
        """Find vias within radius of a point."""
        if self._via_index is None:
            if self.vias:
                self.rebuild_index()
            else:
                return []

        if self._via_index is None:
            return []

        indices = self._via_index.query_ball_point([point.x, point.y], radius)
        return [self.vias[i] for i in indices]

    def query_pads_near(
        self, point: Point, radius: float, layer: int | None = None
    ) -> list[Pad]:
        """Find pads within radius of a point."""
        if self._pad_index is None:
            if self.pads:
                self.rebuild_index()
            else:
                return []

        if self._pad_index is None:
            return []

        indices = self._pad_index.query_ball_point([point.x, point.y], radius)
        pads = [self.pads[i] for i in indices]

        if layer is not None:
            pads = [p for p in pads if p.layer == layer or p.is_pth]

        return pads

    def clear(self) -> None:
        """Remove all geometry."""
        self.tracks.clear()
        self.vias.clear()
        self.pads.clear()
        self._track_index = None
        self._via_index = None
        self._pad_index = None
def merge_collinear_tracks(tracks: list[Track]) -> list[Track]:
    """Merge collinear and connected tracks to reduce geometry count.

    Grid routing produces many small segments. Merging them reduces
    optimization complexity significantly.
    """
    if not tracks:
        return []

    # Group by net and layer
    groups: dict[tuple[str, int], list[Track]] = {}
    for t in tracks:
        key = (t.net, t.layer)
        if key not in groups:
            groups[key] = []
        groups[key].append(t)

    merged_all = []

    for _, group in groups.items():
        # Sort by start point (lexicographical x, then y)
        # This helps finding consecutive segments, but graph traversal is safer.
        # However, for grid routing, segments are usually sequential in the list
        # if they come from RoutePath. But here we have a bag of tracks.
        # Simple sorting might not follow the path if it snakes.
        # But for strictly collinear segments, sorting helps.

        # We only merge if:
        # 1. End of A == Start of B
        # 2. A and B are collinear directionally

        # Let's try to verify simple linear chains first.
        # Since we might have branches, we need to be careful.
        # But grid router produces simple paths per net usually,
        # though nets can branch.

        # Robust approach:
        # 1. Build adjacency graph
        # 2. Find chains of degree-2 nodes that are collinear

        # Optimization: Just sort by coordinates and try to merge adjacent in sorted list?
        # That works for horizontal/vertical lines well.

        # Let's implement a robust geometric merge.
        # Split into horizontal, vertical, and diagonal?
        # Grid router is mostly H/V.

        horizontal = []
        vertical = []
        others = []

        for t in group:
            dx = abs(t.end.x - t.start.x)
            dy = abs(t.end.y - t.start.y)
            if dy < 1e-9:
                # Ensure left-to-right
                if t.start.x > t.end.x:
                    t = Track(t.end, t.start, t.width, t.net, t.layer, t.id)
                horizontal.append(t)
            elif dx < 1e-9:
                # Ensure bottom-to-top
                if t.start.y > t.end.y:
                    t = Track(t.end, t.start, t.width, t.net, t.layer, t.id)
                vertical.append(t)
            else:
                others.append(t)

        # Merge horizontal
        horizontal.sort(key=lambda t: (t.start.y, t.start.x))
        if horizontal:
            current = horizontal[0]
            for next_t in horizontal[1:]:
                # Check if same Y line and overlaps/touches
                if (abs(current.start.y - next_t.start.y) < 1e-9 and
                    abs(current.end.x - next_t.start.x) < 1e-4 and # connected
                    abs(current.width - next_t.width) < 1e-9):
                    # Merge
                    current = Track(current.start, next_t.end, current.width, current.net, current.layer, current.id)
                else:
                    merged_all.append(current)
                    current = next_t
            merged_all.append(current)

        # Merge vertical
        vertical.sort(key=lambda t: (t.start.x, t.start.y))
        if vertical:
            current = vertical[0]
            for next_t in vertical[1:]:
                # Check if same X line and overlaps/touches
                if (abs(current.start.x - next_t.start.x) < 1e-9 and
                    abs(current.end.y - next_t.start.y) < 1e-4 and
                    abs(current.width - next_t.width) < 1e-9):
                    # Merge
                    current = Track(current.start, next_t.end, current.width, current.net, current.layer, current.id)
                else:
                    merged_all.append(current)
                    current = next_t
            merged_all.append(current)

        merged_all.extend(others)

    return merged_all
