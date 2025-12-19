
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import WirelengthLoss

@pytest.fixture
def simple_context():
    board = Board(width=100.0, height=100.0)
    
    c1 = Component("C1", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))])
    c2 = Component("C2", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))])
    c3 = Component("C3", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))])
    
    # Net A: C1-C2 (weight 1.0)
    # Net B: C2-C3 (weight 1.0)
    net_a = Net("NetA", [("C1", "2"), ("C2", "1")], weight=1.0)
    net_b = Net("NetB", [("C2", "2"), ("C3", "1")], weight=1.0)
    
    netlist = Netlist([c1, c2, c3], [net_a, net_b])
    
    return LossContext.from_netlist_and_board(netlist, board)

def test_wirelength_default_weights(simple_context):
    loss_fn = WirelengthLoss()
    
    # Positions: C1(0,0), C2(10,0), C3(20,0)
    # Net A length ~ 10
    # Net B length ~ 10
    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])
    
    result = loss_fn(positions, rotations, simple_context)
    
    # Approx 18.3 (Geometric 9.0 + 9.0 = 18.0)
    assert 18.0 < result.value < 19.0

def test_wirelength_custom_weights(simple_context):
    # Override NetA weight to 10.0
    loss_fn = WirelengthLoss(net_weights={"NetA": 10.0})
    
    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])
    
    result = loss_fn(positions, rotations, simple_context)
    
    # Net A (10.0 * 9) + Net B (1.0 * 9) = 90 + 9 = 99.0
    # Soft max approx adds a bit
    assert 99.0 < result.value < 102.0

def test_wirelength_net_class_weights(simple_context):
    # Assign net classes
    simple_context.netlist.nets[0].net_class = "HighSpeed" # NetA
    simple_context.netlist.nets[1].net_class = "Power"     # NetB
    
    # Re-create context to pick up net classes? 
    # Net classes are on components usually, but Net has net_class too.
    # LossContext uses Component net_class for HV/LV indices.
    # Net.net_class is stored in Net object.
    
    # Test weight by net_class
    loss_fn = WirelengthLoss(net_weights={"HighSpeed": 5.0, "Power": 0.5})
    
    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])
    
    result = loss_fn(positions, rotations, simple_context)
    
    # Net A (HighSpeed): 5.0 * 9 = 45
    # Net B (Power): 0.5 * 9 = 4.5
    # Total = 49.5
    assert 49.0 < result.value < 51.0
