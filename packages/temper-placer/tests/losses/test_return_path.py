import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.losses.return_path import create_return_path_loss


@pytest.fixture
def return_path_netlist():
    # U1 (Source) -> U2 (Dest)
    # R1 (Blocker)
    u1 = Component("U1", "QFN", (5, 5), [Pin("1", "1", (0, 0))])
    u2 = Component("U2", "QFN", (5, 5), [Pin("1", "1", (0, 0))])
    r1 = Component("R1", "0603", (2, 1), [Pin("1", "1", (0, 0))])

    return Netlist([u1, u2, r1], [])


@pytest.fixture
def return_path_context():
    class MockContext:
        pass

    return MockContext()


def test_return_path_loss_blocking(return_path_netlist, return_path_context):
    config = [{"source": "U1", "dest": "U2", "weight": 1.0}]
    loss_fn = create_return_path_loss(return_path_netlist, config, corridor_width=4.0)

    # Place U1 at (0,0), U2 at (20,0)
    # R1 at (10,0) -> Inside corridor (blocked)
    positions = jnp.array(
        [
            [0.0, 0.0],  # U1
            [20.0, 0.0],  # U2
            [10.0, 0.0],  # R1
        ]
    )
    rotations = jnp.zeros((3, 4))

    result = loss_fn(positions, rotations, return_path_context)

    # Expect loss > 0 because R1 is blocking
    assert float(result.value) > 0.1


def test_return_path_loss_clear(return_path_netlist, return_path_context):
    config = [{"source": "U1", "dest": "U2", "weight": 1.0}]
    loss_fn = create_return_path_loss(return_path_netlist, config, corridor_width=4.0)

    # Place U1 at (0,0), U2 at (20,0)
    # R1 at (10, 10) -> Far outside corridor (clear)
    positions = jnp.array(
        [
            [0.0, 0.0],  # U1
            [20.0, 0.0],  # U2
            [10.0, 10.0],  # R1
        ]
    )
    rotations = jnp.zeros((3, 4))

    result = loss_fn(positions, rotations, return_path_context)

    # Expect loss ~ 0
    assert float(result.value) < 1e-4


def test_return_path_gradient(return_path_netlist, return_path_context):
    config = [{"source": "U1", "dest": "U2", "weight": 1.0}]
    loss_fn = create_return_path_loss(return_path_netlist, config, corridor_width=4.0)

    # R1 slightly blocking, gradient should push it away
    positions = jnp.array(
        [
            [0.0, 0.0],  # U1
            [20.0, 0.0],  # U2
            [10.0, 1.0],  # R1 (y=1 is inside width=4/2=2 radius)
        ]
    )
    rotations = jnp.zeros((3, 4))

    grad_fn = jax.grad(lambda p: loss_fn(p, rotations, return_path_context).value)
    grads = grad_fn(positions)

    # R1 is at y=1. Corridor center is y=0.
    # To reduce loss, R1 should move AWAY from center -> +y direction
    # So dLoss/dy should be negative?
    # Wait, Loss decreases as y increases (moves out).
    # So gradient is negative. We move in direction -grad -> positive y.

    # Let's verify direction.
    # Loss is high at y=0, low at y=10.
    # dLoss/dy at y=1 should be negative (slope down).

    assert grads[2, 1] < 0.0  # R1 y-gradient
