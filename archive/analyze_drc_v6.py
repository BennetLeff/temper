
import json
from collections import Counter

try:
    with open('drc_report_v6_fixed.json') as f:
        data = json.load(f)
        
    violations = data.get('violations', [])
    unconnected = data.get('unconnected_items', [])
    
    print(f"Total Violations: {len(violations)}")
    print(f"Total Unconnected: {len(unconnected)}")
    
    types = Counter(v.get('description', 'unknown') for v in violations)
    print("\nViolation Types:")
    for t, c in types.most_common():
        print(f"  {t}: {c}")
        
    # Sample a few clearance violations to see details
    clearance_vios = [v for v in violations if 'Clearance' in v.get('description', '')]
    if clearance_vios:
        print("\nSample Clearance Violation:")
        print(json.dumps(clearance_vios[0], indent=2))
        
except Exception as e:
    print(e)
