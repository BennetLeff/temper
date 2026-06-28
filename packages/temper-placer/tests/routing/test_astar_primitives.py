"""Tests for A* search primitives in routing/heuristics.py."""

from __future__ import annotations

import math

import pytest

from temper_placer.routing.heuristics import (
    OCTILE_DIAG,
    _SAME_LAYER_DELTAS,
    in_bounds,
    octile_distance,
)


class TestOctileDistance:
    def test_origin_to_3_4(self):
        d = octile_distance((0, 0), (3, 4))
        expected = 4.0 + 3.0 * OCTILE_DIAG
        assert abs(d - expected) < 1e-12

    def test_zero_distance(self):
        assert octile_distance((0, 0), (0, 0)) == 0.0
        assert octile_distance((5, 7), (5, 7)) == 0.0

    def test_diagonal(self):
        d = octile_distance((0, 0), (5, 5))
        expected = 5.0 + 5.0 * OCTILE_DIAG
        assert abs(d - expected) < 1e-12

    def test_horizontal(self):
        assert octile_distance((0, 0), (5, 0)) == 5.0
        assert octile_distance((5, 0), (0, 0)) == 5.0

    def test_vertical(self):
        assert octile_distance((0, 0), (0, 7)) == 7.0

    def test_symmetric(self):
        assert (
            octile_distance((2, 3), (8, 6)) == octile_distance((8, 6), (2, 3))
        )

    def test_value_matches_literal(self):
        d = octile_distance((1, 0), (0, 3))
        expected_literal = max(1, 3) + 0.414 * min(1, 3)
        assert abs(d - expected_literal) < 1e-3


class TestInBounds:
    def test_in_bounds(self):
        assert in_bounds(5, 5, 10, 10)

    def test_at_origin(self):
        assert in_bounds(0, 0, 1, 1)

    def test_at_edge(self):
        assert in_bounds(9, 9, 10, 10)
        assert in_bounds(9, 0, 10, 10)
        assert in_bounds(0, 9, 10, 10)

    def test_out_of_bounds_negative(self):
        assert not in_bounds(-1, 0, 10, 10)
        assert not in_bounds(0, -1, 10, 10)

    def test_out_of_bounds_past_edge(self):
        assert not in_bounds(10, 5, 10, 10)
        assert not in_bounds(5, 10, 10, 10)
        assert not in_bounds(10, 10, 10, 10)

    def test_out_of_bounds_both(self):
        assert not in_bounds(-1, -1, 10, 10)
        assert not in_bounds(100, 100, 10, 10)


class TestNeighborDeltas:
    def test_exactly_eight_deltas(self):
        assert len(_SAME_LAYER_DELTAS) == 8

    def test_covers_all_eight_directions(self):
        assert (0, 1) in _SAME_LAYER_DELTAS
        assert (1, 0) in _SAME_LAYER_DELTAS
        assert (0, -1) in _SAME_LAYER_DELTAS
        assert (-1, 0) in _SAME_LAYER_DELTAS
        assert (1, 1) in _SAME_LAYER_DELTAS
        assert (1, -1) in _SAME_LAYER_DELTAS
        assert (-1, 1) in _SAME_LAYER_DELTAS
        assert (-1, -1) in _SAME_LAYER_DELTAS

    def test_order_matches_spec(self):
        expected = (
            (0, 1),
            (1, 0),
            (0, -1),
            (-1, 0),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        )
        assert _SAME_LAYER_DELTAS == expected

    def test_is_immutable(self):
        with pytest.raises((TypeError, AttributeError)):
            _SAME_LAYER_DELTAS[0] = (99, 99)  # type: ignore[index]


class TestOctileDiagPrecision:
    def test_matches_math(self):
        assert abs(OCTILE_DIAG - (math.sqrt(2.0) - 1.0)) < 1e-12

    def test_approximately_0_414(self):
        assert 0.4142 < OCTILE_DIAG < 0.4143
