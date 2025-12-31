
import sys
import time
import numpy as np
import argparse
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad, DrillDefinition
from kiutils.items.common import Position, Net
from kiutils.items.gritems import GrRect

# Ensure imports work
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, Layer
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig

def create_pin_footprint(ref: str, x: float, y: float, net_name: str) -> Footprint:
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Test:Pin"
    fp.properties = {"Reference": ref, "Value": "Pin"}
    
    pad = Pad()
    pad.number = "1"
    pad.position = Position(X=0, Y=0)
    pad.size = Position(X=0.8, Y=0.8) # 0.8mm pad
    pad.type = "thru_hole"
    pad.shape = "circle"
    pad.layers = ["*.Cu", "*.Mask"]
    pad.drill = DrillDefinition(diameter=0.5)
    pad.net = Net(name=net_name)
    fp.pads.append(pad)
    return fp

def generate_weave_pcb(path: Path, grid_size: int = 10, pitch: float = 2.0):
    """
    Generate a N x N grid weave.
    - Horizontal nets connecting rows.
    - Vertical nets connecting cols.
    - 2 Giant Diagonal nets slicing through everything.
    """
    b = KiBoard.create_new()
    
    nets = []
    footprints = []
    


    # Actually, simpler: 
    # Pin Grid is N x N.
    # We assign nets in a checkerboard or just strictly alternating?
    # No, we want distinct H-traces and V-traces.
    # Let's place 2 pins per grid cell? 
    # Or just independent populations.
    
    # Population 1: Row Connectors (Left and Right edge)
    # Population 2: Col Connectors (Top and Bottom edge)
    # This creates the "Traffic Jam" but scaled up.
    # But that's just parallel tracks.
    
    # We want PINS to be obstacles too.
    # So Layer 1 trace must navigate around Layer 2 pins (via barrels).
    
    # Proposed Layout: N x N Matrix of "Nodes".
    # Each Node has 2 pins: P_H (for horizontal net) and P_V (for vertical net).
    # P_H at (x, y). P_V at (x+0.5, y+0.5).
    # This guarantees maximum obstacle density.
    
    for r in range(grid_size):
        # Row Net
        row_net = f"NET_ROW_{r}"
        nets.append(Net(number=len(nets)+1, name=row_net))
        # Place start and end pin, plus maybe middle pins?
        # A fully populated row means pins at every column.
        for c in range(grid_size):
            x = c * pitch + 10
            y = r * pitch + 10
            fp = create_pin_footprint(f"R_{r}_{c}", x, y, row_net)
            footprints.append(fp)

    for c in range(grid_size):
        # Col Net
        col_net = f"NET_COL_{c}"
        nets.append(Net(number=len(nets)+1, name=col_net))
        for r in range(grid_size):
            # Interleaved offset
            x = c * pitch + 10 + (pitch/2)
            y = r * pitch + 10 + (pitch/2)
            fp = create_pin_footprint(f"C_{r}_{c}", x, y, col_net)
            footprints.append(fp)
            
    # Diagonal Nets (The Stress Test)
    # D1: Top-Left to Bottom-Right
    d1_net = "NET_DIAG_1"
    nets.append(Net(number=len(nets)+1, name=d1_net))
    # Place pins sparsely along diagonal
    for i in range(grid_size):
        x = i * pitch + 10 + (pitch/4) # Slight offset to not hit others
        y = i * pitch + 10 + (pitch/4)
        fp = create_pin_footprint(f"D1_{i}", x, y, d1_net)
        footprints.append(fp)

    # D2: Bottom-Left to Top-Right
    d2_net = "NET_DIAG_2"
    nets.append(Net(number=len(nets)+1, name=d2_net))
    for i in range(grid_size):
        x = i * pitch + 10 + (pitch * 0.75)
        y = (grid_size - 1 - i) * pitch + 10 + (pitch * 0.75)
        fp = create_pin_footprint(f"D2_{i}", x, y, d2_net)
        footprints.append(fp)

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

def run_complex_experiment(name: str, grid_size: int, pitch: float, cell_size: float = 0.5):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    
    print(f"\nGenerarting {name}: {grid_size}x{grid_size} Grid, Pitch={pitch}mm...")
    num_nets = generate_weave_pcb(pcb_path, grid_size, pitch)
    print(f"  Created {num_nets} nets.")
    
    # Parse
    result = parse_kicad_pcb(pcb_path)
    # Hack: ensure components have bounds for valid netlist construction if needed
    for c in result.netlist.components:
        if c.bounds == (0.0, 0.0): c.bounds = (2.0, 2.0)
        
    router = MazeRouter(
        grid_size=(int(100/cell_size), int(100/cell_size)), # Approx
        cell_size_mm=cell_size,
        num_layers=2,
        origin=(0,0), # Simplified
        via_cost=5.0, # Moderate via cost
        min_clearance=0.1,
        wrong_way_penalty=5.0 # Strong directional bias
    )
    
    # Re-init grid size correctly
    router = MazeRouter.from_board(
        result.board, 
        cell_size_mm=cell_size, 
        num_layers=2, 
        via_cost=2.0,
        min_clearance=0.1,
        wrong_way_penalty=1.5,
        soft_blocking=True  # Enable RRR
    )
    
    # Block pads
    positions = np.array([c.initial_position for c in result.netlist.components])
    router.block_pads(result.netlist.components, positions, result.netlist, clearance=0.1)

    # 0. Fanout Pass (The Fix)
    print("  Running Fanout Pass...")
    # Load KiBoard for modification
    ki_board = KiBoard.from_file(str(pcb_path))
    
    fanout_gen = FanoutGenerator(ki_board, result.netlist, FanoutConfig(pitch=pitch, strategy="grid"))
    # We only Fanout the Diagonal nets, or all?
    # Fanout everything for consistency?
    # If we fanout everything, we might block channels?
    # Let's fanout ONLY Diagonals first to prove the point.
    target_nets = ["NET_DIAG_1", "NET_DIAG_2"]
    fanout_overrides = fanout_gen.generate_fanouts(target_nets=target_nets)
    print(f"    Generated fanouts for: {list(fanout_overrides.keys())}")
    
    # 1. Assign Layers
    print("  Running Geometric Layer Assignment...")
    t0 = time.time()
    assignments = assign_layers(result.netlist, component_positions=positions)
    print(f"  Assignment took {time.time()-t0:.3f}s")
    
    # Audit Assignments
    l1_count = sum(1 for a in assignments.values() if a.primary_layer == Layer.L1_TOP)
    l4_count = sum(1 for a in assignments.values() if a.primary_layer == Layer.L4_BOT)
    print(f"  Distribution: L1 (Horiz)={l1_count}, L4 (Vert)={l4_count}")
    
    # 2. Route with RRR
    print(f"  Routing {num_nets} nets with Rip-up and Reroute...")
    
    start_time = time.time()
    
    # Sort Diagonals last to give planar nets priority? Or first?
    # Actually RRR doesn't care much, but good initial solution helps.
    # New geometric assignment handles H/V. Diagonals are the trouble.
    net_order = [n.name for n in result.netlist.nets if n.name]
    
    results = router.rrr_route_all_nets(
        netlist=result.netlist,
        positions=positions,
        net_order=net_order,
        assignments=assignments,
        max_iterations=20,  # Give it enough time to converge
        p_scale_step=0.5,
        pin_positions_overrides=fanout_overrides
    )
            
    duration = time.time() - start_time
    print(f"  Routing Finished in {duration:.3f}s")
    
    routed_count = 0
    for net_name, path in results.items():
        if path.success:
            routed_count += 1
            # print(f"    ✓ {net_name}: {path.via_count} vias")
        else:
            print(f"    ✗ {net_name} FAILED: {path.failure_reason}")
    
    # Check conflicts
    conflicts = router.get_conflict_locations()
    
    print(f"  Completion: {routed_count}/{num_nets} ({routed_count/num_nets*100:.1f}%)")
    print(f"  Remaining Conflicts: {len(conflicts)}")
    
    # Validate Diagonals
    d1 = results.get("NET_DIAG_1")
    d2 = results.get("NET_DIAG_2")
    if d1 and d1.success: print(f"  DIAG_1: {d1.via_count} vias")
    if d2 and d2.success: print(f"  DIAG_2: {d2.via_count} vias")
    
    if len(conflicts) == 0 and routed_count == num_nets:
        print("  STATUS: SUCCESS (My work solves it!)")
    else:
        print("  STATUS: BROKEN (Conflicts persist)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=8, help="Grid size (NxN)")
    parser.add_argument("--pitch", type=float, default=2.0, help="Pin pitch (mm)")
    parser.add_argument("--cell", type=float, default=0.25, help="Router cell size (mm)")
    args = parser.parse_args()
    
    run_complex_experiment("EXP02C_Weave", args.size, args.pitch, args.cell)
