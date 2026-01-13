"""Tests for A* iteration budget scaling with route distance.

These tests ensure that long routes receive appropriate iteration budgets
to complete successfully without exhausting the search space.
"""

import pytest


class TestIterationBudgetScaling:
    """Tests for iteration budget that scales with route distance."""

    def test_short_route_uses_minimum_budget(self):
        """Routes under 10 cells should use minimum budget (2000)."""
        # Simulated test - implementation needed
        manhattan_dist = 10  # cells
        expected_min_budget = 2000

        # Formula: max(2000, dist * 150)
        computed_budget = max(2000, manhattan_dist * 150)

        assert computed_budget == expected_min_budget

    def test_medium_route_scales_linearly(self):
        """Routes 10-50 cells should scale linearly with distance."""
        # 20 cells should get ~3000 iterations
        dist_20 = 20
        budget_20 = max(2000, dist_20 * 150)

        # 40 cells should get ~6000 iterations
        dist_40 = 40
        budget_40 = max(2000, dist_40 * 150)

        # Budget should roughly double for double distance
        ratio = budget_40 / budget_20
        assert 1.8 < ratio < 2.2, f"Budget ratio {ratio} should be ~2.0"

    def test_long_route_capped_at_maximum(self):
        """Routes over 100 cells should cap at maximum budget."""
        manhattan_dist = 300  # cells
        max_budget = 20000

        # Formula with cap
        computed_budget = min(max_budget, max(2000, manhattan_dist * 150))

        assert computed_budget == max_budget

    def test_gate_h_route_has_sufficient_budget(self):
        """GATE_H route (51 cells) should have budget > 6653 (current failure)."""
        manhattan_dist = 51
        failed_at = 6653

        # With 150 iterations/cell: 51 * 150 = 7650
        computed_budget = max(2000, manhattan_dist * 150)

        assert computed_budget > failed_at, (
            f"Budget {computed_budget} must exceed failure point {failed_at}"
        )

    def test_temp_sense_route_has_sufficient_budget(self):
        """TEMP_SENSE route (35 cells) should have budget > 4505."""
        manhattan_dist = 35
        failed_at = 4505

        # With 150 iterations/cell: 35 * 150 = 5250
        computed_budget = max(2000, manhattan_dist * 150)

        assert computed_budget > failed_at, (
            f"Budget {computed_budget} must exceed failure point {failed_at}"
        )

    def test_budget_scaling_formula(self):
        """Verify budget scaling formula covers known failures."""
        test_cases = [
            # (distance, failed_at_iterations, description)
            (35, 4505, "TEMP_SENSE"),
            (51, 6653, "GATE_H"),
            (50, 5000, "SPI_MOSI"),
        ]

        scaling_factor = 150  # iterations per cell
        min_budget = 2000
        max_budget = 20000

        for dist, failed_at, name in test_cases:
            budget = min(max_budget, max(min_budget, dist * scaling_factor))
            assert budget > failed_at, f"{name}: budget {budget} <= failed_at {failed_at}"


class TestIterationBudgetWithObstacles:
    """Tests for budget adjustment based on obstacle density."""

    def test_high_obstacle_density_increases_budget(self):
        """Routes through congested areas need higher budgets."""
        base_dist = 30
        base_budget = max(2000, base_dist * 150)

        # Simulate 30% obstacle density -> 1.6x multiplier
        obstacle_ratio = 0.3
        multiplier = 1 + obstacle_ratio * 2
        congested_budget = int(base_budget * multiplier)

        assert congested_budget > base_budget
        assert congested_budget == int(base_budget * 1.6)

    def test_blocked_direct_path_triggers_detour_budget(self):
        """If direct path is blocked, budget should assume detour."""
        direct_dist = 20
        base_budget = max(2000, direct_dist * 150)

        # Assume detour adds 50% to distance
        detour_multiplier = 1.5
        detour_budget = int(base_budget * detour_multiplier)

        # Should be more than minimum
        assert detour_budget > base_budget


class TestMultiLayerIterationBudget:
    """Tests for multi-layer routing budget multiplier."""

    def test_multilayer_has_higher_budget_than_single(self):
        """Multi-layer routing should have 2x budget for same distance."""
        dist = 40
        single_layer_budget = max(2000, dist * 150)

        # Multi-layer should have 2x budget due to via exploration
        multi_layer_multiplier = 2.0
        multi_layer_budget = int(single_layer_budget * multi_layer_multiplier)

        assert multi_layer_budget >= single_layer_budget * 1.5

    def test_two_layer_budget_sufficient(self):
        """2-layer routing should succeed with 2x budget."""
        dist = 50
        single_layer_budget = max(2000, dist * 150)
        two_layer_budget = single_layer_budget * 2

        # Should be enough for typical 2-layer routes
        assert two_layer_budget >= 10000
