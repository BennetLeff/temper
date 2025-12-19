"""
Unit tests for PowerPathLoss.
"""

import jax
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.power_path import (
    HighCurrentPathConfig,
    SwitchingLoopConfig,
    PowerPathLoss,
    create_power_path_loss,
)


@pytest.fixture
def power_netlist():
    """Create a simple netlist with high-current paths."""
    # Two components connected by a high-current net (VIN)
    # C1, C2, C3 for loop tests
    c1 = Component("C1", "0805", (2.0, 1.25), [Pin("1", "1", (1.0, 0.0))])
    c2 = Component("C2", "0805", (2.0, 1.25), [Pin("1", "1", (-1.0, 0.0))])
    c3 = Component("C3", "0805", (2.0, 1.25), [Pin("1", "1", (0.0, 0.0))])

    # Net connecting C1-C2
    net_vin = Net("VIN", [("C1", "1"), ("C2", "1")])

    # Another net (low current)
    net_sig = Net("SIG", [("C1", "1"), ("C2", "1")])

    return Netlist([c1, c2, c3], [net_vin, net_sig])


@pytest.fixture
def power_context(power_netlist):
    board = Board(100.0, 100.0)
    return LossContext.from_netlist_and_board(power_netlist, board)


def test_power_path_loss_basic(power_netlist, power_context):
    """Test basic loss computation for two components (HPWL)."""
    config = [HighCurrentPathConfig("path1", ["VIN"], current_a=1.0, weight=1.0)]
    loss_fn = create_power_path_loss(power_netlist, config, alpha=50.0)

    # Place components 10mm apart on X axis
    # C1 at (10, 0), C2 at (20, 0), C3 at (0,0)
    positions = jnp.array([[10.0, 0.0], [20.0, 0.0], [0.0, 0.0]])
    rotations = jnp.zeros((3, 4))
    rotations = rotations.at[:, 0].set(1.0)  # 0 degrees

    result = loss_fn(positions, rotations, power_context)

    # Expected HPWL:
    # C1 pin offset (1,0) -> pos (11,0)
    # C2 pin offset (-1,0) -> pos (19,0)
    # Width = 8.0, Height = 0.0 -> HPWL = 8.0

    # With smooth_max/min, it will be slightly larger than 8.0
    assert result.value > 7.9
    assert result.value < 8.2  # Allow small error from smoothing


def test_power_path_loss_moves_components(power_netlist, power_context):
    """Test that gradient moves components closer."""
    config = [HighCurrentPathConfig("path1", ["VIN"], current_a=1.0, weight=1.0)]
    loss_fn = create_power_path_loss(power_netlist, config)

    positions = jnp.array([[10.0, 0.0], [20.0, 0.0], [0.0, 0.0]])
    rotations = jnp.zeros((3, 4))
    rotations = rotations.at[:, 0].set(1.0)

    grad_fn = jax.grad(lambda p: loss_fn(p, rotations, power_context).value)
    grads = grad_fn(positions)

    # C1 should move right (+x) to minimize loss (10 -> 20)
    # C2 should move left (-x) to minimize loss (20 -> 10)
    assert grads[0, 0] < 0.0  # C1 gradient is negative (move +x)
    assert grads[1, 0] > 0.0  # C2 gradient is positive (move -x)


def test_current_squared_weighting(power_netlist, power_context):
    """Test that loss scales with current squared."""
    # Case 1: 1A
    config1 = [HighCurrentPathConfig("path1", ["VIN"], current_a=1.0, weight=1.0)]
    loss1 = create_power_path_loss(power_netlist, config1)(
        jnp.array([[0.0, 0.0], [10.0, 0.0], [0.0, 0.0]]),
        jnp.zeros((3, 4)).at[:, 0].set(1.0),
        power_context,
    ).value

    # Case 2: 2A (should be 4x loss)
    config2 = [HighCurrentPathConfig("path1", ["VIN"], current_a=2.0, weight=1.0)]
    loss2 = create_power_path_loss(power_netlist, config2)(
        jnp.array([[0.0, 0.0], [10.0, 0.0], [0.0, 0.0]]),
        jnp.zeros((3, 4)).at[:, 0].set(1.0),
        power_context,
    ).value

    assert jnp.isclose(loss2, 4.0 * loss1, rtol=1e-4)


def test_switching_loop_area(power_netlist, power_context):
    """Test switching loop area calculation (Polygon)."""
    # C1, C2, C3 form a loop
    loop_config = SwitchingLoopConfig(name="loop1", components=["C1", "C2", "C3"], weight=1.0)

    loss_fn = create_power_path_loss(power_netlist, [], [loop_config])

    # Place in a right triangle
    # C1 at (0,0)
    # C2 at (10,0)
    # C3 at (0,10)
    # Area = 0.5 * 10 * 10 = 50.0

    positions = jnp.array(
        [
            [0.0, 0.0],  # C1
            [10.0, 0.0],  # C2
            [0.0, 10.0],  # C3
        ]
    )
    rotations = jnp.zeros((3, 4))

    result = loss_fn(positions, rotations, power_context)

    assert float(result.value) == pytest.approx(50.0, abs=1e-5)

    # Test gradient: Moving C2 closer to origin (reducing x) should reduce area
    # dArea/dx2 should be positive
    grad_fn = jax.grad(lambda p: loss_fn(p, rotations, power_context).value)
    grads = grad_fn(positions)

    assert grads[1, 0] > 0.0  # C2.x gradient positive (move left)
    assert grads[2, 1] > 0.0  # C3.y gradient positive (move down)


def test_empty_config(power_netlist, power_context):
    """Test with no paths/loops configured."""
    loss_fn = create_power_path_loss(power_netlist, [], [])
    result = loss_fn(jnp.zeros((3, 2)), jnp.zeros((3, 4)), power_context)
    assert result.value == 0.0


def test_missing_net_ignored(power_netlist, power_context):
    """Test that configuring a non-existent net doesn't crash."""
    config = [HighCurrentPathConfig("bad", ["MISSING_NET"], 1.0)]
    loss_fn = create_power_path_loss(power_netlist, config)
    result = loss_fn(jnp.zeros((3, 2)), jnp.zeros((3, 4)), power_context)
    assert result.value == 0.0
