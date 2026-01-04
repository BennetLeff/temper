
import logging
import sys
from pathlib import Path
import numpy as np

# Add package root to sys.path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
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
    
    # Target net: GATE_H
    net_name = "GATE_H"
    net = next(n for n in netlist.nets if n.name == net_name)
    
    # Get pins
    pins = []
    comp_by_ref = {c.ref: c for c in netlist.components}
    for ref, pin_name in net.pins:
        comp = comp_by_ref[ref]
        for pin in comp.pins:
            if pin.name == pin_name or pin.number == pin_name:
                pins.append(pin.absolute_position(
                    comp.initial_position,
                    (comp.initial_rotation or 0) * 3.14159 / 2,
                    side=comp.initial_side or 0
                ))
                break
    
    if len(pins) < 2:
        print(f"Net {net_name} has only {len(pins)} pins")
        return

    print(f"Routing {net_name} with {len(pins)} pins...")
    
    # Block Layer 0 between pins to force via
    # GATE_H pins are around (15, 80) and (45, 80) roughly? 
    # Let's just block a big rectangle in the middle of the board on L1
    router.block_rect(0, 0, router.grid_size[0], router.grid_size[1] // 2, layer=0)
    # Actually, let's block everything on L1 except the pins area
    # Or just block a vertical wall.
    router.block_rect(router.grid_size[0]//2 - 5, 0, 10, router.grid_size[1], layer=0)
    print("Blocked Layer 0 wall to force via.")
    
    # Mock assignment
    assignment = LayerAssignment(
        net=net_name,
        primary_layer=Layer.L1_TOP,
        allowed_layers=[Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT]
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

if __name__ == "__main__":
    debug_routing()
