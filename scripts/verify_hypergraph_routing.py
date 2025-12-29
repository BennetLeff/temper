import math
import jax.numpy as jnp
from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.routing.bridge.api import get_routing_context, get_cost_map_for_net
from temper_placer.routing.bridge.types import RoutingStrategy
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

def verify_fix():
    print("=== Verifying Physics-Aware Hypergraph Routing ===")
    
    # 1. Setup realistic failing scenario
    board = Board(
        width=100, height=150,
        zones=[
            Zone("HV_ZONE", (0, 100, 100, 150), net_classes=["HighVoltage"]),
            Zone("LV_ZONE", (0, 0, 100, 50), net_classes=["Signal"]),
        ]
    )
    
    # GND net pins
    # Pin 1: In HV Zone (hostile)
    # Pin 2: In LV Zone (home)
    j_ac_in = Component(
        ref="J_AC_IN", footprint="CONN", bounds=(10, 10),
        pins=[Pin(name="GND", number="1", position=(0, 0), net="GND")],
        initial_position=(10.0, 125.0)
    )
    
    u_mcu = Component(
        ref="U_MCU", footprint="MCU", bounds=(10, 10),
        pins=[Pin(name="GND", number="1", position=(0, 0), net="GND")],
        initial_position=(50.0, 25.0)
    )
    
    gnd_net = Net(name="GND", pins=[("J_AC_IN", "1"), ("U_MCU", "1")], net_class="Signal")
    netlist = Netlist(components=[j_ac_in, u_mcu], nets=[gnd_net])
    
    positions = jnp.array([
        [10.0, 125.0],
        [50.0, 25.0]
    ])
    
    # 2. Build and Analyze
    hg = netlist_to_hypergraph(netlist)
    ctx = get_routing_context(hg, positions, board, netlist)
    
    # Assert inference
    assert ctx.get_strategy("GND") == RoutingStrategy.EDGE_HUG
    print("✓ Inference correct: GND is EDGE_HUG")
    
    # 3. Route
    cell_size = 1.0
    router = MazeRouter.from_board(board, cell_size_mm=cell_size)
    router.block_components(netlist.components, positions)
    
    cost_map = get_cost_map_for_net(router.grid_size, cell_size, ctx, "GND")
    
    # Pins in world coords
    pin_pos = [
        (10.0, 125.0),
        (50.0, 25.0)
    ]
    assignment = LayerAssignment("GND", Layer.L1_TOP, {Layer.L1_TOP}, False, "Test")
    
    path_res = router.route_net("GND", pin_pos, assignment, cost_map=cost_map)
    
    assert path_res.success
    print(f"✓ Path found: {len(path_res.cells)} cells")
    
    # 4. Assert Path hug edges
    # The center of board is (50, 75).
    # If it hugs edge, min_x or max_x should be near 0 or 100, or min_y/max_y near 0/150.
    # More importantly, it should NOT pass through the center (40-60, 60-90)
    
    passed_through_center = False
    for cell in path_res.cells:
        wx, wy = cell.x * cell_size, cell.y * cell_size
        if 30 < wx < 70 and 60 < wy < 90:
            passed_through_center = True
            break
            
    assert not passed_through_center
    print("✓ Verification SUCCESS: Trace hugs edge and avoids zone center")

if __name__ == "__main__":
    verify_fix()
