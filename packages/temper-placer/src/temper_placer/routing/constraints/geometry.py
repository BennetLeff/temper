"""
Geometric primitives for DRC constraint checking.

Provides pure functions for computing distances between geometric objects
used in clearance validation.

Part of temper-lueu.2
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


@dataclass(frozen=True)
class LineSegment:
    """A line segment defined by start and end points."""

    start: Point
    end: Point

    @property
    def length(self) -> float:
        """Length of the segment."""
        return self.start.distance_to(self.end)

    @property
    def direction(self) -> np.ndarray:
        """Unit direction vector from start to end."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        length = math.hypot(dx, dy)
        if length < 1e-10:
            return np.array([1.0, 0.0])  # Degenerate segment
        return np.array([dx / length, dy / length])

    def midpoint(self) -> Point:
        """Midpoint of the segment."""
        return Point(
            (self.start.x + self.end.x) / 2,
            (self.start.y + self.end.y) / 2,
        )


def point_to_segment_distance(point: Point, segment: LineSegment) -> float:
    """Compute minimum distance from point to line segment.

    Args:
        point: The query point
        segment: The line segment

    Returns:
        Minimum Euclidean distance from point to segment
    """
    # Vector from segment start to point
    px = point.x - segment.start.x
    py = point.y - segment.start.y

    # Segment vector
    sx = segment.end.x - segment.start.x
    sy = segment.end.y - segment.start.y

    # Squared length of segment
    seg_len_sq = sx * sx + sy * sy

    # Handle degenerate segment (point)
    if seg_len_sq < 1e-10:
        return math.hypot(px, py)

    # Project point onto segment line, clamp to [0, 1]
    t = max(0.0, min(1.0, (px * sx + py * sy) / seg_len_sq))

    # Closest point on segment
    closest_x = segment.start.x + t * sx
    closest_y = segment.start.y + t * sy

    return math.hypot(point.x - closest_x, point.y - closest_y)


def segment_to_segment_distance(seg1: LineSegment, seg2: LineSegment) -> float:
    """Compute minimum distance between two line segments.

    Args:
        seg1: First line segment
        seg2: Second line segment

    Returns:
        Minimum Euclidean distance between the segments
    """
    # Check if segments intersect
    if _segments_intersect(seg1, seg2):
        return 0.0

    # Distance is minimum of point-to-segment distances for all 4 endpoints
    d1 = point_to_segment_distance(seg1.start, seg2)
    d2 = point_to_segment_distance(seg1.end, seg2)
    d3 = point_to_segment_distance(seg2.start, seg1)
    d4 = point_to_segment_distance(seg2.end, seg1)

    return min(d1, d2, d3, d4)


def _segments_intersect(seg1: LineSegment, seg2: LineSegment) -> bool:
    """Check if two line segments intersect.

    Uses cross product orientation test.
    """
    def _orientation(p: Point, q: Point, r: Point) -> int:
        """Return orientation: 0=collinear, 1=clockwise, 2=counter-clockwise."""
        val = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)
        if abs(val) < 1e-10:
            return 0
        return 1 if val > 0 else 2

    def _on_segment(p: Point, q: Point, r: Point) -> bool:
        """Check if point q lies on segment pr."""
        return (
            min(p.x, r.x) <= q.x <= max(p.x, r.x)
            and min(p.y, r.y) <= q.y <= max(p.y, r.y)
        )

    p1, q1 = seg1.start, seg1.end
    p2, q2 = seg2.start, seg2.end

    o1 = _orientation(p1, q1, p2)
    o2 = _orientation(p1, q1, q2)
    o3 = _orientation(p2, q2, p1)
    o4 = _orientation(p2, q2, q1)

    # General case
    if o1 != o2 and o3 != o4:
        return True

    # Collinear cases
    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    return bool(o4 == 0 and _on_segment(p2, q1, q2))


def point_to_circle_distance(point: Point, center: Point, radius: float) -> float:
    """Distance from point to circle edge (negative if inside).

    Args:
        point: Query point
        center: Circle center
        radius: Circle radius

    Returns:
        Distance to circle edge (0 if on edge, negative if inside)
    """
    return point.distance_to(center) - radius


def segment_to_circle_distance(
    segment: LineSegment, center: Point, radius: float
) -> float:
    """Minimum distance from segment to circle edge.

    Args:
        segment: Line segment
        center: Circle center
        radius: Circle radius

    Returns:
        Distance to circle edge (0 if touching, negative if intersecting)
    """
    dist_to_center = point_to_segment_distance(center, segment)
    return dist_to_center - radius
