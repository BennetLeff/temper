#!/bin/bash
# sweep_runaway_boundary.sh
#
# PURPOSE: 432-point parameter sweep launcher for sim_35_runaway_boundary.cir.
# Sweeps: VBUS (110 170 240 340) x K (0.0 0.2 0.35 0.5) x
#         C_TOL (0.8 1.0 1.2) x TAMB (25 40 55) x FAN (0.0 0.5 1.0)
# = 432 combinations.
#
# Output: simulation/results/runaway_boundary_map.csv
# Errors: simulation/results/sweep_errors.log
#
# USAGE:
#   ./sweep_runaway_boundary.sh [--dry-run] [--parallel N]
#
# DEPENDENCIES: ngspice >= v38

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TESTBENCH="$SCRIPT_DIR/sim_35_runaway_boundary.cir"
RESULTS_DIR="$PROJECT_ROOT/simulation/results"
CSV_OUT="$RESULTS_DIR/runaway_boundary_map.csv"
ERROR_LOG="$RESULTS_DIR/sweep_errors.log"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Sweep parameter arrays
VBUS_VALS=(110 170 240 340)
K_VALS=(0.0 0.2 0.35 0.5)
CTOL_VALS=(0.8 1.0 1.2)
TAMB_VALS=(25 40 55)
FAN_VALS=(0.0 0.5 1.0)

# Total combinations
TOTAL=$(( ${#VBUS_VALS[@]} * ${#K_VALS[@]} * ${#CTOL_VALS[@]} * ${#TAMB_VALS[@]} * ${#FAN_VALS[@]} ))

# Parallelism (default: 1)
PARALLEL=${2:-1}
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# ------------------------------------------------------------------
# CSV header
# ------------------------------------------------------------------
echo "vbus,k,ctol,tamb,fan,tj_max,tj_max_powered,tc_max_powered,tcoil_max_powered,tj_end_powered,tj_end_observe,tj_slope_post,tc_end_powered,ths_end_powered,tcoil_end_powered,classification" > "$CSV_OUT"

# Clear error log
>"$ERROR_LOG"

# ------------------------------------------------------------------
# Helper: classify result
# ------------------------------------------------------------------
classify() {
    local tj_max="$1"
    local tj_slope="$2"
    local tj_end="$3"

    # Protect against empty values
    if [[ -z "$tj_max" || "$tj_max" == "failed" || -z "$tj_slope" || "$tj_slope" == "failed" ]]; then
        echo "failed"
        return
    fi

    # Destructive check: Tj > 175 C at any point
    if awk "BEGIN {exit !($tj_max > 175)}"; then
        echo "destructive"
        return
    fi

    # Runaway check: dTj/dt > 1 C/s post-gate AND Tj > 125 C
    if awk "BEGIN {exit !($tj_slope > 1.0 && $tj_end > 125)}"; then
        echo "runaway"
        return
    fi

    # Steady-state check: Tj < 125 C and dTj/dt < 0
    if awk "BEGIN {exit !($tj_end < 125 && $tj_slope < 0)}"; then
        echo "steady-state"
        return
    fi

    # Edge case: warm but not runaway, not steady
    echo "warm"
}

# ------------------------------------------------------------------
# Helper: run single simulation
# ------------------------------------------------------------------
run_one() {
    local vbus="$1" k="$2" ctol="$3" tamb="$4" fan="$5"
    local combo="v${vbus}_k${k}_c${ctol}_t${tamb}_f${fan}"
    local logfile="$RESULTS_DIR/run_${combo}.log"
    local prefix="$RESULTS_DIR/run_${combo}"

    if $DRY_RUN; then
        echo "[DRY-RUN] VBUS=$vbus K=$k C_TOL=$ctol TAMB=$tamb FAN=$fan"
        return 0
    fi

    # Write parameter override file for this sweep point
    local params_file="$SCRIPT_DIR/sweep_params.sp"
    cat > "$params_file" <<PARAMEOF
* sweep_params.sp - Auto-generated for combo $combo
.param VBUS=$vbus
.param K=$k
.param C_TOL=$ctol
.param TAMB=$tamb
.param FAN=$fan
PARAMEOF

    # Run ngspice with parameter overrides
    if ngspice -b "$TESTBENCH" \
        -o "$prefix" \
        >"$logfile" 2>&1; then

        # Parse ngspice output: measurements are printed to stdout/-o file
        local outfile="${prefix}"
        if [[ ! -f "$outfile" ]]; then
            outfile="$logfile"
        fi

        # Helper: extract measurement value from ngspice output
        # Format: "name          =  1.234e+02" or "name          =  1.234e+02 at=..."
        extract_meas() {
            local name="$1" file="$2"
            awk -v n="$name" '$1 == n {print $3}' "$file" 2>/dev/null | head -1
        }

        local tj_max
        tj_max=$(extract_meas "tj_max_val" "$outfile")
        local tj_max_powered
        tj_max_powered=$(extract_meas "tj_max_pw" "$outfile")
        local tc_max_powered
        tc_max_powered=$(extract_meas "tc_max_pw" "$outfile")
        local tcoil_max_powered
        tcoil_max_powered=$(extract_meas "tcoil_max_pw" "$outfile")
        local tj_end_powered
        tj_end_powered=$(extract_meas "tj_end_pw" "$outfile")
        local tj_end_observe
        tj_end_observe=$(extract_meas "tj_end_obs" "$outfile")
        local tc_end_powered
        tc_end_powered=$(extract_meas "tc_end_pw" "$outfile")
        local ths_end_powered
        ths_end_powered=$(extract_meas "ths_end_pw" "$outfile")
        local tcoil_end_powered
        tcoil_end_powered=$(extract_meas "tcoil_end_pw" "$outfile")

        # Compute slope post-gate
        local tj_slope_post="0.0"
        if [[ -n "$tj_end_powered" && -n "$tj_end_observe" ]]; then
            tj_slope_post=$(awk "BEGIN {printf \"%.6f\", ($tj_end_observe - $tj_end_powered) / 0.5}")
        fi

        echo "$vbus,$k,$ctol,$tamb,$fan,$tj_max,$tj_max_powered,$tc_max_powered,$tcoil_max_powered,$tj_end_powered,$tj_end_observe,$tj_slope_post,$tc_end_powered,$ths_end_powered,$tcoil_end_powered,$classification" >> "$CSV_OUT"

        echo "OK $combo -> $classification (Tj_max=$tj_max)"
    else
        echo "FAIL $combo" | tee -a "$ERROR_LOG"
        echo "$vbus,$k,$ctol,$tamb,$fan,,,,,,,,,,failed" >> "$CSV_OUT"
    fi

    # Clean up large raw data files
    rm -f "$prefix"*.raw 2>/dev/null || true
}

# ------------------------------------------------------------------
# Main: iterate over all combinations
# ------------------------------------------------------------------
echo "=== Runaway Boundary Sweep ==="
echo "Total combinations: $TOTAL"
echo "Parallel workers: $PARALLEL"
echo "Results: $CSV_OUT"
echo "Errors:  $ERROR_LOG"
echo "Started: $TIMESTAMP"
echo ""

count=0
for vbus in "${VBUS_VALS[@]}"; do
    for k in "${K_VALS[@]}"; do
        for ctol in "${CTOL_VALS[@]}"; do
            for tamb in "${TAMB_VALS[@]}"; do
                for fan in "${FAN_VALS[@]}"; do
                    count=$((count + 1))
                    printf "[%3d/%3d] " "$count" "$TOTAL"
                    run_one "$vbus" "$k" "$ctol" "$tamb" "$fan"
                done
            done
        done
    done
done

echo ""
echo "=== Sweep Complete ==="
echo "Coverage: $count/$TOTAL points"
echo "Results in: $CSV_OUT"

# Count classifications
if ! $DRY_RUN; then
    echo ""
    echo "Classification summary:"
    cut -d',' -f15 "$CSV_OUT" | sort | uniq -c | sort -rn
fi
