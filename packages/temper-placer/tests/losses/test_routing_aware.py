"""Tests for routing-aware placement losses."""

import jax.numpy as jnp
import pytest

from temper_placer.losses.routing_aware import (
    BusAlignmentLoss,
    MCUClusteringLoss,
    RoutingChannelLoss,
    compute_routing_channel_penalty,
)
from temper_placer.losses.base import LossContext


class TestRoutingChannelLoss:
    """Tests for RoutingChannelLoss."""
    
    def test_no_penalty_for_wide_corridor(self):
        """Components with wide gap should have no penalty."""
        # Two components 20mm apart (corridor = 15mm with 5mm half-widths)
        positions = jnp.array([
            [0.0, 0.0],
            [20.0, 0.0],
        ])
        bounds = jnp.array([
            [5.0, 5.0, 0.0, 0.0],  # 5mm x 5mm
            [5.0, 5.0, 0.0, 0.0],
        ])
        
        penalty = compute_routing_channel_penalty(
            positions, bounds, min_channel_width=5.0
        )
        
        # Gap is 20 - 2.5 - 2.5 = 15mm, well above 5mm minimum
        # No overlapping in Y, so no corridor exists
        assert penalty == 0.0
    
    def test_penalty_for_narrow_corridor(self):
        """Components with narrow vertical gap should have penalty."""
        # Two components overlapping in X, narrow gap in Y
        positions = jnp.array([
            [0.0, 0.0],
            [0.0, 8.0],  # 8mm apart in Y
        ])
        bounds = jnp.array([
            [10.0, 5.0, 0.0, 0.0],  # 10mm x 5mm
            [10.0, 5.0, 0.0, 0.0],
        ])
        
        penalty = compute_routing_channel_penalty(
            positions, bounds, min_channel_width=5.0
        )
        
        # Overlapping in X (gap_x = 0 - 5 - 5 = -10)
        # Y gap = 8 - 2.5 - 2.5 = 3mm (less than 5mm)
        # Penalty should be positive
        assert penalty > 0.0
    
    def test_loss_class_returns_result(self):
        """RoutingChannelLoss should return LossResult."""
        positions = jnp.array([
            [0.0, 0.0],
            [0.0, 8.0],
        ])
        bounds = jnp.array([
            [10.0, 5.0, 0.0, 0.0],
            [10.0, 5.0, 0.0, 0.0],
        ])
        
        context = LossContext(
            bounds=bounds,
        )
        
        loss = RoutingChannelLoss(weight=10.0, min_channel_width=5.0)
        result = loss(positions, jnp.zeros((2, 4)), context)
        
        assert result.value > 0.0
        assert "routing_channel" in result.breakdown


class TestMCUClusteringLoss:
    """Tests for MCUClusteringLoss."""
    
    def test_no_penalty_for_close_peripherals(self):
        """Peripherals within max_distance should have no penalty."""
        positions = jnp.array([
            [50.0, 50.0],  # MCU at center
            [55.0, 55.0],  # Peripheral 7mm away
            [45.0, 45.0],  # Peripheral 7mm away
        ])
        
        loss = MCUClusteringLoss(
            weight=5.0,
            mcu_index=0,
            peripheral_indices=[1, 2],
            max_distance=15.0,
        )
        
        context = LossContext(
            bounds=jnp.zeros((3, 4)),
        )
        
        result = loss(positions, jnp.zeros((3, 4)), context)
        
        # Both peripherals are within 15mm
        assert result.value == 0.0
    
    def test_penalty_for_distant_peripheral(self):
        """Peripheral beyond max_distance should have penalty."""
        positions = jnp.array([
            [50.0, 50.0],  # MCU at center
            [80.0, 50.0],  # Peripheral 30mm away
        ])
        
        loss = MCUClusteringLoss(
            weight=5.0,
            mcu_index=0,
            peripheral_indices=[1],
            max_distance=15.0,
        )
        
        context = LossContext(
            bounds=jnp.zeros((2, 4)),
        )
        
        result = loss(positions, jnp.zeros((2, 4)), context)
        
        # Peripheral is 30mm away, 15mm excess, penalty = 5 * 15^2 = 1125
        assert result.value > 0.0
        expected = 5.0 * (30.0 - 15.0) ** 2
        assert abs(result.value - expected) < 1.0


class TestBusAlignmentLoss:
    """Tests for BusAlignmentLoss."""
    
    def test_no_penalty_for_aligned_components(self):
        """Components on a line should have minimal penalty."""
        # Three components in a straight horizontal line
        positions = jnp.array([
            [10.0, 50.0],
            [30.0, 50.0],
            [50.0, 50.0],
        ])
        
        loss = BusAlignmentLoss(
            weight=5.0,
            bus_groups=[[0, 1, 2]],
        )
        
        context = LossContext(
            bounds=jnp.zeros((3, 4)),
        )
        
        result = loss(positions, jnp.zeros((3, 4)), context)
        
        # Perfectly aligned, penalty should be near zero
        assert result.value < 1.0
    
    def test_penalty_for_misaligned_components(self):
        """Components not on a line should have penalty."""
        # Three components in L-shape
        positions = jnp.array([
            [10.0, 10.0],
            [10.0, 50.0],
            [50.0, 50.0],
        ])
        
        loss = BusAlignmentLoss(
            weight=5.0,
            bus_groups=[[0, 1, 2]],
        )
        
        context = LossContext(
            bounds=jnp.zeros((3, 4)),
        )
        
        result = loss(positions, jnp.zeros((3, 4)), context)
        
        # L-shaped, should have penalty
        assert result.value > 0.0
