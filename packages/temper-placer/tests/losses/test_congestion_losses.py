from temper_placer.core.netlist import Netlist, Component, Net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.losses.physics.congestion import ElectrostaticCongestionLoss
from temper_placer.core.board import Board
from temper_placer.losses.base import LossContext
import jax.numpy as jnp
import jax

def test_electrostatic_congestion():
    """Verify congestion loss identifies overlaps of net distributions."""
    # 2 Nets, each with 2 components
    c0 = Component("U0", "R", (1,1))
    c1 = Component("U1", "R", (1,1))
    c2 = Component("U2", "R", (1,1))
    c3 = Component("U3", "R", (1,1))
    
    net1 = Net("n1", [("U0", "1"), ("U1", "1")])
    net2 = Net("n2", [("U2", "1"), ("U3", "1")])
    
    netlist = Netlist([c0, c1, c2, c3], [net1, net2])
    board = Board(width=100, height=100)
    ctx = LossContext.from_netlist_and_board(netlist, board)
    
    loss_fn = ElectrostaticCongestionLoss()
    
    # Case 1: Nets are far apart -> Low congestion
    # Components further apart within nets for larger spread
    pos_far = jnp.array([
        [10.0, 10.0], [20.0, 10.0], # Net 1
        [80.0, 80.0], [90.0, 80.0]  # Net 2
    ])
    loss_far = loss_fn(pos_far, jnp.zeros((4, 4)), ctx).value
    
    # Case 2: Nets are on top of each other -> High congestion
    pos_near = jnp.array([
        [50.0, 50.0], [60.0, 50.0], # Net 1
        [50.0, 50.0], [60.0, 50.0]  # Net 2
    ])
    loss_near = loss_fn(pos_near, jnp.zeros((4, 4)), ctx).value
    
    assert loss_near > loss_far
    print(f"Far loss: {loss_far:.4f}, Near loss: {loss_near:.4f}")
