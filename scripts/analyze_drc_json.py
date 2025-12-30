import json
from collections import Counter
from pathlib import Path

def analyze_drc(report_path):
    with open(report_path, 'r') as f:
        data = json.load(f)

    violations = data.get('violations', [])
    unconnected = data.get('unconnected_items', [])

    print(f"Total Violations: {len(violations)}")
    print(f"Total Unconnected: {len(unconnected)}")

    # Categorize Violations
    v_types = Counter()
    v_severities = Counter()
    shorting_pairs = Counter()

    for v in violations:
        v_types[v.get('type', 'unknown')] += 1
        v_severities[v.get('severity', 'unknown')] += 1
        
        if v.get('type') == 'shorting_items':
            # Extract nets involved if available
            desc = v.get('description', '')
            # Try to extract net names from description "Items shorting two nets (nets A and B)"
            if '(nets ' in desc:
                nets_part = desc.split('(nets ')[1].split(')')[0]
                shorting_pairs[nets_part] += 1

    print("\n--- Violation Types ---")
    for v_type, count in v_types.most_common():
        print(f"{v_type}: {count}")

    print("\n--- Top 10 Shorting Pairs ---")
    for pair, count in shorting_pairs.most_common(10):
        print(f"{pair}: {count}")

    print("\n--- Unconnected Nets ---")
    unconnected_nets = Counter()
    for u in unconnected:
        # Extract net names from items
        # Usually unconnected items list pads/tracks belonging to the same net that are disjoint
        # We look at the first item's description or net name if we can infer it
        # Description format: "PTH pad 2 [GND] of J_NTC"
        items = u.get('items', [])
        if items:
            desc = items[0].get('description', '')
            if '[' in desc and ']' in desc:
                net_name = desc.split('[')[1].split(']')[0]
                unconnected_nets[net_name] += 1
            else:
                unconnected_nets['unknown'] += 1
    
    for net, count in unconnected_nets.most_common():
        print(f"{net}: {count} islands")

if __name__ == "__main__":
    analyze_drc("drc_report_v5.json")
