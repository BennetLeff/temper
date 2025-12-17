"""
Unit tests for DecouplingCapProximityLoss.
"""

import jax
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.decoupling import (
    DecouplingCapProximityLoss,
    DecouplingRule,
    create_decoupling_loss,
)


@pytest.fixture
def decoupling_netlist():
    """Create a netlist with IC and caps."""
    components = [
        Component("U1", "QFN", (5.0, 5.0), [Pin("1", "1", (0, 0))]),
        Component("C1", "0402", (1.0, 0.5), [Pin("1", "1", (0, 0))]),  # Close cap
        Component("C2", "0402", (1.0, 0.5), [Pin("1", "1", (0, 0))]),  # Far cap
    ]
    return Netlist(components, [])


@pytest.fixture
def decoupling_context(decoupling_netlist):
    board = Board(100.0, 100.0)
    return LossContext.from_netlist_and_board(decoupling_netlist, board)


def test_cap_close_to_ic_no_penalty(decoupling_netlist, decoupling_context):
    """Test cap within max distance has zero penalty (excess < 0)."""
    # Max distance 3.0mm
    rules = [DecouplingRule("C1", "U1", 3.0)]
    loss_fn = create_decoupling_loss(decoupling_netlist, rules)

    # Place U1 at (0,0), C1 at (2,0) -> dist=2.0 < 3.0
    positions = jnp.zeros((3, 2))
    positions = positions.at[1].set([2.0, 0.0])  # C1

    result = loss_fn(positions, jnp.zeros((3, 4)), decoupling_context)

    # Softplus of negative value is small but non-zero
    # softplus(-1.0) ~ 0.31
    # We expect it to be small
    assert result.value < 0.2


def test_cap_far_from_ic_high_penalty(decoupling_netlist, decoupling_context):
    """Test cap outside max distance has high penalty."""
    rules = [DecouplingRule("C2", "U1", 3.0)]
    loss_fn = create_decoupling_loss(decoupling_netlist, rules)

    # Place U1 at (0,0), C2 at (10,0) -> dist=10.0 > 3.0
    # Excess = 7.0
    positions = jnp.zeros((3, 2))
    positions = positions.at[2].set([10.0, 0.0])  # C2

    result = loss_fn(positions, jnp.zeros((3, 4)), decoupling_context)

    # Should be approx excess^2 approx 49
    # Wait, if we use jnp.zeros for indices, indices must be valid.
    # U1 is at index 0, C1 at 1, C2 at 2.
    # Factory logic maps refs to indices properly.

    assert result.value > 40.0


def test_multiple_rules(decoupling_netlist, decoupling_context):
    """Test sum of penalties for multiple rules."""
    rules = [
        DecouplingRule("C1", "U1", 2.0),
        DecouplingRule("C2", "U1", 2.0),
    ]
    loss_fn = create_decoupling_loss(decoupling_netlist, rules)

    # Both at 5.0mm -> excess = 3.0
    positions = jnp.zeros((3, 2))
    positions = positions.at[1].set([5.0, 0.0])
    positions = positions.at[2].set([5.0, 0.0])

    result = loss_fn(positions, jnp.zeros((3, 4)), decoupling_context)

    # 2 * 3.0^2 = 18.0
    assert result.value > 15.0


def test_empty_rules(decoupling_netlist, decoupling_context):
    """Test empty rules list returns zero."""
    loss_fn = create_decoupling_loss(decoupling_netlist, [])
    result = loss_fn(jnp.zeros((3, 2)), jnp.zeros((3, 4)), decoupling_context)
    assert result.value == 0.0
