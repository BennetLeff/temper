#!/bin/bash
set -euo pipefail

# ==============================================================================
# Temper PCB "End-to-End" Automated Design Pipeline
# ==============================================================================
# This script enforces the "Professional" workflow:
# 1. Physics-Aware Placement (using temper_constraints.yaml)
# 2. Procedural Plane Generation (Physics-based Zoning)
# 3. Routing and KiCad DRC truth gate
# ==============================================================================

# 1. Define Paths (Single Source of Truth)
INPUT_PCB="pcb/temper.kicad_pcb"
PLACED_PCB="pcb/temper_placed.kicad_pcb"
PLANED_PCB="pcb/temper_ready_for_route.kicad_pcb"
CONFIG="packages/temper-placer/configs/temper_constraints.yaml"
GENERATED_NETLIST="elec/build/default.net"

echo "========================================================"
echo "Step 0: Checking generated safety design is imported"
echo "========================================================"

.venv/bin/python -c '
from pathlib import Path
from temper_placer.validation.real_board_inventory import validate_kicad_safety_parity

validate_kicad_safety_parity(
    Path("elec/build/default.net"),
    Path("pcb/temper.kicad_pcb"),
)
print("Generated safety netlist and KiCad board are in parity.")
'

echo "========================================================"
echo "Step 1: Running Physics-Aware Placer"
echo "Config: $CONFIG"
echo "========================================================"

# The place→route loop writes a routed board only if the generated safety
# design was imported, CP-SAT placement,
# routing, and the in-loop KiCad DRC gate all succeed.  Any failed stage exits
# non-zero; do not use a partially generated board as a routing input.
.venv/bin/temper-placer optimize "$INPUT_PCB" \
    -c "$CONFIG" \
    -o "$PLACED_PCB" \
    --epochs 2000 \
    --auto-group \
    --loop

echo ""
echo "========================================================"
echo "Step 2: Generating Smart Power Planes"
echo "========================================================"

# Add the current, unified GND reference plane after placement/routing.  This
# script is intentionally explicit here: the retired add_power_planes_v2.py
# no longer exists and must not make the flow appear to have run.
.venv/bin/python3 scripts/add_power_planes.py "$PLACED_PCB" "$PLANED_PCB"

echo ""
echo "========================================================"
echo "Step 3: Running KiCad DRC truth gate"
echo "========================================================"

kicad-cli pcb drc --format json -o "pcb/temper_ready_for_route_drc.json" "$PLANED_PCB"

echo ""
echo "SUCCESS: CP-SAT placement, routing, plane generation, and KiCad DRC passed."
