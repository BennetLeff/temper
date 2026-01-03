#!/usr/bin/env python3
"""
Add GND-only power plane zones to KiCad PCB.
V4: Simplified strategy - only GND gets a full-board plane.

Strategy:
- GND: Full board on In2.Cu (ground plane)
- GND: Full board on In1.Cu (power layer, as backup for via stitching)
- All other power nets: No zones - rely on stub traces + vias connecting to GND

The fanout vias punch through to the GND plane, providing the return path.
Power rails (+3V3, +5V, etc.) need explicit trace routing or manual zones.
"""

import re
import sys
import uuid
from pathlib import Path

# Configuration
LAYER_GND = "In2.Cu"
LAYER_PWR = "In1.Cu"
BOARD_MARGIN = 0.5  # mm inset from board edge

def generate_tstamp():
    return str(uuid.uuid4())

def parse_pcb_bounds(content):
    """Find board dimensions from Edge.Cuts."""
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer \"Edge\.Cuts\"\)', content)
    if edge_match:
        return list(map(float, edge_match.groups()))
    return [0, 0, 100, 150]  # Default

def get_net_names(content):
    """Map net name to net ID."""
    nets = {}
    for match in re.finditer(r'\(net (\d+) \"([^\"]+)\"\)', content):
        nets[match.group(2)] = int(match.group(1))
    return nets

def create_rect_zone(net_id, net_name, layer, x1, y1, x2, y2, priority=0):
    tstamp = generate_tstamp()
    return f'''  (zone (net {net_id}) (net_name "{net_name}") (layer "{layer}") (tstamp {tstamp}) (hatch edge 0.5)
    (priority {priority})
    (connect_pads (clearance 0.3))
    (min_thickness 0.25)
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy {x1} {y1})
        (xy {x2} {y1})
        (xy {x2} {y2})
        (xy {x1} {y2})
      )
    )
  ) 
'''

def add_gnd_only_planes(input_pcb: Path, output_pcb: Path):
    content = input_pcb.read_text()
    
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    # Apply margin
    zx1, zy1 = bx1 + BOARD_MARGIN, by1 + BOARD_MARGIN
    zx2, zy2 = bx2 - BOARD_MARGIN, by2 - BOARD_MARGIN
    
    nets = get_net_names(content)
    zones = []
    
    # GND - Full board on ground layer
    gnd_id = nets.get("GND")
    if gnd_id:
        print(f"Adding GND full-board zone on {LAYER_GND}")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, zx1, zy1, zx2, zy2, priority=0))
        
        print(f"Adding GND full-board zone on {LAYER_PWR}")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_PWR, zx1, zy1, zx2, zy2, priority=0))
    else:
        print("WARNING: GND net not found!")
    
    # Write output
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote {len(zones)} GND-only zones to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes_v4.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_gnd_plane")
    
    add_gnd_only_planes(inp, out)
