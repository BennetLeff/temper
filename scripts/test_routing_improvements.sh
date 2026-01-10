#!/bin/bash
# Save as: scripts/test_routing_improvements.sh

echo "=== Testing Routing Improvements ==="

# 1. Run deterministic pipeline
echo "Step 1: Running deterministic pipeline..."
export PYTHONPATH=$PYTHONPATH:$(pwd)/packages/temper-placer/src
python3 -m temper_placer.cli place-deterministic \
    pcb/temper.kicad_pcb \
    -c configs/temper_deterministic_config.yaml \
    -o pcb/temper_test_output.kicad_pcb \
    --drc-aware

# 2. Run KiCad DRC
echo "Step 2: Running KiCad DRC..."
kicad-cli pcb drc pcb/temper_test_output.kicad_pcb \
    --output /tmp/drc_test.json \
    --format json \
    --severity-error

# 3. Analyze results
echo "Step 3: Analyzing results..."
python3 << 'EOF'
import json
from collections import Counter
import os

try:
    with open('/tmp/drc_test.json') as f:
        data = json.load(f)
except FileNotFoundError:
    print("Error: DRC output file not found.")
    exit(1)

unconnected = data.get('unconnected_items', [])
violations = data.get('violations', [])

print(f"\n=== DRC Results ===")
print(f"Unconnected items: {len(unconnected)}")
print(f"Violations: {len(violations)}")

# Count by net
net_counts = Counter()
for item in unconnected:
    for subitem in item.get('items', []):
        desc = subitem.get('description', '')
        # Simple parsing: "Net [NETNAME]" or similar
        # Look for [NETNAME]
        if '[' in desc and ']' in desc:
            try:
                parts = desc.split('[')
                if len(parts) > 1:
                    net_name = parts[1].split(']')[0]
                    net_counts[net_name] += 1
            except IndexError:
                pass

print(f"\n=== Unconnected by Net ===")
for net, count in net_counts.most_common(15):
    print(f"  {net}: {count}")

# Check critical nets
critical_nets = ['AC_L', 'AC_N', 'DC_BUS+', 'SW_NODE', 'GATE_H', 'GATE_L', 'GND']
print(f"\n=== Critical Net Status ===")
for net in critical_nets:
    count = net_counts.get(net, 0)
    status = "✓ OK" if count == 0 else f"✗ {count} unconnected"
    print(f"  {net}: {status}")
EOF
