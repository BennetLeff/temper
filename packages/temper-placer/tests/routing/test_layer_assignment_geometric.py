
import jax.numpy as jnp
import pytest
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.layer_assignment import assign_layers, Layer

def test_geometric_assignment():
    # Setup simple netlist
    # C1 (0, 0), C2 (10, 0) -> Horizontal Net
    # C3 (0, 10), C4 (0, 20) -> Vertical Net
    
    c1 = Component(ref="C1", footprint="R", bounds=(1,1), pins=[Pin(name="1", number="1", position=(0,0))])
    c2 = Component(ref="C2", footprint="R", bounds=(1,1), pins=[Pin(name="1", number="1", position=(0,0))])
    c3 = Component(ref="C3", footprint="R", bounds=(1,1), pins=[Pin(name="1", number="1", position=(0,0))])
    c4 = Component(ref="C4", footprint="R", bounds=(1,1), pins=[Pin(name="1", number="1", position=(0,0))])
    
    net_h = Net(name="NET_HORIZ", pins=[("C1", "1"), ("C2", "1")])
    net_v = Net(name="NET_VERT", pins=[("C3", "1"), ("C4", "1")])
    
    netlist = Netlist(components=[c1, c2, c3, c4], nets=[net_h, net_v])
    
    # Mock positions
    positions = jnp.array([
        [0.0, 0.0],
        [10.0, 0.0],
        [0.0, 10.0],
        [0.0, 20.0]
    ])
    
    assignments = assign_layers(netlist, component_positions=positions)
    
    assert assignments["NET_HORIZ"].primary_layer == Layer.L1_TOP
    assert assignments["NET_VERT"].primary_layer == Layer.L4_BOT
    
    print("Geometric assignment verified successfully!")

if __name__ == "__main__":
    test_geometric_assignment()
