import json
import re
from collections import Counter

def main():
    try:
        data = json.load(open('output/optimized_relaxed_drc.json'))
    except FileNotFoundError:
        print("Error: output/optimized_relaxed_drc.json not found")
        return

    violations = [v for v in data['violations'] if v['type'] in ('shorting_items', 'clearance')]
    pairs = []
    
    for v in violations:
        # Expected format: "Items: Track ... (NetA) and Track ... (NetB)"
        # Or similar. We look for "(NetName)" patterns.
        desc = v['description']
        nets = re.findall(r'\((.*?)\)', desc)
        
        # Filter out mechanical items like 'F.Cu' or 'Edge.Cuts' if they appear in parens
        # But usually KiCad puts net names in parens for items.
        # Actually items often look like: "Track starting at ... on F.Cu (NetName)"
        # So finding all parenthesized items might get 'F.Cu'.
        # Let's count specific known nets if possible, or just take the pair if we find exactly 2 distinct ones
        # typically 2 items involved.
        
        valid_nets = [n for n in nets if n not in ('F.Cu', 'B.Cu', 'Edge.Cuts', 'F.SilkS', 'B.SilkS', 'F.Paste', 'B.Paste', 'F.Mask', 'B.Mask', 'User.Drawings', 'User.Comments', 'User.Eco1', 'User.Eco2')]
        
        if len(valid_nets) >= 2:
            # Take the last two, as item description usually ends with net
            n1 = valid_nets[-2]
            n2 = valid_nets[-1]
            if n1 != n2:
                pairs.append(tuple(sorted([n1, n2])))
        elif len(valid_nets) == 1:
             pairs.append(('?', valid_nets[0]))
        else:
             pass # Mechanical vs Mechanical?

    print("\nTop 20 Conflict Pairs (Shorts + Clearance):")
    for pair, count in Counter(pairs).most_common(20):
        print(f"{count:3d}: {pair[0]} <-> {pair[1]}")

if __name__ == "__main__":
    main()
