"""Property-based tests for the Rust creepage/clearance geometry (Wave 3 #7
— the HV-isolation safety validator).

Five invariants on the segment geometry:

1. Distance non-negativity
2. Symmetry (bit-exact — the distance is a min over the same 4
   endpoint-to-opposite-segment values regardless of order)
3. Monotonicity (point-to-segment distance is non-decreasing as the
   point moves directly away from the segment)
4. Rotation invariance (closeness — cos/sin rounding)
5. Boundedness (segment distance <= distance between midpoints)

Plus two classifier invariants (IPC-2221 voltage table monotone in
voltage; HV-net detection case-insensitive) and three metamorphic
relations (translate-both, swap-segments, rotate-both; plus the
verify_creepage HV/LV role swap).
"""

from __future__ import annotations

import math
import random

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.creepage_check import (
    _calculate_required_creepage,
    _is_high_voltage_net,
    _point_to_segment_distance,
    _segment_to_segment_info,
    verify_creepage,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

MAX_EXAMPLES = 200

_coord = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)


@composite
def _seg_pair(draw):
    """Two segments as 8 floats: (x1,y1,x2,y2, x3,y3,x4,y4)."""
    return tuple(draw(st.tuples(*([_coord] * 8))))


def _seg_dist(seg):
    x1, y1, x2, y2, x3, y3, x4, y4 = seg
    return _segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4)[0]


def _rotate_point(x, y, theta):
    c, s = math.cos(theta), math.sin(theta)
    return (x * c - y * s, x * s + y * c)


def _rotate_seg(seg, theta):
    x1, y1, x2, y2, x3, y3, x4, y4 = seg
    rx1, ry1 = _rotate_point(x1, y1, theta)
    rx2, ry2 = _rotate_point(x2, y2, theta)
    rx3, ry3 = _rotate_point(x3, y3, theta)
    rx4, ry4 = _rotate_point(x4, y4, theta)
    return (rx1, ry1, rx2, ry2, rx3, ry3, rx4, ry4)


def _translate_seg(seg, tx, ty):
    x1, y1, x2, y2, x3, y3, x4, y4 = seg
    return (x1 + tx, y1 + ty, x2 + tx, y2 + ty, x3 + tx, y3 + ty, x4 + tx, y4 + ty)


# ---------------------------------------------------------------------------
# P1: Distance non-negativity
# ---------------------------------------------------------------------------


@given(_seg_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p1_segment_distance_nonnegative(seg):
    d = _seg_dist(seg)
    assert d >= 0.0 or math.isnan(d), f"negative distance {d}"


# ---------------------------------------------------------------------------
# P2: Symmetry (bit-exact) — swapping the two segments swaps the four
# endpoint distances but the min over the same values is identical.
# ---------------------------------------------------------------------------


@given(_seg_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p2_segment_distance_symmetric_bit_exact(seg):
    x1, y1, x2, y2, x3, y3, x4, y4 = seg
    d_ab = _segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4)[0]
    d_ba = _segment_to_segment_info(x3, y3, x4, y4, x1, y1, x2, y2)[0]
    assert d_ab == d_ba


# ---------------------------------------------------------------------------
# P3: Monotonicity — for a segment on the x-axis and a point above it,
# moving the point straight away can only increase the distance.
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.0, max_value=20.0, allow_nan=False),
    st.floats(min_value=-10.0, max_value=30.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
)
@settings(max_examples=MAX_EXAMPLES)
def test_p3_point_distance_monotonic_away(seg_len, px, py, step):
    d_near = _point_to_segment_distance(px, py, 0.0, 0.0, seg_len, 0.0)
    d_far = _point_to_segment_distance(px, py + step, 0.0, 0.0, seg_len, 0.0)
    assert d_far >= d_near - 1e-12, f"{d_far} < {d_near}"


# ---------------------------------------------------------------------------
# P4: Rotation invariance (closeness — rotation is an exact isometry, but
# cos/sin rounding shifts the last ulps)
# ---------------------------------------------------------------------------


@given(_seg_pair(), st.floats(min_value=-3.15, max_value=3.15, allow_nan=False))
@settings(max_examples=MAX_EXAMPLES)
def test_p4_rotation_invariance(seg, theta):
    before = _seg_dist(seg)
    after = _seg_dist(_rotate_seg(seg, theta))
    if before == 0.0:
        assert after < 1e-9, f"rotated crossing dist {after}"
    else:
        assert abs(after - before) <= 1e-9 * max(1.0, before), f"{before} -> {after}"


# ---------------------------------------------------------------------------
# P5: Boundedness — the min distance between two segments is at most the
# distance between any chosen point on each, in particular the midpoints.
# ---------------------------------------------------------------------------


@given(_seg_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p5_distance_bounded_by_midpoint_distance(seg):
    x1, y1, x2, y2, x3, y3, x4, y4 = seg
    d = _seg_dist(seg)
    mid1x, mid1y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    mid2x, mid2y = (x3 + x4) / 2.0, (y3 + y4) / 2.0
    bound = math.hypot(mid1x - mid2x, mid1y - mid2y)
    assert d <= bound + 1e-9, f"dist {d} > midpoint bound {bound}"


# ---------------------------------------------------------------------------
# Bonus invariants on the classifier functions
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=-200.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES)
def test_bonus_required_creepage_monotone_in_voltage(v1, delta):
    """The IPC-2221 bracket table is monotone non-decreasing in voltage."""
    r1 = _calculate_required_creepage(v1)
    r2 = _calculate_required_creepage(v1 + delta)
    assert r2 >= r1


@given(st.text(min_size=0, max_size=16, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"))
@settings(max_examples=MAX_EXAMPLES)
def test_bonus_hv_detection_case_insensitive(name):
    """The word-boundary classifier is case-insensitive (upper() first)."""
    assert _is_high_voltage_net(name) is _is_high_voltage_net(name.upper()) is _is_high_voltage_net(
        name.lower()
    )


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


def test_meta_translate_both_segments_preserves_distance():
    rng = random.Random(31)
    for _ in range(200):
        seg = tuple(rng.uniform(-50, 50) for _ in range(8))
        tx, ty = rng.uniform(-25, 25), rng.uniform(-25, 25)
        before = _seg_dist(seg)
        after = _seg_dist(_translate_seg(seg, tx, ty))
        if before == 0.0:
            assert abs(after) < 1e-9
        else:
            assert abs(after - before) <= 1e-9 * max(1.0, before), f"{before} -> {after}"


def test_meta_swap_segments_preserves_distance():
    rng = random.Random(37)
    for _ in range(200):
        seg = tuple(rng.uniform(-50, 50) for _ in range(8))
        x1, y1, x2, y2, x3, y3, x4, y4 = seg
        d_ab = _segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4)[0]
        d_ba = _segment_to_segment_info(x3, y3, x4, y4, x1, y1, x2, y2)[0]
        assert d_ab == d_ba


def test_meta_rotate_both_segments_preserves_distance():
    rng = random.Random(41)
    for _ in range(200):
        seg = tuple(rng.uniform(-50, 50) for _ in range(8))
        theta = rng.uniform(-3.15, 3.15)
        before = _seg_dist(seg)
        after = _seg_dist(_rotate_seg(seg, theta))
        if before == 0.0:
            assert abs(after) < 1e-9
        else:
            assert abs(after - before) <= 1e-9 * max(1.0, before), f"{before} -> {after}"


def _route(net_name, coords):
    path = RoutePath(net_name=net_name, coordinates=coords, layer_name="F.Cu", path_length=0.0)
    return CompiledRoute(net_name=net_name, path=path, width_mm=0.127, vias=[], matched_length_mm=None)


def test_meta_swapping_hv_lv_roles_preserves_violation_count():
    """verify_creepage checks each unordered (hv, lv) net pair exactly
    once from the HV side, so swapping which route carries the HV name
    must not change the violation count."""
    rng = random.Random(43)
    for _ in range(100):
        hv_coords = [(rng.uniform(-50, 50), rng.uniform(-50, 50)) for _ in range(3)]
        lv_coords = [(rng.uniform(-50, 50), rng.uniform(-50, 50)) for _ in range(3)]
        results_a = RoutingResults(
            compiled_routes={"AC_L": _route("AC_L", hv_coords), "SIG1": _route("SIG1", lv_coords)},
            failed_nets=[],
        )
        results_b = RoutingResults(
            compiled_routes={"SIG1": _route("SIG1", hv_coords), "AC_L": _route("AC_L", lv_coords)},
            failed_nets=[],
        )
        ra = verify_creepage(results_a)
        rb = verify_creepage(results_b)
        assert ra.violation_count == rb.violation_count
        assert ra.total_checks == rb.total_checks == 1
