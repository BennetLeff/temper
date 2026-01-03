import sys

def force_drill_rule(filename):
    with open(filename, 'r') as f:
        content = f.read()

    # Check if header needs injection
    if '(min_through_hole' in content:
        print("min_through_hole already present.")
        return

    # Injection: Add min_through_hole and min_clearance inside setup
    # We find (setup and append our rules
    patch = '\n    (min_through_hole 0.250000)\n    (min_clearance 0.150000)\n    (min_track_width 0.150000)'
    
    if '(setup' in content:
        new_content = content.replace('(setup', '(setup' + patch, 1)
        with open(filename, 'w') as f:
            f.write(new_content)
        print(f"Patched {filename} with forced rules.")
    else:
        print("Error: (setup block not found.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python force_drill_rule.py <file>")
        sys.exit(1)
    force_drill_rule(sys.argv[1])
