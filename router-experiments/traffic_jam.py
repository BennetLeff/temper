
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
from temper_placer.routing.layer_assignment import assign_layers

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
    rows = 1  # For simple headers in this test, 1 row is fine or we stick to pitchfork logic
    # The user request said "4 Headers (1x1)" -> So just 1 pin per header. 
    # Pitchfork used multi-pin. Let's adapt to 1x1.
    
    cols = len(net_names) 
    rows = 1
    
    start_x = -((cols - 1) * pitch) / 2
    start_y = -((rows - 1) * pitch) / 2
    
    for i, net_name in enumerate(net_names):
        # r = 0
        # c = i
        px = 0.0 # Single pin is at center
        py = 0.0
        
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

def generate_traffic_jam_pcb(path: Path):
    """Generate the traffic jam benchmark PCB file."""
    b = KiBoard.create_new()
    
    # Define Nets: NET_NS, NET_WE, and empty
    b.nets = [
        Net(number=1, name="NET_NS"), 
        Net(number=2, name="NET_WE"), 
        Net(number=0, name="")
    ]
    
    # Add 4 single-pin headers at cardinal directions
    # J_N (North): (30, 10). Net A (NET_NS)
    # J_S (South): (30, 50). Net A (NET_NS)
    # J_W (West): (10, 30). Net B (NET_WE)
    # J_E (East): (50, 30). Net B (NET_WE)
    
    b.footprints.append(create_header_footprint("J_N", 30.0, 10.0, 2.54, ["NET_NS"]))
    b.footprints.append(create_header_footprint("J_S", 30.0, 50.0, 2.54, ["NET_NS"]))
    b.footprints.append(create_header_footprint("J_W", 10.0, 30.0, 2.54, ["NET_WE"]))
    b.footprints.append(create_header_footprint("J_E", 50.0, 30.0, 2.54, ["NET_WE"]))

    # Add Edge Cuts
    b.graphicItems.append(GrRect(
        start=Position(X=0, Y=0),
        end=Position(X=60, Y=60),
        layer="Edge.Cuts",
        width=0.1
    ))
    
    b.to_file(str(path))

def run_experiment(name: str, via_cost: float, cell_size_mm: float = 0.5):
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / f"{name}_input.kicad_pcb"
    
    print(f"\nRunning {name}: ViaCost={via_cost}, Cell={cell_size_mm}mm")
    generate_traffic_jam_pcb(pcb_path)
    
    # Load into Temper
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # Configure Router
    grid_w = int(board.width / cell_size_mm) + 2
    grid_h = int(board.height / cell_size_mm) + 2
    
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=cell_size_mm,
        num_layers=2,
        origin=board.origin,
        via_cost=via_cost
    )
    
    # Block pads
    positions = np.array([c.initial_position for c in netlist.components])
    router.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        clearance=0.1
    )
    
    # Compute Assignments
    assignments = assign_layers(netlist, component_positions=positions)
    
    # Route
    start_time = time.time()
    routed = 0
    total_vias = 0
    
    paths = []
    
    for net in netlist.nets:
        if not net.name: continue
        
        # Find pins
        pins = []
        for c in netlist.components:
            for p in c.pins:
                if p.net == net.name:
                    abs_x = c.initial_position[0] + p.position[0]
                    abs_y = c.initial_position[1] + p.position[1]
                    pins.append((abs_x, abs_y))
        
        if len(pins) < 2:
            continue
            
        path_obj = router.route_net_rrr(
            net_name=net.name,
            pin_positions=pins,
            assignment=assignments.get(net.name)
        )
        
        if path_obj.success:
            routed += 1
            paths.append(path_obj)
            total_vias += path_obj.via_count
            
            # Commit routing to avoid collisions
            if path_obj.cells:
                for c in path_obj.cells:
                    if 0 <= c.x < grid_w and 0 <= c.y < grid_h:
                        router.occupancy[c.x, c.y, c.layer] = 2 # 2=Routed

    duration = time.time() - start_time
    print(f"  Result: {routed}/2 routed in {duration:.3f}s")
    print(f"  Vias Used: {total_vias}")

    # Success criteria
    success = (routed == 2)
    
    # Analyze Via Usage
    # Case 1: 0 vias (Top + Bottom)
    # Case 2: 2 vias (Top + Top with bridge)
    
    if success:
        if total_vias == 0:
            print("  STRATEGY: Layer Assignment (0 vias)")
        elif total_vias == 2:
            print("  STRATEGY: Bridge (2 vias)")
        else:
            print(f"  STRATEGY: Other ({total_vias} vias)")
        print("  STATUS: PASS")
    else:
        print("  STATUS: FAIL")


if __name__ == "__main__":
    run_experiment("TrafficJam_Standard", via_cost=1.0)
    run_experiment("TrafficJam_Expensive", via_cost=50.0)
