#!/usr/bin/env bash
#
# Full experiment for temper-a98v
# Runs 30 placements per condition
#
# Usage: ./scripts/run_temper_a98v_full.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

INPUT_PCB="packages/temper-placer/tests/fixtures/medium_board.kicad_pcb"
EPOCHS=2000  # Increased for better convergence
N_RUNS=30    # Full sample size

RESULTS_DIR="experiments/temper-a98v"
mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "temper-a98v Full Experiment"
echo "Input: $INPUT_PCB"
echo "Epochs: $EPOCHS"
echo "Runs per condition: $N_RUNS"
echo "========================================"
echo

# Function to run one placement
run_placement() {
    local condition="$1"
    local run_num="$2"
    local config_file="$3"
    local seed=$((100 + run_num)) # Start from 100 to avoid POC seeds
    
    local output_pcb="$RESULTS_DIR/${condition}_run${run_num}.kicad_pcb"
    local placements_json="$RESULTS_DIR/${condition}_run${run_num}_placements.json"
    local log_file="$RESULTS_DIR/${condition}_run${run_num}.log"
    
    # Skip if already done (useful if script is interrupted)
    if [ -f "$output_pcb" ] && [ -f "$placements_json" ]; then
        echo ">>> Skipping: $condition #$run_num (already exists)"
        return
    fi

    echo ">>> Running: $condition #$run_num (seed=$seed)"
    
uv run temper-placer optimize \
        "$INPUT_PCB" \
        -c "$config_file" \
        -o "$output_pcb" \
        --epochs "$EPOCHS" \
        --seed "$seed" \
        --placements-json "$placements_json" \
        --no-curriculum \
        --no-heuristics \
        2>&1 > "$log_file" # Redirect to file to keep console clean
    
    echo "  ✓ Complete"
}

# Baseline condition
echo "Condition: BASELINE"
CONFIG_BASELINE="experiments/temper-a98v/config_baseline.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "baseline" "$run" "$CONFIG_BASELINE"
done

# Option A condition
echo "Condition: OPTION A (reduced spread)"
CONFIG_A="experiments/temper-a98v/config_option_a.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "option_a" "$run" "$CONFIG_A"
done

# Option C condition
echo "Condition: OPTION C (edge avoidance)"
CONFIG_C="experiments/temper-a98v/config_option_c.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "option_c" "$run" "$CONFIG_C"
done

echo "========================================"
echo "✓ Full Experiment Placements Complete!"
echo "========================================"
