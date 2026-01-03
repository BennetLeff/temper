#!/bin/bash
# Clearance sweep experiment
# Tests different clearance values to find optimal routing settings

BASE_DSN="pcb/temper_ordered.dsn"
OUTPUT_DIR="experiments/routing_data"

mkdir -p "$OUTPUT_DIR"

for CLEARANCE in 8 10 12 15; do
    echo "=== Testing clearance: $CLEARANCE ==="

    # Copy base DSN and modify clearance
    DSN_FILE="$OUTPUT_DIR/clearance_${CLEARANCE}.dsn"
    cp "$BASE_DSN" "$DSN_FILE"

    # Replace clearance value in the DSN file
    sed -i '' "s/(clearance [0-9]*)/(clearance $CLEARANCE)/g" "$DSN_FILE"

    # Also try reducing trace width for better routing
    if [ "$CLEARANCE" -lt 12 ]; then
        sed -i '' "s/(width 13)/(width 10)/g" "$DSN_FILE"
    fi

    # Run FreeRouter with limited passes
    echo "Running FreeRouter..."
    java -jar ~/tools/freerouting.jar -de "$DSN_FILE" -mp 100 -mt 1 2>&1 | \
        grep -E "(unrouted|completed)" | tail -3

    echo ""
done
