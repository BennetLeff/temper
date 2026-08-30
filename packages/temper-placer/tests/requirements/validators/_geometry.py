"""Test-side adapter for the Rust-owned requirements geometry kernels.

The requirements validators live under ``tests/`` for historical reasons,
but their geometry implementation is owned by ``temper_geometry``.  Keep
this module as a signature-preserving adapter so the validators can retain
their public call sites without introducing a second Python implementation.
"""

from __future__ import annotations

import temper_geometry as _tg


def _flatten(points: list[tuple[float, float]]) -> list[float]:
    return [coordinate for point in points for coordinate in point]


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return _tg.geom_point_distance_py(a[0], a[1], b[0], b[1])


def _point_in_rect(
    point: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x, y = point
    rx, ry, rw, rh = rect
    return _tg.geom_point_in_rect_py(x, y, rx, ry, rw, rh)


def _rects_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    x1, y1, w1, h1 = first
    x2, y2, w2, h2 = second
    return _tg.geom_rects_overlap_py(x1, y1, w1, h1, x2, y2, w2, h2)


def _point_to_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    return _tg.geom_point_to_segment_distance_py(
        point[0], point[1], start[0], start[1], end[0], end[1]
    )


def _point_to_polyline_distance(
    point: tuple[float, float], polyline: list[tuple[float, float]]
) -> float:
    return _tg.geom_point_to_polyline_distance_py(point[0], point[1], _flatten(polyline))


def _orientation(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return _tg.geom_orientation_py(
        first[0], first[1], second[0], second[1], third[0], third[1]
    )


def _on_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
) -> bool:
    return _tg.geom_on_segment_py(
        start[0], start[1], end[0], end[1], point[0], point[1]
    )


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    return _tg.geom_segments_intersect_py(
        first_start[0],
        first_start[1],
        first_end[0],
        first_end[1],
        second_start[0],
        second_start[1],
        second_end[0],
        second_end[1],
    )


def _segment_to_segment_distance(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> float:
    return _tg.geom_segment_to_segment_distance_py(
        first_start[0],
        first_start[1],
        first_end[0],
        first_end[1],
        second_start[0],
        second_start[1],
        second_end[0],
        second_end[1],
    )


def _polyline_min_distance(
    first: list[tuple[float, float]], second: list[tuple[float, float]]
) -> float:
    return _tg.geom_polyline_min_distance_py(_flatten(first), _flatten(second))


def _polylines_intersect(
    first: list[tuple[float, float]], second: list[tuple[float, float]]
) -> bool:
    return _tg.geom_polylines_intersect_py(_flatten(first), _flatten(second))


def _polyline_length(polyline: list[tuple[float, float]]) -> float:
    return _tg.geom_polyline_length_py(_flatten(polyline))
