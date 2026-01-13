"""
EXP-24C: Piantor Benchmark - Blocking Analysis
Diagnose why /k00 is physically blocked.
"""

import sys
import time
from pathlib import Path
import numpy as np

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.deterministic.stages.clearance_grid import ClearanceGridStage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage
from temper_placer.deterministic.stages.net_ordering import NetOrderingStage
from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.core.netlist import Netlist
from temper_placer.deterministic.state import BoardState

# Piantor PCB paths
PIANTOR_RIGHT = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")

def run_diagnostic(target_net="/k00"):
    print("\n" + "=" * 60)
    print(f"EXP-24C: Blocking Analysis for {target_net}")
    print("=" * 60)
    
    if not PIANTOR_RIGHT.exists():
        print("ERROR: Piantor not cloned.")
        return 
    
    # Parse
    result = parse_kicad_pcb(PIANTOR_RIGHT)

    # PATCH: Move J1 (Out of Bounds) to valid location
    j1 = next((c for c in result.netlist.components if c.ref == "J1"), None)
    if j1:
        print(f"PATCH: Moving J1 from {j1.initial_position} to (10.0, 65.0)")
        j1.initial_position = (10.0, 65.0)
    
    # Detect zone nets
    zone_nets = set()
    for z in result.board.zones:
        for net_name in z.net_classes:
            if net_name and net_name != "Signal":
                zone_nets.add(net_name)
    
    # Filter out zone nets
    trace_nets = [n for n in result.netlist.nets if n.name not in zone_nets]
    print(f"Routing {len(trace_nets)} trace nets...")

    # Create filtered netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=trace_nets,
    )

    # Setup Pipeline
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(
            cell_size_mm=0.25,  # Same as Exp B
            layer_count=2
        ),
        LayerAssignmentStage(),
        NetOrderingStage(),
        SequentialRoutingStage(),
    ])

    # Initialize State
    initial_state = BoardState(
        netlist=filtered_netlist,
        board=result.board
    )

    # Run Pipeline
    print("Running pipeline...")
    state = pipeline.run(initial_state)
    print("Pipeline finished.")

    # DIAGNOSTIC: Check specific net
    # target_net passed as arg
    net_id = state.grid.get_net_id(target_net)
    print(f"\nAnalyzing {target_net} (ID: {net_id})")

    # Find stats for this net
    print(f"Board Dimensions: {result.board.width:.1f}x{result.board.height:.1f} mm")
    print(f"Grid Dimensions: {state.grid.rows} rows x {state.grid.cols} cols")

    # Find /k00 components/pins
    print(f"\nFinding pins for {target_net}:")
    target_net_obj = next((n for n in filtered_netlist.nets if n.name == target_net), None)
    
    pin_coords = []
    
    if target_net_obj:
        for pin_ref in target_net_obj.pins:
            # pin_ref is likely a tuple ('Ref', 'Pin') based on previous output
            try:
                if isinstance(pin_ref, tuple):
                    ref, pin = pin_ref
                elif "-" in pin_ref:
                     ref, pin = pin_ref.split("-")
                elif "." in pin_ref:
                     ref, pin = pin_ref.split(".")
                else:
                     ref = pin_ref
                     pin = ""
                
                comp = next((c for c in filtered_netlist.components if c.ref == ref), None)
                if comp:
                    # Find specific pin
                    target_pin_obj = next((p for p in comp.pins if p.name == pin or p.number == pin), None)
                    if target_pin_obj:
                         offset = target_pin_obj.position
                         pos = (comp.initial_position[0] + offset[0], comp.initial_position[1] + offset[1])
                         print(f"  {ref}-{pin}: {pos} (Comp: {comp.initial_position} + Pin: {offset})")
                         
                         # Check if pos is within board
                         if pos[0] < 0 or pos[0] > result.board.width or pos[1] < 0 or pos[1] > result.board.height:
                             print(f"    WARNING: Pin {ref}-{pin} is OUT OF BOUNDS!")
                         pin_coords.append(pos)
                    else:
                         print(f"  {ref}-{pin}: Pin object not found in component pins")
                else:
                    print(f"  {ref}-{pin}: Component not found in netlist")
            except Exception as e:
                print(f"  Error parsing pin {pin_ref}: {e}")

    # Inspect Grid at detected points
    print("\nchecking blocked cells...")
    
    # Helper to check cell
    def check_cell(x, y, layer, name="Point"):
        row, col = state.grid._mm_to_cell(x, y)
        if row < 0 or row >= state.grid.rows or col < 0 or col >= state.grid.cols:
             print(f"{name} ({x:.1f}, {y:.1f}) -> OUT OF BOUNDS")
             return 0
             
        val = state.grid._trace_net_ids[layer][row, col]
        net_name = state.grid._id_to_net.get(val, "FREE" if val==0 else "OBSTACLE" if val<0 else f"NET_{val}")
        print(f"{name} ({x:.1f}, {y:.1f}) -> Cell ({row}, {col}) L{layer}: {val} ({net_name})")
        return val

    # Neighborhood Check
    def print_neighborhood(row, col, name):
        print(f"\nNeighborhood for {name} @ ({row}, {col}):")
        min_r, max_r = max(0, row-5), min(state.grid.rows, row+6)
        min_c, max_c = max(0, col-5), min(state.grid.cols, col+6)
        
        for r in range(min_r, max_r):
            line0 = []
            line1 = []
            for c in range(min_c, max_c):
                t0 = state.grid._trace_net_ids[0][r, c]
                p0 = state.grid._pad_net_ids[0][r, c]
                v0 = t0 if t0 != 0 else p0
                
                t1 = state.grid._trace_net_ids[1][r, c]
                p1 = state.grid._pad_net_ids[1][r, c]
                v1 = t1 if t1 != 0 else p1

                sym0 = "." if v0 == 0 else ("#" if v0 == net_id else "X")
                sym1 = "." if v1 == 0 else ("#" if v1 == net_id else "X") # Wait. If v0 == net_id it should be * (Match). If != net_id it is #.
                
                # Correct Logic:
                # 0 -> .
                # net_id -> * (Match)
                # other -> # (Obstacle)
                
                sym0 = "." 
                if v0 == net_id: sym0 = "*"
                elif v0 != 0: sym0 = "#"
                
                sym1 = "."
                if v1 == net_id: sym1 = "*"
                elif v1 != 0: sym1 = "#"

                if r == row and c == col:
                    sym0 = "@"
                    sym1 = "@"
                line0.append(sym0)
                line1.append(sym1)
            print(f"  R{r:3d} L0: {''.join(line0)}  L1: {''.join(line1)}")

    # Check detected pins
    for i, (x, y) in enumerate(pin_coords):
         r, c = state.grid._mm_to_cell(x, y)
         print_neighborhood(r, c, f"Pin {i}")

    # Count Net Cells
    total_l0 = np.sum(state.grid._trace_net_ids[0] == net_id)
    total_l1 = np.sum(state.grid._trace_net_ids[1] == net_id)
    print(f"\nTotal Cells for Net {net_id}: L0={total_l0}, L1={total_l1}")
    
    # Hardcoded check (if pin detection fails)
    if not pin_coords:
        check_cell(142.3, 76.2, 0, "Hardcoded Start (F.Cu)")
        check_cell(10.0, 76.2, 0, "Hardcoded End (F.Cu)")
    
    # Define BBox from Actual Pins if available
    if len(pin_coords) >= 2:
        xs = [p[0] for p in pin_coords]
        ys = [p[1] for p in pin_coords]
        
        min_r_bbox, _ = state.grid._mm_to_cell(0, min(ys))
        max_r_bbox, _ = state.grid._mm_to_cell(0, max(ys))
        _, min_c_bbox = state.grid._mm_to_cell(min(xs), 0)
        _, max_c_bbox = state.grid._mm_to_cell(max(xs), 0)
        
        min_row = min(min_r_bbox, max_r_bbox)
        max_row = max(min_r_bbox, max_r_bbox)
        min_col = min(min_c_bbox, max_c_bbox)
        max_col = max(min_c_bbox, max_c_bbox)
    else:
        # Fallback
        min_row = 100
        max_row = 150
        min_col = 50
        max_col = 500
    
    # Expand slightly to see surround
    min_row = max(0, min_row - 10)
    max_row = min(state.grid.rows, max_row + 10)
    
    print(f"\nScanning BBox Rows {min_row}-{max_row}, Cols {min_col}-{max_col}...")
    
    # Check for Column Walls (vertical cuts)
    walls = []
    
    for col in range(min_col, max_col):
        # Check if this column is impassable within the row band
        is_impassable = True
        for row in range(min_row, max_row):
            t0 = state.grid._trace_net_ids[0][row, col]
            p0 = state.grid._pad_net_ids[0][row, col]
            val_l0 = t0 if t0 != 0 else p0
            
            t1 = state.grid._trace_net_ids[1][row, col]
            p1 = state.grid._pad_net_ids[1][row, col]
            val_l1 = t1 if t1 != 0 else p1
            
            # If any cell in this column (within row band) is passable, then the column is passable
            # Passable = (L0 or L1 is free/same_net)
            l0_pass = (val_l0 == 0 or val_l0 == net_id)
            l1_pass = (val_l1 == 0 or val_l1 == net_id)
            
            if l0_pass or l1_pass:
                is_impassable = False
                break
        
        if is_impassable:
            walls.append(col)

    if walls:
         print(f"FOUND {len(walls)} BLOCKED COLUMNS (WALLS) preventing horizontal passage!")
         # Group into ranges
         ranges = []
         if walls:
             start = walls[0]
             prev = walls[0]
             for x in walls[1:]:
                 if x > prev + 1:
                     ranges.append((start, prev))
                     start = x
                 prev = x
             ranges.append((start, prev))
         
         for start, end in ranges:
             mid = (start + end) // 2
             # Sample what is blocking the middle of the wall
             row_samp = (min_row + max_row) // 2
             val0 = state.grid._trace_net_ids[0][row_samp, mid]
             val1 = state.grid._trace_net_ids[1][row_samp, mid]
             n0 = state.grid._id_to_net.get(val0, str(val0))
             n1 = state.grid._id_to_net.get(val1, str(val1))
             print(f"  Wall at Cols {start}-{end}: Sample blocker @ {row_samp},{mid} -> L0:{n0} / L1:{n1}")
    else:
         print("No full vertical walls found in BBox.")

    # Inspect U2 Pads (Using netlist)
    u2 = next((c for c in state.netlist.components if c.ref == "U2"), None)
    if u2:
        print(f"\nInspecting U2 Pins ({len(u2.pins)} found):")
        for i, pin in enumerate(u2.pins[:5]): # Print first 5
             print(f"  Pin {i}: Net='{pin.net}', Pos={pin.position}")
    else:
        print("\nU2 Component NOT FOUND in state.netlist!")

    # Midpoint
    check_cell(76.0, 76.2, 0, "Midpoint (F.Cu)")
    check_cell(76.0, 76.2, 1, "Midpoint (B.Cu)")

    # Also checking rx/tx
    # rx is usually around the MCU.
    # MCU is usually at one end.

if __name__ == "__main__":
    # run_experiment() # Already ran in previous steps, just checking blockage now
    run_diagnostic("rx")
