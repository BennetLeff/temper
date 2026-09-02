"""Edge-case coverage for the Rust-backed segment distance primitives.

The production clearance path no longer owns a Python segment-distance helper.
These tests exercise the public ``constraints_geometry`` wrappers so the CI
registration remains meaningful without recreating the retired implementation.

# @req(N10, U4): segment-to-segment distance edge case tests
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    closest_points_segment_segment,
    segment_to_segment_distance,
)


def _segment(x1: float, y1: float, x2: float, y2: float) -> LineSegment:
    return LineSegment(Point(x1, y1), Point(x2, y2))


def test_both_zero_length() -> None:
    first = _segment(0.0, 0.0, 0.0, 0.0)
    second = _segment(3.0, 4.0, 3.0, 4.0)

    assert segment_to_segment_distance(first, second) == pytest.approx(5.0)
    assert closest_points_segment_segment(first, second) == (
        Point(0.0, 0.0),
        Point(3.0, 4.0),
    )


def test_first_zero_length_projects_to_second() -> None:
    first = _segment(0.0, 0.0, 0.0, 0.0)
    second = _segment(3.0, 0.0, 3.0, 5.0)

    assert segment_to_segment_distance(first, second) == pytest.approx(3.0)
    closest_first, closest_second = closest_points_segment_segment(first, second)
    assert closest_first == Point(0.0, 0.0)
    assert closest_second == Point(3.0, 0.0)


def test_second_zero_length_projects_from_first() -> None:
    first = _segment(0.0, 0.0, 5.0, 0.0)
    second = _segment(3.0, 4.0, 3.0, 4.0)

    assert segment_to_segment_distance(first, second) == pytest.approx(4.0)
    closest_first, closest_second = closest_points_segment_segment(first, second)
    assert closest_first == Point(3.0, 0.0)
    assert closest_second == Point(3.0, 4.0)


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(0.0, 5.0, 5.0, 5.0), 5.0),
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(2.0, 0.0, 7.0, 0.0), 0.0),
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(5.0, 0.0, 5.0, 5.0), 0.0),
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(3.0, 0.0, 8.0, 0.0), 0.0),
        (_segment(0.0, 0.0, 2.0, 0.0), _segment(5.0, 0.0, 8.0, 0.0), 3.0),
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(2.5, -2.0, 2.5, 2.0), 0.0),
        (_segment(0.0, 0.0, 5.0, 0.0), _segment(0.0, 0.0, 5.0, 0.0), 0.0),
    ],
)
def test_distance_edge_cases(first: LineSegment, second: LineSegment, expected: float) -> None:
    assert segment_to_segment_distance(first, second) == pytest.approx(expected)


def test_interior_projection() -> None:
    first = _segment(1.0, 3.0, 1.0, 0.0)
    second = _segment(4.0, 3.0, 4.0, 0.0)

    assert segment_to_segment_distance(first, second) == pytest.approx(3.0)
    closest_first, closest_second = closest_points_segment_segment(first, second)
    assert closest_first.x == pytest.approx(1.0)
    assert closest_second.x == pytest.approx(4.0)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (_segment(0.0, 0.0, float("nan"), 0.0), _segment(10.0, 0.0, 10.0, 5.0)),
        (_segment(0.0, 0.0, float("inf"), 0.0), _segment(10.0, 0.0, 10.0, 5.0)),
    ],
)
def test_non_finite_endpoint_follows_kernel_contract(
    first: LineSegment, second: LineSegment
) -> None:
    """Non-finite inputs do not crash the Rust kernel's degenerate path."""
    assert math.isfinite(segment_to_segment_distance(first, second))
