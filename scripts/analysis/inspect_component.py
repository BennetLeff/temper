import sys
import re
import math

def parse_pads(footprint_data):
    pads = []
    # (pad "1" smd rect (at -2.3 0) (size 2.6 5.6) ...)
    # Simplified regex for pad extraction
    pad_regex = re.compile(r'\((pad|via)\s+"?([^"\s]+)"?\s+[^)]+\(at\s+([-\d\.]+)\s+([-\d\.]+)(?:\s+([-\d\.]+))?\)\s+\(size\s+([-\d\.]+)\s+([-\d\.]+)\)(?:\s+\(drill\s+([-\d\.]+)\))?')
    
    # We need to find pads inside the footprint text
    # This is rough because S-expressions are nested.
    # We'll just scan the lines of the footprint block.
    
    for line in footprint_data.split('\n'):
        line = line.strip()
        if line.startswith('(pad'):
            # Simple extraction of position and size
            # This doesn't handle rotation fully correctly relative to footprint if we don't apply footprint transform,
            # but usually for a single component inspection we want local coordinates or absolute if we have the component position.
            pass
            # Let's use a more robust regex or just manual parsing for the line
            parts = line.split()
            try:
                # Find (at x y)
                at_idx = parts.index('(at')
                x = float(parts[at_idx+1])
                y = float(parts[at_idx+2].replace(')', ''))
                
                # Find (size w h)
                size_idx = parts.index('(size')
                w = float(parts[size_idx+1])
                h = float(parts[size_idx+2].replace(')', ''))
                
                # Find net if possible (net 1 "name")
                net_name = "Unknown"
                if '(net' in line:
                    net_start = line.find('(net')
                    net_end = line.find(')', net_start)
                    net_str = line[net_start:net_end+1]
                    # (net 5 "AC_L")
                    net_parts = net_str.split()
                    if len(net_parts) >= 3:
                        net_name = net_parts[2].strip('"')

                pads.append({
                    'x': x, 'y': y, 'w': w, 'h': h, 'net': net_name, 'raw': line
                })
            except ValueError:
                continue
                
    return pads

def inspect_component(pcb_path, ref_designator):
    with open(pcb_path, 'r') as f:
        content = f.read()

    # Find the footprint block
    # (footprint "Library:Name" (layer "F.Cu") ... (at X Y R) ... (fp_text reference "REF" ...) ... )
    
    # We need to be careful. The reference is inside the footprint block.
    # We'll split by "(footprint"
    blocks = content.split('(footprint')
    
    target_block = None
    target_pos = (0, 0, 0) # x, y, rot
    
    for block in blocks:
        # Check for standard fp_text reference or property Reference
        # Regex is safer than string matching for exact ref
        # standard: (fp_text reference "D2"
        # property: (property "Reference" "D2"
        
        ref_pattern = f'reference "{ref_designator}"'
        prop_pattern = f'property "Reference" "{ref_designator}"'
        
        if ref_pattern in block or prop_pattern in block:
            target_block = block
            
            # Extract position (at 39.37 37.785 180)
            at_match = re.search(r'\(at\s+([-\d\.]+)\s+([-\d\.]+)(?:\s+([-\d\.]+))?\)', block)
            if at_match:
                tx = float(at_match.group(1))
                ty = float(at_match.group(2))
                rot = float(at_match.group(3)) if at_match.group(3) else 0.0
                target_pos = (tx, ty, rot)
            break
            
    if not target_block:
        print(f"Component {ref_designator} not found.")
        return

    # Extract library name (first quoted string usually)
    lib_match = re.search(r'\s+"([^"]+)"', target_block)
    footprint_name = lib_match.group(1) if lib_match else "Unknown"
    
    print(f"Component: {ref_designator}")
    print(f"Footprint: {footprint_name}")
    print(f"Position: X={target_pos[0]}mm, Y={target_pos[1]}mm, Rot={target_pos[2]} deg")
    
    pads = parse_pads(target_block)
    print(f"Found {len(pads)} pads:")
    
    for i, p in enumerate(pads):
        # Transform local pad pos to absolute? 
        # The pad (at x y) in KiCad is usually relative to the footprint center, rotated by footprint rotation.
        # But if the file is fully expanded, sometimes it's different. 
        # In .kicad_pcb, pad (at ...) is relative to the footprint (at ...).
        
        # Local pos
        lx, ly = p['x'], p['y']
        
        # Rotate
        rad = math.radians(target_pos[2])
        rx = lx * math.cos(rad) - ly * math.sin(rad)
        ry = lx * math.sin(rad) + ly * math.cos(rad)
        
        # Translate
        ax = target_pos[0] + rx
        ay = target_pos[1] + ry
        
        print(f"  Pad {i+1}: Net='{p['net']}' Size={p['w']}x{p['h']}mm Local=({lx},{ly}) Abs=({ax:.3f},{ay:.3f})")
        p['abs_x'] = ax
        p['abs_y'] = ay

    # Check internal spacing
    print("\nInternal Pad-to-Pad Spacing (Center-to-Center - Copper Radii):")
    for i in range(len(pads)):
        for j in range(i+1, len(pads)):
            p1 = pads[i]
            p2 = pads[j]
            
            dx = p1['abs_x'] - p2['abs_x']
            dy = p1['abs_y'] - p2['abs_y']
            dist_center = math.sqrt(dx*dx + dy*dy)
            
            # Approximate copper edge distance by subtracting half-diagonals or half-widths?
            # Easiest is subtracting min radius (conservative) or max radius.
            # Usually strict edge-to-edge is dist_center - r1 - r2
            # where r is roughly min(w,h)/2 for simple primitives.
            
            r1 = min(p1['w'], p1['h']) / 2.0
            r2 = min(p2['w'], p2['h']) / 2.0
            
            gap = dist_center - r1 - r2
            
            print(f"  {p1['net']} vs {p2['net']}: CenterDist={dist_center:.3f}mm, Est.Gap={gap:.3f}mm")
            
            if abs(gap) < 6.0:
                 print(f"     -> VIOLATES 6mm rule internally if these nets require it!")

if __name__ == "__main__":
    inspect_component(sys.argv[1], sys.argv[2])
