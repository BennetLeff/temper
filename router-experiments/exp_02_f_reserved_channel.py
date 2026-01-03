
import sys
import time
import numpy as np
import argparse
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad
from kiutils.items.common import Position, Net
from kiutils.items.gritems import GrRect

# Ensure imports work
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, Layer, LayerConstraint
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig

def create_pin_footprint(ref: str, x: float, y: float, net_name: str) -> Footprint:
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Test:Pin"
    fp.properties = {"Reference": ref, "Value": "Pin"}
    
    pad = Pad()
    pad.number = "1"
    pad.position = Position(X=0, Y=0)
    pad.size = Position(X=0.8, Y=0.8) 
    pad.type = "smd"
    pad.shape = "rect"
    pad.layers = ["F.Cu", "F.Mask"]
    pad.drill = None
    pad.net = Net(name=net_name)
    fp.pads.append(pad)
    return fp

def generate_reserved_channel_pcb(path: Path, grid_size: int = 8, pitch: float = 2.54):
    """
    Generate an N x N grid of pins with a RESERVED CHANNEL.
    The center row (grid_size // 2) is missing all pins except the center pin.
    This creates an empty escape corridor.
    """
    b = KiBoard.create_new()
    nets = []
    footprints = []
    
    center_idx = grid_size // 2
    
    # 1. Target Net: Pin at (Center, Center)
    escape_net = "NET_ESCAPE"
    nets.append(Net(number=1, name=escape_net))
    
    # Place target pin at the VERY center
    tx = center_idx * pitch + 10
    ty = center_idx * pitch + 10
    footprints.append(create_pin_footprint("TARGET", tx, ty, escape_net))
    
    # External Destination (Top edge)
    footprints.append(create_pin_footprint("DEST", tx, 5.0, escape_net))
    
    # 2. Obstacle Nets (The Dense Grid)
    # We populate every row/col EXCEPT the center row corridor.
    net_count = 2
    for r in range(grid_size):
        for c in range(grid_size):
            # Skip the target pin position (already placed)
            if r == center_idx and c == center_idx:
                continue
            
            # THE RESERVED CHANNEL:
            # Skip all pins in the center row EXCEPT the target pin.
            # This leaves a horizontal "highway" free of pins.
            if r == center_idx:
                continue
                
            net_name = f"NET_OBS_{r}_{c}"
            nets.append(Net(number=net_count, name=net_name))
            
            x = c * pitch + 10
            y = r * pitch + 10
            footprints.append(create_pin_footprint(f"P_{r}_{c}", x, y, net_name))
            net_count += 1

    b.nets = nets
    b.footprints = footprints
    
    # Boundary
    max_dim = (grid_size + 2) * pitch + 20
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=max_dim, Y=max_dim),
        layer="Edge.Cuts", width=0.1
    ))
    
    b.to_file(str(path))
    return len(nets)

def run_reserved_channel_benchmark(grid_size: int = 8, pitch: float = 2.54, cell_size: float = 0.1):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    pcb_path = output_dir / "exp_02_f_reserved_channel_input.kicad_pcb"
    
    print(f"\nGenerating Reserved Channel Benchmark: {grid_size}x{grid_size} Grid, Pitch={pitch}mm...")
    num_nets = generate_reserved_channel_pcb(pcb_path, grid_size, pitch)
    print(f"  Created {num_nets} nets.")
    
    # Parse
    result = parse_kicad_pcb(pcb_path)
    for c in result.netlist.components:
        if c.bounds == (0.0, 0.0): c.bounds = (0.8, 0.8)
        
    # Re-init router with 2 layers
    router = MazeRouter.from_board(
        result.board, 
        cell_size_mm=cell_size, 
        num_layers=2, 
        via_cost=5.0,
        min_clearance=0.1,
        wrong_way_penalty=2.0,
        soft_blocking=True
    )
    
    # Block pads
    positions = np.array([c.initial_position for c in result.netlist.components])
    router.block_pads(result.netlist.components, positions, result.netlist, clearance=0.1)

    # 1. Assign Layers
    custom_constraints = [
        LayerConstraint(
            net_pattern=r"NET_ESCAPE",
            allowed_layers={Layer.L1_TOP},
            preferred_layer=Layer.L1_TOP,
            reason="Channel Strategy: Route on L1 highway"
        )
    ]

    assignments = assign_layers(
        result.netlist, 
        constraints=custom_constraints,
        component_positions=positions
    )
    
    # 2. Route
    print(f"  Routing {num_nets} nets...")
    start_time = time.time()
    
    net_order = [n.name for n in result.netlist.nets if n.name]
    
    # Run Routing
    results = router.rrr_route_all_nets(
        netlist=result.netlist,
        positions=positions,
        net_order=net_order,
        assignments=assignments,
        max_iterations=5,
        component_margin=0.1,
    )
            
    duration = time.time() - start_time
    print(f"  Routing Finished in {duration:.3f}s")
    
    # Completion audit
    routed_count = sum(1 for r in results.values() if r.success)
    print(f"  Completion: {routed_count}/{num_nets} ({routed_count/num_nets*100:.1f}%)")
    
    # Check specifically for the escape net
    esc_result = results.get("NET_ESCAPE")
    if esc_result and esc_result.success:
        print("  ✓ NET_ESCAPE: SUCCESS (Found the corridor!)")
    else:
        print(f"  ✗ NET_ESCAPE: FAILED ({esc_result.failure_reason if esc_result else 'Not found'})")
    
    conflicts = router.get_conflict_locations()
    print(f"  Remaining Conflicts: {len(conflicts)}")
    
    if len(conflicts) == 0 and routed_count == num_nets and esc_result and esc_result.success:
        print("\n  STATUS: SUCCESS")
    else:
        print("\n  STATUS: FAILED")

if __name__ == "__main__":
    run_reserved_channel_benchmark()
