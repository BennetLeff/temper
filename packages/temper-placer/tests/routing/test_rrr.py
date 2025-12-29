import math
import jax.numpy as jnp
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

def test_rrr_convergence():
    print("=== Testing RRR Convergence on Crossing Nets ===")
    
    # Simple board where two nets MUST cross or one must take long way
    board = Board(width=20, height=20)
    
    # Net 1: (5, 5) to (15, 5)
    # Net 2: (10, 2) to (10, 10)
    # They cross at (10, 5)
    
    c1 = Component(ref="C1", footprint="P", bounds=(2, 2), pins=[Pin("1", "1", (0,0), "N1")], initial_position=(5, 5))
    c2 = Component(ref="C2", footprint="P", bounds=(2, 2), pins=[Pin("1", "1", (0,0), "N1")], initial_position=(15, 5))
    c3 = Component(ref="C3", footprint="P", bounds=(2, 2), pins=[Pin("1", "1", (0,0), "N2")], initial_position=(10, 2))
    c4 = Component(ref="C4", footprint="P", bounds=(2, 2), pins=[Pin("1", "1", (0,0), "N2")], initial_position=(10, 10))
    
    n1 = Net("N1", [("C1", "1"), ("C2", "1")])
    n2 = Net("N2", [("C3", "1"), ("C4", "1")])
    
    netlist = Netlist(components=[c1, c2, c3, c4], nets=[n1, n2])
    positions = jnp.array([[5., 5.], [15., 5.], [10., 2.], [10., 10.]])
    
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1) # Single layer forces one to move around
    
    net_order = ["N1", "N2"]
    assignments = {
        "N1": LayerAssignment("N1", Layer.L1_TOP, {Layer.L1_TOP}),
        "N2": LayerAssignment("N2", Layer.L1_TOP, {Layer.L1_TOP})
    }
    
    print("Running RRR...")
    results = router.rrr_route_all_nets(netlist, positions, net_order, assignments, max_iterations=20)
    
    conflicts = int(jnp.sum(router.present_congestion > 1.0))
    print(f"Final Conflicts: {conflicts}")
    
    assert conflicts == 0
    print("✓ Success: RRR resolved the crossing conflict on a single layer!")

if __name__ == "__main__":
    test_rrr_convergence()
