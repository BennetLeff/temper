
import sys
import time
import numpy as np
import math
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
    
    fp.properties = {
        "Reference": ref,
        "Value": f"Conn_{len(net_names)}",
    }
    
    fp.pads = []
    
    # 1.27mm Pitch Headers usually have smaller pads (~0.8mm)
    pad_w = 0.8 
    pad_h = 0.8
    drill = 0.6
    
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
        pad.net = Net(name=net_name)
        
        fp.pads.append(pad)
        
    return fp

def generate_pitchfork_pcb(path: Path, pitch: float):
    b = KiBoard.create_new()
    net_names = [f"SIG_{i}" for i in range(10)]
    b.nets = [Net(number=i+1, name=n) for i, n in enumerate(net_names)]
    b.nets.insert(0, Net(number=0, name=""))
    
    b.footprints.append(create_header_footprint("J1", 20.0, 30.0, pitch, net_names))
    b.footprints.append(create_header_footprint("J2", 40.0, 30.0, pitch, net_names))
    
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=60, Y=60),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_experiment(name: str, pitch: float, cell_size_mm: float, 
                   trace_width_mm: float, clearance_mm: float):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    
    print(f"\nRunning {name}: Pitch={pitch}mm, Cell={cell_size_mm}mm")
    print(f"  Neckdown Strategy: Width={trace_width_mm}mm, Clearance={clearance_mm}mm")
    
    generate_pitchfork_pcb(pcb_path, pitch)
    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist
    
    grid_w = int(result.board.width / cell_size_mm) + 5
    grid_h = int(result.board.height / cell_size_mm) + 5
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size_mm,
        num_layers=2,
        origin=result.board.origin
    )
    
    positions = np.array([c.initial_position for c in netlist.components])
    
    # Apply Neckdown constraints here
    router.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        margin=None, # Auto-calc from clearance+width
        clearance=clearance_mm,
        trace_width=trace_width_mm
    )
    
    start_time = time.time()
    routed = 0
    
    for net in netlist.nets:
        pins = []
        for c in netlist.components:
            for p in c.pins:
                if p.net == net.name:
                    abs_x = c.initial_position[0] + p.position[0]
                    abs_y = c.initial_position[1] + p.position[1]
                    pins.append((abs_x, abs_y))
        
        if len(pins) < 2: continue
            
        path_obj = router.route_net_rrr(
            net_name=net.name,
            pin_positions=pins,
            assignment=None
        )
        
        if path_obj.success:
            routed += 1
            if path_obj.cells:
                for c in path_obj.cells:
                    if 0 <= c.x < grid_w and 0 <= c.y < grid_h:
                        router.occupancy[c.x, c.y, c.layer] = 1
                
    duration = time.time() - start_time
    print(f"  Result: {routed}/{len(netlist.nets)} routed in {duration:.3f}s")
    
    # Calculate Theoretical Gap
    # Gap = Pitch 1.27 - Pad 0.8 = 0.47mm
    # Required = TraceWidth + 2*Clearance
    req_width = trace_width_mm + 2 * clearance_mm
    gap = 1.27 - 0.8
    print(f"  Physics Check: Gap {gap:.3f}mm vs Required Channel {req_width:.3f}mm")
    if gap > req_width:
        print("  Physics Check: PASS (Should Route)")
    else:
        print("  Physics Check: FAIL (Impossible)")

    if routed == len(netlist.nets):
        print("  STATUS: PASS")
    else:
        print("  STATUS: FAIL")

if __name__ == "__main__":
    # Case 1: Standard Rules (Should Fail)
    # 0.2mm Width + 0.2mm Clearance = 0.6mm Req > 0.47mm Gap
    run_experiment("Exp1B_Standard", 1.27, 0.05, 0.2, 0.2)
    
    # Case 2: Neckdown Rules (0.15mm/6mil)
    # The gap is 0.02mm wide (0.625 to 0.645). 
    # A 0.05mm grid might skip over this tiny gap.
    # Result: Likely Fail due to aliasing.
    run_experiment("Exp1B_Neckdown_6mil_Coarse", 1.27, 0.05, 0.15, 0.15)

    # Case 3: Neckdown Rules (0.15mm/6mil) with Fine Grid
    # 0.01mm grid should resolve the 0.02mm gap.
    run_experiment("Exp1B_Neckdown_6mil_Fine", 1.27, 0.01, 0.15, 0.15)
    
    # Case 4: Aggressive Neckdown (0.127mm/5mil)
    # Margin = 0.127 + 0.0635 = 0.1905.
    # Gap window = 0.235 - 0.1905 = 0.0445mm * 2 = ~0.09mm
    # A 0.05mm grid is guaranteed to hit this.
    run_experiment("Exp1B_Neckdown_5mil_Coarse", 1.27, 0.05, 0.127, 0.127)
