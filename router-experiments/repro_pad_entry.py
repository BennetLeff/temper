
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
from temper_placer.routing.maze_router import MazeRouter, RoutePath
from temper_placer.io.trace_writer import write_traces_to_pcb

def create_tight_footprint(ref: str, x: float, y: float, pitch: float) -> Footprint:
    """Create a header with tight pitch to force tricky entry."""
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = f"Test:TightHeader_P{pitch}mm"
    fp.locked = False
    
    fp.properties = {
        "Reference": ref,
        "Value": "Conn_2",
    }
    
    fp.pads = []
    
    # Square pads, large enough to cover most of the grid cell
    pad_w = 1.0 
    pad_h = 1.0
    drill = 0.6
    
    # Pad 1 at (0, 0)
    pad1 = Pad()
    pad1.number = "1"
    pad1.position = Position(X=0, Y=0)
    pad1.size = Position(X=pad_w, Y=pad_h)
    pad1.type = "thru_hole"
    pad1.shape = "rect"
    pad1.layers = ["*.Cu", "*.Mask"]
    pad1.drill = DrillDefinition(diameter=drill)
    pad1.net = Net(name="NET_A")
    fp.pads.append(pad1)
    
    # Pad 2 at (pitch, pitch) -> Diagonal placement
    pad2 = Pad()
    pad2.number = "2"
    pad2.position = Position(X=pitch, Y=pitch) 
    pad2.size = Position(X=pad_w, Y=pad_h)
    pad2.type = "thru_hole"
    pad2.shape = "rect"
    pad2.layers = ["*.Cu", "*.Mask"]
    pad2.drill = DrillDefinition(diameter=drill)
    pad2.net = Net(name="NET_A")
    fp.pads.append(pad2)
        
    return fp

def generate_repro_pcb(path: Path):
    """Generate PCB with diagonal pads."""
    b = KiBoard.create_new()
    
    b.nets = [Net(number=0, name=""), Net(number=1, name="NET_A")]
    
    # Diagonal placement forces a staircase route if not handled
    # Pitch 2.0mm, Pad 1.0mm -> Gap 1.0mm
    # Grid 0.2mm -> multiple valid paths, but diagonal is shortest
    b.footprints.append(create_tight_footprint(
        "J1", 20.0, 20.0, pitch=2.0
    ))
    
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=40, Y=40),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_repro():
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / "repro_pad_entry.kicad_pcb"
    output_path = output_dir / "repro_pad_entry_routed.kicad_pcb"
    
    generate_repro_pcb(pcb_path)
    
    # Load
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # Use 0.2mm grid - roughly standard
    cell_size = 0.2
    
    grid_w = int(board.width / cell_size) + 2
    grid_h = int(board.height / cell_size) + 2
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size,
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
    
    # Route NET_A
    print("Routing NET_A...")
    routed_path = None
    
    for net in netlist.nets:
        if net.name == "NET_A":
            pins = []
            for c in netlist.components:
                for p in c.pins:
                    if p.net == net.name:
                        abs_x = c.initial_position[0] + p.position[0]
                        abs_y = c.initial_position[1] + p.position[1]
                        pins.append((abs_x, abs_y))
            
            path_obj = router.route_net_rrr(
                net_name=net.name,
                pin_positions=pins,
                assignment=None
            )
            
            if path_obj.success:
                print(f"Success! Path length: {len(path_obj.cells)}")
                routed_path = path_obj.cells
            else:
                print("Failed to route.")


    if routed_path:
        # Export to check visually
        rp = RoutePath(
             net="NET_A",
             cells=routed_path,
             length=float(len(routed_path))*cell_size,
             via_count=0,
             success=True,
             cell_size=cell_size
        )
        router.routed_paths = {"NET_A": rp}
        write_traces_to_pcb(pcb_path, output_path, router.routed_paths, cell_size=cell_size)
        print(f"Exported to {output_path}")

if __name__ == "__main__":
    run_repro()
