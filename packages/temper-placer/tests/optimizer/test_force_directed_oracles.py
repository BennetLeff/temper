import jax
import jax.numpy as jnp
import pytest
from temper_placer.heuristics.force_directed import compute_force_directed_layout
from temper_placer.core.netlist import Netlist, Component, Net, Pin

def test_force_directed_equilibrium_known():
    """Verify force-directed layout reaches equilibrium for two connected components."""
    # Two components R1-R2 connected by a net
    components = [
        Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
    ]
    nets = [Net(name="N1", pins=[("R1", "1"), ("R2", "1")])]
    netlist = Netlist(components=components, nets=nets)
    
    # Start them far apart
    initial_pos = jnp.array([
        [0.0, 0.0],
        [100.0, 0.0]
    ])
    
    # Run simulation
    # With F_attraction = -diff and F_repulsion = diff/dist^2
    # Equilibrium occurs when attraction = repulsion
    # -d + 1/d = 0 -> d^2 = 1 -> d = 1
    
    # Use many iterations and small learning rate for stability
    final_pos = compute_force_directed_layout(
        netlist, 
        initial_pos, 
        iterations=1000, 
        learning_rate=0.01
    )
    
    dist = jnp.sqrt(jnp.sum((final_pos[0] - final_pos[1])**2))
    # Equilibrium distance should be around 1.0 (based on formula in compute_force_directed_layout)
    assert float(dist) == pytest.approx(1.0, abs=0.1)

def test_force_directed_newton_third_law():
    """Verify that forces are symmetric (F_ab = -F_ba)."""
    # We can't easily extract forces from the current implementation, 
    # but we can check if the center of mass remains constant if no external forces.
    # Note: the current repulsion formula sum(diff / dist_sq) is symmetric.
    
    components = [
        Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
        Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0), net="N1")]),
    ]
    nets = [Net(name="N1", pins=[("R1", "1"), ("R2", "1")])]
    netlist = Netlist(components=components, nets=nets)
    
    initial_pos = jnp.array([
        [10.0, 10.0],
        [20.0, 20.0]
    ])
    initial_com = jnp.mean(initial_pos, axis=0)
    
    final_pos = compute_force_directed_layout(
        netlist, 
        initial_pos, 
        iterations=10, 
        learning_rate=0.1
    )
    
    final_com = jnp.mean(final_pos, axis=0)
    # Center of mass should be conserved if forces are symmetric and no boundaries
    assert jnp.allclose(initial_com, final_com, atol=1e-5)
