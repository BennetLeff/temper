"""
TDD tests for EdgeAvoidanceLoss.

These tests define the expected behavior before implementation per temper-a98v requirements.
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.regularization import EdgeAvoidanceLoss


@pytest.fixture
def simple_board():
    """Create a 100x100mm board for testing."""
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])


@pytest.fixture
def simple_netlist():
    """Create a simple netlist with one 10x10mm component."""
    comp = Component(
        ref="U1",
        footprint="TEST",
        bounds=(10.0, 10.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="GND")],
    )
    return Netlist(components=[comp], nets=[])


@pytest.fixture
def loss_context(simple_board, simple_netlist):
    """Create loss context."""
    return LossContext.from_netlist_and_board(
        netlist=simple_netlist,
        board=simple_board,
    )


class TestEdgeAvoidanceLossZero:
    """Test that loss is zero when components are away from edges."""

    def test_component_at_center_has_zero_loss(self, loss_context):
        """Component at board center (50, 50) should have zero loss with default margin."""
        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        positions = jnp.array([[50.0, 50.0, 0.0]])  # Center of board
        rotations = jnp.array([0.0])

        result = loss_fn(positions, rotations, loss_context)

        assert result.value == pytest.approx(0.0), (
            "Component at center should have zero edge penalty"
        )

    def test_component_just_outside_margin_has_zero_loss(self, simple_board, simple_netlist):
        """Component just outside margin zone should have zero loss."""
        # Position component at (15, 50) - left edge at 10mm, margin at 10mm, just safe
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        positions = jnp.array([[15.0, 50.0, 0.0]])  # Component bounds: left=10, right=20
        rotations = jnp.array([0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        result = loss_fn(positions, rotations, context)

        # Distance to left edge: 15 - 5 = 10mm (component center - half width)
        # Since distance >= margin, penalty should be zero
        assert result.value == pytest.approx(0.0, abs=1e-6)


class TestEdgeAvoidanceLossPositive:
    """Test that loss is positive when components approach edges."""

    def test_component_near_left_edge_has_positive_loss(self, simple_board, simple_netlist):
        """Component near left edge should have positive loss."""
        # Position component at (10, 50) - left edge at 5mm, within margin of 10mm
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        positions = jnp.array([[10.0, 50.0, 0.0]])  # Component bounds: left=5, right=15
        rotations = jnp.array([0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        result = loss_fn(positions, rotations, context)

        # Distance to left edge: 10 - 5 = 5mm
        # Deficit: 10 - 5 = 5mm
        # Penalty: 5^2 = 25
        assert result.value > 0, "Component within margin should have positive penalty"
        assert result.value == pytest.approx(25.0, abs=1.0)

    def test_component_near_right_edge_has_positive_loss(self, simple_board, simple_netlist):
        """Component near right edge should have positive loss."""
        # Position component at (90, 50) - right edge at 95mm, board edge at 100mm, deficit=5mm
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        positions = jnp.array([[90.0, 50.0, 0.0]])  # Component bounds: left=85, right=95
        rotations = jnp.array([0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        result = loss_fn(positions, rotations, context)

        # Distance from right edge: 100 - (90 + 5) = 5mm
        # Deficit: 10 - 5 = 5mm
        # Penalty: 5^2 = 25
        assert result.value > 0
        assert result.value == pytest.approx(25.0, abs=1.0)

    def test_component_near_all_edges_accumulates_penalty(self, simple_board, simple_netlist):
        """Component in corner should accumulate penalties from multiple edges."""
        # Position at (8, 8) - near both left and bottom edges
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        positions = jnp.array([[8.0, 8.0, 0.0]])  # Left edge at 3mm, bottom at 3mm
        rotations = jnp.array([0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        result = loss_fn(positions, rotations, context)

        # Left deficit: 10 - (8-5) = 10 - 3 = 7mm → 49
        # Bottom deficit: 10 - (8-5) = 7mm → 49
        # Total: 49 + 49 = 98
        assert result.value > 50, "Corner placement should have accumulated penalties"
        assert result.value == pytest.approx(98.0, abs=2.0)


class TestEdgeAvoidanceLossRespectsBounds:
    """Test that loss correctly uses component bounds."""

    def test_larger_component_has_earlier_penalty(self, simple_board):
        """Larger components should trigger penalties earlier (further from edge)."""
        # Small component (10x10) at x=15
        small_comp = Component(ref="U1", footprint="SMALL", bounds=(10.0, 10.0), pins=[])
        small_netlist = Netlist(components=[small_comp], nets=[])
        small_context = LossContext.from_netlist_and_board(
            netlist=small_netlist,
            board=simple_board,
        )

        # Large component (20x20) at same x=15
        large_comp = Component(ref="U2", footprint="LARGE", bounds=(20.0, 20.0), pins=[])
        large_netlist = Netlist(components=[large_comp], nets=[])
        large_context = LossContext.from_netlist_and_board(
            netlist=large_netlist,
            board=simple_board,
        )

        positions_small = jnp.array([[15.0, 50.0, 0.0]])
        positions_large = jnp.array([[15.0, 50.0, 0.0]])
        rotations = jnp.array([0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        small_loss = loss_fn(positions_small, rotations, small_context)
        large_loss = loss_fn(positions_large, rotations, large_context)

        # Small: left edge at 15-5=10mm, no penalty
        # Large: left edge at 15-10=5mm, deficit=5mm, penalty=25
        assert small_loss.value == pytest.approx(0.0, abs=1e-6)
        assert large_loss.value > small_loss.value


class TestEdgeAvoidanceLossDifferentiable:
    """Test that loss is differentiable for JAX optimization."""

    def test_loss_is_differentiable(self, loss_context):
        """Loss should be differentiable with respect to positions."""
        import jax

        loss_fn = EdgeAvoidanceLoss(margin=10.0)

        def loss_wrapper(positions):
            rotations = jnp.array([0.0])
            return loss_fn(positions, rotations, loss_context).value

        # Position near left edge to ensure non-zero gradient
        positions = jnp.array([[10.0, 50.0, 0.0]])
        grad_fn = jax.grad(loss_wrapper)
        grads = grad_fn(positions)

        assert grads.shape == positions.shape
        # Gradient should be non-zero
        # Gradient is negative near left edge: moving left (negative x) increases loss
        # Optimizer will move opposite to gradient (toward positive x, away from edge)
        assert grads[0, 0] != 0, "Gradient should be non-zero near edge"
        # Near left edge, gradient should be negative (loss increases as we move left)
        assert grads[0, 0] < 0, (
            "Gradient should be negative near left edge (loss increases moving left)"
        )

    def test_gradient_points_away_from_nearest_edge(self, simple_board, simple_netlist):
        """Gradient direction should cause optimizer to move away from edge."""
        import jax

        # Component near left edge
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        loss_fn = EdgeAvoidanceLoss(margin=10.0)

        def loss_wrapper(positions):
            rotations = jnp.array([0.0])
            return loss_fn(positions, rotations, context).value

        positions = jnp.array([[10.0, 50.0, 0.0]])
        grad_fn = jax.grad(loss_wrapper)
        grads = grad_fn(positions)

        # Near left edge, gradient is negative (loss increases as we move left)
        # Gradient descent (moving opposite to gradient) will push right (away from edge)
        assert grads[0, 0] < 0, "Gradient should be negative near left edge"

        # Verify: moving right reduces loss
        positions_right = jnp.array([[11.0, 50.0, 0.0]])
        loss_left = loss_wrapper(positions)
        loss_right = loss_wrapper(positions_right)
        assert loss_right < loss_left, "Moving right should reduce loss"


class TestEdgeAvoidanceLossMultipleComponents:
    """Test loss with multiple components."""

    def test_multiple_components_accumulate_loss(self, simple_board):
        """Loss should accumulate across all components."""
        # Two components near edges
        comps = [
            Component(ref="U1", footprint="TEST", bounds=(10.0, 10.0), pins=[]),
            Component(ref="U2", footprint="TEST", bounds=(10.0, 10.0), pins=[]),
        ]
        netlist = Netlist(components=comps, nets=[])

        # One near left edge, one near right edge
        context = LossContext.from_netlist_and_board(
            netlist=netlist,
            board=simple_board,
        )

        positions = jnp.array([[10.0, 50.0, 0.0], [90.0, 50.0, 0.0]])
        rotations = jnp.array([0.0, 0.0])

        loss_fn = EdgeAvoidanceLoss(margin=10.0)
        result = loss_fn(positions, rotations, context)

        # Each component has deficit of 5mm → 25 penalty
        # Total: 25 + 25 = 50
        assert result.value == pytest.approx(50.0, abs=2.0)


class TestEdgeAvoidanceLossConfiguration:
    """Test loss configuration options."""

    def test_different_margins_produce_different_losses(self, simple_board, simple_netlist):
        """Larger margins should increase loss for same position."""
        context = LossContext.from_netlist_and_board(
            netlist=simple_netlist,
            board=simple_board,
        )

        positions = jnp.array([[15.0, 50.0, 0.0]])
        rotations = jnp.array([0.0])

        # Small margin (5mm): component at 10mm distance, no penalty
        loss_small = EdgeAvoidanceLoss(margin=5.0)(positions, rotations, context)

        # Large margin (15mm): component at 10mm distance, deficit=5mm, penalty=25
        loss_large = EdgeAvoidanceLoss(margin=15.0)(positions, rotations, context)

        assert loss_large.value > loss_small.value
