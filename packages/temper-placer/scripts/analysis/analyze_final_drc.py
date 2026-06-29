
import json
from collections import Counter

try:
    with open('drc_report_final.json') as f:
        data = json.load(f)

    violations = data.get('violations', [])
    unconnected = data.get('unconnected_items', [])

    print(f"Total Violations: {len(violations)}")
    print(f"Total Unconnected: {len(unconnected)}")

    types = Counter(v.get('description', 'unknown') for v in violations)
    print("\nViolation Types:")
    for t, c in types.most_common():
        print(f"  {t}: {c}")

except Exception as e:
    print(e)

