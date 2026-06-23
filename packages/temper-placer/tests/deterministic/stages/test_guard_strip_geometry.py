"""
Pure shapely tests for compute_guard_strip. @req(2026-06-23-001, U4)
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString, Polygon

from temper_placer.deterministic.geometry.guard_strip import compute_guard_strip


def _rect(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_compute_guard_strip_corridor_area_matches_analytical_formula():
    outline = _rect(0.0, 0.0, 100.0, 150.0)
    width = 6.0
    hv, lv, corridor = compute_guard_strip(outline, width)
    expected = 2 * (100.0 + 150.0) * width - 4 * width**2
    assert abs(corridor.area - expected) < 0.01
    # LV region is the shrunken rectangle
    assert math.isclose(lv.area, (100.0 - 2 * width) * (150.0 - 2 * width), abs_tol=0.01)
    # HV region equals the corridor (ring around the board)
    assert math.isclose(hv.area, expected, abs_tol=0.01)


def test_compute_guard_strip_width_zero_returns_outline_as_lv():
    outline = _rect(0.0, 0.0, 100.0, 150.0)
    hv, lv, corridor = compute_guard_strip(outline, 0.0)
    assert lv.equals(outline)
    assert hv.is_empty
    assert corridor.is_empty


def test_compute_guard_strip_width_larger_than_min_side_empties_lv():
    # 10x10 board, width=6 -> LV is shrunk to (-2..2) which collapses
    outline = _rect(0.0, 0.0, 10.0, 10.0)
    hv, lv, corridor = compute_guard_strip(outline, 6.0)
    assert lv.is_empty
    assert corridor.equals(outline)
    assert hv.equals(outline)


def test_compute_guard_strip_ring_is_closed_and_no_self_intersections():
    outline = _rect(0.0, 0.0, 100.0, 150.0)
    _, _, corridor = compute_guard_strip(outline, 6.0)
    assert corridor.is_valid
    assert not corridor.is_empty
    assert corridor.exterior.is_closed
    # A clean ring is a single connected piece with one exterior ring
    assert len(list(corridor.interiors)) == 1
    assert corridor.geom_type == "Polygon"


def test_compute_guard_strip_rejects_non_polygon():
    with pytest.raises(ValueError):
        compute_guard_strip(LineString([(0, 0), (100, 0), (100, 150)]), 6.0)  # type: ignore[arg-type]


def test_compute_guard_strip_rejects_invalid_polygon():
    # A self-intersecting "polygon" — shapely marks it invalid even
    # though the input looks like a closed ring. compute_guard_strip
    # raises a ValueError (or a wrapped GEOSException) on bad geometry.
    bad = Polygon([(0, 0), (100, 100), (100, 0), (0, 100), (0, 0)])
    with pytest.raises((ValueError, Exception)):
        compute_guard_strip(bad, 6.0)


def test_compute_guard_strip_lv_region_is_inside_outline():
    outline = _rect(0.0, 0.0, 100.0, 150.0)
    _, lv, _ = compute_guard_strip(outline, 8.0)
    # LV should be entirely within outline
    assert lv.within(outline)
    # LV should be strictly smaller than outline
    assert lv.area < outline.area
