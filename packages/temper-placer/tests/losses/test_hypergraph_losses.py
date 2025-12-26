from temper_placer.core.netlist import Netlist, Component, Net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.losses.physics.hypergraph_losses import (
    hypergraph_wirelength_loss, 
    high_voltage_repulsion_loss
)
import jax.numpy as jnp
import jax

def test_wirelength_accuracy():
    """
    Verify the sparse matrix wirelength calculation matches a manual check.
    """
    # Simple star: Center (0,0) connected to (1,0) and (0,1)
    c0 = Component("U0", "R", (1,1))
    c1 = Component("U1", "R", (1,1))
    c2 = Component("U2", "R", (1,1))
    
    # Net connecting all three
    net = Net("n0", [("U0", "1"), ("U1", "1"), ("U2", "1")])
    netlist = Netlist([c0, c1, c2], [net])
    
    hg = netlist_to_hypergraph(netlist)
    
    # Positions: U0=(0,0), U1=(1,0), U2=(0,1)
    positions = jnp.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0]
    ])
    
    # Manual Calc
    # Centroid = (1/3, 1/3)
    # Dist^2 sum = 
    # U0: (1/3)^2 + (1/3)^2 = 2/9
    # U1: (2/3)^2 + (1/3)^2 = 5/9
    # U2: (1/3)^2 + (2/3)^2 = 5/9
    # Total = 12/9 = 4/3 = 1.333...
    
    loss = hypergraph_wirelength_loss(positions, hg)
    assert jnp.allclose(loss, 1.3333333)

def test_hv_repulsion():
    """Verify HV-LV repulsion logic."""
    # HV Component at 0,0
    # LV Component at 5,0
    # Limit = 10.0
    # Violation = 5.0
    
    c_hv = Component("HV", "R", (1,1))
    c_lv = Component("LV", "R", (1,1))
    
    net_hv = Net("HV", [("HV", "1")], net_class="HighVoltage")
    # Need dummy net for LV to ensure it's in the graph
    net_lv = Net("LV", [("LV", "1")], net_class="Signal")
    
    # Add dummy connections to make nets valid (>=2 pins)
    # Actually, let's just make the components self-loop for testing 
    # or add dummy components.
    c_hv2 = Component("HV2", "R", (1,1))
    c_lv2 = Component("LV2", "R", (1,1))
    
    net_hv.pins.append(("HV2", "1"))
    net_lv.pins.append(("LV2", "1"))
    
    netlist = Netlist([c_hv, c_lv, c_hv2, c_lv2], [net_hv, net_lv])
    hg = netlist_to_hypergraph(netlist)
    
    positions = jnp.array([
        [0.0, 0.0], # HV
        [5.0, 0.0], # LV
        [0.0, 0.0], # HV2
        [15.0, 0.0] # LV2 (Safe)
    ])
    
    # Calc expected loss
    # Pair (HV, LV): dist 5, violation 5. loss 25
    # Pair (HV2, LV): dist 5, violation 5. loss 25
    # Pair (HV, LV2): dist 15, violation 0.
    # Pair (HV2, LV2): dist 15, violation 0.
    # Total = 50
    
    loss = high_voltage_repulsion_loss(positions, hg, min_clearance=10.0)
    assert jnp.allclose(loss, 50.0)
