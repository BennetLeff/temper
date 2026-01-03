"""Tests for heuristic strategy pattern.

Tests for the routing heuristics module that provides different
A* search heuristics for pathfinding.
"""

import numpy as np
import pytest


class MockCell:
    """Mock cell for testing heuristics."""

    def __init__(self, x: int, y: int, layer: int = 0):
        self.x = x
        self.y = y
        self.layer = layer

    def __repr__(self):
        return f"MockCell({self.x}, {self.y}, {self.layer})"


class TestManhattanHeuristic:
    """Test Manhattan distance heuristic."""

    def test_same_cell(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(5, 5, 0)
        result = manhattan_heuristic(a, a)
        assert result == 0.0

    def test_horizontal_distance(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(5, 0, 0)
        result = manhattan_heuristic(a, b)
        assert result == 5.0

    def test_vertical_distance(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(0, 3, 0)
        result = manhattan_heuristic(a, b)
        assert result == 3.0

    def test_diagonal_distance(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)
        result = manhattan_heuristic(a, b)
        assert result == 7.0

    def test_layer_change_cost(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(0, 0, 1)
        result = manhattan_heuristic(a, b)
        assert result == 2.0

    def test_combined_movement(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(2, 3, 1)
        result = manhattan_heuristic(a, b)
        assert result == 7.0


class TestEuclideanHeuristic:
    """Test Euclidean distance heuristic."""

    def test_same_cell(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(5, 5, 0)
        result = euclidean_heuristic(a, a)
        assert result == 0.0

    def test_horizontal_distance(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(3, 0, 0)
        result = euclidean_heuristic(a, b)
        assert result == pytest.approx(3.0)

    def test_vertical_distance(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(0, 4, 0)
        result = euclidean_heuristic(a, b)
        assert result == pytest.approx(4.0)

    def test_diagonal_distance(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)
        result = euclidean_heuristic(a, b)
        assert result == pytest.approx(5.0)

    def test_layer_change_included(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(0, 0, 1)
        result = euclidean_heuristic(a, b)
        assert result == pytest.approx(2.0)


class TestDistanceMapHeuristic:
    """Test distance map based heuristic."""

    def test_returns_zero_for_target(self):
        from temper_placer.routing.heuristics import create_distance_map_heuristic

        dist_map = np.array([[[0.0]]])
        heuristic = create_distance_map_heuristic(dist_map)
        result = heuristic(MockCell(0, 0, 0), MockCell(0, 0, 0))
        assert result == 0.0

    def test_uses_precomputed_distances(self):
        from temper_placer.routing.heuristics import create_distance_map_heuristic

        dist_map = np.zeros((5, 5, 1), dtype=np.float32)
        dist_map[0, 0, 0] = 0.0
        dist_map[1, 0, 0] = 1.0
        dist_map[2, 0, 0] = 2.0
        dist_map[3, 0, 0] = 3.0
        heuristic = create_distance_map_heuristic(dist_map)
        result = heuristic(MockCell(3, 0, 0), MockCell(0, 0, 0))
        assert result == 3.0


class TestHeuristicStrategy:
    """Test heuristic strategy pattern."""

    def test_strategy_interface(self):
        from temper_placer.routing.heuristics import HeuristicStrategy, manhattan_heuristic

        strategy = HeuristicStrategy(manhattan_heuristic)
        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)
        result = strategy(a, b)
        assert result == 7.0

    def test_strategy_with_custom_name(self):
        from temper_placer.routing.heuristics import HeuristicStrategy, euclidean_heuristic

        strategy = HeuristicStrategy(euclidean_heuristic, name="euclidean")
        assert strategy.name == "euclidean"

    def test_strategy_default_name(self):
        from temper_placer.routing.heuristics import HeuristicStrategy, manhattan_heuristic

        strategy = HeuristicStrategy(manhattan_heuristic)
        assert "manhattan" in strategy.name.lower() or strategy.name == "default"

    def test_different_strategies_same_interface(self):
        from temper_placer.routing.heuristics import HeuristicStrategy
        from temper_placer.routing.heuristics import manhattan_heuristic, euclidean_heuristic

        manhattan = HeuristicStrategy(manhattan_heuristic)
        euclidean = HeuristicStrategy(euclidean_heuristic)

        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)

        manhattan_result = manhattan(a, b)
        euclidean_result = euclidean(a, b)

        assert manhattan_result == 7.0
        assert euclidean_result == pytest.approx(5.0)


class TestHeuristicFactory:
    """Test heuristic factory."""

    def test_get_manhattan(self):
        from temper_placer.routing.heuristics import get_heuristic

        heuristic = get_heuristic("manhattan")
        assert heuristic is not None

    def test_get_euclidean(self):
        from temper_placer.routing.heuristics import get_heuristic

        heuristic = get_heuristic("euclidean")
        assert heuristic is not None

    def test_get_default(self):
        from temper_placer.routing.heuristics import get_heuristic

        heuristic = get_heuristic("default")
        assert heuristic is not None

    def test_unknown_heuristic(self):
        from temper_placer.routing.heuristics import get_heuristic

        with pytest.raises(ValueError):
            get_heuristic("unknown_strategy")


class TestHeuristicProperties:
    """Test heuristic properties."""

    def test_manhattan_is_admissible(self):
        from temper_placer.routing.heuristics import manhattan_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)

        result = manhattan_heuristic(a, b)
        assert result <= 7.0

    def test_euclidean_is_admissible(self):
        from temper_placer.routing.heuristics import euclidean_heuristic

        a = MockCell(0, 0, 0)
        b = MockCell(3, 4, 0)

        result = euclidean_heuristic(a, b)
        assert result <= 5.0

    def test_heuristic_never_negative(self):
        from temper_placer.routing.heuristics import manhattan_heuristic, euclidean_heuristic

        a = MockCell(5, 5, 0)
        b = MockCell(10, 10, 1)

        assert manhattan_heuristic(a, b) >= 0.0
        assert euclidean_heuristic(a, b) >= 0.0
