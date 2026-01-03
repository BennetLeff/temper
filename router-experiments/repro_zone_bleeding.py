
import sys
import time
import numpy as np
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad, DrillDefinition
from kiutils.items.common import Position, Net
from kiutils.items.gritems import GrRect
from kiutils.items.zones import Zone, ZonePolygon

# Ensure imports work
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter, RoutePath
from temper_placer.io.trace_writer import write_traces_to_pcb

def create_header(ref: str, x: float, y: float) -> Footprint:
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical"
    fp.locked = False
    fp.properties = {"Reference": ref, "Value": "Conn_1"}
    
    pad = Pad()
    pad.number = "1"
    pad.position = Position(X=0, Y=0)
    pad.size = Position(X=0.5, Y=0.5)
    pad.type = "thru_hole"
    pad.shape = "circle"
    pad.layers = ["*.Cu", "*.Mask"]
    pad.drill = DrillDefinition(diameter=0.3)
    pad.net = Net(name="SIGNAL")
    fp.pads.append(pad)
    return fp

def generate_zone_pcb(path: Path):
    b = KiBoard.create_new()
    b.nets = [Net(number=0, name=""), Net(number=1, name="SIGNAL"), Net(number=2, name="GND")]
    
    # Create two pins for SIGNAL net
    b.footprints.append(create_header("J1", 10.0, 10.0))
    b.footprints.append(create_header("J2", 20.0, 10.0)) # 10mm away
    
    # Pad radius 0.25. Edge at 10.25.
    # Trace width 0.2. Center 10.0. Edge 10.1.
    # Zone at 10.5.
    # Clearance 0.2.
    # Pad to Zone: 10.5 - 10.25 = 0.25 >= 0.2. Safe.
    # Trace to Zone: 10.5 - 10.1 = 0.4. Safe.
    # BUT if router moves to Y=10.2 (Cell 51).
    # Trace Edge 10.3. Zone 10.5. Gap 0.2. Marginal/Safe?
    # If Y=10.4 (Cell 52). Trace Edge 10.5. Touch! Violation.
    # So router should strictly avoid Y>=10.4.
    
    z = Zone()
    z.net = 2
    z.netName = "GND"
    z.layers = ["F.Cu"]
    z.minThickness = 0.25
    z.filledAreas = []
    
    z.polygons = [ZonePolygon(coordinates=[
        Position(X=5, Y=12.5),
        Position(X=25, Y=12.5),
        Position(X=25, Y=20),
        Position(X=5, Y=20)
    ])]
    b.zones.append(z)
    
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=30, Y=30),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_repro():
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / "repro_zone_bleeding.kicad_pcb"
    output_path = output_dir / "repro_zone_bleeding_routed.kicad_pcb"
    
    generate_zone_pcb(pcb_path)
    
    # Load
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # Grid 0.2mm
    cell_size = 0.2
    
    grid_w = int(board.width / cell_size) + 2
    grid_h = int(board.height / cell_size) + 2
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size,
        num_layers=2,
        origin=board.origin
    )
    
    # Block pads and ZONES
    positions = np.array([c.initial_position for c in netlist.components])
    router.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        clearance=0.1
    )
    
    # Block Zones explicitly? 
    # MazeRouter usually does this internally or we need to call something?
    # Router usually parses zones from board?
    # verify block_zones availability.
    # Checking MazeRouter source... it has block_zones(zones, clearance).
    if hasattr(board, 'zones'):
        router.block_zones(board.zones, clearance=0.3)
    
    print("Routing SIGNAL...")
    routed_path = None
    
    # Manually route SIGNAL
    path_obj = router.route_net_rrr(
        net_name="SIGNAL",
        pin_positions=[(10.0, 10.0), (20.0, 10.0)],
        assignment=None
    )
    
    if path_obj.success:
        print(f"Success! Path length: {len(path_obj.cells)}")
        routed_path = path_obj.cells
        
        print(f"DEBUG: Path coordinates: {routed_path}")
        rp = RoutePath(
             net="SIGNAL",
             cells=routed_path,
             length=float(len(routed_path))*cell_size,
             via_count=0,
             success=True,
             cell_size=cell_size
        )
        router.routed_paths = {"SIGNAL": rp}
        write_traces_to_pcb(pcb_path, output_path, router.routed_paths, cell_size=cell_size)
    else:
        print("Failed to route.")

if __name__ == "__main__":
    run_repro()
