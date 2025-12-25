import jax.numpy as jnp
import numpy as np
import pytest
from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Netlist, Component
from temper_placer.core.board import Board
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.legalization import legalize_abacus, resolve_overlaps_priority

def test_abacus_1d_optimality():
    """Verify Abacus produces optimal 1D placement."""
    board = Board(width=100.0, height=100.0)
    
    # 2 components, 10x10
    # C0 at 45, C1 at 50 -> Overlap of 5mm
    # Optimal should be C0 at 47.5, C1 at 57.5 (if uniform weights)
    # Total displacement = (47.5-45)^2 + (57.5-50)^2 = 2.5^2 + 7.5^2 = 6.25 + 56.25 = 62.5
    # Wait, if we minimize sum of squared displacements:
    # min (x0 - 45)^2 + (x1 - 50)^2 subject to x1 - x0 >= 10.5 (with 0.5 spacing)
    # Let x1 = x0 + 10.5
    # f(x0) = (x0 - 45)^2 + (x0 + 10.5 - 50)^2 = (x0 - 45)^2 + (x0 - 39.5)^2
    # f'(x0) = 2(x0 - 45) + 2(x0 - 39.5) = 4x0 - 169 = 0 -> x0 = 42.25
    # x1 = 52.75
    # Displacement: (42.25-45)^2 + (52.75-50)^2 = (-2.75)^2 + 2.75^2 = 7.5625 + 7.5625 = 15.125
    
    components = [
        Component(ref="C0", footprint="R", bounds=(10.0, 10.0), pins=[]),
        Component(ref="C1", footprint="R", bounds=(10.0, 10.0), pins=[]),
    ]
    netlist = Netlist(components=components, nets=[])
    
    positions = jnp.array([
        [45.0, 50.0],
        [50.0, 50.0]
    ])
    state = PlacementState(positions=positions, rotation_logits=jnp.zeros((2, 4)))
    
    context = LossContext(
        netlist=netlist,
        board=board,
        fixed_mask=np.zeros(2, dtype=bool)
    )
    
    legalized = legalize_abacus(state, context, n_rows=1, spacing=0.5)
    pos = np.array(legalized.positions)
    
    assert abs(pos[0, 0] - 42.25) < 1e-3
    assert abs(pos[1, 0] - 52.75) < 1e-3
    assert abs(pos[0, 1] - 50.0) < 1e-3 # Snapped to row center

def test_resolve_overlaps_priority():
    """Verify priority-based overlap resolution converges on a dense case."""
    board = Board(width=50.0, height=50.0)
    
    # 4 components in a tight 2x2 grid that overlap
    components = [
        Component(ref=f"C{i}", footprint="R", bounds=(10.0, 10.0), pins=[])
        for i in range(4)
    ]
    netlist = Netlist(components=components, nets=[])
    
    # All near center (25, 25)
    positions = jnp.array([
        [24.0, 24.0],
        [26.0, 24.0],
        [24.0, 26.0],
        [26.0, 26.0]
    ])
    
    # They should be pushed apart to at least 10.5mm center-to-center on one axis
    legalized_pos = resolve_overlaps_priority(
        np.array(positions),
        netlist,
        board,
        max_iterations=100,
        min_separation=0.5
    )
    
    # Check for overlaps
    for i in range(4):
        for j in range(i + 1, 4):
            dx = abs(legalized_pos[i, 0] - legalized_pos[j, 0])
            dy = abs(legalized_pos[i, 1] - legalized_pos[j, 1])
            assert (dx >= 10.5 - 1e-3) or (dy >= 10.5 - 1e-3), f"Overlap between {i} and {j}"

if __name__ == "__main__":
    pytest.main([__file__])
