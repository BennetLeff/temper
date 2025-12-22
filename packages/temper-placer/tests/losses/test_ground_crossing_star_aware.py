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
from temper_placer.losses.types import StarGroundConstraint


@pytest.fixture
def star_aware_context():
    """Create a LossContext with a split ground and a star net."""
    # Define two ground domains: PGND (left) and CGND (right)
    # Split at x = 50, Board Star Point at y=50
    pgnd = GroundDomain(name="PGND", bounds=(0, 0, 50, 100), star_point=(50, 50))
    cgnd = GroundDomain(name="CGND", bounds=(50, 0, 100, 100), star_point=(50, 50))

    board = Board(width=100, height=100, ground_domains=[pgnd, cgnd])

    # Components
    # U1, U3 in PGND; U2, U4 in CGND
    components = [
        Component(ref="U1", footprint="test", bounds=(1, 1), 
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
        Component(ref="U2", footprint="test", bounds=(1, 1), 
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
        Component(ref="U3", footprint="test", bounds=(1, 1), 
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
        Component(ref="U4", footprint="test", bounds=(1, 1), 
                  pins=[Pin(name="1", number="1", position=(0, 0))]),
    ]

    # Nets
    # NET1: Regular signal net (detours to 50, 50)
    # NET2: Star Ground net (detours to its virtual node)
    nets = [
        Net(name="NET1", pins=[("U1", "1"), ("U2", "1")], weight=1.0),
        Net(name="NET2", pins=[("U3", "1"), ("U4", "1")], weight=1.0)
    ]

    netlist = Netlist(components=components, nets=nets)
    
    # Define star ground constraint for NET2
    constraints = [
        StarGroundConstraint(net_name="NET2", weight=1.0)
    ]
    
    # Manual context creation to simulate StarGroundConstraint effectively
    context = LossContext.from_netlist_and_board(netlist, board)
    
    # Find index of NET2
    net2_idx = -1
    for i, n in enumerate(netlist.nets):
        if n.name == "NET2":
            net2_idx = i
            break
            
    # Update context with star info
    context.star_net_indices = jnp.array([net2_idx], dtype=jnp.int32)
    context.is_star_net = jnp.zeros((netlist.n_nets,), dtype=jnp.bool_).at[net2_idx].set(True)
    context.star_weights = jnp.array([1.0], dtype=jnp.float32)
    context.star_anchor_pos = jnp.zeros((1, 2), dtype=jnp.float32) # Not used for crossing
    context.star_has_anchor = jnp.array([False], dtype=jnp.bool_)
    
    return context


def test_star_net_detours_to_virtual_node(star_aware_context):
    """Verify that a star-net detours to its virtual node instead of the board star point."""
    loss_fn = GroundCrossingLoss()
    
    # Components at y=25 (far from board star point at y=50)
    # Positions: [U1, U2, U3, U4]
    # U3, U4 are the star net (NET2)
    positions = jnp.array([
        [25.0, 25.0], [75.0, 25.0], # NET1 (Regular)
        [25.0, 25.0], [75.0, 25.0]  # NET2 (Star)
    ])
    rotations = jnp.zeros((4, 4))
    
    # Virtual Nodes: [NET1_VN, NET2_VN]
    # Set NET2_VN exactly where the crossing occurs (at y=25)
    net_virtual_nodes = jnp.array([
        [50.0, 50.0], # NET1_VN (at board star point)
        [50.0, 25.0]  # NET2_VN (exactly at crossing path)
    ])
    
    # Compute penalty
    penalty = loss_fn(positions, rotations, star_aware_context, net_virtual_nodes=net_virtual_nodes).value
    
    # NET1 should have penalty because it's at y=25 but detours to y=50
    # NET2 should have NO penalty because it's at y=25 and detours to NET2_VN which is also at y=25
    # The direct distance is 50.
    # NET1 detour: dist([25,25], [50,50]) + dist([75,25], [50,50]) - 50
    # dist = sqrt(25^2 + 25^2) = 25*sqrt(2) approx 35.35
    # detour = 35.35 + 35.35 - 50 = 20.7
    
    # NET2 detour: dist([25,25], [50,25]) + dist([75,25], [50,25]) - 50
    # dist = 25 + 25 = 50
    # detour = 50 + 50 - 50 = 0
    
    # Total penalty should be just from NET1
    assert penalty > 0, "Total penalty should be non-zero due to NET1"
    assert penalty < 25.0, f"Penalty should be approx 20.7, got {penalty}"
    
    # Now move NET2_VN far away (y=75) and verify penalty increases
    net_virtual_nodes_far = jnp.array([
        [50.0, 50.0],
        [50.0, 75.0]
    ])
    penalty_far = loss_fn(positions, rotations, star_aware_context, net_virtual_nodes=net_virtual_nodes_far).value
    assert penalty_far > penalty, "Penalty should increase if star node is far from crossing"


def test_star_gradient_pulls_towards_virtual_node(star_aware_context):
    """Verify that gradients pull star-net components towards their virtual node."""
    loss_fn = GroundCrossingLoss()
    
    positions = jnp.array([
        [25.0, 25.0], [75.0, 25.0],
        [25.0, 25.0], [75.0, 25.0]
    ])
    
    # NET2_VN at y=75
    net_virtual_nodes = jnp.array([
        [50.0, 50.0],
        [50.0, 75.0]
    ])
    
    grad_fn = jax.grad(lambda pos: loss_fn(pos, jnp.zeros((4, 4)), star_aware_context, net_virtual_nodes=net_virtual_nodes).value)
    grads = grad_fn(positions)
    
    # For NET2 (U3, U4 at indices 2, 3), grad_y should be NEGATIVE to pull towards y=75
    # (Since grad is steepest ASCENT, we move in -grad to decrease loss).
    # If loss decreases as y -> 75, then grad_y should be negative.
    assert grads[2, 1] < 0, f"U3.y gradient should pull towards virtual node at y=75, got {grads[2, 1]}"
    assert grads[3, 1] < 0, f"U4.y gradient should pull towards virtual node at y=75, got {grads[3, 1]}"
