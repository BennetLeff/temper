"""
Tests for Star Ground Crossing Awareness in GroundCrossingLoss.
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, GroundDomain
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.ground_crossing import GroundCrossingLoss


@pytest.fixture
def star_ground_context():
    """Create a LossContext with a split ground and a star point."""
    # Define two ground domains: PGND (left) and CGND (right)
    # Split at x = 50
    pgnd = GroundDomain(name="PGND", bounds=(0, 0, 50, 100), star_point=(50, 50))
    cgnd = GroundDomain(name="CGND", bounds=(50, 0, 100, 100), star_point=(50, 50))

    board = Board(width=100, height=100, ground_domains=[pgnd, cgnd])

    # Components
    # U1 in PGND, U2 in CGND
    components = [
        Component(ref="U1", footprint="test", bounds=(10, 10),
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
        Component(ref="U2", footprint="test", bounds=(10, 10),
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
    ]

    # Net crossing the split
    nets = [
        Net(name="NET1", pins=[("U1", "1"), ("U2", "1")], weight=1.0)
    ]

    netlist = Netlist(components=components, nets=nets)
    return LossContext.from_netlist_and_board(netlist, board)


def test_penalty_for_crossing_without_star_point(star_ground_context):
    """Verify penalty when crossing ground split far from star point."""
    loss_fn = GroundCrossingLoss()

    # U1 at (25, 25), U2 at (75, 25)
    # Crossing at y=25, star point at y=50. Distance to star point is 25mm.
    positions = jnp.array([
        [25.0, 25.0],
        [75.0, 25.0]
    ])
    rotations = jnp.zeros((2, 4))

    result = loss_fn(positions, rotations, star_ground_context)
    assert result.value > 0, "Should have penalty for crossing away from star point"


def test_no_penalty_for_crossing_through_star_point(star_ground_context):
    """Verify zero or reduced penalty when crossing through star point."""
    loss_fn = GroundCrossingLoss()

    # U1 at (48, 50), U2 at (52, 50)
    # Crossing exactly through star point (50, 50)
    positions = jnp.array([
        [48.0, 50.0],
        [52.0, 50.0]
    ])
    rotations = jnp.zeros((2, 4))

    result = loss_fn(positions, rotations, star_ground_context)
    # The current implementation might still have a small penalty if it's not perfectly 0,
    # but it should be significantly less than the far crossing.

    # For TDD, we want it to be 0 or very small.
    assert result.value < 1e-3, f"Should have minimal penalty at star point, got {result.value}"


def test_ground_crossing_differentiability(star_ground_context):
    """Verify that the loss is differentiable with respect to positions."""
    loss_fn = GroundCrossingLoss()

    def loss_val(pos):
        return loss_fn(pos, jnp.zeros((2, 4)), star_ground_context).value

    # Initial positions
    positions = jnp.array([
        [25.0, 25.0],
        [75.0, 25.0]
    ])

    grad_fn = jax.grad(loss_val)
    grads = grad_fn(positions)

    assert not jnp.any(jnp.isnan(grads)), "Gradients should not be NaN"
    assert jnp.any(grads != 0), "Gradients should be non-zero for a violation"

    # Check that moving towards star point reduces loss
    # Star point is at (50, 50).
    # Current crossing is at y=25. Moving y towards 50 should reduce loss.
    # So grad w.r.t y should be negative for U1 and U2 if we want to increase y to decrease loss?
    # Wait, grad is direction of steepest ASCENT. So if we want to decrease loss, we move in -grad.
    # If loss decreases as y increases, then grad_y should be negative.

    assert grads[0, 1] < 0, f"Grad for U1.y should be negative to move towards star point, got {grads[0, 1]}"
    assert grads[1, 1] < 0, f"Grad for U2.y should be negative to move towards star point, got {grads[1, 1]}"
