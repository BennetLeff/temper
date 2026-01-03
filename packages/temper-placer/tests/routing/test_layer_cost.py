"""Tests for layer cost calculations."""

import numpy as np
import pytest

from temper_placer.routing.cost import (
    compute_congestion_cost,
    compute_layer_balance_penalty,
    compute_layer_preference_penalty,
    compute_strategy_multiplier,
    compute_total_move_cost,
    compute_via_cost,
    compute_wrong_way_penalty,
)


class TestComputeViaCost:
    """Test via cost computation."""

    def test_no_layer_change(self):
        cost = compute_via_cost(is_layer_change=False, congestion=1.0)
        assert cost == 0.0

    def test_base_via_cost(self):
        cost = compute_via_cost(is_layer_change=True, congestion=0.0, via_cost=1.5)
        assert cost == 1.5

    def test_congestion_discount(self):
        cost = compute_via_cost(
            is_layer_change=True,
            congestion=3.0,
            via_cost=1.0,
            congestion_via_discount=0.5,
            soft_blocking=True,
        )
        assert cost == 0.5

    def test_no_discount_in_strict_mode(self):
        cost = compute_via_cost(
            is_layer_change=True,
            congestion=3.0,
            via_cost=1.0,
            congestion_via_discount=0.5,
            soft_blocking=False,
        )
        assert cost == 1.0


class TestComputeWrongWayPenalty:
    """Test wrong-way penalty computation."""

    def test_no_penalty_setting(self):
        cost = compute_wrong_way_penalty(0, 0, 1, 0, 0, 0.0)
        assert cost == 0.0

    def test_layer0_horizontal_ok(self):
        cost = compute_wrong_way_penalty(0, 0, 1, 0, 0, 2.0)
        assert cost == 0.0

    def test_layer0_vertical_penalty(self):
        cost = compute_wrong_way_penalty(0, 0, 0, 1, 0, 2.0)
        assert cost == 2.0

    def test_layer1_vertical_ok(self):
        cost = compute_wrong_way_penalty(0, 0, 0, 1, 1, 2.0)
        assert cost == 0.0

    def test_layer1_horizontal_penalty(self):
        cost = compute_wrong_way_penalty(0, 0, 1, 0, 1, 2.0)
        assert cost == 2.0


class TestComputeLayerPreferencePenalty:
    """Test layer preference penalty computation."""

    def test_no_assignment(self):
        cost = compute_layer_preference_penalty(1, None)
        assert cost == 0.0

    def test_primary_layer(self):
        class MockAssignment:
            primary_layer = type("Layer", (), {"value": 1})()

        cost = compute_layer_preference_penalty(0, MockAssignment())
        assert cost == 0.0

    def test_non_primary_layer(self):
        class MockAssignment:
            primary_layer = type("Layer", (), {"value": 1})()

        cost = compute_layer_preference_penalty(1, MockAssignment())
        assert cost == 5.0


class TestComputeLayerBalancePenalty:
    """Test layer balance penalty computation."""

    def test_no_weight(self):
        penalty = compute_layer_balance_penalty(np.array([10, 10]), 1, 0.0)
        assert penalty == 0.0

    def test_no_usage(self):
        penalty = compute_layer_balance_penalty(np.array([0, 0]), 1, 0.1)
        assert penalty == 0.0

    def test_below_average(self):
        layer_usage = np.array([10, 5, 5])
        penalty = compute_layer_balance_penalty(layer_usage, 1, 0.1)
        assert penalty == 0.0

    def test_above_average(self):
        layer_usage = np.array([5, 15, 10])
        mean = np.mean(layer_usage)
        penalty = compute_layer_balance_penalty(layer_usage, 1, 0.1)
        expected = 0.1 * ((15 - mean) / mean)
        assert penalty == pytest.approx(expected)


class TestComputeStrategyMultiplier:
    """Test strategy multiplier computation."""

    def test_no_cost_map(self):
        mult = compute_strategy_multiplier(None, 5, 5, 0)
        assert mult == 1.0

    def test_2d_cost_map(self):
        cost_map = np.array([[1.0, 2.0], [3.0, 4.0]])
        mult = compute_strategy_multiplier(cost_map, 1, 0, 0)
        assert mult == 3.0

    def test_3d_cost_map(self):
        cost_map = np.zeros((2, 2, 2))
        cost_map[1, 0, 1] = 5.0
        mult = compute_strategy_multiplier(cost_map, 1, 0, 1)
        assert mult == 5.0


class TestComputeCongestionCost:
    """Test congestion cost computation."""

    def test_basic_congestion(self):
        cost = compute_congestion_cost(
            base_cost=1.0,
            history_cost=0.5,
            sharing_penalty=0.0,
            difficulty=0.1,
            c_space_cost=0.0,
            congestion=1.0,
        )
        assert cost == pytest.approx((1.0 + 0.5 + 0.1) * (1.0 + 1.0))

    def test_with_strategy_multiplier(self):
        cost = compute_congestion_cost(
            base_cost=1.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            congestion=0.0,
            strategy_multiplier=2.0,
        )
        assert cost == 2.0

    def test_high_congestion(self):
        cost = compute_congestion_cost(
            base_cost=1.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            congestion=3.0,
            p_scale=1.0,
        )
        assert cost == pytest.approx(4.0)


class TestComputeTotalMoveCost:
    """Test total move cost computation."""

    def test_basic_move(self):
        layer_usage = np.array([10, 10])
        cost = compute_total_move_cost(
            current_x=0,
            current_y=0,
            neighbor_x=1,
            neighbor_y=0,
            neighbor_layer=0,
            layer_usage=layer_usage,
            cost_map=None,
            congestion=0.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            assignment=None,
            via_cost=1.0,
        )
        assert cost == pytest.approx(2.0)

    def test_layer_change(self):
        layer_usage = np.array([10, 10])
        cost = compute_total_move_cost(
            current_x=0,
            current_y=0,
            neighbor_x=0,
            neighbor_y=1,
            neighbor_layer=1,
            layer_usage=layer_usage,
            cost_map=None,
            congestion=0.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            assignment=None,
            via_cost=1.0,
        )
        assert cost == pytest.approx(2.0)

    def test_wrong_way_penalty(self):
        layer_usage = np.array([10, 10])
        cost = compute_total_move_cost(
            current_x=0,
            current_y=0,
            neighbor_x=0,
            neighbor_y=1,
            neighbor_layer=0,
            layer_usage=layer_usage,
            cost_map=None,
            congestion=0.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            assignment=None,
            wrong_way_penalty=2.0,
            via_cost=1.0,
        )
        assert cost == pytest.approx(4.0)

    def test_high_congestion_discounts_via(self):
        layer_usage = np.array([10, 10])
        cost = compute_total_move_cost(
            current_x=0,
            current_y=0,
            neighbor_x=0,
            neighbor_y=1,
            neighbor_layer=1,
            layer_usage=layer_usage,
            cost_map=None,
            congestion=3.0,
            history_cost=0.0,
            sharing_penalty=0.0,
            difficulty=0.0,
            c_space_cost=0.0,
            assignment=None,
            via_cost=1.0,
            congestion_via_discount=0.5,
            soft_blocking=True,
        )
        assert cost == pytest.approx(4.5)
