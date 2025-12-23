#!/usr/bin/env bash
#
# Quick proof-of-concept for temper-a98v experiment
# Runs 2 placements per condition to verify pipeline
#
# Usage: ./scripts/run_temper_a98v_poc.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

INPUT_PCB="packages/temper-placer/tests/fixtures/medium_board.kicad_pcb"
EPOCHS=500  # Reduced for POC
N_RUNS=2    # Just 2 runs per condition for POC

RESULTS_DIR="experiments/temper-a98v"
mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "temper-a98v Proof of Concept"
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
    local seed=$((42 + run_num))
    
    local output_pcb="$RESULTS_DIR/${condition}_run${run_num}.kicad_pcb"
    local placements_json="$RESULTS_DIR/${condition}_run${run_num}_placements.json"
    local log_file="$RESULTS_DIR/${condition}_run${run_num}.log"
    
    echo ">>> Running: $condition #$run_num (seed=$seed)"
    
    temper-placer optimize \
        "$INPUT_PCB" \
        -c "$config_file" \
        -o "$output_pcb" \
        --epochs "$EPOCHS" \
        --seed "$seed" \
        --placements-json "$placements_json" \
        --no-curriculum \
        --no-heuristics \
        2>&1 | tee "$log_file"
    
    echo "✓ Complete: $output_pcb"
    echo
}

# Baseline condition
echo "========================================  "
echo "Condition: BASELINE"
echo "========================================"
CONFIG_BASELINE="experiments/temper-a98v/config_baseline.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "baseline" "$run" "$CONFIG_BASELINE"
done

# Option A condition
echo "========================================"
echo "Condition: OPTION A (reduced spread)"
echo "========================================"
CONFIG_A="experiments/temper-a98v/config_option_a.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "option_a" "$run" "$CONFIG_A"
done

# Option C condition
echo "========================================"
echo "Condition: OPTION C (edge avoidance)"
echo "========================================"
CONFIG_C="experiments/temper-a98v/config_option_c.yaml"
for run in $(seq 1 $N_RUNS); do
    run_placement "option_c" "$run" "$CONFIG_C"
done

echo "========================================"
echo "✓ POC Complete!"
echo "Results in: $RESULTS_DIR"
echo "========================================"
echo
echo "Next steps:"
echo "1. Extract metrics from placements JSON files"
echo "2. Run routing verification"
echo "3. Compute statistics"
echo "4. Scale up to 30 runs per condition"
