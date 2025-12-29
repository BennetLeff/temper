#!/bin/bash
set -e

# ==============================================================================
# Physics-Aware End-to-End Flow
# ==============================================================================
# 1. Placement (skipped if exists)
# 2. Plane Generation
# 3. Physics-Aware Routing (Internal MazeRouter + Hypergraph Bridge)
# ==============================================================================

INPUT_PCB="pcb/temper.kicad_pcb"
PLACED_PCB="pcb/temper_placed.kicad_pcb"
PLANED_PCB="pcb/temper_ready_for_route.kicad_pcb"
ROUTED_PCB="pcb/temper_physics_routed.kicad_pcb"
CONFIG="packages/temper-placer/configs/temper_constraints.yaml"

echo "========================================================"
echo "Step 1: Placement"
echo "========================================================"

if [ -f "$PLACED_PCB" ]; then
    echo "Using existing placement: $PLACED_PCB"
else
    echo "Running Physics-Aware Placer..."
    .venv/bin/temper-placer optimize "$INPUT_PCB" \
        -c "$CONFIG" \
        -o "$PLACED_PCB" \
        --epochs 2000 \
        --auto-group
fi

echo ""

echo "========================================================"
echo "Step 2: Generating Smart Power Planes"
echo "========================================================"

.venv/bin/python3 add_power_planes_v2.py "$PLACED_PCB" "$PLANED_PCB"

echo ""

echo "========================================================"
echo "Step 3: Physics-Aware Routing"
echo "========================================================"

# Using 0.5mm cell size for balance between speed and resolution
.venv/bin/python3 scripts/internal_route.py "$PLANED_PCB" \
    -o "$ROUTED_PCB" \
    --cell-size 0.5

echo ""

echo "SUCCESS: Routed PCB saved to $ROUTED_PCB"
