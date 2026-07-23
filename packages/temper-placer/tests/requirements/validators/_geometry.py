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
