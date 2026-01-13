#!/bin/bash
# Run full Temper board deterministic placement + routing pipeline
set -e

echo "=== Temper Board Deterministic Pipeline ==="
echo "25 nets | 4 zones | 4-layer routing"
echo ""

cd "$(dirname "$0")/../packages/temper-placer"

# Run the deterministic placement pipeline
python -m temper_placer.cli place-deterministic \
  ../../pcb/temper.kicad_pcb \
  --config ../../configs/temper_deterministic_config.yaml \
  --output ../../pcb/temper_deterministic.kicad_pcb \
  --max-iterations 3 \
  --no-local-refinement \
  --seed 42

echo ""
echo "✓ Output written to: pcb/temper_deterministic.kicad_pcb"
echo "  Next: Open in KiCad and run DRC"
