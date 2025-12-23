#!/usr/bin/env bash
#
# Run routing verification for all temper-a98v POC results
#
# Usage: ./scripts/verify_temper_a98v_all_routing.sh

set -euo pipefail

RESULTS_DIR="experiments/temper-a98v"
SUMMARY_FILE="$RESULTS_DIR/routing_summary.txt"

echo "Routing Verification Summary" > "$SUMMARY_FILE"
echo "============================" >> "$SUMMARY_FILE"
echo "Condition | Run | Completion" >> "$SUMMARY_FILE"
echo "----------|-----|-----------" >> "$SUMMARY_FILE"

run_routing() {
    local condition="$1"
    local run_num="$2"
    local pcb_file="$RESULTS_DIR/${condition}_run${run_num}.kicad_pcb"
    
    echo ">>> Routing: $condition #$run_num"
    
    local output=$(uv run python scripts/internal_route.py "$pcb_file" --cell-size 1.0)
    local completion=$(echo "$output" | grep "Completion rate" | awk '{print $4}')
    
    echo "$condition | $run_num | $completion" >> "$SUMMARY_FILE"
    echo "  ✓ Completion: $completion"
}

# Run for all conditions and runs
for condition in baseline option_a option_c; do
    for run in $(seq 1 30); do
        run_routing "$condition" "$run"
    done
done

echo
cat "$SUMMARY_FILE"
