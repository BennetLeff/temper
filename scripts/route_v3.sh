#!/bin/bash
# Recommended command for Router V3 (temper-v3-opt)
# Usage: ./scripts/route_v3.sh <input_pcb> [output_pcb]

INPUT_PCB=${1:-"packages/temper-placer/output_temper_with_priority.kicad_pcb"}
OUTPUT_PCB=${2:-"routed_v3.kicad_pcb"}

echo "Running Router V3 on $INPUT_PCB..."

# Best practice settings for 4-layer induction cooker board:
# --layers 4:         Enable full stackup (Sig-GND-PWR-Sig)
#                     In1.Cu = GND plane (copper pour)
#                     In2.Cu = VCC/+15V plane (copper pour)
# --exclude-power-nets: Skip GND/VCC - they connect via vias to planes, not traces
# --cell-size 0.5:    Coarse enough for signal clearance
# --min-clearance 0.5: Enforce 0.5mm spacing between traces

uv run scripts/internal_route.py \
    "$INPUT_PCB" \
    --output "$OUTPUT_PCB" \
    --layers 4 \
    --cell-size 0.5 \
    --rrr-iters 50 \
    --history-increment 2.0 \
    --via-cost 200.0 \
    --min-clearance 0.5 \
    --exclude-power-nets \
    --add-power-zones

echo "Done! Output at $OUTPUT_PCB"
echo "NOTE: Power nets (GND, VCC, +15V) connected via copper pour zones on In1.Cu (GND) and In2.Cu (VCC)."
