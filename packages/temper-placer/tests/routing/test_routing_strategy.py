import jax.numpy as jnp
import numpy as np
from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.core.design_rules import DesignRules, NetClassRules

def test_plane_preferred_strategy():
    print("\n=== Testing plane_preferred Strategy ===")
    # 4-layer board: L1=Signal, L2=GND(Plane), L3=PWR(Plane), L4=Signal
    stackup = LayerStackup.default_4layer()
    board = Board(width=20, height=20, layer_stackup=stackup)
    
    # GND net with pins on Top (side 0)
    c1 = Component(ref="C1", footprint="P", bounds=(2, 2), pins=[Pin("1", "GND", (0,0), "GND")], initial_position=(5, 5))
    c2 = Component(ref="C2", footprint="P", bounds=(2, 2), pins=[Pin("1", "GND", (0,0), "GND")], initial_position=(15, 15))
    n_gnd = Net("GND", [("C1", "GND"), ("C2", "GND")])
    
    netlist = Netlist(components=[c1, c2], nets=[n_gnd])
    positions = jnp.array([[5., 5.], [15., 15.]])
    
    # Design rules with plane_preferred
    dr = DesignRules()
    dr.net_classes["GND"] = NetClassRules(
        name="GND",
        trace_width=0.5,
        clearance=0.2,
        routing_strategy="plane_preferred"
    )
    
    router = MazeRouter.from_board(board, cell_size_mm=1.0, design_rules=dr)
    
    net_order = ["GND"]
    # Initial assignment allows Top and Bottom
    assignments = {
        "GND": LayerAssignment("GND", Layer.L1_TOP, {Layer.L1_TOP, Layer.L4_BOT})
    }
    
    print("Routing with plane_preferred...")
    results = router.rrr_route_all_nets(netlist, positions, net_order, assignments)
    
    gnd_path = results["GND"]
    assert gnd_path.success
    
    # Check if path uses L2 (index 1) or L3 (index 2)
    # These are plane layers in default_4layer
    uses_plane = any(cell.layer in (1, 2) for cell in gnd_path.cells)
    
    # DEBUG: print layers used
    layers_used = sorted(list(set(cell.layer for cell in gnd_path.cells)))
    print(f"Layers used by GND: {layers_used}")
    
    assert uses_plane, "GND net should have used plane layers but used only outer layers"
    print("✓ Success: GND net preferred plane layers!")

def test_wide_trace_strategy():
    print("\n=== Testing wide_trace Strategy (Via Penalty) ===")
    # 2-layer board to make it simpler
    board = Board(width=20, height=20)
    
    # PWR net with pins on Top
    # Put an obstacle in the middle of L1 to force a choice: 
    # 1. Route around on L1
    # 2. Use vias to jump to L4 and back
    c1 = Component(ref="C1", footprint="P", bounds=(2, 2), pins=[Pin("1", "PWR", (0,0), "PWR")], initial_position=(5, 10))
    c2 = Component(ref="C2", footprint="P", bounds=(2, 2), pins=[Pin("1", "PWR", (0,0), "PWR")], initial_position=(15, 10))
    n_pwr = Net("PWR", [("C1", "PWR"), ("C2", "PWR")])
    
    netlist = Netlist(components=[c1, c2], nets=[n_pwr])
    positions = jnp.array([[5., 10.], [15., 10.]])
    
    # Design rules with wide_trace
    dr = DesignRules()
    dr.net_classes["PWR"] = NetClassRules(
        name="PWR",
        trace_width=1.0,
        clearance=0.2,
        routing_strategy="wide_trace"
    )
    
    router = MazeRouter.from_board(board, cell_size_mm=1.0, design_rules=dr)
    # Lower normal via cost to make it competitive with routing around
    router.via_cost = 5.0 
    
    # Add a wall on L1 at x=10, y=5..15
    for y in range(5, 16):
        router.occupancy[10, y, 0] = -1 # Blocked
        
    net_order = ["PWR"]
    assignments = {
        "PWR": LayerAssignment("PWR", Layer.L1_TOP, {Layer.L1_TOP, Layer.L4_BOT})
    }
    
    print("Routing with wide_trace (should prefer routing around obstacle on L1)...")
    results = router.rrr_route_all_nets(netlist, positions, net_order, assignments)
    
    pwr_path = results["PWR"]
    assert pwr_path.success
    print(f"PWR Via Count with wide_trace: {pwr_path.via_count}")
    
    # Should have 0 vias because of high via penalty from wide_trace strategy
    assert pwr_path.via_count == 0, f"Expected 0 vias with wide_trace strategy, got {pwr_path.via_count}"
    
    # Now compare with standard strategy
    dr.net_classes["PWR"].routing_strategy = "standard"
    router.rip_up_net("PWR")
    
    print("Routing with standard strategy (should use vias to jump over obstacle)...")
    results_std = router.rrr_route_all_nets(netlist, positions, net_order, assignments)
    pwr_path_std = results_std["PWR"]
    assert pwr_path_std.success
    print(f"PWR Via Count with standard: {pwr_path_std.via_count}")
    
    # With standard strategy and via_cost=5, it might choose to jump
    # Route around length is approx 10 (across) + 12 (up and down) = 22
    # Route through length is approx 10 + 2*via_cost = 10 + 10 = 20
    # So it should prefer vias.
    assert pwr_path_std.via_count > 0, "Standard strategy should have used vias"
    print("✓ Success: wide_trace strategy effectively discouraged vias!")

if __name__ == "__main__":
    test_plane_preferred_strategy()
    test_wide_trace_strategy()
