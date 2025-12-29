#!/bin/bash
set -e

# ==============================================================================
# Temper PCB "End-to-End" Automated Design Pipeline
# ==============================================================================
# This script enforces the "Professional" workflow:
# 1. Physics-Aware Placement (using temper_constraints.yaml)
# 2. Procedural Plane Generation (Physics-based Zoning)
# 3. Router Export
# ==============================================================================

# 1. Define Paths (Single Source of Truth)
INPUT_PCB="pcb/temper.kicad_pcb"
PLACED_PCB="pcb/temper_placed.kicad_pcb"
PLANED_PCB="pcb/temper_ready_for_route.kicad_pcb"
CONFIG="packages/temper-placer/configs/temper_constraints.yaml"

echo "========================================================"
echo "Step 1: Running Physics-Aware Placer"
echo "Config: $CONFIG"
echo "========================================================"

# Run the placer with the STRICT constraints
# We use --no-curriculum for a faster "cold start" check, or enable it for quality.
# We'll use defaults which enable curriculum.
.venv/bin/temper-placer optimize "$INPUT_PCB" \
    -c "$CONFIG" \
    -o "$PLACED_PCB" \
    --epochs 2000 \
    --auto-group

echo ""
echo "========================================================"
echo "Step 2: Generating Smart Power Planes"
echo "========================================================"

# Run the smart plane generator
.venv/bin/python3 add_power_planes_v2.py "$PLACED_PCB" "$PLANED_PCB"

echo ""
echo "========================================================"
echo "Step 3: Exporting to DSN for Router"
echo "========================================================"

# We export the DSN. Note: We do NOT exclude the power nets because
# we want the router to connect to the planes we just generated.
# However, if the router is struggling, we can use export_dsn.py with specific flags.
# For now, we use the placer's built-in export or the standalone script?
# The placer has an export command but it applies JSON placements to a PCB.
# We need to convert the .kicad_pcb to .dsn.
# We'll use the existing python script for that if available, or we assume
# the user will open FreeRouting on the .dsn file.

# Check if we have a DSN exporter script
if [ -f "export_dsn.py" ]; then
    .venv/bin/python3 export_dsn.py "$PLANED_PCB" "pcb/temper_autoroute.dsn"
    echo "DSN file created at pcb/temper_autoroute.dsn"
else
    echo "Warning: export_dsn.py not found. You may need to export DSN manually from KiCad."
fi

echo ""
echo "SUCCESS: Design is ready for routing."
echo "1. Open pcb/temper_autoroute.dsn in FreeRouting"
echo "2. Run Autorouter"
echo "3. Import Session file back to KiCad"
