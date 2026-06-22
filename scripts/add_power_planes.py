#!/usr/bin/env python3
"""
Add unified GND plane to KiCad PCB.
V5: Professional-aligned single GND zone on inner ground layer.

Strategy:
- Single GND zone on In2.Cu (ground reference plane)
- All ground nets (GND, PGND, CGND) connect to this via fanout vias
- NO overlapping priority zones - clean, solid copper pour
- Power rails (+3V3, +5V, +15V) are routed as traces, not zones

This aligns with industry-standard 4-layer stackup practice.
"""

import re
import sys
import uuid
from pathlib import Path

# Configuration
LAYER_GND = "In2.Cu"
BOARD_MARGIN = 0.5  # mm inset from board edge

def generate_tstamp():
    return str(uuid.uuid4())

def parse_pcb_bounds(content):
    """Find board dimensions from Edge.Cuts."""
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer \"Edge\.Cuts\"\)', content)
    if edge_match:
        return list(map(float, edge_match.groups()))
    return [0, 0, 100, 150]  # Default

def get_net_id(content, net_name):
    """Get net ID by name."""
    match = re.search(rf'\(net (\d+) "{re.escape(net_name)}"\)', content)
    return int(match.group(1)) if match else None

def create_rect_zone(net_id, net_name, layer, x1, y1, x2, y2, priority=0):
    tstamp = generate_tstamp()
    return f'''  (zone (net {net_id}) (net_name "{net_name}") (layer "{layer}") (tstamp {tstamp}) (hatch edge 0.5)
    (priority {priority})
    (connect_pads thermal_reliefs (clearance 0.3))
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

def add_unified_gnd_plane(input_pcb: Path, output_pcb: Path):
    content = input_pcb.read_text()
    
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    # Apply margin
    zx1, zy1 = bx1 + BOARD_MARGIN, by1 + BOARD_MARGIN
    zx2, zy2 = bx2 - BOARD_MARGIN, by2 - BOARD_MARGIN
    
    zones = []
    
    # Get GND net ID (primary ground net)
    gnd_id = get_net_id(content, "GND")
    if gnd_id:
        print(f"Adding unified GND plane on {LAYER_GND} (net ID: {gnd_id})")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, zx1, zy1, zx2, zy2, priority=0))
    else:
        print("ERROR: GND net not found in PCB!")
        sys.exit(1)
    
    # Note: PGND and CGND pads connect to this GND plane via their fanout vias
    # The fanout script places vias that punch through to In2.Cu where GND plane exists
    # This creates a unified ground reference
    
    pgnd_id = get_net_id(content, "PGND")
    cgnd_id = get_net_id(content, "CGND")
    print(f"Ground nets present: GND={gnd_id}, PGND={pgnd_id}, CGND={cgnd_id}")
    print("Note: PGND/CGND connect via fanout vias to the unified GND plane")
    
    # Write output
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote 1 unified GND zone to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes_v5.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_gnd_plane")
    
    add_unified_gnd_plane(inp, out)
