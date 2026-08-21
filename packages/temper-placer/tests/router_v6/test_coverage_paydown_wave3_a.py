"""Coverage paydown tests — Wave 3 easy wins (Batch A).

Covers simple pure functions and dataclass properties across router_v6
that are on the allowlist but have no exercising test.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_geometry as _tg

from temper_placer.router_v6 import constraints_geometry as CG
from temper_placer.router_v6._astar_theta_star import (
    get_los_bb_stats,
    log_los_bb_stats,
    reset_los_bb_stats,
)
from temper_placer.router_v6.astar_core import (
    RouteNode3D,
    RoutePath,
    RoutePath3D,
    in_bounds,
    octile_distance,
)
from temper_placer.router_v6.astar_core_rust import (
    RouteProfileStats,
    get_route_profile_stats,
    reset_route_profile_stats,
)
from temper_placer.router_v6.grid_types import (
    GridCell,
)
from temper_placer.router_v6.path_simplify import (
    estimate_segment_count,
    is_collinear,
    simplify_path,
)


# ── astar_core module-level helpers ────────────────────────────────


def test_octile_distance_cardinal():
    assert octile_distance((0, 0), (5, 0)) == pytest.approx(5.0)


def test_octile_distance_diagonal():
    import math

    expected = max(5, 5) + (math.sqrt(2.0) - 1.0) * min(5, 5)
    assert octile_distance((0, 0), (5, 5)) == pytest.approx(expected)


def test_octile_distance_mixed():
    import math

    expected = max(3, 5) + (math.sqrt(2.0) - 1.0) * min(3, 5)
    assert octile_distance((0, 0), (3, 5)) == pytest.approx(expected)


def test_octile_distance_same_point():
    assert octile_distance((1, 2), (1, 2)) == pytest.approx(0.0)


def test_in_bounds_inside():
    assert in_bounds(5, 5, 10, 10) is True


def test_in_bounds_edge():
    assert in_bounds(0, 0, 10, 10) is True
    assert in_bounds(9, 9, 10, 10) is True


def test_in_bounds_outside():
    assert in_bounds(-1, 0, 10, 10) is False
    assert in_bounds(0, -1, 10, 10) is False
    assert in_bounds(10, 0, 10, 10) is False
    assert in_bounds(0, 10, 10, 10) is False


# ── astar_core RoutePath ───────────────────────────────────────────


def test_route_path_segment_count():
    """RoutePath.segment_count property."""
    p = RoutePath("N", [(0, 0), (1, 1), (2, 2)], "F.Cu", 10.0)
    assert p.segment_count == 2


def test_route_path_single_point():
    p = RoutePath("N", [(0, 0)], "F.Cu", 10.0)
    assert p.segment_count == 0


def test_route_path_success():
    p = RoutePath("N", [(0, 0), (1, 1)], "F.Cu", 10.0)
    assert p.success is True


def test_route_path_failure_empty():
    p = RoutePath("N", [(0, 0)], "F.Cu", 10.0)
    assert p.success is False


def test_route_path_forced_segment_default():
    p = RoutePath("N", [(0, 0), (1, 1)], "F.Cu", 10.0)
    assert p.forced_segment_count == 0


# ── astar_core RoutePath3D ─────────────────────────────────────────


def test_route_path3d_segment_count():
    p = RoutePath3D(
        "N", [(0, 0, "F.Cu"), (1, 1, "F.Cu"), (2, 2, "F.Cu")], [], 10.0
    )
    assert p.segment_count == 2


def test_route_path3d_to_route_path():
    p3d = RoutePath3D(
        "NET1",
        [(0.0, 0.0, "F.Cu"), (5.0, 5.0, "F.Cu")],
        [],
        7.07,
        forced_segment_count=1,
        failed_waypoint_indices=[0],
    )
    rp = p3d.to_route_path(default_layer="F.Cu")
    assert rp.net_name == "NET1"
    assert rp.coordinates == [(0.0, 0.0), (5.0, 5.0)]
    assert rp.layer_name == "F.Cu"
    assert rp.path_length == 7.07
    assert rp.forced_segment_count == 1
    assert rp.failed_waypoint_indices == [0]


def test_route_node3d_hash_eq():
    a = RouteNode3D(1, 2, "F.Cu")
    b = RouteNode3D(1, 2, "F.Cu")
    c = RouteNode3D(1, 2, "B.Cu")
    assert hash(a) == hash(b)
    assert a == b
    assert a != c
    assert a != (1, 2, "F.Cu")  # not a RouteNode3D


# ── astar_core LOS BB stats ────────────────────────────────────────


def test_reset_los_bb_stats():
    # just exercise — function resets module globals
    reset_los_bb_stats()
    hits, falls = get_los_bb_stats()
    assert hits == 0
    assert falls == 0


def test_log_los_bb_stats():
    reset_los_bb_stats()
    # Log calls; shouldn't raise
    log_los_bb_stats()


def test_los_stats_after_reset():
    reset_los_bb_stats()
    hits, falls = get_los_bb_stats()
    assert isinstance(hits, int)
    assert isinstance(falls, int)


# ── astar_core_rust ────────────────────────────────────────────────


def test_route_profile_stats_reset():
    s = RouteProfileStats(rust_time_ms=100.0, python_time_ms=50.0)
    s.reset()
    assert s.rust_time_ms == 0.0
    assert s.python_time_ms == 0.0
    assert s.astar_total_ms == 0.0
    assert s.dist_map_ms == 0.0


def test_get_route_profile_stats_returns_object():
    s = get_route_profile_stats()
    assert isinstance(s, RouteProfileStats)


def test_reset_route_profile_stats_zeros():
    # reset then check
    reset_route_profile_stats()
    s = get_route_profile_stats()
    assert s.rust_time_ms == 0.0


# ── grid_converter ─────────────────────────────────────────────────


def test_grid_to_world_origin_zero():
    x, y = _tg.grid_to_world_py(10, 20, 0.0, 0.0, 0.5)
    assert x == pytest.approx(10 * 0.5 + 0.25)
    assert y == pytest.approx(20 * 0.5 + 0.25)


def test_grid_to_world_with_offset():
    x, y = _tg.grid_to_world_py(0, 0, 10.0, 20.0, 1.0)
    assert x == pytest.approx(10.5)
    assert y == pytest.approx(20.5)


# ── path_simplify ──────────────────────────────────────────────────


def test_is_collinear_horizontal():
    p1 = GridCell(0, 0, 0)
    p2 = GridCell(1, 0, 0)
    p3 = GridCell(2, 0, 0)
    assert is_collinear(p1, p2, p3) is True


def test_is_collinear_L_shape():
    p1 = GridCell(0, 0, 0)
    p2 = GridCell(1, 0, 0)
    p3 = GridCell(1, 1, 0)
    assert is_collinear(p1, p2, p3) is False


def test_estimate_segment_count():
    cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
    assert estimate_segment_count(cells) > 0


def test_simplify_path_straight():
    cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
    result = simplify_path(cells)
    assert len(result) <= len(cells)
    assert result[0].x == 0
    assert result[-1].x == 2


# ── constraints_geometry ───────────────────────────────────────────


def test_point_distance_to():
    p1 = CG.Point(0.0, 0.0)
    p2 = CG.Point(3.0, 4.0)
    assert p1.distance_to(p2) == pytest.approx(5.0)


def test_point_to_array():
    p = CG.Point(1.5, 2.5)
    arr = p.to_array()
    assert np.allclose(arr, np.array([1.5, 2.5]))


def test_line_segment_length():
    seg = CG.LineSegment(CG.Point(0, 0), CG.Point(3, 4))
    assert seg.length == pytest.approx(5.0)


def test_line_segment_direction():
    seg = CG.LineSegment(CG.Point(0, 0), CG.Point(1, 0))
    d = seg.direction
    assert isinstance(d, np.ndarray)
    assert np.allclose(d, np.array([1.0, 0.0]))


def test_line_segment_midpoint():
    seg = CG.LineSegment(CG.Point(0, 0), CG.Point(10, 20))
    m = seg.midpoint()
    assert m.x == pytest.approx(5.0)
    assert m.y == pytest.approx(10.0)


def test_rotated_rect_corners():
    rect = CG.RotatedRect(CG.Point(0, 0), (4.0, 2.0), 0.0)
    corners = rect.corners
    assert len(corners) == 4


def test_rotated_rect_bounding_radius():
    rect = CG.RotatedRect(CG.Point(0, 0), (4.0, 2.0), 45.0)
    r = rect.bounding_radius
    assert r > 0


def test_point_to_segment_distance():
    p = CG.Point(1, 1)
    seg = CG.LineSegment(CG.Point(0, 0), CG.Point(2, 0))
    d = CG.point_to_segment_distance(p, seg)
    assert d == pytest.approx(1.0)


def test_segment_to_segment_distance():
    s1 = CG.LineSegment(CG.Point(0, 0), CG.Point(2, 0))
    s2 = CG.LineSegment(CG.Point(0, 2), CG.Point(2, 2))
    d = CG.segment_to_segment_distance(s1, s2)
    assert d == pytest.approx(2.0)


def test_closest_points_segment_segment():
    s1 = CG.LineSegment(CG.Point(0, 0), CG.Point(2, 0))
    s2 = CG.LineSegment(CG.Point(1, 1), CG.Point(1, 3))
    p1, p2 = CG.closest_points_segment_segment(s1, s2)
    assert p1.y == pytest.approx(0.0)
    assert p2.x == pytest.approx(1.0)


def test_point_to_circle_distance_outside():
    d = CG.point_to_circle_distance(CG.Point(5, 0), CG.Point(0, 0), 3.0)
    assert d == pytest.approx(2.0)


def test_point_to_circle_distance_inside():
    d = CG.point_to_circle_distance(CG.Point(1, 0), CG.Point(0, 0), 3.0)
    assert d == pytest.approx(-2.0)


def test_point_to_rotated_rect_distance():
    p = CG.Point(5, 0)
    rect = CG.RotatedRect(CG.Point(0, 0), (2.0, 2.0), 0.0)
    d = CG.point_to_rotated_rect_distance(p, rect)
    assert d > 0


def test_segment_to_rotated_rect_distance():
    seg = CG.LineSegment(CG.Point(5, -10), CG.Point(5, 10))
    rect = CG.RotatedRect(CG.Point(0, 0), (2.0, 2.0), 0.0)
    d = CG.segment_to_rotated_rect_distance(seg, rect)
    assert d > 0
