#!/bin/bash
set -e

echo '=== DRC Improvement Measurement ==='
echo ''

# Paths
INPUT_PCB="pcb/temper.kicad_pcb"
CONFIG="configs/temper_deterministic_config.yaml"
BASELINE_PCB="/tmp/baseline.kicad_pcb"
DRC_AWARE_PCB="/tmp/drc_aware.kicad_pcb"
BASELINE_DRC="/tmp/baseline_drc.json"
DRC_AWARE_DRC="/tmp/drc_aware_drc.json"

# Baseline (no DRC integration)
echo 'Running baseline (no DRC integration)...'
export PYTHONPATH="$(pwd)/packages/temper-placer/src"
python3 -m temper_placer.cli place-deterministic \
  "$INPUT_PCB" \
  --config "$CONFIG" \
  --no-drc-aware \
  --output "$BASELINE_PCB"

echo 'Running KiCad DRC on baseline...'
kicad-cli pcb drc "$BASELINE_PCB" \
  --output "$BASELINE_DRC" --format json 2>/dev/null || echo "kicad-cli finished with warnings (expected)"

# DRC-aware
echo 'Running DRC-aware pipeline...'
python3 -m temper_placer.cli place-deterministic \
  "$INPUT_PCB" \
  --config "$CONFIG" \
  --drc-aware \
  --output "$DRC_AWARE_PCB"

echo 'Running KiCad DRC on DRC-aware...'
kicad-cli pcb drc "$DRC_AWARE_PCB" \
  --output "$DRC_AWARE_DRC" --format json 2>/dev/null || echo "kicad-cli finished with warnings (expected)"

# Compare
echo ''
echo '=== Results ==='
python3 << 'EOF'
import json
import os

def analyze(path):
    if not os.path.exists(path):
        return 0, {}
    with open(path) as f:
        try:
            d = json.load(f)
        except:
            return 0, {}
    violations = d.get('violations', [])
    by_type = {}
    for v in violations:
        t = v.get('type', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
    return len(violations), by_type

baseline_total, baseline_types = analyze('/tmp/baseline_drc.json')

drc_total, drc_types = analyze('/tmp/drc_aware_drc.json')



print(f'Baseline: {baseline_total} violations')

print(f'DRC-aware: {drc_total} violations')

if baseline_total > 0:

    reduction = baseline_total - drc_total

    percent = 100 * reduction / baseline_total

    print(f'Reduction: {reduction} ({percent:.1f}%)')

else:

    print(f'Reduction: {baseline_total - drc_total} violations')

print()
print('By type:')
all_types = set(baseline_types) | set(drc_types)
for t in sorted(all_types):
    b = baseline_types.get(t, 0)
    d = drc_types.get(t, 0)
    delta = d - b
    print(f'  {t}: {b} -> {d} ({delta:+d})')
EOF
