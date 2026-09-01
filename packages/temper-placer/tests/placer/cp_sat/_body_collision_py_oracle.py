"""Pinned Shapely oracle for the Rust F.Fab relation.

This is intentionally independent of the production ``body_collision.py``
audit.  It models only the geometry contract needed by U1: real polygon
intersection, KiCad's clockwise quarter-turn convention, and the shared
1e-6 mm² boundary tolerance.
"""

from __future__ import annotations

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

AREA_TOLERANCE_MM2 = 1e-6


def classify(
    points_a: list[tuple[float, float]],
    pose_a: tuple[float, float, int],
    points_b: list[tuple[float, float]],
    pose_b: tuple[float, float, int],
) -> tuple[str, float]:
    def world(points, pose):
        x, y, quadrant = pose
        polygon = Polygon(points)
        return translate(rotate(polygon, -90.0 * quadrant, origin=(0.0, 0.0)), xoff=x, yoff=y)

    polygon_a = world(points_a, pose_a)
    polygon_b = world(points_b, pose_b)
    if not polygon_a.bounds or not polygon_b.bounds:
        return ("clear", 0.0)
    ax0, ay0, ax1, ay1 = polygon_a.bounds
    bx0, by0, bx1, by1 = polygon_b.bounds
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return ("clear", 0.0)
    area = float(polygon_a.intersection(polygon_b).area)
    if area > AREA_TOLERANCE_MM2:
        return ("overlap", area)
    if polygon_a.intersects(polygon_b):
        return ("boundary_touch", 0.0)
    return ("clear", 0.0)
