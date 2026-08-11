"""VERBATIM pre-migration oracle for
``deterministic/stages/zone_aware_slot_generation.py``.

Wave 4, **Phase 5, final leaves**. Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py``
at the dispatch base (origin/main a596ce61f). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

Four geometry kernels are pinned as module-level functions:

- ``_point_in_polygon`` (ray-casting) — the copper-zone containment test.
- ``_slot_intersects_iso`` — AABB-vs-AABB cutout test.
- ``_min_distance_to_polygon`` — minimum point-to-segment distance over the
  polygon's edges (``inf`` for degenerate polygons).
- ``_point_to_segment_distance`` — projection distance.

The surrounding stage orchestration (zone walking, ``_is_slot_in_copper_zone``
bounds-margin branch, ``copper_zone_margin``) stays Python in the shim.

Numerical pins (see the differential):
- ``_point_to_segment_distance`` closes with ``math.hypot`` — RE-PINNED
  2026-08-11 (issue #987) from the Wave-4 ``** 0.5`` (libm ``pow``) close:
  the reimplementation it mirrored was deleted in the point-to-segment
  dedupe, and the oracle now mirrors temper-geometry's canonical hypot
  contract (≤1-ulp, decision-immune on real inputs — see
  ``docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md``).
- ``t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / l2))`` — Python
  ``max``/``min`` (first argument on ties).
- ``_point_in_polygon``: the ``xinters`` ternary is
  ``(y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x if p1y != p2y else x``
  (division precedence), the boundary rules are the classic ray-casting
  half-open tests, and the vertex walk is ``range(1, n + 1)`` with
  ``polygon[i % n]``.
- ``_min_distance_to_polygon``: ``float("inf")`` sentinel; ``min_dist = min
  (min_dist, dist)`` over edges in polygon order; ``len(polygon) < 2`` -> inf.
"""

from __future__ import annotations

import math


def point_in_polygon(
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
) -> bool:
    """The module-level ``_point_in_polygon`` (ray casting)."""
    if len(polygon) < 3:
        return False

    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x if p1y != p2y else x
            if p1x == p2x or x <= xinters:
                inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def slot_intersects_iso(
    slot: tuple[float, float],
    iso_aabbs: list[tuple[tuple[float, float], tuple[float, float]]],
) -> bool:
    """The module-level ``_slot_intersects_iso`` (AABB containment)."""
    sx, sy = slot
    for (x_lo, y_lo), (x_hi, y_hi) in iso_aabbs:
        if x_lo <= sx <= x_hi and y_lo <= sy <= y_hi:
            return True
    return False


def min_distance_to_polygon(
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
) -> float:
    """The ``RoutingChannelAwareSlotStage._min_distance_to_polygon`` (body only)."""
    if len(polygon) < 2:
        return float("inf")

    min_dist = float("inf")
    n = len(polygon)

    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]

        dist = point_to_segment_distance(x, y, p1, p2)
        min_dist = min(min_dist, dist)

    return min_dist


def point_to_segment_distance(
    px: float,
    py: float,
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> float:
    """The ``RoutingChannelAwareSlotStage._point_to_segment_distance`` (body only).

    Re-pinned 2026-08-11 (issue #987) to the canonical temper-geometry
    contract (creepage_check): the Wave-4 ``pow(pow+pow, 0.5)`` copy this
    oracle used to mirror was deleted. CPython ``math.hypot`` == the Rust
    ``py_hypot`` Dekker double-double; ``denom == 0`` OR non-finite triggers
    the degenerate arm; builtin ``min``/``max`` clamp a NaN ``t`` to 1.0.
    ≤1-ulp, decision-immune on real inputs
    (docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md).
    """
    x1, y1 = p1
    x2, y2 = p2

    dx = x2 - x1
    dy = y2 - y1

    denom = dx * dx + dy * dy

    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - x1, py - y1)

    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / denom))

    proj_x = x1 + t * dx
    proj_y = y1 + t * dy

    return math.hypot(px - proj_x, py - proj_y)
