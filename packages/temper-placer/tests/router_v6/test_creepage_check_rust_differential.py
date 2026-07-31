"""Differential tests: Rust creepage/clearance geometry vs the pure-Python
reference (temper_placer/router_v6/creepage_check.py, Wave 3 #7 — the
HV-isolation clearance/creepage validator).

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including Python-builtin ``min``/``max`` NaN handling,
CPython ``math.hypot`` = Dekker vector_norm, and the exact f64 operation
order).  Any change to the Rust core (packages/temper-geometry/src/
creepage_check.rs) or the Python delegation that disagrees with the
oracle fails here, bit-exactly.

The direct ``temper_geometry`` pins fail first (the crate is not yet
built / the functions do not exist); the module-level pins exercise the
full delegation path once wired.
"""

from __future__ import annotations

import math
import random
import re

import pytest
import temper_geometry as _tg

from temper_placer.router_v6.creepage_check import (
    _calculate_required_creepage,
    _closest_point_on_segment,
    _extract_segments,
    _find_clearance_violations,
    _is_high_voltage_net,
    _point_to_segment_distance,
    _segment_to_segment_info,
    _segments_intersect,
)
from temper_placer.router_v6.routing_results import CompiledRoute

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementations, verbatim)
# ---------------------------------------------------------------------------


def _oracle_point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _oracle_closest_point_on_segment(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0 or not math.isfinite(denom):
        return (x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    return (x1 + t * dx, y1 + t * dy)


def _oracle_orient(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _oracle_segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    o1 = _oracle_orient(x1, y1, x2, y2, x3, y3)
    o2 = _oracle_orient(x1, y1, x2, y2, x4, y4)
    o3 = _oracle_orient(x3, y3, x4, y4, x1, y1)
    o4 = _oracle_orient(x3, y3, x4, y4, x2, y2)
    if o1 * o2 < 0.0 and o3 * o4 < 0.0:
        dx1, dy1 = x2 - x1, y2 - y1
        dx2, dy2 = x4 - x3, y4 - y3
        denom = dx1 * dy2 - dy1 * dx2
        if denom != 0.0:
            t = ((x1 - x3) * dy1 - (y1 - y3) * dx1) / denom
            ix = x3 + t * dx2
            iy = y3 + t * dy2
            return True, ix, iy
    return False, 0.0, 0.0


def _oracle_segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4):
    intersects, ix, iy = _oracle_segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4)
    if intersects:
        return 0.0, (ix, iy), (ix, iy)
    best_dist = float("inf")
    best_p1 = (0.0, 0.0)
    best_p2 = (0.0, 0.0)
    for px, py in [(x1, y1), (x2, y2)]:
        d = _oracle_point_to_segment_distance(px, py, x3, y3, x4, y4)
        if d < best_dist:
            best_dist = d
            best_p1 = (px, py)
            best_p2 = _oracle_closest_point_on_segment(px, py, x3, y3, x4, y4)
    for px, py in [(x3, y3), (x4, y4)]:
        d = _oracle_point_to_segment_distance(px, py, x1, y1, x2, y2)
        if d < best_dist:
            best_dist = d
            best_p1 = _oracle_closest_point_on_segment(px, py, x1, y1, x2, y2)
            best_p2 = (px, py)
    return best_dist, best_p1, best_p2


def _oracle_min_clearance_distance(segs1, segs2):
    best_dist = float("inf")
    best_loc = (0.0, 0.0)
    for x1, y1, x2, y2, layer1 in segs1:
        for x3, y3, x4, y4, layer2 in segs2:
            if layer1 != layer2:
                continue
            dist, p1, p2 = _oracle_segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4)
            if dist < best_dist:
                best_dist = dist
                best_loc = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    return best_dist, best_loc[0], best_loc[1]


def _oracle_required_creepage(voltage):
    if math.isnan(voltage) or not math.isfinite(voltage):
        raise ValueError(f"Voltage must be a finite number, got {voltage!r}")
    if voltage <= 15:
        return 0.13
    elif voltage <= 30:
        return 0.25
    elif voltage <= 50:
        return 0.5
    elif voltage <= 100:
        return 0.8
    elif voltage <= 150:
        return 1.25
    elif voltage <= 170:
        return 1.6
    elif voltage <= 250:
        return 3.2
    elif voltage <= 300:
        return 6.4
    elif voltage <= 600:
        return 8.0
    else:
        return 12.0


_BROAD_KEYWORDS = [
    "HIGH_VOLTAGE",
    "MAINS",
    "LINE",
    "NEUTRAL",
    "PRIMARY",
    "HOT",
    "L1",
    "L2",
    "L3",
    "PHASE",
    "VBUS",
]


def _oracle_is_high_voltage_net(net_name):
    name_upper = net_name.upper()
    for kw in _BROAD_KEYWORDS:
        if re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", name_upper):
            return True
    if re.search(r"(?:^|_)B\+", name_upper):
        return True
    if re.search(r"(?:^|_)AC(?:$|[\d_])", name_upper):
        return True
    return bool(re.search(r"(?:^|_)HV(?:$|[\d_])", name_upper))


# ---------------------------------------------------------------------------
# Random helpers
# ---------------------------------------------------------------------------

_LAYERS = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]


def _random_segment(rng, degenerate_prob=0.05):
    x1, y1 = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
    if rng.random() < degenerate_prob:
        x2, y2 = x1, y1  # zero-length segment (point)
    else:
        x2, y2 = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
    layer = rng.choice(_LAYERS)
    return (x1, y1, x2, y2, layer)


def _random_segment_list(rng, max_n=6):
    return [_random_segment(rng) for _ in range(rng.randint(0, max_n))]


def _route_from_segments(net_name, segs):
    """Build a RoutePath3D from (x1,y1,x2,y2,layer) segments — per-segment
    layers preserved, so ``_extract_segments`` round-trips single-segment
    routes exactly.  Multi-segment routes gain zero-length junction
    segments on extraction (same endpoint, same layer) which contribute
    no new distances; the oracle comparisons below compute over the
    extracted segments to stay exact regardless."""
    from temper_placer.router_v6.astar_core import RoutePath3D

    pts: list[tuple[float, float, str]] = []
    for x1, y1, x2, y2, layer in segs:
        pts.append((x1, y1, layer))
        pts.append((x2, y2, layer))
    path = RoutePath3D(net_name=net_name, segments=pts, via_positions=[], path_length=0.0)
    return CompiledRoute(net_name=net_name, path=path, width_mm=0.127, vias=[], matched_length_mm=None)


# ---------------------------------------------------------------------------
# point_to_segment_distance parity
# ---------------------------------------------------------------------------


def test_point_to_segment_distance_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(500):
        px, py = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        x1, y1, x2, y2 = (rng.uniform(-50.0, 50.0) for _ in range(4))
        assert _point_to_segment_distance(px, py, x1, y1, x2, y2) == _oracle_point_to_segment_distance(
            px, py, x1, y1, x2, y2
        )


def test_point_to_segment_distance_rust_direct_pin():
    rng = random.Random(17)
    for _ in range(300):
        px, py = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        x1, y1, x2, y2 = (rng.uniform(-50.0, 50.0) for _ in range(4))
        assert _tg.point_to_segment_distance_py(px, py, x1, y1, x2, y2) == _oracle_point_to_segment_distance(
            px, py, x1, y1, x2, y2
        )


def test_point_to_segment_distance_edge_cases():
    # Zero-length segment → point-to-point distance.
    assert _point_to_segment_distance(3.0, 4.0, 1.0, 1.0, 1.0, 1.0) == math.hypot(2.0, 3.0)
    assert _tg.point_to_segment_distance_py(3.0, 4.0, 1.0, 1.0, 1.0, 1.0) == math.hypot(2.0, 3.0)
    # Point exactly on the segment → 0.
    assert _point_to_segment_distance(5.0, 0.0, 0.0, 0.0, 10.0, 0.0) == 0.0
    # Point beyond the segment's endpoint → endpoint distance.
    assert _point_to_segment_distance(12.0, 0.0, 0.0, 0.0, 10.0, 0.0) == 2.0
    # NaN point → NaN distance (propagates through hypot).
    assert math.isnan(_point_to_segment_distance(float("nan"), 3.0, 0.0, 0.0, 10.0, 0.0))
    assert math.isnan(_tg.point_to_segment_distance_py(float("nan"), 3.0, 0.0, 0.0, 10.0, 0.0))
    # inf point → inf distance.
    assert math.isinf(_point_to_segment_distance(float("inf"), 3.0, 0.0, 0.0, 10.0, 0.0))
    assert math.isinf(_tg.point_to_segment_distance_py(float("inf"), 3.0, 0.0, 0.0, 10.0, 0.0))


# ---------------------------------------------------------------------------
# closest_point_on_segment parity
# ---------------------------------------------------------------------------


def test_closest_point_on_segment_matches_oracle_bit_exact():
    rng = random.Random(23)
    for _ in range(500):
        px, py = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        x1, y1, x2, y2 = (rng.uniform(-50.0, 50.0) for _ in range(4))
        assert _closest_point_on_segment(px, py, x1, y1, x2, y2) == _oracle_closest_point_on_segment(
            px, py, x1, y1, x2, y2
        )


def test_closest_point_on_segment_rust_direct_pin():
    rng = random.Random(29)
    for _ in range(300):
        px, py = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        x1, y1, x2, y2 = (rng.uniform(-50.0, 50.0) for _ in range(4))
        assert _tg.closest_point_on_segment_py(px, py, x1, y1, x2, y2) == _oracle_closest_point_on_segment(
            px, py, x1, y1, x2, y2
        )


def test_closest_point_on_segment_edge_cases():
    # Zero-length segment → returns the point itself.
    assert _closest_point_on_segment(3.0, 4.0, 1.0, 1.0, 1.0, 1.0) == (1.0, 1.0)
    # Interior projection clamps.
    assert _closest_point_on_segment(12.0, 5.0, 0.0, 0.0, 10.0, 0.0) == (10.0, 0.0)
    assert _closest_point_on_segment(-3.0, 5.0, 0.0, 0.0, 10.0, 0.0) == (0.0, 0.0)
    assert _closest_point_on_segment(5.0, 5.0, 0.0, 0.0, 10.0, 0.0) == (5.0, 0.0)
    # NaN point → builtin min(1.0, nan) = 1.0 → projection lands on the far
    # endpoint (matches the pre-migration behavior bit-for-bit).
    assert _closest_point_on_segment(float("nan"), 3.0, 0.0, 0.0, 10.0, 0.0) == (10.0, 0.0)
    assert _tg.closest_point_on_segment_py(float("nan"), 3.0, 0.0, 0.0, 10.0, 0.0) == (10.0, 0.0)


# ---------------------------------------------------------------------------
# segments_intersect parity
# ---------------------------------------------------------------------------


def test_segments_intersect_matches_oracle_bit_exact():
    rng = random.Random(31)
    for _ in range(300):
        coords = [rng.uniform(-50.0, 50.0) for _ in range(8)]
        assert _segments_intersect(*coords) == _oracle_segments_intersect(*coords)


def test_segments_intersect_rust_direct_pin():
    rng = random.Random(37)
    for _ in range(300):
        coords = [rng.uniform(-50.0, 50.0) for _ in range(8)]
        assert _tg.segments_intersect_py(*coords) == _oracle_segments_intersect(*coords)


def test_segments_intersect_edge_cases():
    # Crossing segments: the reference's t formula is
    # cross(P1-P3, d1)/cross(d1, d2) = -t_true, so the reported
    # intersection mirrors through P3 (a latent sign bug in the
    # pre-migration code — dist is still 0, so the pass/fail verdict is
    # unaffected). Bit-exact migration pins the mirrored values.
    res = _segments_intersect(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0)
    assert res[0] is True
    assert res[1] == -5.0
    assert res[2] == 15.0
    assert res == _oracle_segments_intersect(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0)
    # Shared endpoint is NOT a proper intersection (strict orientation test).
    assert _segments_intersect(0.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 10.0)[0] is False
    # Collinear overlapping segments do not intersect (proper only).
    assert _segments_intersect(0.0, 0.0, 10.0, 0.0, 2.0, 0.0, 8.0, 0.0)[0] is False
    # Disjoint parallel segments.
    assert _segments_intersect(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 10.0, 1.0)[0] is False


# ---------------------------------------------------------------------------
# segment_to_segment_info parity
# ---------------------------------------------------------------------------


def test_segment_to_segment_info_matches_oracle_bit_exact():
    rng = random.Random(41)
    for _ in range(500):
        coords = [rng.uniform(-50.0, 50.0) for _ in range(8)]
        got = _segment_to_segment_info(*coords)
        expected = _oracle_segment_to_segment_info(*coords)
        assert got[0] == expected[0]
        assert got[1] == expected[1]
        assert got[2] == expected[2]


def test_segment_to_segment_info_rust_direct_pin():
    rng = random.Random(43)
    for _ in range(300):
        coords = [rng.uniform(-50.0, 50.0) for _ in range(8)]
        got = _tg.segment_to_segment_info_py(*coords)
        expected = _oracle_segment_to_segment_info(*coords)
        assert got[0] == expected[0]
        assert (got[1], got[2]) == expected[1]
        assert (got[3], got[4]) == expected[2]


def test_segment_to_segment_info_edge_cases():
    # Crossing segments → distance 0, closest points at the intersection.
    dist, p1, p2 = _segment_to_segment_info(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0)
    assert dist == 0.0
    assert p1 == p2
    # Two points (zero-length segments).
    dist, p1, p2 = _segment_to_segment_info(0.0, 0.0, 0.0, 0.0, 3.0, 4.0, 3.0, 4.0)
    assert dist == 5.0
    assert p1 == (0.0, 0.0) and p2 == (3.0, 4.0)
    # Parallel segments with a clear gap.
    dist, _, _ = _segment_to_segment_info(0.0, 0.0, 10.0, 0.0, 0.0, 2.0, 10.0, 2.0)
    assert dist == 2.0
    # NaN endpoint: the NaN arm is ignored by the `<` comparison and the
    # finite endpoint falls back (boundary suite pins this contract).
    dist, _, _ = _segment_to_segment_info(0.0, 0.0, float("nan"), 0.0, 5.0, 5.0, 15.0, 5.0)
    assert not math.isnan(dist)


# ---------------------------------------------------------------------------
# min_clearance_distance parity (via _find_clearance_violations)
# ---------------------------------------------------------------------------


def _run_violations(segs1, segs2, required, hv="AC_L", lv="SIG1"):
    r1 = _route_from_segments(hv, segs1)
    r2 = _route_from_segments(lv, segs2)
    return _find_clearance_violations(r1, r2, required, hv, lv)


def test_find_clearance_violations_matches_oracle_bit_exact():
    rng = random.Random(47)
    for _ in range(300):
        segs1 = _random_segment_list(rng)
        segs2 = _random_segment_list(rng)
        required = rng.uniform(0.0, 12.0)
        r1 = _route_from_segments("AC_L", segs1)
        r2 = _route_from_segments("SIG1", segs2)
        # Oracle over the *extracted* segments — the exact set the module
        # passes to Rust (RoutePath3D extraction round-trips single
        # segments exactly and adds only harmless zero-length junction
        # segments for multi-segment routes).
        best_dist, mx, my = _oracle_min_clearance_distance(
            _extract_segments(r1), _extract_segments(r2)
        )
        violations = _find_clearance_violations(r1, r2, required, "AC_L", "SIG1")
        if best_dist < required:
            assert len(violations) == 1
            v = violations[0]
            assert v.actual_distance == best_dist
            assert v.location == (mx, my)
            assert v.required_distance == required
        else:
            assert violations == []


def test_min_clearance_distance_rust_direct_pin():
    rng = random.Random(53)
    for _ in range(200):
        segs1 = _random_segment_list(rng)
        segs2 = _random_segment_list(rng)
        got = _tg.min_clearance_distance_py(segs1, segs2)
        expected = _oracle_min_clearance_distance(segs1, segs2)
        assert got == expected


def test_find_clearance_violations_same_layer_only():
    """Different-layer pairs are skipped — only same-layer segments count."""
    segs1 = [(0.0, 0.0, 10.0, 0.0, "F.Cu")]
    segs2 = [(0.0, 0.5, 10.0, 0.5, "B.Cu")]  # physically adjacent, other layer
    assert _run_violations(segs1, segs2, 3.2) == []
    segs3 = [(0.0, 0.5, 10.0, 0.5, "F.Cu")]
    v = _run_violations(segs1, segs3, 3.2)
    assert len(v) == 1
    assert v[0].actual_distance == 0.5


def test_find_clearance_violations_empty_routes():
    """Empty route → no pairs → no violation, inf distance never trips."""
    assert _run_violations([], [(0.0, 0.0, 1.0, 0.0, "F.Cu")], 3.2) == []
    assert _run_violations([(0.0, 0.0, 1.0, 0.0, "F.Cu")], [], 3.2) == []
    assert _run_violations([], [], 3.2) == []


# ---------------------------------------------------------------------------
# calculate_required_creepage parity
# ---------------------------------------------------------------------------

_BRACKETS = [
    (0.0, 0.13), (15.0, 0.13), (15.000001, 0.25), (30.0, 0.25), (30.000001, 0.5),
    (50.0, 0.5), (50.000001, 0.8), (100.0, 0.8), (100.000001, 1.25), (150.0, 1.25),
    (150.000001, 1.6), (170.0, 1.6), (170.000001, 3.2), (250.0, 3.2), (250.000001, 6.4),
    (300.0, 6.4), (300.000001, 8.0), (600.0, 8.0), (600.000001, 12.0), (1000.0, 12.0),
    (1e9, 12.0), (-1.0, 0.13), (-1e6, 0.13),
]


def test_required_creepage_table_matches_oracle_bit_exact():
    for voltage, expected in _BRACKETS:
        assert _calculate_required_creepage(voltage) == _oracle_required_creepage(voltage) == expected


def test_required_creepage_random_matches_oracle_bit_exact():
    rng = random.Random(59)
    for _ in range(500):
        voltage = rng.uniform(-100.0, 2000.0)
        assert _calculate_required_creepage(voltage) == _oracle_required_creepage(voltage)


def test_required_creepage_rust_direct_pin():
    rng = random.Random(61)
    for _ in range(300):
        voltage = rng.uniform(-100.0, 2000.0)
        assert _tg.calculate_required_creepage_py(voltage) == _oracle_required_creepage(voltage)


def test_required_creepage_nan_inf_raise_value_error():
    for voltage in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValueError, match="finite"):
            _calculate_required_creepage(voltage)
        with pytest.raises(ValueError, match="finite"):
            _tg.calculate_required_creepage_py(voltage)
        # Message parity with the Python repr (nan / inf / -inf).
        with pytest.raises(ValueError) as py_exc:
            _oracle_required_creepage(voltage)
        with pytest.raises(ValueError) as rs_exc:
            _tg.calculate_required_creepage_py(voltage)
        assert str(rs_exc.value) == str(py_exc.value)


# ---------------------------------------------------------------------------
# is_high_voltage_net parity
# ---------------------------------------------------------------------------


def _random_net_name(rng):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-.:"
    n = rng.randint(0, 12)
    return "".join(rng.choice(alphabet) for _ in range(n))


def test_is_high_voltage_net_matches_oracle():
    rng = random.Random(67)
    for _ in range(1000):
        name = _random_net_name(rng)
        assert _is_high_voltage_net(name) is _oracle_is_high_voltage_net(name)


def test_is_high_voltage_net_rust_direct_pin():
    rng = random.Random(71)
    for _ in range(500):
        name = _random_net_name(rng)
        assert _tg.is_high_voltage_net_py(name) is _oracle_is_high_voltage_net(name)


def test_is_high_voltage_net_known_positives():
    for name in [
        "ac_l", "ac_n", "AC_L", "AC_N", "HV_BUS", "_AC", "AC1", "MAINS_L",
        "PHASE_A", "BUS_L1", "PHASE_L2", "HIGH_VOLTAGE", "high_voltage",
        "MAINS", "mains_return", "LINE", "NEUTRAL", "PRIMARY", "HOT", "L1",
        "L2", "L3", "PHASE", "VBUS", "B+", "b+", "AC", "ac", "AC_", "_AC_",
        "HV", "hv", "HV1", "HV_", "_HV", "PHASE_L1", "BUS_L2", "HV_GATE",
    ]:
        assert _is_high_voltage_net(name) is True, name
        assert _tg.is_high_voltage_net_py(name) is True, name


def test_is_high_voltage_net_known_false_positives():
    """The 2026-07-27 word-boundary regression set must stay negative."""
    for name in [
        "discharge.k_dis1-coil1", "discharge.k_dis1-coil2",
        "discharge.k_dis2-coil1", "power_in.bypass_relay-coil1",
        "power_in.bypass_relay-coil2", "safety-line", "safety-line-1",
        "safety-line-2", "safety-line-3", "safety.coil_thermal-line",
        "safety.ocp-line", "safety.ovp-line", "safety.thermal-line",
        "safety.uvlo_logic-line", "TRACE", "SPACE", "FACTORY", "ACH", "CAC",
        "HIVE", "BEHAVE", "XHVX", "AC-", "AC.", "AC:", "", "   ",
    ]:
        assert _is_high_voltage_net(name) is False, name
        assert _tg.is_high_voltage_net_py(name) is False, name


def test_is_high_voltage_net_non_ascii_does_not_crash():
    for name in [
        "\N{GREEK CAPITAL LETTER ALPHA}\N{GREEK CAPITAL LETTER BETA}",
        "\N{CYRILLIC CAPITAL LETTER A}\N{CYRILLIC CAPITAL LETTER BE}",
        "\N{LATIN SMALL LETTER A WITH ACUTE}",
        "\u4e2d\u6587",
        "\u3042\u3044",
        "net\N{EN DASH}name",
        "\u0663\u0664",  # Arabic-Indic digits 3,4 — Unicode \d in the reference
    ]:
        assert _is_high_voltage_net(name) is _oracle_is_high_voltage_net(name)
        assert _tg.is_high_voltage_net_py(name) is _oracle_is_high_voltage_net(name)


def test_is_high_voltage_net_segment_extraction_passthrough():
    """_extract_segments stays in Python and feeds the Rust aggregator; a
    RoutePath3D with per-segment layers exercises the 3D arm."""
    from temper_placer.router_v6.astar_core import RoutePath3D

    r3d = RoutePath3D(
        net_name="AC_L",
        segments=[(0.0, 0.0, "F.Cu"), (10.0, 0.0, "F.Cu"), (10.0, 5.0, "B.Cu")],
        via_positions=[],
        path_length=0.0,
    )
    route = CompiledRoute(net_name="AC_L", path=r3d, width_mm=0.254, vias=[], matched_length_mm=None)
    segs = _extract_segments(route)
    assert segs == [(0.0, 0.0, 10.0, 0.0, "F.Cu")]  # layer change drops the pair
