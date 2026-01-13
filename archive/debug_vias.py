import logging
import sys
from pathlib import Path
import math
import numpy as np

# Add package root to sys.path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
import temper_placer.routing.maze_router as mr
mr.HAS_NUMBA = True
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

# Configure logging to capture my new debug statements
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("temper_placer.routing.maze_router")

def debug_routing():
    input_pcb = Path("pcb/temper_placed.kicad_pcb")
    parse_result = parse_kicad_pcb(input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    
    router = MazeRouter.from_board(
        board,
        cell_size_mm=0.1,
        via_cost=25.0
    )
    
    positions = np.array([c.initial_position for c in netlist.components])
    rotations = np.array([c.initial_rotation or 0 for c in netlist.components])
    sides = np.array([c.initial_side or 0 for c in netlist.components])
    
    router.block_pads(
        netlist.components,
        positions,
        netlist,
        rotations=rotations,
        sides=sides
    )
    
    # Target net: SW_NODE
    net_name = "SW_NODE"
    net = next(n for n in netlist.nets if n.name == net_name)
    
    # Get pins
    pins = []
    comp_by_ref = {c.ref: c for c in netlist.components}
    for ref, pin_num in net.pins:
        comp = comp_by_ref[ref]
        pin = comp.get_pin(pin_num)
        if not pin:
            continue
            
        # Get absolute position
        cx, cy = comp.initial_position
        rot_rad = (comp.initial_rotation or 0) * (math.pi / 2)
        side_idx = comp.initial_side or 0
        
        px, py = pin.absolute_position((cx, cy), rot_rad, side_idx)
        pins.append((px, py))
    
    if len(pins) < 2:
        print(f"Net {net_name} has only {len(pins)} pins")
        return

    print(f"Routing {net_name} with {len(pins)} pins...")
    
    # Identify pad layers for debug
    for i, pin_pos in enumerate(pins):
        gx, gy = router._world_to_grid(pin_pos[0], pin_pos[1])
        pad_layers = [l for l in range(router.num_layers) if (gx, gy, l) in router._pad_net_map and router._pad_net_map[(gx, gy, l)] == net_name]
        print(f"Pin {i} at grid ({gx}, {gy}) is on layers: {pad_layers}")

    # Block Layer 0 between pins to force via
    # Pins are around x=170 and x=500. Block x=300 across FULL height.
    wall_gx = 300
    for y in range(router.grid_size[1]):
        router.block_rect(wall_gx, y, 10, 1, layer=0)
        # CRITICAL: Also add to _pad_net_map to prevent it from being unblocked as 'courtyard'
        for dx in range(10):
            router._pad_net_map[(wall_gx + dx, y, 0)] = "WALL_NET"
    print(f"Blocked Layer 0 TOTAL wall at x={wall_gx} between pins (locked against unblocking).")
    
    # Check wall status
    wall_check_x, wall_check_y = wall_gx + 5, 500
    occ = router.occupancy[wall_check_x, wall_check_y, 0]
    owner = router._pad_net_map.get((wall_check_x, wall_check_y, 0))
    print(f"Wall check at ({wall_check_x}, {wall_check_y}, L0): Occ={occ}, Owner={owner}")

    assignment = LayerAssignment(
        net=net_name,
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT} 
    )
    
    # We call route_net_mst since it's the default
    result = router.route_net_mst(
        net_name,
        pins,
        assignment,
        p_scale=10.0
    )
    
    print(f"Result successful: {result.success}")
    print(f"Via count: {result.via_count}")
    print(f"Layers used: {set(c.layer for c in result.cells)}")
    if result.success:
        layer_counts = {}
        for c in result.cells:
            layer_counts[c.layer] = layer_counts.get(c.layer, 0) + 1
        print(f"Layer distribution: {layer_counts}")

if __name__ == "__main__":
    debug_routing()
