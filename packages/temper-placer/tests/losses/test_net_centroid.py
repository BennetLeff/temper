
from dataclasses import dataclass

import jax.numpy as jnp
import pytest

from temper_placer.losses.net_centroid import NetCentroidAttractionLoss


def test_net_centroid_attraction():
    """Verify that loss pulls pins toward their shared center."""
    # 2 components, 1 net connecting them
    positions = jnp.array([
        [0.0, 0.0],
        [10.0, 0.0]
    ])
    rotations = jnp.zeros((2, 4))

    # Mock context
    # net_pin_indices: [1, P] - net 0 has 2 pins
    # pin 0 -> component 0, pin 1 -> component 1
    @dataclass
    class MockContext:
        net_pin_indices: jnp.ndarray
        net_pin_mask: jnp.ndarray
        net_pin_offsets: jnp.ndarray
        net_weights: jnp.ndarray

    context = MockContext(
        net_pin_indices=jnp.array([[0, 1]]),
        net_pin_mask=jnp.array([[True, True]]),
        net_pin_offsets=jnp.zeros((1, 2, 2)),
        net_weights=jnp.array([1.0])
    )

    loss_fn = NetCentroidAttractionLoss()
    result = loss_fn(positions, rotations, context)

    # Center is at (5, 0)
    # distsq = (0-5)^2 + (10-5)^2 = 25 + 25 = 50
    assert float(result.value) == pytest.approx(50.0)
