"""
Geometric primitives for DRC constraint checking.

Provides pure functions for computing distances between geometric objects
used in clearance validation.

Part of temper-lueu.2

Wave 4 migration (router_v6 core slice)
--------------------------------------
Every numeric body below now delegates to ``temper_geometry``'s
``drc_constraints_geometry`` kernel.  The *types* deliberately stay plain
frozen Python dataclasses rather than becoming pyclasses: they are stored on
``Pad``/``Track``/``PCBGeometry`` objects that the router pickles and
``copy.deepcopy``s, and a pyo3 pyclass is unpicklable by default -- the
vacuity that let PR #724's differential stay green across 941 assertions
while ``pickle`` and ``deepcopy`` were completely broken.  Keeping the
dataclasses in Python makes that failure mode structurally impossible here,
and ``test_types_are_still_plain_frozen_dataclasses`` asserts it anyway.

Bit-exactness notes (the full contract is in
``packages/temper-geometry/src/drc_constraints_geometry.rs`` and
``packages/temper-geometry/VERIFICATION.md``):

* ``math.hypot`` is CPython's compensated ``vector_norm``, not
  ``sqrt(x*x + y*y)`` -- 17.1% of random 2-vectors disagree.  The kernel
  replicates ``vector_norm``; it does not call ``f64::hypot``.
* ``math.radians`` is ``x * (pi/180)``.  The kernel uses that association;
  ``(x * pi) / 180`` disagrees on 27.9% of random angles.
* CPython ``min``/``max`` propagate NaN from the left operand only and
  return the first argument on ties.  The kernel replicates both.
* ``math.cos``/``math.sin`` raise ``ValueError('math domain error')`` on an
  infinite argument; the kernel replicates the raise at the pyo3 boundary.

DELIBERATELY NOT DELEGATED: nothing.  Every executable expression that was
in this module's pre-migration bodies now runs in Rust, except the
``np.array`` construction in :attr:`LineSegment.direction` (a container
build, not arithmetic) and the ``w, h = self.size`` tuple unpacking, whose
``ValueError`` on a malformed ``size`` is part of the public contract and is
raised before the boundary is crossed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import temper_geometry as _tg

from temper_placer.core.geometry_types import Point  # noqa: F401  re-exported

__all__ = ["Point", "LineSegment", "RotatedRect"]


@dataclass(frozen=True)
class LineSegment:
    """A line segment defined by start and end points."""

    start: Point
    end: Point

    @property
    def length(self) -> float:
        """Length of the segment."""
        return _tg.drc_segment_length_py(self.start.x, self.start.y, self.end.x, self.end.y)

    @property
    def direction(self) -> np.ndarray:
        """Unit direction vector from start to end."""
        dx, dy = _tg.drc_segment_direction_py(
            self.start.x, self.start.y, self.end.x, self.end.y
        )
        return np.array([dx, dy])

    def midpoint(self) -> Point:
        """Midpoint of the segment."""
        return Point(
            *_tg.drc_segment_midpoint_py(self.start.x, self.start.y, self.end.x, self.end.y)
        )


def point_to_segment_distance(point: Point, segment: LineSegment) -> float:
    """Compute minimum distance from point to line segment.

    Args:
        point: The query point
        segment: The line segment

    Returns:
        Minimum Euclidean distance from point to segment
    """
    return _tg.drc_point_to_segment_distance_py(
        point.x, point.y, segment.start.x, segment.start.y, segment.end.x, segment.end.y
    )


def segment_to_segment_distance(seg1: LineSegment, seg2: LineSegment) -> float:
    """Compute minimum distance between two line segments.

    Args:
        seg1: First line segment
        seg2: Second line segment

    Returns:
        Minimum Euclidean distance between the segments
    """
    return _tg.drc_segment_to_segment_distance_py(
        seg1.start.x, seg1.start.y, seg1.end.x, seg1.end.y,
        seg2.start.x, seg2.start.y, seg2.end.x, seg2.end.y,
    )


def closest_points_segment_segment(seg1: LineSegment, seg2: LineSegment) -> tuple[Point, Point]:
    """Find closest points between two line segments.

    Args:
        seg1: First segment
        seg2: Second segment

    Returns:
        (p1, p2) where p1 is on seg1, p2 is on seg2, and dist(p1, p2) is minimized.
    """
    c1x, c1y, c2x, c2y = _tg.drc_closest_points_segment_segment_py(
        seg1.start.x, seg1.start.y, seg1.end.x, seg1.end.y,
        seg2.start.x, seg2.start.y, seg2.end.x, seg2.end.y,
    )
    return Point(c1x, c1y), Point(c2x, c2y)


def _segments_intersect(seg1: LineSegment, seg2: LineSegment) -> bool:
    """Check if two line segments intersect.

    Uses cross product orientation test.
    """
    return _tg.drc_segments_intersect_py(
        seg1.start.x, seg1.start.y, seg1.end.x, seg1.end.y,
        seg2.start.x, seg2.start.y, seg2.end.x, seg2.end.y,
    )


def point_to_circle_distance(point: Point, center: Point, radius: float) -> float:
    """Distance from point to circle edge (negative if inside).

    Args:
        point: Query point
        center: Circle center
        radius: Circle radius

    Returns:
        Distance to circle edge (0 if on edge, negative if inside)
    """
    return _tg.drc_point_to_circle_distance_py(point.x, point.y, center.x, center.y, radius)


@dataclass(frozen=True)
class RotatedRect:
    """A rectangle rotated around its center."""

    center: Point
    size: tuple[float, float]  # (width, height)
    rotation: float  # Degrees counter-clockwise

    @property
    def corners(self) -> list[Point]:
        """Get the 4 corners of the rotated rectangle.

        ``self.rotation`` is populated from real board pad/component
        rotation (see ``deterministic/stages/setup.py``), so this must use
        KiCad's own footprint-child rotation convention, R(-theta) -- see
        ``temper_placer.geometry.kicad_transform``'s module docstring.  The
        Rust kernel carries the same convention; the two are pinned
        together by the differential suite and by
        ``tests/geometry/test_kicad_transform_rust_differential.py``.
        """
        w, h = self.size
        return [
            Point(x, y)
            for x, y in _tg.drc_rotated_rect_corners_py(
                self.center.x, self.center.y, w, h, self.rotation
            )
        ]

    @property
    def bounding_radius(self) -> float:
        """Radius of the bounding circle."""
        w, h = self.size
        return _tg.drc_rotated_rect_bounding_radius_py(w, h)


def point_to_rotated_rect_distance(point: Point, rect: RotatedRect) -> float:
    """Distance from point to rotated rectangle.

    Returns:
        Positive if outside, negative if inside, 0 on edge.
    """
    # `rect.size` crosses the boundary as a sequence, NOT pre-unpacked: the
    # reference indexes it (`rect.size[0]`), so a malformed size must raise
    # IndexError rather than the ValueError an unpack would raise, and it
    # must raise it *after* the rotation trig.  See `size_wh` in
    # drc_constraints_geometry.rs.
    return _tg.drc_point_to_rotated_rect_distance_py(
        point.x, point.y, rect.center.x, rect.center.y, rect.size, rect.rotation
    )


def segment_to_rotated_rect_distance(segment: LineSegment, rect: RotatedRect) -> float:
    """Distance from segment to rotated rectangle.

    Returns negative if intersecting.
    """
    return _tg.drc_segment_to_rotated_rect_distance_py(
        segment.start.x, segment.start.y, segment.end.x, segment.end.y,
        rect.center.x, rect.center.y, rect.size, rect.rotation,
    )
