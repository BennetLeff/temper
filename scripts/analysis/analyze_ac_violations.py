import json
import sys
import collections
import statistics
import re
import os

def analyze_drc(json_path):
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    violations = data.get('violations', [])
    print(f"Total violations in JSON: {len(violations)}")

    ac_mains_violations = []
    other_violations = []

    for v in violations:
        desc = v.get('description', '')
        if "netclass 'ACMains'" in desc:
            ac_mains_violations.append(v)
        else:
            other_violations.append(v)

    print(f"ACMains violations: {len(ac_mains_violations)}")
    print(f"Other violations: {len(other_violations)}")

    if not ac_mains_violations:
        return

    # Extract coordinates and object pairs
    ac_points = []
    object_pairs = collections.Counter()
    
    print("\n--- AC Mains Violation Details ---")
    
    for v in ac_mains_violations:
        items = v.get('items', [])
        current_points = []
        obj_descs = []
        
        for item in items:
            pos = item.get('pos')
            if pos:
                current_points.append((pos['x'], pos['y']))
                ac_points.append((pos['x'], pos['y']))
            
            d = item.get('description', 'Unknown')
            # simplify description to get generic type (e.g. "Pad 14 [VCC_BOOT] of U_GATE" -> "U_GATE Pad [VCC_BOOT]")
            # Regex to capture Ref and Name
            # "Pad 14 [VCC_BOOT] of U_GATE on F.Cu" -> "U_GATE"
            # "Track [AC_L] on F.Cu" -> "Track [AC_L]"
            
            ref_match = re.search(r'of ([A-Za-z0-9_]+)', d)
            net_match = re.search(r'\[([^\]]+)\]', d)
            
            label = d
            if ref_match:
                label = f"Comp {ref_match.group(1)}"
            elif "Track" in d:
                label = "Track"
            elif "Via" in d:
                label = "Via"
                
            if net_match:
                label += f" [{net_match.group(1)}]"
            
            obj_descs.append(label)
        
        objects_key = " vs ".join(sorted(obj_descs))
        object_pairs[objects_key] += 1

    print("\nTop 10 AC Violation Object Pairs:")
    for pair, count in object_pairs.most_common(10):
        print(f"{count}: {pair}")

    if not ac_points:
        print("No coordinates found in ACMains violations.")
        return

    xs = [p[0] for p in ac_points]
    ys = [p[1] for p in ac_points]

    print("\n--- ACMains Violation Distribution ---")
    print(f"X range: {min(xs):.2f} to {max(xs):.2f} mm")
    print(f"Y range: {min(ys):.2f} to {max(ys):.2f} mm")
    
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    print(f"Bounding Box: {width:.2f} x {height:.2f} mm")
    
    center_x = statistics.mean(xs)
    center_y = statistics.mean(ys)
    print(f"Centroid: ({center_x:.2f}, {center_y:.2f})")

    # ASCII Plot
    if width < 1: width = 1
    if height < 1: height = 1
    
    grid_w, grid_h = 60, 20
    grid = [['.' for _ in range(grid_w)] for _ in range(grid_h)]
    
    for x, y in ac_points:
        gx = int((x - min(xs)) / width * (grid_w - 1))
        gy = int((y - min(ys)) / height * (grid_h - 1))
        grid[gy][gx] = '#'

    print("\nMap (Bounds: X=%.1f-%.1f, Y=%.1f-%.1f):" % (min(xs), max(xs), min(ys), max(ys)))
    for row in grid:
        print("".join(row))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_drc(sys.argv[1])
    else:
        print("Usage: python analyze_drc.py <json_file>")
