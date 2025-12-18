"""Extended tests for SpectralInitializer."""
import pytest
import jax.numpy as jnp
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.board import Board

def test_disconnected_component_separation():
    """Verify that nodes within disconnected components are separated."""
    # Topology: R1-R2 and R3-R4
    components = [
        Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R3", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N2")]),
        Component(ref="R4", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N2")]),
    ]
    nets = [
        Net(name="N1", pins=[("R1", "1"), ("R2", "1")]),
        Net(name="N2", pins=[("R3", "1"), ("R4", "1")]),
    ]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100, height=100)
    
    initializer = SpectralInitializer()
    positions = initializer.initialize(netlist, board)
    
    # R1 and R2 should have different positions
    dist12 = float(jnp.linalg.norm(positions[0] - positions[1]))
    assert dist12 > 1.0, f"R1 and R2 are too close: {dist12}"
    
    # R3 and R4 should have different positions
    dist34 = float(jnp.linalg.norm(positions[2] - positions[3]))
    assert dist34 > 1.0, f"R3 and R4 are too close: {dist34}"
