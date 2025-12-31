
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
from temper_placer.routing.maze_router import MazeRouter

def create_header_footprint(ref: str, x: float, y: float, pitch: float, net_names: list[str]) -> Footprint:
    """Create a synthetic header footprint."""
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = f"Test:Header_{len(net_names)}pin_P{pitch}mm"
    fp.locked = False
    
    # Add properties
    fp.properties = {
        "Reference": ref,
        "Value": f"Conn_{len(net_names)}",
    }
    
    # Pads
    fp.pads = []
    
    # Dimensions
    pad_w = 0.8 if pitch < 2.0 else 1.5
    pad_h = pad_w
    drill = 0.6 if pitch < 2.0 else 1.0
    
    # 2 rows, N/2 cols
    rows = 2
    cols = len(net_names) // rows
    
    start_x = -((cols - 1) * pitch) / 2
    start_y = -((rows - 1) * pitch) / 2
    
    for i, net_name in enumerate(net_names):
        r = i // cols
        c = i % cols
        px = start_x + c * pitch
        py = start_y + r * pitch
        
        pad = Pad()
        pad.number = str(i + 1)
        pad.position = Position(X=px, Y=py)
        pad.size = Position(X=pad_w, Y=pad_h)
        pad.type = "thru_hole"
        pad.shape = "rect"
        pad.layers = ["*.Cu", "*.Mask"]
        pad.drill = DrillDefinition(diameter=drill)
        
        # We need to assign the net explicitly if we want parser to pick it up
        # Kiutils Pad.net is a Net object ref usually
        # But we can set it to a dummy obj with name
        pad.net = Net(name=net_name)
        
        fp.pads.append(pad)
        
    return fp

def generate_pitchfork_pcb(path: Path, pitch: float):
    """Generate the benchmark PCB file."""
    b = KiBoard.create_new()
    
    # Define Nets
    # 10 signals + GND/VCC
    net_names = [f"SIG_{i}" for i in range(10)]
    
    b.nets = [Net(number=i+1, name=n) for i, n in enumerate(net_names)]
    b.nets.insert(0, Net(number=0, name=""))
    
    # J1 at (20, 30)
    b.footprints.append(create_header_footprint(
        "J1", 20.0, 30.0, pitch, net_names
    ))
    
    # J2 at (40, 30)
    b.footprints.append(create_header_footprint(
        "J2", 40.0, 30.0, pitch, net_names
    ))
    
    # Add Edge Cuts
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=60, Y=60),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_experiment(name: str, pitch: float, cell_size_mm: float):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    
    print(f"\nRunning {name}: Pitch={pitch}mm, Cell={cell_size_mm}mm")
    generate_pitchfork_pcb(pcb_path, pitch)
    
    # Load into Temper
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    print(f"  Loaded {len(netlist.nets)} nets, {len(netlist.components)} comps")
    
    # Configure Router
    grid_w = int(board.width / cell_size_mm) + 2
    grid_h = int(board.height / cell_size_mm) + 2
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size_mm,
        num_layers=2,
        origin=board.origin
    )
    
    # Block pads
    positions = np.array([c.initial_position for c in netlist.components])
    router.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        clearance=0.1
    )
    
    # Route
    start_time = time.time()
    routed = 0
    
    for net in netlist.nets:
        # Find start/end
        # J1 pin i -> J2 pin i
        # Net name is SIG_{i}
        # In this simple case, we know pin mapping
        # But let's look it up
        pins = []
        for c in netlist.components:
            for p in c.pins:
                if p.net == net.name:
                    # Calc absolute pos
                    # board.origin is subtracted by parser, need to add it?
                    # No, parser normalizes positions. 
                    # Router expects internal coords.
                    # parse_kicad_pcb returns components with relative positions.
                    # So (c.initial_position + p.position) is correct internal coord?
                    # Yes.
                    abs_x = c.initial_position[0] + p.position[0]
                    abs_y = c.initial_position[1] + p.position[1]
                    pins.append((abs_x, abs_y))
        
        if len(pins) < 2:
            print(f"Warning: Net {net.name} has < 2 pins")
            continue
            
        path_obj = router.route_net_rrr(
            net_name=net.name,
            pin_positions=pins,
            assignment=None
        )
        
        if path_obj.success:
            routed += 1
            # Commit routing to avoid collisions
            if path_obj.cells:
                # Manually commit path to occupancy grid
                for c in path_obj.cells:
                    if 0 <= c.x < grid_w and 0 <= c.y < grid_h:
                        router.occupancy[c.x, c.y, c.layer] = 1
                
    duration = time.time() - start_time
    print(f"  Result: {routed}/{len(netlist.nets)} routed in {duration:.3f}s")
    
    if routed == len(netlist.nets):
        print("  STATUS: PASS")
    else:
        print("  STATUS: FAIL")

if __name__ == "__main__":
    run_experiment("A_Control", 2.54, 0.5)
    run_experiment("B_Problem", 1.27, 0.5)
    run_experiment("C_SOLVED", 1.27, 0.25)
