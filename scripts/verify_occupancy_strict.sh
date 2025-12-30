#!/bin/bash
# scripts/verify_occupancy_strict.sh
#
# Verification script for occupancy grid enforcement in strict mode.
# Verifies that tracks_crossing violations are eliminated when soft_blocking=False.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Occupancy Enforcement Verification (Strict Mode) ==="

# 1. Run router in strict mode on the Temper board
# Note: --soft-blocking is False by default in the script if not specified, 
# but we'll ensure the behavior by checking the internal_route.py implementation.
OUTPUT_PCB="/tmp/temper_strict_verification.kicad_pcb"
DRC_REPORT="/tmp/drc_strict_verification.json"

echo "Routing board in strict mode..."
uv run --python 3.11 scripts/internal_route.py \
    pcb/temper.kicad_pcb \
    --output "$OUTPUT_PCB" \
    --cell-size 1.0 \
    --layers 2 \
    --rrr-iters 5

# 2. Run DRC
echo "Running KiCad DRC..."
kicad-cli pcb drc "$OUTPUT_PCB" -o "$DRC_REPORT" --format json --exit-code-violations || true

# 3. Check for tracks_crossing violations
echo "Analyzing DRC results..."
CROSSINGS=$(jq '[.violations[] | select(.type == "tracks_crossing")] | length' "$DRC_REPORT")

if [ "$CROSSINGS" -eq 0 ]; then
    echo "✓ SUCCESS: 0 tracks_crossing violations found."
    exit 0
else
    echo "✗ FAILURE: Found $CROSSINGS tracks_crossing violations."
    echo "This indicates that occupancy enforcement is not working as expected."
    exit 1
fi
