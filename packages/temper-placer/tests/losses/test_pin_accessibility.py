"""
Tests for PinAccessibilityLoss.
"""

import jax
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.pin_accessibility import PinAccessibilityLoss


def test_pin_accessibility_loss_basic():
    """Test basic functionality of PinAccessibilityLoss."""
    # Create a simple netlist with 2 components and 1 net
    # Component 1: Center (0,0), Pin at (1,0)
    # Component 2: Center (10,0), Pin at (-1,0)
    
    comp1 = Component(
        ref="U1",
        footprint="SOIC-8",
        bounds=(1.0, 1.0),
        pins=[Pin(name="1", number="1", position=(1.0, 0.0), net="NET1")]
    )
    comp2 = Component(
        ref="U2",
        footprint="SOIC-8",
        bounds=(1.0, 1.0),
        pins=[Pin(name="1", number="1", position=(-1.0, 0.0), net="NET2")]
    )
    comp3 = Component(
        ref="U3",
        footprint="DUMMY",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(-2.0, 0.0), net="NET1"),
            Pin(name="2", number="2", position=(2.0, 0.0), net="NET2"),
        ]
    )
    
    netlist = Netlist(
        components=[comp1, comp2, comp3],
        nets=[
            Net(name="NET1", pins=[("U1", "1"), ("U3", "1")]),
            Net(name="NET2", pins=[("U2", "1"), ("U3", "2")]),
        ]
    )
    
    board = Board(width=100.0, height=100.0)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    loss_fn = PinAccessibilityLoss(pin_pin_margin=2.0, pin_body_margin=2.0)
    
    # Case 1: No violation
    positions = jnp.array([
        [10.0, 10.0],
        [20.0, 10.0],
        [50.0, 50.0],
    ])
    rotations = jnp.array([
        [1.0, 0.0, 0.0, 0.0], # 0 deg
        [1.0, 0.0, 0.0, 0.0], # 0 deg
        [1.0, 0.0, 0.0, 0.0], # 0 deg
    ])
    
    result = loss_fn(positions, rotations, context)
    assert result.value == 0.0
    
    # Case 2: Pin-to-Pin violation
    # U1 pin is at (11, 10), U2 pin is at (11.5, 10)
    # Distance is 0.5, margin is 2.0
    positions_pp = jnp.array([
        [10.0, 10.0], # Pin1 at (11, 10)
        [12.5, 10.0], # Pin1 at (11.5, 10)
        [50.0, 50.0],
    ])
    result_pp = loss_fn(positions_pp, rotations, context)
    assert result_pp.value > 0.0
    assert result_pp.breakdown["pin_pin_loss"] > 0.0
    # Pin-to-Body might also be triggered if the pin of U1 is close to U2's body
    
    # Case 3: Pin-to-Body violation
    # U1 Pin 1 at (11, 10)
    # U2 Body at (11, 10)
    positions_pb = jnp.array([
        [10.0, 10.0], # Pin1 at (11, 10)
        [11.0, 10.0], # Body at (11, 10)
        [50.0, 50.0],
    ])
    result_pb = loss_fn(positions_pb, rotations, context)
    assert result_pb.value > 0.0
    assert result_pb.breakdown["pin_body_loss"] > 0.0


def test_pin_accessibility_differentiable():
    """Verify that the loss function is differentiable."""
    comp1 = Component(
        ref="U1",
        footprint="SOIC-8",
        bounds=(1.0, 1.0),
        pins=[Pin(name="1", number="1", position=(1.0, 0.0), net="NET1")]
    )
    comp2 = Component(
        ref="U2",
        footprint="SOIC-8",
        bounds=(1.0, 1.0),
        pins=[Pin(name="1", number="1", position=(-1.0, 0.0), net="NET2")]
    )
    comp3 = Component(
        ref="U3",
        footprint="DUMMY",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(-2.0, 0.0), net="NET1"),
            Pin(name="2", number="2", position=(2.0, 0.0), net="NET2"),
        ]
    )
    
    netlist = Netlist(
        components=[comp1, comp2, comp3],
        nets=[
            Net(name="NET1", pins=[("U1", "1"), ("U3", "1")]),
            Net(name="NET2", pins=[("U2", "1"), ("U3", "2")]),
        ]
    )
    board = Board(width=100.0, height=100.0)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    loss_fn = PinAccessibilityLoss()
    
    # U1 at (10, 10), Pin 1 at (11, 10)
    # U2 at (12, 10), Body covers [9.5, 14.5] x [7.5, 12.5]
    # U1 Pin 1 is inside U2 body.
    positions = jnp.array([[10.0, 10.0], [12.0, 10.0], [50.0, 50.0]])
    rotations = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    
    def loss_val(p):
        return loss_fn(p, rotations, context).value
        
    val = loss_val(positions)
    assert val > 0.0
    
    grads = jax.grad(loss_val)(positions)
    
    assert jnp.any(jnp.abs(grads) > 0.0)
    assert not jnp.any(jnp.isnan(grads))
