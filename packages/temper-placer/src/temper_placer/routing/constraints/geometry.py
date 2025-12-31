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
def closest_points_segment_segment(
    seg1: LineSegment, seg2: LineSegment
) -> tuple[Point, Point]:
    """Find closest points between two line segments.
    
    Args:
        seg1: First segment
        seg2: Second segment
        
    Returns:
        (p1, p2) where p1 is on seg1, p2 is on seg2, and dist(p1, p2) is minimized.
    """
    # Algorithm based on calculating the shortest distance between two lines,
    # then clamping parameters to segments.
    
    p1, q1 = seg1.start, seg1.end
    p2, q2 = seg2.start, seg2.end
    
    d1 = Point(q1.x - p1.x, q1.y - p1.y)
    d2 = Point(q2.x - p2.x, q2.y - p2.y)
    r = Point(p1.x - p2.x, p1.y - p2.y)
    
    a = d1.x * d1.x + d1.y * d1.y
    e = d2.x * d2.x + d2.y * d2.y
    f = d2.x * r.x + d2.y * r.y
    
    if a <= 1e-10 and e <= 1e-10:
        # Both segments are points
        return p1, p2
    if a <= 1e-10:
        # Seg1 is a point
        t = max(0.0, min(1.0, f / e))
        return p1, Point(p2.x + t * d2.x, p2.y + t * d2.y)
    if e <= 1e-10:
        # Seg2 is a point
        c = d1.x * r.x + d1.y * r.y
        s = max(0.0, min(1.0, -c / a))
        return Point(p1.x + s * d1.x, p1.y + s * d1.y), p2
        
    c = d1.x * r.x + d1.y * r.y
    b = d1.x * d2.x + d1.y * d2.y
    denom = a * e - b * b
    
    # Parallel lines check
    if denom != 0.0:
        s = max(0.0, min(1.0, (b * f - c * e) / denom))
    else:
        s = 0.0
        
    t = (b * s + f) / e
    
    if t < 0.0:
        t = 0.0
        s = max(0.0, min(1.0, -c / a))
    elif t > 1.0:
        t = 1.0
        s = max(0.0, min(1.0, (b - c) / a))
        
    c1 = Point(p1.x + s * d1.x, p1.y + s * d1.y)
    c2 = Point(p2.x + t * d2.x, p2.y + t * d2.y)
    return c1, c2


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


    return dist_to_center - radius


@dataclass(frozen=True)
class RotatedRect:
    """A rectangle rotated around its center."""

    center: Point
    size: tuple[float, float]  # (width, height)
    rotation: float  # Degrees counter-clockwise

    @property
    def corners(self) -> list[Point]:
        """Get the 4 corners of the rotated rectangle."""
        w, h = self.size
        # Half dimensions
        hw, hh = w / 2, h / 2
        
        # Rotation matrix
        rad = math.radians(self.rotation)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # Local corners (unrotated, center at 0,0)
        # TL, TR, BR, BL
        local_pts = [
            (-hw, -hh),
            (hw, -hh),
            (hw, hh),
            (-hw, hh)
        ]
        
        corners = []
        for lx, ly in local_pts:
            # Rotate
            rx = lx * cos_a - ly * sin_a
            ry = lx * sin_a + ly * cos_a
            # Translate
            corners.append(Point(self.center.x + rx, self.center.y + ry))
            
        return corners

    @property
    def bounding_radius(self) -> float:
        """Radius of the bounding circle."""
        w, h = self.size
        return math.hypot(w/2, h/2)


def point_to_rotated_rect_distance(point: Point, rect: RotatedRect) -> float:
    """Distance from point to rotated rectangle.
    
    Returns:
        Positive if outside, negative if inside, 0 on edge.
    """
    # Transform point into rect's local coordinate system
    dx = point.x - rect.center.x
    dy = point.y - rect.center.y
    
    rad = math.radians(-rect.rotation) # Rotate point opposite to rect rotation
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    
    local_x = dx * cos_a - dy * sin_a
    local_y = dx * sin_a + dy * cos_a
    
    # Calculate signed distance in local AABB
    hw = rect.size[0] / 2
    hh = rect.size[1] / 2
    
    # q is absolute position in first quadrant
    qx = abs(local_x) - hw
    qy = abs(local_y) - hh
    
    # Exterior distance (length of vector max(0, q))
    exterior = math.hypot(max(0.0, qx), max(0.0, qy))
    
    # Interior distance (max of q components, clamped to 0)
    # If point is inside, both qx and qy are negative.
    interior = min(max(qx, qy), 0.0)
    
    return exterior + interior


def segment_to_rotated_rect_distance(segment: LineSegment, rect: RotatedRect) -> float:
    """Distance from segment to rotated rectangle.
    
    Returns negative if intersecting.
    """
    # 1. Quick bounding circle check
    dist_to_center = point_to_segment_distance(rect.center, segment)
    # If we are really far, we can trust the bounding circle lower bound?
    # No, for DRC we need exactness to avoid false positives.
    # Only return if we are sure we are colliding?
    # Actually, we can just skip the early return and do the edge checks.
    
    # Optimization: If dist_to_center is huge, return approximate.
    # But let's be correct first.
        
    # 2. Check if segment endpoints are inside
    d_start = point_to_rotated_rect_distance(segment.start, rect)
    d_end = point_to_rotated_rect_distance(segment.end, rect)
    if d_start <= 0 or d_end <= 0:
        return min(d_start, d_end)
        
    # 3. Check distance to each of the 4 edges
    corners = rect.corners
    edges = [
        LineSegment(corners[0], corners[1]),
        LineSegment(corners[1], corners[2]),
        LineSegment(corners[2], corners[3]),
        LineSegment(corners[3], corners[0])
    ]
    
    # If segment intersects any edge, distance is 0 (or negative to indicate intersection)
    # But standard segment_to_segment returns 0 if intersecting.
    # We want to know if it's INSIDE.
    
    # If we are here, endpoints are outside.
    # So we just need point_to_segment distance from rect edges to segment?
    # No, we need to know if the segment PIERCES the rect.
    
    min_dist = float('inf')
    intersects = False
    
    for edge in edges:
        d = segment_to_segment_distance(segment, edge)
        if d < 1e-9:
            intersects = True
        min_dist = min(min_dist, d)
        
    if intersects:
        return -1.0 # Arbitrary negative to indicate collision
        
    # If no intersection and endpoints outside, it's the distance to the closest edge
    # UNLESS the rect is fully inside the segment (impossible given bounding check usually?)
    # Actually segment to rect distance is min(dist(seg, edge_i)) generally.
    
    return min_dist
