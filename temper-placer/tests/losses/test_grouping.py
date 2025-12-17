"""
Tests for functional grouping loss functions.

Tests GroupClusterLoss, ProximityLoss, and GroupSeparationLoss.
"""

import jax.numpy as jnp
import pytest

from temper_placer.losses.grouping import (
    GroupClusterLoss,
    GroupConfig,
    GroupSeparationLoss,
    ProximityLoss,
    ProximityRule,
    _compute_group_diameter,
)


class TestGroupDiameter:
    """Tests for _compute_group_diameter helper."""

    def test_two_points_diameter(self):
        """Diameter of two points is their distance."""
        positions = jnp.array([[0.0, 0.0], [3.0, 4.0]])
        diameter = _compute_group_diameter(positions)
        assert jnp.isclose(diameter, 5.0, atol=1e-5)

    def test_three_collinear_points(self):
        """Diameter of collinear points is max gap."""
        positions = jnp.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]])
        diameter = _compute_group_diameter(positions)
        assert jnp.isclose(diameter, 10.0, atol=1e-5)

    def test_square_points(self):
        """Diameter of square is the diagonal."""
        positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
        diameter = _compute_group_diameter(positions)
        expected = jnp.sqrt(200.0)  # diagonal of 10x10 square
        assert jnp.isclose(diameter, expected, atol=1e-5)


class TestGroupClusterLoss:
    """Tests for GroupClusterLoss."""

    def test_group_within_diameter_zero_penalty(self):
        """Group within max diameter should have zero penalty."""
        group = GroupConfig(
            name="test_group",
            component_indices=jnp.array([0, 1, 2]),
            max_diameter_mm=20.0,
        )
        loss_fn = GroupClusterLoss([group])

        # Positions within 15mm diameter
        positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [5.0, 5.0],
            ]
        )
        rotations = jnp.eye(4)[:3]  # dummy

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)

    def test_group_exceeds_diameter_positive_penalty(self):
        """Group exceeding max diameter should have positive penalty."""
        group = GroupConfig(
            name="test_group",
            component_indices=jnp.array([0, 1]),
            max_diameter_mm=10.0,
        )
        loss_fn = GroupClusterLoss([group])

        # Positions with 20mm diameter (exceeds 10mm limit by 10mm)
        positions = jnp.array(
            [
                [0.0, 0.0],
                [20.0, 0.0],
            ]
        )
        rotations = jnp.eye(4)[:2]

        result = loss_fn(positions, rotations, None)
        # Excess is 10mm, penalty is 10^2 = 100
        assert jnp.isclose(result.value, 100.0, atol=1e-5)

    def test_single_component_group_zero_penalty(self):
        """Single component group has zero diameter, zero penalty."""
        group = GroupConfig(
            name="singleton",
            component_indices=jnp.array([0]),
            max_diameter_mm=5.0,
        )
        loss_fn = GroupClusterLoss([group])

        positions = jnp.array([[10.0, 10.0]])
        rotations = jnp.eye(4)[:1]

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)


class TestProximityLoss:
    """Tests for ProximityLoss."""

    def test_pair_within_distance_zero_penalty(self):
        """Pair within max distance should have zero penalty."""
        rule = ProximityRule(idx_a=0, idx_b=1, max_distance_mm=10.0)
        loss_fn = ProximityLoss([rule])

        positions = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],  # 5mm apart, within 10mm limit
            ]
        )
        rotations = jnp.eye(4)[:2]

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)

    def test_pair_exceeds_distance_positive_penalty(self):
        """Pair exceeding max distance should have positive penalty."""
        rule = ProximityRule(idx_a=0, idx_b=1, max_distance_mm=5.0)
        loss_fn = ProximityLoss([rule])

        positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],  # 10mm apart, exceeds 5mm limit by 5mm
            ]
        )
        rotations = jnp.eye(4)[:2]

        result = loss_fn(positions, rotations, None)
        # Excess is 5mm, penalty is 5^2 = 25
        assert jnp.isclose(result.value, 25.0, atol=1e-5)

    def test_multiple_rules_sum_penalties(self):
        """Multiple rules should sum their penalties."""
        rules = [
            ProximityRule(idx_a=0, idx_b=1, max_distance_mm=5.0),
            ProximityRule(idx_a=1, idx_b=2, max_distance_mm=5.0),
        ]
        loss_fn = ProximityLoss(rules)

        positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],  # 10mm from pos0, 5mm excess
                [20.0, 0.0],  # 10mm from pos1, 5mm excess
            ]
        )
        rotations = jnp.eye(4)[:3]

        result = loss_fn(positions, rotations, None)
        # Both rules have 5mm excess, penalty = 25 + 25 = 50
        assert jnp.isclose(result.value, 50.0, atol=1e-5)

    def test_no_rules_zero_penalty(self):
        """No rules should return zero penalty."""
        loss_fn = ProximityLoss([])

        positions = jnp.array([[0.0, 0.0], [100.0, 100.0]])
        rotations = jnp.eye(4)[:2]

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)


class TestGroupSeparationLoss:
    """Tests for GroupSeparationLoss."""

    def test_groups_far_apart_zero_penalty(self):
        """Groups with adequate separation should have zero penalty."""
        group_a = GroupConfig(
            name="group_a",
            component_indices=jnp.array([0, 1]),
            max_diameter_mm=10.0,
        )
        group_b = GroupConfig(
            name="group_b",
            component_indices=jnp.array([2, 3]),
            max_diameter_mm=10.0,
        )
        loss_fn = GroupSeparationLoss([(group_a, group_b, 20.0)])

        # Group A centroid at (5, 0), Group B centroid at (50, 0) -> 45mm apart
        positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [45.0, 0.0],
                [55.0, 0.0],
            ]
        )
        rotations = jnp.eye(4)

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)

    def test_groups_too_close_positive_penalty(self):
        """Groups that are too close should have positive penalty."""
        group_a = GroupConfig(
            name="group_a",
            component_indices=jnp.array([0, 1]),
            max_diameter_mm=10.0,
        )
        group_b = GroupConfig(
            name="group_b",
            component_indices=jnp.array([2, 3]),
            max_diameter_mm=10.0,
        )
        loss_fn = GroupSeparationLoss([(group_a, group_b, 20.0)])

        # Group A centroid at (5, 0), Group B centroid at (15, 0) -> 10mm apart
        # Requires 20mm, so deficit is 10mm
        positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [12.0, 0.0],
                [18.0, 0.0],
            ]
        )
        rotations = jnp.eye(4)

        result = loss_fn(positions, rotations, None)
        # Deficit is 10mm, penalty is 10^2 = 100
        assert jnp.isclose(result.value, 100.0, atol=1e-5)

    def test_no_separations_zero_penalty(self):
        """No separation rules should return zero penalty."""
        loss_fn = GroupSeparationLoss([])

        positions = jnp.array([[0.0, 0.0]])
        rotations = jnp.eye(4)[:1]

        result = loss_fn(positions, rotations, None)
        assert jnp.isclose(result.value, 0.0, atol=1e-5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
