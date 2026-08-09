"""
Shared geometry helpers for PCB layout validation.

Extracted from layout_review, switching_nodes, bypass_caps, and pick_and_place
to eliminate duplicated implementations.

Wave 4: all geometry kernels now delegate to the ``temper_geometry`` Rust
crate (``packages/temper-geometry/src/geometry_kernels.rs``).  The
pre-migration implementations are pinned verbatim as ``_oracle_*`` functions
in ``tests/requirements/validators/test_geometry_rust_differential.py``,
which asserts bit-identical parity.  The public names and signatures are
unchanged.
"""

import temper_geometry as _tg


def _flatten(pts):
    out = []
    for x, y in pts:
        out.append(x)
        out.append(y)
    return out


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return _tg.geom_point_distance_py(a[0], a[1], b[0], b[1])


def _point_in_rect(
    pt: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x, y = pt
    rx, ry, rw, rh = rect
    return _tg.geom_point_in_rect_py(x, y, rx, ry, rw, rh)


def _rects_overlap(
    r1: tuple[float, float, float, float],
    r2: tuple[float, float, float, float],
) -> bool:
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return _tg.geom_rects_overlap_py(x1, y1, w1, h1, x2, y2, w2, h2)


def _point_to_segment_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Closest (perpendicular, clamped) distance from point ``p`` to segment ``a``-``b``."""
    return _tg.geom_point_to_segment_distance_py(p[0], p[1], a[0], a[1], b[0], b[1])


def _point_to_polyline_distance(
    p: tuple[float, float], polyline: list[tuple[float, float]]
) -> float:
    """Minimum distance from a point to any segment of a polyline (or to the
    single point of a degenerate one-point polyline)."""
    return _tg.geom_point_to_polyline_distance_py(p[0], p[1], _flatten(polyline))


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return _tg.geom_orientation_py(a[0], a[1], b[0], b[1], c[0], c[1])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return _tg.geom_on_segment_py(a[0], a[1], b[0], b[1], p[0], p[1])


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    """Standard orientation-based segment intersection test.

    Includes touching endpoints and collinear-overlap cases.
    """
    return _tg.geom_segments_intersect_py(a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])


def _segment_to_segment_distance(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    """Minimum distance between segment ``a``-``b`` and segment ``c``-``d``.

    Returns 0.0 if the segments intersect (including touching/collinear-overlap).
    """
    return _tg.geom_segment_to_segment_distance_py(
        a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1]
    )


def _polyline_min_distance(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> float:
    """Minimum distance between two polylines (0.0 if any segments cross)."""
    return _tg.geom_polyline_min_distance_py(_flatten(poly1), _flatten(poly2))


def _polylines_intersect(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> bool:
    """Whether any segment of poly1 crosses any segment of poly2."""
    return _tg.geom_polylines_intersect_py(_flatten(poly1), _flatten(poly2))


def _polyline_length(polyline: list[tuple[float, float]]) -> float:
    """Total path length along a polyline."""
    return _tg.geom_polyline_length_py(_flatten(polyline))
