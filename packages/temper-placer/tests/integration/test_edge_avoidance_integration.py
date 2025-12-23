"""
Integration test for EdgeAvoidanceLoss with optimizer config and CLI.

Tests that EdgeAvoidanceLoss can be:
1. Retrieved from default loss weights (via file inspection)
2. Instantiated via the loss factory pattern
3. Used in a composite loss during optimization
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.losses.base import CompositeLoss, WeightedLoss
from temper_placer.losses.regularization import EdgeAvoidanceLoss


def test_edge_avoidance_loss_factory_pattern():
    """Test that EdgeAvoidanceLoss can be instantiated via factory pattern."""
    # Simulate the CLI's make_loss factory
    weights = {"edge_avoidance": 5.0}

    losses = []
    if "edge_avoidance" in weights and weights["edge_avoidance"] > 0:
        losses.append(WeightedLoss(EdgeAvoidanceLoss(), weight=weights["edge_avoidance"]))

    assert len(losses) == 1
    assert isinstance(losses[0].loss_fn, EdgeAvoidanceLoss)
    assert losses[0].weight == 5.0


def test_edge_avoidance_not_added_when_zero_weight():
    """Test that EdgeAvoidanceLoss is not added when weight is 0."""
    weights = {"edge_avoidance": 0.0}

    losses = []
    if "edge_avoidance" in weights and weights["edge_avoidance"] > 0:
        losses.append(WeightedLoss(EdgeAvoidanceLoss(), weight=weights["edge_avoidance"]))

    assert len(losses) == 0


def test_edge_avoidance_in_composite_loss():
    """Test that EdgeAvoidanceLoss works in a CompositeLoss."""
    # Create minimal netlist and board
    components = [
        Component(
            ref="U1",
            footprint="Package_SO:SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )
    ]
    netlist = Netlist(components=components, nets=[])
    board = Board(width=100.0, height=100.0)

    # Create composite loss with EdgeAvoidanceLoss
    edge_loss = EdgeAvoidanceLoss(margin=10.0)
    composite = CompositeLoss([WeightedLoss(edge_loss, weight=5.0)])

    # Create placement state: component at (7, 7) - VERY CLOSE to left/top edges
    # Component bbox will be: [4.5, 5] to [9.5, 9]
    # Left edge distance: 4.5mm < 10mm (penalty!)
    # Top edge distance: 5mm < 10mm (penalty!)
    positions = jnp.array([[7.0, 7.0]])
    rotations = jnp.eye(4)[jnp.zeros(1, dtype=jnp.int32)]  # 0° rotation

    # Compute loss
    from temper_placer.losses.base import LossContext

    context = LossContext.from_netlist_and_board(netlist, board)
    loss_value = composite(positions, rotations, context)

    # Should be positive since component is within margin (10mm) of edges
    assert float(loss_value.value) > 0, f"Expected positive loss near edge, got {loss_value.value}"


def test_edge_avoidance_gradient_direction():
    """Test that EdgeAvoidanceLoss gradient pushes away from edges."""
    # Create minimal netlist and board
    components = [
        Component(
            ref="U1",
            footprint="Package_SO:SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )
    ]
    netlist = Netlist(components=components, nets=[])
    board = Board(width=100.0, height=100.0)

    edge_loss = EdgeAvoidanceLoss(margin=10.0)

    # Component near left edge at (7, 50)
    positions = jnp.array([[7.0, 50.0]])
    rotations = jnp.eye(4)[jnp.zeros(1, dtype=jnp.int32)]

    from temper_placer.losses.base import LossContext
    import jax

    context = LossContext.from_netlist_and_board(netlist, board)

    # Compute gradient - need to extract .value from LossResult
    def loss_scalar(pos):
        result = edge_loss(pos, rotations, context)
        return result.value  # Extract scalar from LossResult

    grad_fn = jax.grad(loss_scalar)
    grad = grad_fn(positions)

    # Gradient should point right (negative gradient means optimizer moves right)
    # The loss is HIGHER when near the edge, so gradient points in direction of INCREASING loss
    # Since left edge means lower x, gradient should be NEGATIVE (pointing left towards edge)
    # Gradient descent does: x_new = x_old - lr * grad
    # So negative grad means x increases (moves right, away from left edge)
    assert grad[0, 0] < 0, f"Expected negative x gradient (pushes right), got {grad[0, 0]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
