"""
Unit tests for advanced thermal loss functions.

Tests cover:
- ThermalSpreadLoss: Spreading high-power components
- HeatSensitiveDistanceLoss: Keeping sensitive components away from heat sources
- EdgePreferenceLoss: Encouraging thermal pad components near edges
- Factory functions for creating losses from configs
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.thermal import (
    EdgePreferenceLoss,
    HeatSensitiveDistanceLoss,
    ThermalComponentConfig,
    ThermalSpreadLoss,
    create_edge_preference_loss,
    create_heat_sensitive_distance_loss,
    create_temper_thermal_losses,
    create_thermal_spread_loss,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def thermal_netlist():
    """Create a netlist with thermal-relevant components."""
    components = [
        # High-power components (heat sources)
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[Pin("G", "1", (0, 0))],
            net_class="HighVoltage",
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[Pin("G", "1", (0, 0))],
            net_class="HighVoltage",
        ),
        Component(
            ref="D1",
            footprint="DO-247",
            bounds=(12.0, 15.0),
            pins=[Pin("A", "1", (0, 0))],
            net_class="HighVoltage",
        ),
        # Heat-sensitive components
        Component(
            ref="U_MCU",
            footprint="QFN-48",
            bounds=(7.0, 7.0),
            pins=[Pin("VCC", "1", (0, 0))],
            net_class="Signal",
        ),
        Component(
            ref="U_TEMP_SENSE",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("OUT", "1", (0, 0))],
            net_class="Signal",
        ),
        # Regular components
        Component(
            ref="R1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[Pin("1", "1", (0, 0))],
            net_class="Signal",
        ),
    ]
    return Netlist(components=components, nets=[])


@pytest.fixture
def thermal_board():
    """Create a board for thermal testing."""
    return Board(width=100.0, height=150.0, origin=(0.0, 0.0))


@pytest.fixture
def thermal_context(thermal_netlist, thermal_board):
    """Create a LossContext for thermal testing."""
    return LossContext.from_netlist_and_board(thermal_netlist, thermal_board)


# =============================================================================
# ThermalSpreadLoss Tests
# =============================================================================


class TestThermalSpreadLoss:
    """Tests for ThermalSpreadLoss."""

    def test_no_penalty_when_spread(self, thermal_context):
        """Components far apart should have zero penalty."""
        # Q1 at (10, 10), Q2 at (80, 80), D1 at (10, 80) - all > 15mm apart
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1
                [80.0, 80.0],  # Q2
                [10.0, 80.0],  # D1
                [50.0, 50.0],  # U_MCU (not in loss)
                [60.0, 60.0],  # U_TEMP_SENSE (not in loss)
                [70.0, 70.0],  # R1 (not in loss)
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = ThermalSpreadLoss(
            high_power_indices=jnp.array([0, 1, 2]),  # Q1, Q2, D1
            min_separation_mm=15.0,
            power_weights=jnp.array([50.0, 50.0, 10.0]),
        )

        result = loss(positions, rotations, thermal_context)

        # Very small penalty (softplus never quite reaches zero)
        assert result.value < 1.0

    def test_penalty_when_clustered(self, thermal_context):
        """Components too close should have penalty."""
        # Q1 and Q2 only 5mm apart (< 15mm minimum)
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1
                [15.0, 10.0],  # Q2 - only 5mm from Q1
                [80.0, 80.0],  # D1 - far away
                [50.0, 50.0],  # U_MCU
                [60.0, 60.0],  # U_TEMP_SENSE
                [70.0, 70.0],  # R1
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = ThermalSpreadLoss(
            high_power_indices=jnp.array([0, 1, 2]),
            min_separation_mm=15.0,
            power_weights=jnp.array([50.0, 50.0, 10.0]),
        )

        result = loss(positions, rotations, thermal_context)

        # Significant penalty due to Q1-Q2 proximity
        assert result.value > 100.0

    def test_higher_power_higher_penalty(self, thermal_context):
        """Components with higher power should create larger penalties."""
        # Same proximity, but different power weights
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1
                [15.0, 10.0],  # Q2 - 5mm from Q1
                [80.0, 80.0],  # D1
                [50.0, 50.0],
                [60.0, 60.0],
                [70.0, 70.0],
            ]
        )
        rotations = jnp.zeros((6, 4))

        # High power weights
        loss_high = ThermalSpreadLoss(
            high_power_indices=jnp.array([0, 1]),
            min_separation_mm=15.0,
            power_weights=jnp.array([100.0, 100.0]),
        )

        # Low power weights
        loss_low = ThermalSpreadLoss(
            high_power_indices=jnp.array([0, 1]),
            min_separation_mm=15.0,
            power_weights=jnp.array([1.0, 1.0]),
        )

        result_high = loss_high(positions, rotations, thermal_context)
        result_low = loss_low(positions, rotations, thermal_context)

        # Higher power weights should give higher penalty
        assert result_high.value > result_low.value * 100  # Quadratic with weights

    def test_single_component_no_penalty(self, thermal_context):
        """Single high-power component should have zero penalty."""
        positions = jnp.zeros((6, 2))
        rotations = jnp.zeros((6, 4))

        loss = ThermalSpreadLoss(
            high_power_indices=jnp.array([0]),  # Only Q1
            min_separation_mm=15.0,
        )

        result = loss(positions, rotations, thermal_context)
        assert result.value == 0.0


# =============================================================================
# HeatSensitiveDistanceLoss Tests
# =============================================================================


class TestHeatSensitiveDistanceLoss:
    """Tests for HeatSensitiveDistanceLoss."""

    def test_no_penalty_when_far(self, thermal_context):
        """Sensitive components far from heat sources should have zero penalty."""
        # MCU and temp sensor far from IGBTs
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1 (heat source)
                [20.0, 10.0],  # Q2 (heat source)
                [80.0, 80.0],  # D1
                [80.0, 140.0],  # U_MCU - far from Q1, Q2
                [90.0, 140.0],  # U_TEMP_SENSE - far from Q1, Q2
                [50.0, 50.0],  # R1
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = HeatSensitiveDistanceLoss(
            sensitive_indices=jnp.array([3, 4]),  # MCU, TEMP_SENSE
            heat_source_indices=jnp.array([0, 1]),  # Q1, Q2
            min_distance_mm=20.0,
            heat_source_powers=jnp.array([50.0, 50.0]),
        )

        result = loss(positions, rotations, thermal_context)

        # Very small penalty (softplus asymptote)
        assert result.value < 1.0

    def test_penalty_when_near(self, thermal_context):
        """Sensitive components near heat sources should have penalty."""
        # MCU very close to Q1
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1 (heat source)
                [80.0, 80.0],  # Q2 (heat source)
                [50.0, 50.0],  # D1
                [15.0, 10.0],  # U_MCU - only 5mm from Q1!
                [90.0, 140.0],  # U_TEMP_SENSE - far
                [50.0, 70.0],  # R1
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = HeatSensitiveDistanceLoss(
            sensitive_indices=jnp.array([3, 4]),
            heat_source_indices=jnp.array([0, 1]),
            min_distance_mm=20.0,
            heat_source_powers=jnp.array([50.0, 50.0]),
        )

        result = loss(positions, rotations, thermal_context)

        # Significant penalty due to MCU-Q1 proximity
        assert result.value > 100.0

    def test_breakdown_has_min_distance(self, thermal_context):
        """Breakdown should include minimum distance metric."""
        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1
                [80.0, 80.0],  # Q2
                [50.0, 50.0],  # D1
                [15.0, 10.0],  # U_MCU - 5mm from Q1
                [90.0, 140.0],  # U_TEMP_SENSE
                [50.0, 70.0],  # R1
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = HeatSensitiveDistanceLoss(
            sensitive_indices=jnp.array([3]),  # MCU only
            heat_source_indices=jnp.array([0]),  # Q1 only
            min_distance_mm=20.0,
        )

        result = loss(positions, rotations, thermal_context)

        assert result.breakdown is not None
        assert "heat_sensitive_min_distance" in result.breakdown
        # MCU is 5mm from Q1
        min_dist = result.breakdown.get("heat_sensitive_min_distance")
        assert min_dist is not None
        assert float(min_dist) == pytest.approx(5.0, abs=0.1)


# =============================================================================
# EdgePreferenceLoss Tests
# =============================================================================


class TestEdgePreferenceLoss:
    """Tests for EdgePreferenceLoss."""

    def test_no_penalty_at_edge(self, thermal_context):
        """Components at board edge should have zero penalty."""
        # Q1 and Q2 at edges
        positions = jnp.array(
            [
                [5.0, 75.0],  # Q1 - 5mm from left edge (within 10mm margin)
                [95.0, 75.0],  # Q2 - 5mm from right edge
                [50.0, 50.0],  # D1 (not in loss)
                [50.0, 100.0],  # U_MCU (not in loss)
                [60.0, 100.0],  # U_TEMP_SENSE (not in loss)
                [70.0, 100.0],  # R1 (not in loss)
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0, 1]),  # Q1, Q2
            board_width=100.0,
            board_height=150.0,
            preferred_margin_mm=10.0,
        )

        result = loss(positions, rotations, thermal_context)

        # Zero penalty - both components within margin of edge
        assert result.value == pytest.approx(0.0, abs=0.01)

    def test_penalty_in_center(self, thermal_context):
        """Components in board center should have penalty."""
        # Q1 and Q2 in center (far from all edges)
        positions = jnp.array(
            [
                [50.0, 75.0],  # Q1 - center, 50mm from any edge
                [55.0, 75.0],  # Q2 - center
                [50.0, 50.0],
                [50.0, 100.0],
                [60.0, 100.0],
                [70.0, 100.0],
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0, 1]),
            board_width=100.0,
            board_height=150.0,
            preferred_margin_mm=10.0,
        )

        result = loss(positions, rotations, thermal_context)

        # Penalty for being far from edge
        # Distance to nearest edge is 45mm for both, excess is 35mm each
        # Penalty = 35^2 * 2 = 2450 (with weight=1)
        assert result.value > 1000.0

    def test_breakdown_has_distance_metrics(self, thermal_context):
        """Breakdown should include distance statistics."""
        positions = jnp.array(
            [
                [50.0, 75.0],  # Q1 - 50mm from edge
                [10.0, 75.0],  # Q2 - 10mm from edge
                [50.0, 50.0],
                [50.0, 100.0],
                [60.0, 100.0],
                [70.0, 100.0],
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0, 1]),
            board_width=100.0,
            board_height=150.0,
            preferred_margin_mm=10.0,
        )

        result = loss(positions, rotations, thermal_context)

        assert result.breakdown is not None
        assert "edge_preference_avg_distance" in result.breakdown
        assert "edge_preference_max_distance" in result.breakdown
        # Max distance should be 50mm (Q1)
        assert float(result.breakdown["edge_preference_max_distance"]) == pytest.approx(
            50.0, abs=0.1
        )


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions that create thermal losses from configs."""

    def test_create_thermal_spread_loss(self, thermal_netlist):
        """Test creating ThermalSpreadLoss from configs."""
        configs = [
            ThermalComponentConfig("Q1", 50.0),
            ThermalComponentConfig("Q2", 50.0),
            ThermalComponentConfig("D1", 10.0),
        ]

        loss = create_thermal_spread_loss(configs, thermal_netlist, min_separation_mm=15.0)

        assert loss is not None
        assert len(loss.high_power_indices) == 3
        assert loss.power_weights is not None
        assert float(loss.power_weights[0]) == 50.0

    def test_create_thermal_spread_loss_missing_component(self, thermal_netlist):
        """Factory should skip missing components."""
        configs = [
            ThermalComponentConfig("Q1", 50.0),
            ThermalComponentConfig("NONEXISTENT", 100.0),  # Not in netlist
            ThermalComponentConfig("Q2", 50.0),
        ]

        loss = create_thermal_spread_loss(configs, thermal_netlist, min_separation_mm=15.0)

        assert loss is not None
        assert len(loss.high_power_indices) == 2  # Only Q1 and Q2

    def test_create_heat_sensitive_distance_loss(self, thermal_netlist):
        """Test creating HeatSensitiveDistanceLoss."""
        sensitive = ["U_MCU", "U_TEMP_SENSE"]
        sources = [
            ThermalComponentConfig("Q1", 50.0),
            ThermalComponentConfig("Q2", 50.0),
        ]

        loss = create_heat_sensitive_distance_loss(
            sensitive, sources, thermal_netlist, min_distance_mm=20.0
        )

        assert loss is not None
        assert len(loss.sensitive_indices) == 2
        assert len(loss.heat_source_indices) == 2

    def test_create_edge_preference_loss(self, thermal_netlist):
        """Test creating EdgePreferenceLoss."""
        thermal_pad_refs = ["Q1", "Q2"]

        loss = create_edge_preference_loss(
            thermal_pad_refs,
            thermal_netlist,
            board_width=100.0,
            board_height=150.0,
            preferred_margin_mm=10.0,
        )

        assert loss is not None
        assert len(loss.thermal_pad_indices) == 2
        assert loss.board_width == 100.0
        assert loss.board_height == 150.0

    def test_create_temper_thermal_losses(self, thermal_netlist):
        """Test creating all Temper thermal losses."""
        spread_loss, distance_loss, edge_loss = create_temper_thermal_losses(
            thermal_netlist, board_width=100.0, board_height=150.0
        )

        # All losses should be created (some may be None if components missing)
        # At minimum, we should have spread and edge since Q1, Q2 exist
        assert spread_loss is not None or distance_loss is not None or edge_loss is not None


# =============================================================================
# Gradient Tests
# =============================================================================


class TestThermalGradients:
    """Test that gradients flow correctly through thermal losses."""

    def test_thermal_spread_loss_gradient(self, thermal_context):
        """ThermalSpreadLoss should have non-zero gradients."""
        import jax

        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1
                [15.0, 10.0],  # Q2 - close to Q1
                [50.0, 50.0],  # D1
                [50.0, 100.0],
                [60.0, 100.0],
                [70.0, 100.0],
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = ThermalSpreadLoss(
            high_power_indices=jnp.array([0, 1]),
            min_separation_mm=15.0,
        )

        def loss_fn(pos):
            return loss(pos, rotations, thermal_context).value

        grads = jax.grad(loss_fn)(positions)

        # Gradients should be non-zero for Q1 and Q2
        assert jnp.abs(grads[0]).sum() > 0
        assert jnp.abs(grads[1]).sum() > 0
        # Gradients point in direction of increase
        # To minimize loss, we move in opposite direction of gradient
        # So gradient directions tell us where loss increases
        # Q1 gradient positive x means moving Q1 right increases loss (bad)
        # So optimizer would move Q1 left (good - away from Q2)
        # Key check: gradients are non-zero and opposite for Q1 and Q2
        assert jnp.sign(grads[0, 0]) != jnp.sign(grads[1, 0])  # Opposite directions

    def test_heat_sensitive_distance_gradient(self, thermal_context):
        """HeatSensitiveDistanceLoss should have non-zero gradients."""
        import jax

        positions = jnp.array(
            [
                [10.0, 10.0],  # Q1 (heat source)
                [50.0, 50.0],  # Q2
                [50.0, 70.0],  # D1
                [15.0, 10.0],  # U_MCU - close to Q1
                [60.0, 100.0],
                [70.0, 100.0],
            ]
        )
        rotations = jnp.zeros((6, 4))

        loss = HeatSensitiveDistanceLoss(
            sensitive_indices=jnp.array([3]),  # MCU
            heat_source_indices=jnp.array([0]),  # Q1
            min_distance_mm=20.0,
        )

        def loss_fn(pos):
            return loss(pos, rotations, thermal_context).value

        grads = jax.grad(loss_fn)(positions)

        # Gradient should be non-zero for MCU (sensitive component)
        assert jnp.abs(grads[3]).sum() > 0
        # The gradient for the MCU should be non-zero in x direction
        # (since MCU is horizontally close to Q1)
        assert jnp.abs(grads[3, 0]) > 0
