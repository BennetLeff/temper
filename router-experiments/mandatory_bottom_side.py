
import os
import jax.numpy as jnp
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad
from kiutils.items.common import Position, Net as KiNet
from kiutils.items.gritems import GrRect

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_exporter import export_routed_pcb
from temper_placer.routing.maze_router import MazeRouter

def create_smd_footprint(ref: str, x: float, y: float, side: int) -> Footprint:
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Capacitor_SMD:C_0805_2012Metric"
    fp.layer = "F.Cu" if side == 0 else "B.Cu"
    
    fp.properties = {
        "Reference": ref,
        "Value": "10uF",
    }
    
    # Pad 1 at (-1.0, 0), Pad 2 at (1.0, 0)
    for i, px in enumerate([-1.0, 1.0]):
        pad = Pad()
        pad.number = str(i + 1)
        pad.position = Position(X=px, Y=0.0)
        pad.size = Position(X=1.2, Y=1.3)
        pad.type = "smd"
        pad.shape = "rect"
        pad.layers = ["F.Cu", "F.Paste", "F.Mask"] if side == 0 else ["B.Cu", "B.Paste", "B.Mask"]
        fp.pads.append(pad)
        
    return fp

def generate_mandatory_bottom_pcb(output_dir: Path):
    board_width, board_height = 50.0, 50.0
    pcb_path = output_dir / "mandatory_bottom_input.kicad_pcb"
    
    # 1. Create Initial PCB with kiutils
    kb = KiBoard.create_new()
    kb.nets = [KiNet(number=0, name=""), KiNet(number=1, name="NET1"), KiNet(number=2, name="NET2")]
    
    # C1 on Top at (15, 25)
    c1_fp = create_smd_footprint("C1", 15.0, 25.0, 0)
    c1_fp.pads[0].net = kb.nets[1] # NET1
    c1_fp.pads[1].net = kb.nets[2] # NET2
    kb.footprints.append(c1_fp)
    
    # C2 on Bottom at (35, 25)
    c2_fp = create_smd_footprint("C2", 35.0, 25.0, 1)
    c2_fp.pads[0].net = kb.nets[1] # NET1
    c2_fp.pads[1].net = kb.nets[2] # NET2
    kb.footprints.append(c2_fp)
    
    kb.graphicItems.append(GrRect(
        start=Position(X=0, Y=0), end=Position(X=board_width, Y=board_height),
        layer="Edge.Cuts", width=0.1
    ))
    kb.to_file(str(pcb_path))
    print(f"Initial PCB created at {pcb_path}")
    
    # 2. Parse into Temper to get internal objects
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # 3. Setup Router and Route
    cell_size = 0.5
    maze = MazeRouter.from_board(board, cell_size_mm=cell_size)
    
    # Mock positions and sides for block_pads
    positions = jnp.array([c.initial_position for c in netlist.components])
    # initial_side is correctly populated by parser
    comp_sides = jnp.array([c.initial_side for c in netlist.components])
    comp_rots = jnp.array([0, 0]) # degrees
    
    maze.block_pads(
        components=netlist.components,
        positions=positions,
        netlist=netlist,
        rotations=comp_rots,
        sides=comp_sides
    )
    
    routes = {}
    for net in netlist.nets:
        if len(net.pins) < 2: continue
        
        # Determine pin sides
        pin_sides_list = []
        pin_positions = []
        for ref, pin_name in net.pins:
            comp = next(c for c in netlist.components if c.ref == ref)
            pin = next(p for p in comp.pins if p.name == pin_name)
            pin_sides_list.append(comp.initial_side)
            
            # Use side-aware absolute position logic for verification script
            px, py = pin.position
            if comp.initial_side == 1:
                px = -px # Mirroring
            
            # Simple rotation (0)
            abs_x = comp.initial_position[0] + px
            abs_y = comp.initial_position[1] + py
            pin_positions.append((abs_x, abs_y))
            
        print(f"Routing {net.name} (Sides: {pin_sides_list})...")
        path_obj = maze.route_net_rrr(
            net_name=net.name,
            pin_positions=pin_positions,
            assignment=None,
            pin_sides=pin_sides_list
        )
        if path_obj.success:
            routes[net.name] = path_obj
            print(f"  SUCCESS: {net.name} routed.")
        else:
            print(f"  FAILURE: {net.name} failed to route.")

    # 4. Export Final Routed PCB
    if len(routes) == 2:
        final_pcb_path = output_dir / "mandatory_bottom_routed.kicad_pcb"
        export_routed_pcb(
            template_pcb=pcb_path,
            routes=routes,
            output_pcb=final_pcb_path,
            cell_size=cell_size
        )
        print(f"Final routed PCB exported to {final_pcb_path}")
    else:
        print("Final export skipped due to routing failures.")

if __name__ == "__main__":
    output_dir = Path("router-experiments")
    os.makedirs(output_dir, exist_ok=True)
    generate_mandatory_bottom_pcb(output_dir)
