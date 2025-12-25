import jax.numpy as jnp
import numpy as np
from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Netlist, Component
from temper_placer.core.board import Board
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.legalization import legalize_abacus

def test_abacus_simple_row():
    # Board 100x100
    board = Board(width=100.0, height=100.0)
    
    # 3 components, 10x10, all at same Y
    # C0 at 10, C1 at 15 (overlap), C2 at 20 (overlap)
    components = [
        Component(ref="C0", footprint="R", bounds=(10.0, 10.0), pins=[]),
        Component(ref="C1", footprint="R", bounds=(10.0, 10.0), pins=[]),
        Component(ref="C2", footprint="R", bounds=(10.0, 10.0), pins=[]),
    ]
    netlist = Netlist(components=components, nets=[])
    
    positions = jnp.array([
        [10.0, 50.0],
        [15.0, 50.0],
        [20.0, 50.0]
    ])
    rotation_logits = jnp.zeros((3, 4))
    state = PlacementState(positions=positions, rotation_logits=rotation_logits)
    
    context = LossContext(
        netlist=netlist,
        board=board,
        fixed_mask=np.zeros(3, dtype=bool)
    )
    
    # Currently legalize_abacus returns project_to_drc_feasible(state, context)
    legalized = legalize_abacus(state, context, n_rows=1)
    
    print("Original positions:\n", positions)
    print("Legalized positions:\n", legalized.positions)
    
    # Check for overlaps
    # In Abacus, they should be packed tightly if they overlapped
    # C0 width=10, C1 width=10, C2 width=10
    # Total width 30.
    # Center positions: x, x+10, x+20
    
    pos = np.array(legalized.positions)
    for i in range(3):
        for j in range(i + 1, 3):
            dx = abs(pos[i, 0] - pos[j, 0])
            min_dx = (components[i].bounds[0] + components[j].bounds[0]) / 2
            assert dx >= min_dx - 1e-3, f"Overlap between {i} and {j}: dx={dx} < {min_dx}"

if __name__ == "__main__":
    test_abacus_simple_row()
