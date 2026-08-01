"""Differential tests: Rust pad-geometry core and isolation-barrier
sweep vs the pure-Python reference implementations.

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including operation order).  Any change to the Rust core
(packages/temper-geometry/src/pad_geometry.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.
"""

from __future__ import annotations

import math
import random

import pytest

from temper_placer.core.pad_geometry import (
    pad_axis_radius,
    pad_bounding_radius,
    pad_core_half_extents,
    pad_corner_radius,
    pad_support_radius,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    Pad,
    _axis_gap,
    _best_rotation_for_barrier,
)

SHAPES = ["circle", "oval", "rect", "roundrect", "thru_hole", "custom"]


# ---------------------------------------------------------------------------
# Oracles (pre-migration implementations, verbatim)
# ---------------------------------------------------------------------------


def _oracle_corner_radius(width, height, shape, roundrect_ratio):
    norm = "circle" if shape == "thru_hole" else shape
    if norm == "circle":
        return max(width, height) / 2.0
    if norm == "oval":
        return min(width, height) / 2.0
    if norm == "roundrect":
        return roundrect_ratio * min(width, height)
    if norm == "rect":
        return 0.0
    return 0.0


def _oracle_half_extents(width, height, shape, roundrect_ratio):
    r = _oracle_corner_radius(width, height, shape, roundrect_ratio)
    return (max(width / 2.0 - r, 0.0), max(height / 2.0 - r, 0.0))


def _oracle_support_radius(width, height, shape, direction_rad, rotation_rad, roundrect_ratio):
    local_angle = direction_rad - rotation_rad
    dx, dy = math.cos(local_angle), math.sin(local_angle)
    hw, hh = _oracle_half_extents(width, height, shape, roundrect_ratio)
    r = _oracle_corner_radius(width, height, shape, roundrect_ratio)
    return hw * abs(dx) + hh * abs(dy) + r


def _oracle_axis_radius(width, height, shape, axis, rotation_rad, roundrect_ratio):
    direction = 0.0 if axis == 0 else math.pi / 2.0
    return _oracle_support_radius(width, height, shape, direction, rotation_rad, roundrect_ratio)


def _oracle_bounding_radius(width, height, shape, roundrect_ratio):
    hw, hh = _oracle_half_extents(width, height, shape, roundrect_ratio)
    r = _oracle_corner_radius(width, height, shape, roundrect_ratio)
    return math.hypot(hw, hh) + r


def _oracle_axis_gap(hv_pads, selv_pads, axis_idx):
    worst = float("inf")
    for hp in hv_pads:
        for sp in selv_pads:
            h = (hp.x, hp.y)[axis_idx]
            s = (sp.x, sp.y)[axis_idx]
            gap = abs(h - s) - hp.axis_radius(axis_idx) - sp.axis_radius(axis_idx)
            worst = min(worst, gap)
    return worst


def _oracle_best_rotation(hv_pads, selv_pads, barrier_axis):
    from temper_placer.placer.cp_sat.isolation_barrier import _project_onto_barrier_axis

    best = None
    fallback = None
    for rot_value in (0, 1, 2, 3):
        rot_rad = rot_value * math.pi / 2.0
        hv_proj = [
            (_project_onto_barrier_axis(p.x, p.y, rot_value, barrier_axis), p.axis_radius(barrier_axis, rot_rad))
            for p in hv_pads
        ]
        selv_proj = [
            (_project_onto_barrier_axis(p.x, p.y, rot_value, barrier_axis), p.axis_radius(barrier_axis, rot_rad))
            for p in selv_pads
        ]
        hv_mean = sum(p for p, _ in hv_proj) / len(hv_proj)
        selv_mean = sum(p for p, _ in selv_proj) / len(selv_proj)
        gap = min(abs(hp - sp) - hr - sr for hp, hr in hv_proj for sp, sr in selv_proj)
        if fallback is None or gap > fallback[1]:
            fallback = (rot_value, gap)
        if hv_mean > selv_mean:
            continue
        if best is None or gap > best[1]:
            best = (rot_value, gap)
    if best is not None:
        return (best[0], best[1], True)
    assert fallback is not None
    return (fallback[0], fallback[1], False)


def _random_pads(rng, n):
    return [
        Pad(
            x=rng.uniform(-15, 15),
            y=rng.uniform(-15, 15),
            width=rng.uniform(0.2, 5.0),
            height=rng.uniform(0.2, 5.0),
            shape=rng.choice(SHAPES),
            roundrect_ratio=rng.uniform(0.05, 0.45),
        )
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# Pad geometry parity
# ---------------------------------------------------------------------------


def test_corner_radius_matches_oracle():
    rng = random.Random(20260731)
    for _ in range(500):
        w, h = rng.uniform(0.1, 8.0), rng.uniform(0.1, 8.0)
        shape = rng.choice(SHAPES)
        ratio = rng.uniform(0.05, 0.45)
        assert pad_corner_radius(w, h, shape, ratio) == _oracle_corner_radius(w, h, shape, ratio)


def test_half_extents_matches_oracle():
    rng = random.Random(3)
    for _ in range(500):
        w, h = rng.uniform(0.1, 8.0), rng.uniform(0.1, 8.0)
        shape = rng.choice(SHAPES)
        ratio = rng.uniform(0.05, 0.45)
        assert pad_core_half_extents(w, h, shape, ratio) == _oracle_half_extents(w, h, shape, ratio)


def test_support_radius_matches_oracle():
    rng = random.Random(7)
    for _ in range(1000):
        w, h = rng.uniform(0.1, 8.0), rng.uniform(0.1, 8.0)
        shape = rng.choice(SHAPES)
        ratio = rng.uniform(0.05, 0.45)
        direction = rng.uniform(-4 * math.pi, 4 * math.pi)
        rotation = rng.uniform(-4 * math.pi, 4 * math.pi)
        assert pad_support_radius(w, h, shape, direction, rotation, ratio) == _oracle_support_radius(
            w, h, shape, direction, rotation, ratio
        )


def test_axis_radius_matches_oracle():
    rng = random.Random(11)
    for _ in range(500):
        w, h = rng.uniform(0.1, 8.0), rng.uniform(0.1, 8.0)
        shape = rng.choice(SHAPES)
        ratio = rng.uniform(0.05, 0.45)
        for axis in (0, 1):
            rotation = rng.uniform(-4 * math.pi, 4 * math.pi)
            assert pad_axis_radius(w, h, shape, axis, rotation, ratio) == _oracle_axis_radius(
                w, h, shape, axis, rotation, ratio
            )


def test_bounding_radius_matches_oracle():
    rng = random.Random(13)
    for _ in range(500):
        w, h = rng.uniform(0.1, 8.0), rng.uniform(0.1, 8.0)
        shape = rng.choice(SHAPES)
        ratio = rng.uniform(0.05, 0.45)
        assert pad_bounding_radius(w, h, shape, ratio) == _oracle_bounding_radius(w, h, shape, ratio)


def test_axis_radius_rejects_bad_axis():
    with pytest.raises(ValueError):
        pad_axis_radius(1.0, 1.0, "circle", 2)


# ---------------------------------------------------------------------------
# Barrier sweep parity
# ---------------------------------------------------------------------------


def test_axis_gap_matches_oracle():
    rng = random.Random(17)
    for _ in range(200):
        hv = _random_pads(rng, rng.randrange(1, 6))
        selv = _random_pads(rng, rng.randrange(1, 6))
        for axis in (0, 1):
            assert _axis_gap(hv, selv, axis) == _oracle_axis_gap(hv, selv, axis)


def test_best_rotation_matches_oracle():
    rng = random.Random(19)
    for _ in range(200):
        hv = _random_pads(rng, rng.randrange(1, 6))
        selv = _random_pads(rng, rng.randrange(1, 6))
        for barrier_axis in (0, 1):
            got = _best_rotation_for_barrier(hv, selv, barrier_axis)
            expect = _oracle_best_rotation(hv, selv, barrier_axis)
            assert got == expect, f"hv={hv} selv={selv} axis={barrier_axis}"


def test_best_rotation_prefers_y_separation_via_rotation():
    # The bug this module historically fixed: Y-axis-only separation must
    # be found via a 90-degree rotation, not reported infeasible at rot 0.
    hv = [Pad(0.0, 0.0, 1.0, 1.0, "circle")]
    selv = [Pad(0.0, 12.0, 1.0, 1.0, "circle")]
    rot, gap, kept = _best_rotation_for_barrier(hv, selv, 0)
    assert rot in (1, 3)
    assert gap == pytest.approx(11.0)
    assert kept


def test_mean_equality_keeps_convention():
    # The HV=lo/SELV=hi convention uses `hv_mean > selv_mean` to skip, so
    # EQUAL means are eligible. Trace: rot=0 projects x (gap -1, eligible);
    # rot=1 projects +y (hv_mean 5 > 0 -> skipped); rot=2 negates x (gap
    # -1, eligible, not better); rot=3 projects -y (hv_mean -5, eligible,
    # gap 4.0 -> best). Note the fallback branch is unreachable by the mean
    # rule: rot=2 negates rot=0's projections, so hv_mean > selv_mean
    # cannot hold for all four rotations (this is why the module's
    # "never observed" is a proof, not an observation).
    hv = [Pad(0.0, 5.0, 1.0, 1.0, "circle")]
    selv = [Pad(0.0, 0.0, 1.0, 1.0, "circle")]
    rot, gap, kept = _best_rotation_for_barrier(hv, selv, 0)
    assert rot == 3
    assert gap == pytest.approx(4.0)
    assert kept
