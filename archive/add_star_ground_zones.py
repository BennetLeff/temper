#!/usr/bin/env python3
"""
Add star-ground zones to KiCad PCB.

Strategy:
- Separate zones for GND, PGND, CGND on In2.Cu (ground layer)
- Each zone is bounded to the area containing that net's pads
- All zones meet at a single tie-point near the power input
- This creates proper star-ground topology for power electronics

The tie-point is implemented as overlapping zone corners near the input connector.
"""

import re
import sys
import uuid
from pathlib import Path

# Configuration
LAYER_GND = "In2.Cu"
PAD_PADDING = 8.0  # mm extra around pins for zone
BOARD_MARGIN = 0.5

def generate_tstamp():
    return str(uuid.uuid4())

def parse_pcb_bounds(content):
    """Find board dimensions from Edge.Cuts."""
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer \"Edge\.Cuts\"\)', content)
    if edge_match:
        return list(map(float, edge_match.groups()))
    return [0, 0, 100, 150]

def get_net_names(content):
    """Map net name to net ID."""
    nets = {}
    for match in re.finditer(r'\(net (\d+) \"([^\"]+)\"\)', content):
        nets[match.group(2)] = int(match.group(1))
    return nets

def get_net_pins_bounds(content, net_name, net_id):
    """Find bounding box of all pads for a net."""
    xs = []
    ys = []
    
    for fm in re.finditer(r'\(footprint \"([^\"]+)\" \(layer \"([^\"]+)\"\)', content):
        start_idx = fm.start()
        chunk = content[start_idx:start_idx+300]
        at_match = re.search(r'\(at ([\d.]+) ([\d.]+)(?: ([\d.-]+))?\)', chunk)
        if at_match:
            fx, fy = float(at_match.group(1)), float(at_match.group(2))
            next_fp = content.find('(footprint', start_idx + 1)
            if next_fp == -1: next_fp = len(content)
            fp_content = content[start_idx:next_fp]
            
            for pm in re.finditer(r'\(pad \"[^\"]+\" \S+ \S+ \(at ([\d.-]+) ([\d.-]+)(?: [\d.-]+)?\).*?\(net (\d+)', fp_content, re.DOTALL):
                px, py = float(pm.group(1)), float(pm.group(2))
                p_net = int(pm.group(3))
                if p_net == net_id:
                    xs.append(fx + px)
                    ys.append(fy + py)
    
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]

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
        (xy {x1:.2f} {y1:.2f})
        (xy {x2:.2f} {y1:.2f})
        (xy {x2:.2f} {y2:.2f})
        (xy {x1:.2f} {y2:.2f})
      )
    )
  ) 
'''

def create_tie_point_via(x, y, net_id):
    """Create a via at the star-ground tie point."""
    tstamp = generate_tstamp()
    return f'  (via (at {x:.2f} {y:.2f}) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net {net_id}) (tstamp "{tstamp}"))\n'

def create_tie_segment(x1, y1, x2, y2, width, layer, net_id):
    """Create a trace segment for tie-point."""
    tstamp = generate_tstamp()
    return f'  (segment (start {x1:.2f} {y1:.2f}) (end {x2:.2f} {y2:.2f}) (width {width}) (layer "{layer}") (net {net_id}) (tstamp "{tstamp}"))\n'

def add_star_ground_zones(input_pcb: Path, output_pcb: Path):
    content = input_pcb.read_text()
    
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    nets = get_net_names(content)
    gnd_id = nets.get("GND")
    pgnd_id = nets.get("PGND")
    cgnd_id = nets.get("CGND")
    
    print(f"Ground nets: GND={gnd_id}, PGND={pgnd_id}, CGND={cgnd_id}")
    
    zones = []
    tie_point_items = []
    
    # --- GND Zone: Full board base layer ---
    if gnd_id:
        print(f"Adding GND base zone (full board, priority 0)")
        zones.append(create_rect_zone(
            gnd_id, "GND", LAYER_GND,
            bx1 + BOARD_MARGIN, by1 + BOARD_MARGIN,
            bx2 - BOARD_MARGIN, by2 - BOARD_MARGIN,
            priority=0
        ))
    
    # --- PGND Zone: Bounded to power stage area ---
    if pgnd_id:
        pgnd_bounds = get_net_pins_bounds(content, "PGND", pgnd_id)
        if pgnd_bounds:
            px1 = max(bx1, pgnd_bounds[0] - PAD_PADDING)
            py1 = max(by1, pgnd_bounds[1] - PAD_PADDING)
            px2 = min(bx2, pgnd_bounds[2] + PAD_PADDING)
            py2 = min(by2, pgnd_bounds[3] + PAD_PADDING)
            print(f"Adding PGND zone (priority 1): {px1:.1f},{py1:.1f} -> {px2:.1f},{py2:.1f}")
            zones.append(create_rect_zone(pgnd_id, "PGND", LAYER_GND, px1, py1, px2, py2, priority=1))
    
    # --- CGND Zone: Bounded to control/gate driver area ---
    if cgnd_id:
        cgnd_bounds = get_net_pins_bounds(content, "CGND", cgnd_id)
        if cgnd_bounds:
            cx1 = max(bx1, cgnd_bounds[0] - PAD_PADDING)
            cy1 = max(by1, cgnd_bounds[1] - PAD_PADDING)
            cx2 = min(bx2, cgnd_bounds[2] + PAD_PADDING)
            cy2 = min(by2, cgnd_bounds[3] + PAD_PADDING)
            print(f"Adding CGND zone (priority 1): {cx1:.1f},{cy1:.1f} -> {cx2:.1f},{cy2:.1f}")
            zones.append(create_rect_zone(cgnd_id, "CGND", LAYER_GND, cx1, cy1, cx2, cy2, priority=1))
    
    # --- Star Tie-Point ---
    # Place the tie-point near the power input (J_AC_IN area, typically bottom-left)
    # This is where all grounds should meet
    tie_x, tie_y = bx1 + 15.0, by2 - 20.0  # Near bottom-left power input area
    
    print(f"Adding star tie-point at ({tie_x:.1f}, {tie_y:.1f})")
    
    # Create short traces from tie-point to each ground zone
    # These ensure electrical connection between the zones
    if gnd_id and pgnd_id:
        # Trace stub from tie-point (labeled as GND) to nearby PGND area
        tie_point_items.append(create_tie_segment(tie_x, tie_y, tie_x + 2, tie_y, 1.0, "B.Cu", gnd_id))
        # Note: The zones will fill and connect where they overlap
        # The tie-point is in an area where both PGND and GND zones exist
    
    # Write output
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + ''.join(tie_point_items) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote {len(zones)} star-ground zones + tie-point to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_star_ground_zones.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_star_gnd")
    
    add_star_ground_zones(inp, out)
