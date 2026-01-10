"""Debug script to trace CGND segment 2->3 routing failure.

This script sets up the exact same conditions as the pipeline but with
verbose logging to understand why a 3-cell route times out.
"""

from pathlib import Path
import sys
import yaml

# Run the full pipeline up to CGND routing
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_pipeline_config
from temper_placer.deterministic.state import BoardState

pcb_path = Path("../../pcb/temper.kicad_pcb")
config_path = Path("../../configs/temper_deterministic_config.yaml")

print("=" * 80)
print("CGND ROUTING DEBUG")
print("=" * 80)

# Parse PCB
result = parse_kicad_pcb(pcb_path)
netlist = result.netlist
board_info = result.board

# Find CGND net
cgnd_net = None
for net in netlist.nets:
    if net.name == "CGND":
        cgnd_net = net
        break

if not cgnd_net:
    print("ERROR: CGND net not found!")
    sys.exit(1)

print(f"\nCGND Net Info:")
print(f"  Pins: {cgnd_net.pins}")
print(f"  Pin count: {len(cgnd_net.pins)}")

# Get pin positions
pin_positions = []
for comp_ref, pin_name in cgnd_net.pins:
    comp = None
    for c in netlist.components:
        if c.ref == comp_ref:
            comp = c
            break
    
    if comp:
        for pin in comp.pins:
            if pin.name == pin_name:
                abs_pos = (
                    comp.initial_position[0] + pin.position[0],
                    comp.initial_position[1] + pin.position[1]
                )
                pin_positions.append(abs_pos)
                print(f"  {comp_ref}-{pin_name}: {abs_pos}")
                break

# Segment 2->3 is pins[2] to pins[3]
if len(pin_positions) >= 4:
    seg_start = pin_positions[2]
    seg_end = pin_positions[3]
    
    distance = ((seg_end[0] - seg_start[0])**2 + (seg_end[1] - seg_start[1])**2)**0.5
    
    print(f"\nSegment 2->3:")
    print(f"  Start: {seg_start}")
    print(f"  End: {seg_end}")
    print(f"  Distance: {distance:.3f}mm")
    print(f"  Grid cells (0.5mm): {distance / 0.5:.1f}")
    
    # Now build the pipeline stages manually
    print(f"\nLoading config...")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    stages, _ = load_pipeline_config(config_path)
    
    print(f"  Loaded {len(stages)} stages")
    
    # Run up to routing stage
    state = BoardState(netlist=netlist, board=board_info)
    
    for stage in stages:
        stage_name = stage.name if hasattr(stage, 'name') else stage.__class__.__name__
        print(f"  Running {stage_name}...")
        state = stage.run(state)
        
        # Stop after clearance grid is built but before routing
        if stage_name == "clearance_grid":
            print(f"\n  Grid created: {state.grid.cols}x{state.grid.rows} @ {state.grid.cell_size_mm}mm")
            print(f"  Blocked cells on L0: {state.grid.blocked_count_on_layer(0)}")
            
            # Check if cells between seg_start and seg_end are blocked
            print(f"\n  Checking cells for CGND segment 2->3...")
            
            cgnd_net_id = state.grid.get_net_id("CGND")
            print(f"  CGND net ID: {cgnd_net_id}")
            
            # Sample cells along the path
            for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
                x = seg_start[0] + t * (seg_end[0] - seg_start[0])
                y = seg_start[1] + t * (seg_end[1] - seg_start[1])
                
                # Check L0 (F.Cu)
                is_avail = state.grid.is_available(x, y, layer=0, net_name="CGND")
                row, col = state.grid._mm_to_cell(x, y)
                
                # Get what's blocking it
                pad_id = state.grid._pad_net_ids[0][row, col]
                trace_id = state.grid._trace_net_ids[0][row, col]
                
                pad_net = state.grid._id_to_net.get(pad_id, f"ID={pad_id}") if pad_id > 0 else ("FREE" if pad_id == 0 else "OBSTACLE")
                trace_net = state.grid._id_to_net.get(trace_id, f"ID={trace_id}") if trace_id > 0 else ("FREE" if trace_id == 0 else "OBSTACLE")
                
                status = "✓ AVAILABLE" if is_avail else "✗ BLOCKED"
                print(f"    t={t:.2f} ({x:.2f},{y:.2f}) cell=({row},{col}): {status}")
                print(f"      Pad: {pad_net}, Trace: {trace_net}")
            
            break
else:
    print("ERROR: CGND doesn't have enough pins for segment 2->3")
