"""Tests for neighbor cost calculation."""

import numpy as np
import pytest

from temper_placer.routing.cost import (
    BLOCKED_COST,
    check_blocked,
    check_net_isolation,
    compute_base_cost,
    compute_congestion_multiplier,
    compute_layer_balance_cost,
    compute_sharing_penalty,
    get_strategy_multiplier,
)


class TestCheckBlocked:
    """Test blocked cell checking."""

    def test_free_cell(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        blocked, occupied, c_space = check_blocked(5, 5, 0, None, None, None, occupancy)
        assert blocked is False
        assert occupied is False
        assert c_space == 0.0

    def test_blocked_cell(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        occupancy[5, 5, 0] = -1
        blocked, occupied, c_space = check_blocked(5, 5, 0, None, None, None, occupancy)
        assert blocked is True
        assert occupied is False

    def test_occupied_cell(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        occupancy[5, 5, 0] = 2
        blocked, occupied, c_space = check_blocked(5, 5, 0, None, None, None, occupancy)
        assert blocked is False
        assert occupied is True

    def test_numpy_array_preferred(self):
        occupancy_np = np.zeros((10, 10, 1), dtype=np.int32)
        occupancy_np[5, 5, 0] = -1
        blocked, occupied, c_space = check_blocked(5, 5, 0, occupancy_np, None, None)
        assert blocked is True

    def test_soft_c_space_cost(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        soft_c_space = np.zeros((10, 10, 1), dtype=np.float32)
        soft_c_space[5, 5, 0] = 0.5
        blocked, occupied, c_space = check_blocked(
            5, 5, 0, None, None, None, occupancy, soft_c_space
        )
        assert c_space == 0.5

    def test_soft_c_space_infinite_blocks(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        soft_c_space = np.zeros((10, 10, 1), dtype=np.float32)
        soft_c_space[5, 5, 0] = np.inf
        blocked, occupied, c_space = check_blocked(
            5, 5, 0, None, None, None, occupancy, soft_c_space
        )
        assert blocked is True

    def test_c_space_grid_blocks(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        c_space_grid = np.zeros((10, 10, 1), dtype=np.bool_)
        c_space_grid[5, 5, 0] = True
        blocked, occupied, c_space = check_blocked(5, 5, 0, None, None, c_space_grid, occupancy)
        assert blocked is True

    def test_2d_soft_c_space(self):
        occupancy = np.zeros((10, 10, 1), dtype=np.int32)
        soft_c_space = np.zeros((10, 10), dtype=np.float32)
        soft_c_space[5, 5] = 0.3
        blocked, occupied, c_space = check_blocked(
            5, 5, 0, None, None, None, occupancy, soft_c_space
        )
        assert c_space == pytest.approx(0.3)


class TestCheckNetIsolation:
    """Test net isolation checking (DRC-1)."""

    def test_no_current_net(self):
        cell_owner = {(5, 5, 0): "net_a"}
        result = check_net_isolation(5, 5, 0, cell_owner, None)
        assert result is False

    def test_same_net_allowed(self):
        cell_owner = {(5, 5, 0): "net_a"}
        result = check_net_isolation(5, 5, 0, cell_owner, "net_a")
        assert result is False

    def test_different_net_blocked(self):
        cell_owner = {(5, 5, 0): "net_a"}
        result = check_net_isolation(5, 5, 0, cell_owner, "net_b")
        assert result is True

    def test_unowned_cell(self):
        cell_owner = {}
        result = check_net_isolation(5, 5, 0, cell_owner, "net_a")
        assert result is False


class TestComputeSharingPenalty:
    """Test sharing penalty calculation."""

    def test_not_occupied(self):
        penalty = compute_sharing_penalty(occupied=False, congestion=1.0, soft_blocking=True)
        assert penalty == 0.0

    def test_strict_mode_blocks(self):
        penalty = compute_sharing_penalty(occupied=True, congestion=1.0, soft_blocking=False)
        assert penalty == BLOCKED_COST

    def test_soft_blocking_with_congestion(self):
        penalty = compute_sharing_penalty(occupied=True, congestion=2.0, soft_blocking=True)
        assert penalty == 150.0


class TestGetStrategyMultiplier:
    """Test strategy multiplier lookup."""

    def test_no_cost_map(self):
        mult = get_strategy_multiplier(None, 5, 5, 0)
        assert mult == 1.0

    def test_2d_cost_map(self):
        cost_map = np.array([[1.0, 2.0], [3.0, 4.0]])
        mult = get_strategy_multiplier(cost_map, 1, 0, 0)
        assert mult == 3.0

    def test_3d_cost_map(self):
        cost_map = np.zeros((2, 2, 2))
        cost_map[1, 0, 1] = 5.0
        mult = get_strategy_multiplier(cost_map, 1, 0, 1)
        assert mult == 5.0


class TestComputeLayerBalanceCost:
    """Test layer balance cost calculation."""

    def test_no_weight(self):
        penalty = compute_layer_balance_cost(np.array([10, 10]), 1, 0.0)
        assert penalty == 0.0

    def test_no_usage(self):
        penalty = compute_layer_balance_cost(np.array([0, 0]), 1, 0.1)
        assert penalty == 0.0

    def test_below_average(self):
        layer_usage = np.array([10, 5, 5])
        penalty = compute_layer_balance_cost(layer_usage, 1, 0.1)
        assert penalty == 0.0

    def test_above_average(self):
        layer_usage = np.array([5, 15, 10])
        penalty = compute_layer_balance_cost(layer_usage, 1, 0.1)
        assert penalty > 0.0


class TestComputeBaseCost:
    """Test history cost lookup."""

    def test_numpy_array(self):
        history = np.ones((10, 10, 1), dtype=np.float32)
        history[5, 5, 0] = 2.5
        cost = compute_base_cost(5, 5, 0, history)
        assert cost == 2.5

    def test_fallback_array(self):
        history = np.ones((10, 10, 1), dtype=np.float32)
        history[5, 5, 0] = 3.0
        cost = compute_base_cost(5, 5, 0, None, history)
        assert cost == 3.0

    def test_no_arrays(self):
        cost = compute_base_cost(5, 5, 0, None, None)
        assert cost == 0.0


class TestComputeCongestionMultiplier:
    """Test congestion multiplier calculation."""

    def test_no_congestion(self):
        mult = compute_congestion_multiplier(0.0)
        assert mult == 1.0

    def test_normal_congestion(self):
        mult = compute_congestion_multiplier(1.0)
        assert mult == 2.0

    def test_high_congestion(self):
        mult = compute_congestion_multiplier(3.0)
        assert mult == 4.0

    def test_custom_scale(self):
        mult = compute_congestion_multiplier(2.0, p_scale=0.5)
        assert mult == 2.0


class TestBlockedCostConstant:
    """Test BLOCKED_COST constant."""

    def test_blocked_cost_value(self):
        assert BLOCKED_COST == 1e9
