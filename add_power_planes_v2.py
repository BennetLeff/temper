#!/usr/bin/env python3
"""
Add component-aware power plane zones to KiCad PCB.
Replaces the 'flood everything' approach with targeted zones based on component clustering.
"""

import re
import sys
import uuid
import math
from pathlib import Path
from collections import defaultdict

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
    Returns None if no pads found.
    """
    # Regex to find pads with specific net.
    # Note: This is a simplified parser. It looks for (pad ... (at X Y) ... (net ID "NAME"))
    # We need to capture the 'at' coordinates for pads that match the net.
    
    # Strategy: Find all footprints, then find pads within them.
    # But regex on nested structures is hard. 
    # Let's try a simpler approach: iterate over all (pad ...) lines that contain the net ID.
    # This might miss rotation transforms but is a good heuristic for "zones".
    
    # We need to match: (pad "..." ... (at X Y ...) ... (net ID "NAME")
    # This is tricky because 'at' comes before 'net'.
    
    xs = []
    ys = []
    
    # Extract all footprint blocks to handle relative coordinates
    footprint_pattern = r'\(footprint \".*?\" \(layer \".*?\"\)(.*?)\(attr'
    # This regex is too brittle. 
    
    # Let's rely on the fact that 'temper-placer' output usually has absolute coordinates in pads?
    # No, KiCad pads are relative to footprint.
    # We need to parse footprint (at x y) and pad (at x y).
    
    # Let's assume standard KiCad formatting from the file we read earlier:
    # (footprint ... (at 10 126.25 0) ... 
    #   (pad "1" ... (at 0 0) ... (net 19 "AC_L"))
    
    # 1. Find all footprints and their absolute positions
    footprints = [] # (index, x, y, content_start, content_end)
    
    for fm in re.finditer(r'\(footprint \"([^\"]+)\" \(layer \"([^\"]+)\"\)', content):
        start_idx = fm.start()
        # Find the matching closing paren is hard with regex. 
        # We will scan for "(at X Y R)" immediately following.
        
        # Search for (at ...) in the next 200 chars
        chunk = content[start_idx:start_idx+300]
        at_match = re.search(r'\(at ([\d.]+) ([\d.]+)(?: ([\d.-]+))?\)', chunk)
        if at_match:
            fx, fy = float(at_match.group(1)), float(at_match.group(2))
            
            # Now search for pads belonging to this footprint until the next footprint starts
            # We'll just look ahead until we hit another (footprint or end of file
            next_fp = content.find('(footprint', start_idx + 1)
            if next_fp == -1: next_fp = len(content)
            
            fp_content = content[start_idx:next_fp]
            
            # Find pads in this footprint
            for pm in re.finditer(r'\(pad \"[^\"]+\" \S+ \S+ \(at ([\d.-]+) ([\d.-]+)(?: [\d.-]+)?\).*?\(net (\d+)', fp_content, re.DOTALL):
                px, py = float(pm.group(1)), float(pm.group(2))
                p_net = int(pm.group(3))
                
                if p_net == net_id:
                    # Absolute position = Footprint Pos + Pad Pos (ignoring rotation for bounding box safety)
                    # For zones, slight inaccuracies due to rotation are fine if we add padding
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
    
    # 1. Get Board Size
    bx1, by1, bx2, by2 = parse_pcb_bounds(content)
    print(f"Board Bounds: {bx1},{by1} -> {bx2},{by2}")
    
    # 2. Map Nets
    nets = get_net_names(content)
    # Map common aliases
    pgnd_id = nets.get("PGND")
    cgnd_id = nets.get("CGND") or nets.get("GND") # Fallback if CGND not explicit
    gnd_id = nets.get("GND")
    p5v_id = nets.get("+5V")
    p3v3_id = nets.get("+3V3")
    
    zones = []
    
    # --- STRATEGY 1: SPLIT GROUND (Layer 2) ---
    # We assume High Power is at the Bottom (High Y) and Logic is at Top (Low Y)
    # based on component inspection.
    
    if pgnd_id and gnd_id:
        print("Detected Split Ground (PGND + GND)")
        
        # Get bounds of PGND components
        pgnd_bounds = get_net_pins_bounds(content, "PGND", pgnd_id)
        gnd_bounds = get_net_pins_bounds(content, "GND", gnd_id)
        
        split_y = (by1 + by2) / 2 # Default center split
        
        if pgnd_bounds and gnd_bounds:
            # PGND is likely High Y, GND is Low Y
            min_pgnd_y = pgnd_bounds[1]
            max_gnd_y = gnd_bounds[3]
            
            print(f"PGND Top Y: {min_pgnd_y}")
            print(f"GND Bottom Y: {max_gnd_y}")
            
            if min_pgnd_y > max_gnd_y:
                # Clean separation
                split_y = (min_pgnd_y + max_gnd_y) / 2
                print(f"Calculated Split Line: Y={split_y}")
            else:
                print("Warning: PGND and GND components overlap in Y. Using default center split.")
        
        # Create GND Zone (Top Half)
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, bx1 + 0.5, by1 + 0.5, bx2 - 0.5, split_y - 0.5, priority=1))
        
        # Create PGND Zone (Bottom Half)
        zones.append(create_rect_zone(pgnd_id, "PGND", LAYER_GND, bx1 + 0.5, split_y + 0.5, bx2 - 0.5, by2 - 0.5, priority=1))
        
    elif gnd_id:
        print("Single GND detected. Flooding Layer 2.")
        zones.append(create_rect_zone(gnd_id, "GND", LAYER_GND, bx1 + 0.5, by1 + 0.5, bx2 - 0.5, by2 - 0.5, priority=1))

    # --- STRATEGY 2: POWER ISLANDS (Layer 3) ---
    # targeted rectangles for +5V and +3V3
    
    if p5v_id:
        bounds = get_net_pins_bounds(content, "+5V", p5v_id)
        if bounds:
            # Add padding
            zx1 = max(bx1, bounds[0] - PAD_PADDING)
            zy1 = max(by1, bounds[1] - PAD_PADDING)
            zx2 = min(bx2, bounds[2] + PAD_PADDING)
            zy2 = min(by2, bounds[3] + PAD_PADDING)
            
            zones.append(create_rect_zone(p5v_id, "+5V", LAYER_PWR, zx1, zy1, zx2, zy2, priority=1))
            print(f"Added +5V Zone: {zx1},{zy1} -> {zx2},{zy2}")
        else:
            print("Warning: No +5V pins found.")

    if p3v3_id:
        bounds = get_net_pins_bounds(content, "+3V3", p3v3_id)
        if bounds:
            # Add padding
            zx1 = max(bx1, bounds[0] - PAD_PADDING)
            zy1 = max(by1, bounds[1] - PAD_PADDING)
            zx2 = min(bx2, bounds[2] + PAD_PADDING)
            zy2 = min(by2, bounds[3] + PAD_PADDING)
            
            # Check for overlap with 5V? 
            # Priority logic: If they overlap, one wins. But with calculated bounds,
            # they should naturally separate if placement is good.
            # If they overlap, we really should have a placer constraint! 
            
            zones.append(create_rect_zone(p3v3_id, "+3V3", LAYER_PWR, zx1, zy1, zx2, zy2, priority=1))
            print(f"Added +3V3 Zone: {zx1},{zy1} -> {zx2},{zy2}")
        else:
            print("Warning: No +3V3 pins found.")

    # Write output
    # Insert before last parenthesis
    insert_pos = content.rfind(')')
    new_content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]
    
    output_pcb.write_text(new_content)
    print(f"Wrote {len(zones)} smart zones to {output_pcb}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes_v2.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)
        
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_stem(inp.stem + "_smart_planes")
    
    add_smart_power_planes(inp, out)
