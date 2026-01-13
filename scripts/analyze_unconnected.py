import json
import sys
from collections import Counter

def analyze_drc(drc_file):
    with open(drc_file, 'r') as f:
        data = json.load(f)
    
    unconnected = data.get('unconnected_items', [])
    print(f"Total Unconnected Items: {len(unconnected)}")
    
    # Categorize by net
    net_counts = Counter()
    layer_counts = Counter()
    description_summary = Counter()
    
    for item in unconnected:
        # KiCad output format for unconnected items is a bit complex
        # It usually lists two items that aren't connected
        items_list = item.get('items', [])
        nets = set()
        layers = set()
        
        for sub_item in items_list:
            desc = sub_item.get('description', '')
            # Extract net name from description: e.g. "Track [GND] on F.Cu"
            if '[' in desc and ']' in desc:
                net = desc.split('[')[1].split(']')[0]
                nets.add(net)
            
            # Extract layer name
            if ' on ' in desc:
                layer = desc.split(' on ')[1].split(',')[0].strip()
                layers.add(layer)
        
        for net in nets:
            net_counts[net] += 1
        for layer in layers:
            layer_counts[layer] += 1
            
        description_summary[item.get('description', 'Unknown')] += 1

    print("\nBy Net:")
    for net, count in net_counts.most_common():
        print(f"  {net}: {count}")
        
    print("\nBy Layer:")
    for layer, count in layer_counts.most_common():
        print(f"  {layer}: {count}")
        
    print("\nSample Violations:")
    for item in unconnected[:5]:
        print(f"  - {item.get('description')}")
        for sub in item.get('items', []):
            print(f"    * {sub.get('description')} at {sub.get('pos')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/analyze_unconnected.py <drc_report.json>")
    else:
        analyze_drc(sys.argv[1])
