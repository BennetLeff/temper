"""Quick diagnostic to understand CGND routing failure.

This script checks CGND pad positions and obstacles to identify blockage.
"""

from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb

pcb_path = Path("../../pcb/temper.kicad_pcb")
result = parse_kicad_pcb(pcb_path)
netlist = result.netlist

# Find CGND net
cgnd_net = None
for net in netlist.nets:
    if net.name == "CGND":
        cgnd_net = net
        break

if cgnd_net:
    print(f"\nCGND Net Analysis:")
    print(f"  Total pins: {len(cgnd_net.pins)}")
    print("\n  Pin locations:")
    
    for comp_ref, pin_name in cgnd_net.pins:
        # Find component
        comp = None
        for c in netlist.components:
            if c.ref == comp_ref:
                comp = c
                break
        
        if comp:
            # Find pin in component
            for pin in comp.pins:
                if pin.name == pin_name:
                    # Calculate absolute position
                    abs_pos = (
                        comp.initial_position[0] + pin.position[0],
                        comp.initial_position[1] + pin.position[1]
                    )
                    print(f"    {comp_ref}-{pin_name}: {abs_pos} ({comp.initial_position} + {pin.position})")
                    break
    
    print(f"\n  Segment analysis:")
    print(f"    Expected segments: {len(cgnd_net.pins) - 1}")
    print(f"    Segment 2->3 would connect pins {cgnd_net.pins[2]} to {cgnd_net.pins[3]}")
else:
    print("ERROR: CGND net not found!")
