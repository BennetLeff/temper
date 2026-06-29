"""Unit tests for ``_segment_to_segment_dist`` degenerate and edge cases.

# @req(N10, U4): segment-to-segment distance edge case tests

Tests the analytical closest-distance function from ``clearance_check.py``
across zero-length segments, parallel configurations, coincident endpoints,
collinear arrangements, perpendicular crossings, and NaN/inf propagation.
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.clearance_check import _segment_to_segment_dist

# --- Both zero-length ---


def test_both_zero_length():
    dist, cp1, cp2 = _segment_to_segment_dist(
        (0.0, 0.0), (0.0, 0.0), (3.0, 4.0), (3.0, 4.0),
    )
    assert dist == pytest.approx(5.0)
    assert cp1 == (0.0, 0.0)
    assert cp2 == (3.0, 4.0)


def test_ab_zero_length():
    dist, cp1, cp2 = _segment_to_segment_dist(
        (0.0, 0.0), (0.0, 0.0), (3.0, 0.0), (3.0, 5.0),
    )
    assert dist == pytest.approx(3.0)
    assert cp1 == (0.0, 0.0)


def test_cd_zero_length():
    dist, cp1, cp2 = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (3.0, 4.0), (3.0, 4.0),
    )
    assert dist == pytest.approx(4.0)
    assert cp2 == (3.0, 4.0)


# --- Parallel segments ---


def test_parallel_separated():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (0.0, 5.0), (5.0, 5.0),
    )
    assert dist == pytest.approx(5.0)


def test_parallel_overlapping_projection():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (2.0, 0.0), (7.0, 0.0),
    )
    assert dist == pytest.approx(0.0)


# --- Coincident / collinear ---


def test_coincident_endpoint():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (5.0, 0.0), (5.0, 5.0),
    )
    assert dist == pytest.approx(0.0)


def test_collinear_overlapping():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (3.0, 0.0), (8.0, 0.0),
    )
    assert dist == pytest.approx(0.0)


def test_collinear_separated():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (2.0, 0.0), (5.0, 0.0), (8.0, 0.0),
    )
    assert dist == pytest.approx(3.0)


# --- Perpendicular crossing ---


def test_perpendicular_crossing():
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (2.5, -2.0), (2.5, 2.0),
    )
    assert dist == pytest.approx(0.0)


def test_identical_segments():
    dist, cp1, cp2 = _segment_to_segment_dist(
        (0.0, 0.0), (5.0, 0.0), (0.0, 0.0), (5.0, 0.0),
    )
    assert dist == pytest.approx(0.0)


# --- NaN/inf propagation (behavioral — documents current handling) ---


def test_nan_in_ab_b():
    """NaN in segment endpoint — does not crash; degeneracy path returns
    a finite distance (NaN is absorbed by the degenerate-branch check)."""
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (float("nan"), 0.0), (10.0, 0.0), (10.0, 5.0),
    )
    # NaN input triggers degenerate segment fallback; distance is finite
    assert math.isfinite(dist)


def test_inf_endpoint():
    """inf in segment endpoint — does not crash; degeneracy path returns
    a finite distance (inf is absorbed by the degenerate-branch check)."""
    dist, _, _ = _segment_to_segment_dist(
        (0.0, 0.0), (float("inf"), 0.0), (10.0, 0.0), (10.0, 5.0),
    )
    assert math.isfinite(dist)


# --- Interior single-point projection ---


def test_interior_projection():
    dist, cp1, cp2 = _segment_to_segment_dist(
        (1.0, 3.0), (1.0, 0.0), (4.0, 3.0), (4.0, 0.0),
    )
    assert dist == pytest.approx(3.0)
    assert cp1[0] == pytest.approx(1.0)
    assert cp2[0] == pytest.approx(4.0)
