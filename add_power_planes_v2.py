#!/usr/bin/env python3
"""
Add component-aware power plane zones to KiCad PCB.
V3: Priority-based overlapping zones to handle interleaved placements.
"""

import re
import sys
import uuid
import math
from pathlib import Path

# Configuration
PAD_PADDING = 5.0  # mm extra around pins for zone
LAYER_GND = "In2.Cu"
LAYER_PWR = "In1.Cu"

def generate_tstamp():
    return str(uuid.uuid4())

def parse_pcb_bounds(content):
    """Find board dimensions from Edge.Cuts."""
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer \"Edge\.Cuts\"\)', content)
    if edge_match:
        return list(map(float, edge_match.groups()))
    return [0, 0, 100, 150] # Default

def get_net_names(content):
    """Map net name to net ID."""
    nets = {}
    for match in re.finditer(r'\(net (\d+) \"([^\"]+)\"\)', content):
        nets[match.group(2)] = int(match.group(1))
    return nets

def get_net_pins_bounds(content, net_name, net_id):
    """
    Find the bounding box (min_x, min_y, max_x, max_y) of all pads belonging to a specific net.
    """
    xs = []
    ys = []
    
    # 1. Find all footprints and their absolute positions
    for fm in re.finditer(r'\(footprint \"([^\"]+)\" \(layer \"([^\"]+)\"\)', content):
        start_idx = fm.start()
        
        # Search for (at ...) in the next 300 chars
        chunk = content[start_idx:start_idx+300]
        at_match = re.search(r'\(at ([\d.]+) ([\d.]+)(?: ([\d.-]+))?\)', chunk)
        if at_match:
            fx, fy = float(at_match.group(1)), float(at_match.group(2))
            
            # Look ahead for pads until next footprint or file end
            next_fp = content.find('(footprint', start_idx + 1)
            if next_fp == -1: next_fp = len(content)
            
            fp_content = content[start_idx:next_fp]
            
            # Find pads in this footprint
            for pm in re.finditer(r'\(pad \"[^\"]+\" \S+ \S+ \(at ([\d.-]+) ([\d.-]+)(?: [\d.-]+)?\).*?\(net (\d+)', fp_content, re.DOTALL):
                px, py = float(pm.group(1)), float(pm.group(2))
                p_net = int(pm.group(3))
                
                if p_net == net_id:
                    # Absolute position (ignoring rotation for bounding box)
                    abs_x = fx + px
                    abs_y = fy + py
                    xs.append(abs_x)
                    ys.append(abs_y)
                    
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
        (xy {x1} {y1})
        (xy {x2} {y1})
        (xy {x2} {y2})
        (xy {x1} {y2})
      )
    )
  ) 
'''

def add_smart_power_planes(input_pcb: Path, output_pcb: Path):
    content = input_pcb.read_text()
    
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    nets = get_net_names(content)
    pgnd_id = nets.get("PGND")
    gnd_id = nets.get("GND")
    p5v_id = nets.get("+5V")
    p3v3_id = nets.get("+3V3")
    
    zones = []
    
    # --- STRATEGY: Priority-Based Flooding ---
    
    # 1. Base GND Plane (Low Priority, fills everywhere)
    if gnd_id:
        print("Adding Base GND Plane (Priority 0)")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, bx1 + 0.5, by1 + 0.5, bx2 - 0.5, by2 - 0.5, priority=0))
        # Also add GND on Power Layer (In1.Cu) to help stitching
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_PWR, bx1 + 0.5, by1 + 0.5, bx2 - 0.5, by2 - 0.5, priority=0))
    
    # 2. PGND Island (High Priority, overrides GND)
    if pgnd_id:
        pgnd_bounds = get_net_pins_bounds(content, "PGND", pgnd_id)
        if pgnd_bounds:
            # Expand bounds by padding
            px1 = max(bx1, pgnd_bounds[0] - PAD_PADDING)
            py1 = max(by1, pgnd_bounds[1] - PAD_PADDING)
            px2 = min(bx2, pgnd_bounds[2] + PAD_PADDING)
            py2 = min(by2, pgnd_bounds[3] + PAD_PADDING)
            
            print(f"Adding PGND Island (Priority 1): {px1},{py1} -> {px2},{py2}")
            zones.append(create_rect_zone(pgnd_id, "PGND", LAYER_GND, px1, py1, px2, py2, priority=1))
        else:
            print("Warning: PGND net found but no pins found.")

    # 3. Logic Power Islands (+5V, +3V3) on Power Layer
    if p5v_id:
        bounds = get_net_pins_bounds(content, "+5V", p5v_id)
        if bounds:
            zx1 = max(bx1, bounds[0] - PAD_PADDING)
            zy1 = max(by1, bounds[1] - PAD_PADDING)
            zx2 = min(bx2, bounds[2] + PAD_PADDING)
            zy2 = min(by2, bounds[3] + PAD_PADDING)
            
            zones.append(create_rect_zone(p5v_id, "+5V", LAYER_PWR, zx1, zy1, zx2, zy2, priority=1))
            print(f"Added +5V Zone: {zx1},{zy1} -> {zx2},{zy2}")

    if p3v3_id:
        bounds = get_net_pins_bounds(content, "+3V3", p3v3_id)
        if bounds:
            zx1 = max(bx1, bounds[0] - PAD_PADDING)
            zy1 = max(by1, bounds[1] - PAD_PADDING)
            zx2 = min(bx2, bounds[2] + PAD_PADDING)
            zy2 = min(by2, bounds[3] + PAD_PADDING)
            
            zones.append(create_rect_zone(p3v3_id, "+3V3", LAYER_PWR, zx1, zy1, zx2, zy2, priority=1))
            print(f"Added +3V3 Zone: {zx1},{zy1} -> {zx2},{zy2}")

    # Write output
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote {len(zones)} priority-based zones to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes_v2.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_smart_planes")
    
    add_smart_power_planes(inp, out)