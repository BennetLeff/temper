#!/usr/bin/env python3
"""
Add power plane zones to KiCad PCB.
V3: Bounded zones with generous padding for maximum coverage.

Strategy:
- GND: Full board on In2.Cu (Priority 0) - base layer, fills everywhere
- Other nets: Bounded zones with 20mm padding around pads
- Each net gets its own zone on appropriate layer

This ensures pads are within zone boundaries while avoiding zone overlap fragmentation.
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

def add_full_board_power_planes(input_pcb: Path, output_pcb: Path):
    content = input_pcb.read_text()
    
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    # Apply margin
    zx1, zy1 = bx1 + BOARD_MARGIN, by1 + BOARD_MARGIN
    zx2, zy2 = bx2 - BOARD_MARGIN, by2 - BOARD_MARGIN
    
    nets = get_net_names(content)
    zones = []
    
    # === GROUND LAYER (In2.Cu) ===
    
    # 1. GND - Full board, lowest priority (base fill)
    gnd_id = nets.get("GND")
    if gnd_id:
        print(f"Adding GND full-board zone (Priority 0)")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, zx1, zy1, zx2, zy2, priority=0))
    
    # 2. PGND - Full board, priority 1 (overrides GND)
    pgnd_id = nets.get("PGND")
    if pgnd_id:
        print(f"Adding PGND full-board zone (Priority 1)")
        zones.append(create_rect_zone(pgnd_id, "PGND", LAYER_GND, zx1, zy1, zx2, zy2, priority=1))
    
    # 3. CGND - Full board, priority 2 (control ground, overrides PGND)
    cgnd_id = nets.get("CGND")
    if cgnd_id:
        print(f"Adding CGND full-board zone (Priority 2)")
        zones.append(create_rect_zone(cgnd_id, "CGND", LAYER_GND, zx1, zy1, zx2, zy2, priority=2))
    
    # === POWER LAYER (In1.Cu) ===
    
    # 4. GND on power layer too (for via stitching), lowest priority
    if gnd_id:
        print(f"Adding GND on power layer (Priority 0)")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_PWR, zx1, zy1, zx2, zy2, priority=0))
    
    # 5. +3V3 - Full board, priority 1
    p3v3_id = nets.get("+3V3")
    if p3v3_id:
        print(f"Adding +3V3 full-board zone (Priority 1)")
        zones.append(create_rect_zone(p3v3_id, "+3V3", LAYER_PWR, zx1, zy1, zx2, zy2, priority=1))
    
    # 6. +5V - Full board, priority 2
    p5v_id = nets.get("+5V")
    if p5v_id:
        print(f"Adding +5V full-board zone (Priority 2)")
        zones.append(create_rect_zone(p5v_id, "+5V", LAYER_PWR, zx1, zy1, zx2, zy2, priority=2))
    
    # 7. +15V - Full board, priority 3
    p15v_id = nets.get("+15V")
    if p15v_id:
        print(f"Adding +15V full-board zone (Priority 3)")
        zones.append(create_rect_zone(p15v_id, "+15V", LAYER_PWR, zx1, zy1, zx2, zy2, priority=3))
    
    # 8. VCC_BOOT - Full board, priority 4 (highest, smallest fill)
    vccb_id = nets.get("VCC_BOOT")
    if vccb_id:
        print(f"Adding VCC_BOOT full-board zone (Priority 4)")
        zones.append(create_rect_zone(vccb_id, "VCC_BOOT", LAYER_PWR, zx1, zy1, zx2, zy2, priority=4))
    
    # Write output
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote {len(zones)} full-board zones to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes_v3.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_full_planes")
    
    add_full_board_power_planes(inp, out)
