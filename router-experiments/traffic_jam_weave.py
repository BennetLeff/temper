
import sys
import time
import numpy as np
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad, DrillDefinition
from kiutils.items.common import Position, Net
from kiutils.items.gritems import GrRect

# Ensure imports work
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter, order_nets_for_routing

def create_pin_header(ref: str, x: float, y: float, net_name: str) -> Footprint:
    """Create a single pin header footprint."""
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Test:Pin"
    fp.locked = False
    fp.properties = {"Reference": ref, "Value": "Pin"}
    
    pad = Pad()
    pad.number = "1"
    pad.position = Position(X=0, Y=0)
    pad.size = Position(X=1.0, Y=1.0)
    pad.type = "thru_hole"
    pad.shape = "circle"
    pad.layers = ["*.Cu", "*.Mask"]
    pad.drill = DrillDefinition(diameter=0.6)
    pad.net = Net(name=net_name)
    
    fp.pads = [pad]
    return fp

def generate_weave_pcb(path: Path, num_nets: int = 5, pitch: float = 1.27):
    """Generate a Weave topology: Two orthogonal buses crossing."""
    b = KiBoard.create_new()
    
    nets = []
    # Vertical Bus: V_0 .. V_N
    for i in range(num_nets):
        nets.append(Net(number=len(nets)+1, name=f"V_{i}"))
        
    # Horizontal Bus: H_0 .. H_N
    for i in range(num_nets):
        nets.append(Net(number=len(nets)+1, name=f"H_{i}"))
        
    nets.insert(0, Net(number=0, name=""))
    b.nets = nets
    
    # Center of board is (30, 30)
    center_x, center_y = 30.0, 30.0
    
    # Vertical Bus placement
    # Spaced by 'pitch' along X, centered at center_x
    v_width = (num_nets - 1) * pitch
    v_start_x = center_x - v_width / 2
    
    for i in range(num_nets):
        x = v_start_x + i * pitch
        # Start (Top)
        b.footprints.append(create_pin_header(f"JV_N_{i}", x, 10.0, f"V_{i}"))
        # End (Bottom)
        b.footprints.append(create_pin_header(f"JV_S_{i}", x, 50.0, f"V_{i}"))
        
    # Horizontal Bus placement
    # Spaced by 'pitch' along Y, centered at center_y
    h_height = (num_nets - 1) * pitch
    h_start_y = center_y - h_height / 2
    
    for i in range(num_nets):
        y = h_start_y + i * pitch
        # Start (West)
        b.footprints.append(create_pin_header(f"JH_W_{i}", 10.0, y, f"H_{i}"))
        # End (East)
        b.footprints.append(create_pin_header(f"JH_E_{i}", 50.0, y, f"H_{i}"))

    # Add Edge Cuts
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=60, Y=60),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_experiment(name: str, num_nets: int, pitch: float, cell_size_mm: float = 0.25):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    output_pcb_path = output_dir / f"{name}_routed.kicad_pcb"
    
    print(f"\nRunning {name}: {num_nets}x{num_nets} Weave, Pitch={pitch}mm, Cell={cell_size_mm}mm")
    generate_weave_pcb(pcb_path, num_nets, pitch)
    
    # Load into Temper
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    print(f"  Loaded {len(netlist.nets)} nets")
    
    # Configure Router
    grid_w = int(board.width / cell_size_mm) + 2
    grid_h = int(board.height / cell_size_mm) + 2
    
    # Configure Router
    grid_w = int(board.width / cell_size_mm) + 2
    grid_h = int(board.height / cell_size_mm) + 2
    
    # Use standard 2-layer router in STRICT MODE
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size_mm,
        num_layers=2,
        origin=board.origin,
        via_cost=5.0, 
        soft_blocking=False, # STRICT MODE: No Overlaps Allowed
        min_clearance=0.05
    )
    router._default_trace_width_mm = 0.15 

    # Block pads
    positions = np.array([c.initial_position for c in netlist.components])
    router.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        clearance=0.1
    )
    
    # Route All Nets (Uses Hard RRR: Fail -> Ripup -> Retry)
    net_names = [n.name for n in netlist.nets if n.name]
    
    print(f"  Starting Hard RRR Routing with {len(net_names)} nets...")
    routes = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=net_names,
        assignments={}, 
        max_iterations=20 # Should converge much faster
    )
    
    # Analysis
    routed_count = sum(1 for r in routes.values() if r.success)
    total_nets = len(net_names)
    total_vias = sum(r.via_count for r in routes.values() if r.success)
    
    # Check for conflicts (overlap_conflicts should be 0)
    # The stats object tracks this for the LAST iteration
    # But wait, MazeRouter.stats is global for the instance?
    # Actually rrr_route_all_nets updates stats.
    # But let's check the conflicts reported in the progress history if available,
    # or re-analyze.
    # The method returns routes. The conflicts are in router.net_occupancy.
    
    overlap_count, bottleneck_count, conflicted_nets = router._analyze_conflicts()
    total_conflicts = overlap_count + bottleneck_count
    
    print(f"  Result: {routed_count}/{total_nets} routed")
    print(f"  Total Vias: {total_vias}")
    print(f"  Remaining Conflicts: {total_conflicts} (Overlap: {overlap_count})")
    
    if routed_count == total_nets and total_conflicts == 0:
        print("  STATUS: PASS")
    else:
        print("  STATUS: FAIL")

        
    # Save output for visualization
    # We need to serialize routes back to PCB. 
    # Since we don't have the full exporter setup here easily, we'll skip saving tracks
    # properly unless we use temper_placer.io.trace_writer but that's complex to setup here.
    # But wait, MazeRouter has no export logic itself.
    # We can just rely on the console output for verification.


def run_experiment_assigned(name: str, num_nets: int, pitch: float, cell_size_mm: float = 0.25):
    """Run experiment with forced layer assignments to prove geometric solvability."""
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    print(f"\nRunning {name}: {num_nets}x{num_nets} Weave (Assigned Layers)")
    generate_weave_pcb(pcb_path, num_nets, pitch)
    
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # Configure Router (Strict)
    grid_w = int(board.width / cell_size_mm) + 2
    grid_h = int(board.height / cell_size_mm) + 2
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size_mm,
        num_layers=2,
        origin=board.origin,
        via_cost=5.0,
        soft_blocking=False,
        min_clearance=0.05
    )
    router._default_trace_width_mm = 0.15 
    
    positions = np.array([c.initial_position for c in netlist.components])
    router.block_pads(netlist.components, positions, netlist, clearance=0.1)
    
    # ASSIGNMENTS
    # V nets -> Top (L1/0)
    # H nets -> Bottom (L2/1)
    from temper_placer.routing.layer_assignment import LayerAssignment, Layer
    assignments = {}
    net_names = []
    
    for n in netlist.nets:
        if not n.name: continue
        net_names.append(n.name)
        if n.name.startswith("V_"):
            assignments[n.name] = LayerAssignment(net=n.name, primary_layer=Layer.L1_TOP, allowed_layers=[Layer.L1_TOP])
        elif n.name.startswith("H_"):
            assignments[n.name] = LayerAssignment(net=n.name, primary_layer=Layer.L4_BOT, allowed_layers=[Layer.L4_BOT]) # L4_BOT maps to last layer

    print("  Routing with forced assignments...")
    routes = router.route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=net_names,
        assignments=assignments
    )
    
    routed_count = sum(1 for r in routes.values() if r.success)
    print(f"  Result: {routed_count}/{len(net_names)} routed")
    
    if routed_count == len(net_names):
        print("  STATUS: PASS (Geometry Valid)")
    else:
        print("  STATUS: FAIL (Geometry Invalid)")

if __name__ == "__main__":
    # Test 1: Auto (Failed before, let's keep it commented or retry if you want, but focus on Assigned)
    # run_experiment("Weave_Auto", num_nets=5, pitch=1.27, cell_size_mm=0.25)
    
    # Test 2: Assigned
    run_experiment_assigned("Weave_Assigned", num_nets=5, pitch=1.27, cell_size_mm=0.25)

