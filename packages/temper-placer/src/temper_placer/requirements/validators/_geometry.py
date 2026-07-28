"""
Shared geometry helpers for PCB layout validation.

Extracted from layout_review, switching_nodes, bypass_caps, and pick_and_place
to eliminate duplicated implementations.
"""

import math


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.dist(a, b)


def _point_in_rect(
    pt: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x, y = pt
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _rects_overlap(
    r1: tuple[float, float, float, float],
    r2: tuple[float, float, float, float],
) -> bool:
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1)


# =============================================================================
# Polyline / segment helpers (added for emi_filter.py and ground_plane.py --
# distinct from the whole-route clearance machinery in
# router_v6/clearance_check.py, which operates on compiled RoutingResults
# routes with per-layer widths/vias, not bare point-lists. These operate on
# the plain ``list[tuple[float, float]]`` polyline representation the EMC
# requirement validators use.)
# =============================================================================


def _point_to_segment_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Closest (perpendicular, clamped) distance from point ``p`` to segment ``a``-``b``."""
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    len2 = abx * abx + aby * aby
    if len2 < 1e-12:
        return _distance(p, a)
    t = ((px - ax) * abx + (py - ay) * aby) / len2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    return _distance(p, (cx, cy))


def _point_to_polyline_distance(
    p: tuple[float, float], polyline: list[tuple[float, float]]
) -> float:
    """Minimum distance from a point to any segment of a polyline (or to the
    single point of a degenerate one-point polyline)."""
    if not polyline:
        return math.inf
    if len(polyline) == 1:
        return _distance(p, polyline[0])
    return min(
        _point_to_segment_distance(p, polyline[i], polyline[i + 1])
        for i in range(len(polyline) - 1)
    )


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9) and (
        min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    """Standard orientation-based segment intersection test.

    Includes touching endpoints and collinear-overlap cases.
    """
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)

    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)):
        return True

    eps = 1e-9
    if abs(o1) < eps and _on_segment(a, b, c):
        return True
    if abs(o2) < eps and _on_segment(a, b, d):
        return True
    if abs(o3) < eps and _on_segment(c, d, a):
        return True
    return bool(abs(o4) < eps and _on_segment(c, d, b))


def _segment_to_segment_distance(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    """Minimum distance between segment ``a``-``b`` and segment ``c``-``d``.

    Returns 0.0 if the segments intersect (including touching/collinear-overlap).
    """
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _point_to_segment_distance(a, c, d),
        _point_to_segment_distance(b, c, d),
        _point_to_segment_distance(c, a, b),
        _point_to_segment_distance(d, a, b),
    )


def _polyline_min_distance(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> float:
    """Minimum distance between two polylines (0.0 if any segments cross)."""
    if not poly1 or not poly2:
        return math.inf
    if len(poly1) == 1:
        return _point_to_polyline_distance(poly1[0], poly2)
    if len(poly2) == 1:
        return _point_to_polyline_distance(poly2[0], poly1)
    best = math.inf
    for i in range(len(poly1) - 1):
        for j in range(len(poly2) - 1):
            d = _segment_to_segment_distance(poly1[i], poly1[i + 1], poly2[j], poly2[j + 1])
            if d < best:
                best = d
            if best <= 0.0:
                return 0.0
    return best


def _polylines_intersect(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> bool:
    """Whether any segment of poly1 crosses any segment of poly2."""
    if len(poly1) < 2 or len(poly2) < 2:
        return False
    for i in range(len(poly1) - 1):
        for j in range(len(poly2) - 1):
            if _segments_intersect(poly1[i], poly1[i + 1], poly2[j], poly2[j + 1]):
                return True
    return False


def _polyline_length(polyline: list[tuple[float, float]]) -> float:
    """Total path length along a polyline."""
    if len(polyline) < 2:
        return 0.0
    return sum(_distance(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))
