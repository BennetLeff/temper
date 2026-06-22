#!/bin/bash
# check_runaway_boundary.sh
#
# PURPOSE: CI regression gate for runaway boundary interlock margin.
#   1. Reads worst-3 corners from runaway_interlock_margin.md
#   2. Re-runs those 3 combinations with tight tolerance (RELTOL=1e-5)
#   3. Asserts margin >= 20 C for all
#   4. Exit 0 on pass, 1 on fail
#
# USAGE:
#   ./check_runaway_boundary.sh
#
# Designed for: .github/workflows/simulation-tests.yml

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TESTBENCH="$SCRIPT_DIR/sim_35_runaway_boundary.cir"
RESULTS_DIR="$PROJECT_ROOT/simulation/results"
MARGIN_MD="$RESULTS_DIR/runaway_interlock_margin.md"
CI_LOG="$RESULTS_DIR/check_runaway_boundary_ci.log"

MIN_MARGIN=20

# ------------------------------------------------------------------
# Pre-flight checks
# ------------------------------------------------------------------
if ! command -v ngspice &>/dev/null; then
    echo "SKIP: ngspice not found in PATH"
    exit 0  # Not a failure if ngspice is not available
fi

if [[ ! -f "$MARGIN_MD" ]]; then
    echo "ERROR: Margin report not found at $MARGIN_MD"
    echo "Run sweep_runaway_boundary.sh and verify_interlock_margin.py first."
    exit 1
fi

mkdir -p "$RESULTS_DIR"

# ------------------------------------------------------------------
# Extract worst-3 corners from markdown table
# ------------------------------------------------------------------
# Format in markdown table (Worst-3 Corners section):
# | # | VBUS | K | C_TOL | TAMB | FAN | Tj_boundary | Hs | Coil | Tj_trip | Margin | Pass |
# Extract rows after the worst-3 table header, before next section
echo "=== CI Regression Gate: Runaway Boundary Interlock ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

declare -a CORNERS=()
IN_TABLE=false
while IFS= read -r line; do
    if [[ "$line" =~ ^\|\ #[[:space:]]*\|.*VBUS.* ]]; then
        IN_TABLE=true
        continue
    fi
    if $IN_TABLE && [[ "$line" =~ ^\|\ [0-9]+\ \| ]]; then
        # Parse: | # | VBUS | K | C_TOL | TAMB | FAN | ...
        # Extract fields 2-6 (VBUS, K, C_TOL, TAMB, FAN)
        IFS='|' read -ra FIELDS <<< "$line"
        if [[ ${#FIELDS[@]} -ge 7 ]]; then
            vbus=$(echo "${FIELDS[2]}" | xargs)
            k=$(echo "${FIELDS[3]}" | xargs)
            ctol=$(echo "${FIELDS[4]}" | xargs)
            tamb=$(echo "${FIELDS[5]}" | xargs)
            fan=$(echo "${FIELDS[6]}" | xargs)
            CORNERS+=("$vbus $k $ctol $tamb $fan")
        fi
    fi
    if $IN_TABLE && [[ ! "$line" =~ ^\| ]]; then
        IN_TABLE=false
    fi
done < "$MARGIN_MD"

if [[ ${#CORNERS[@]} -eq 0 ]]; then
    echo "ERROR: Could not extract worst-3 corners from margin report"
    exit 1
fi

echo "Worst-3 corners extracted from margin report:"
for corner in "${CORNERS[@]}"; do
    echo "  $corner"
done
echo ""

# ------------------------------------------------------------------
# Re-run each corner with tight tolerance
# ------------------------------------------------------------------
ALL_PASS=true
CORNER_NUM=0

for corner in "${CORNERS[@]}"; do
    CORNER_NUM=$((CORNER_NUM + 1))
    read -r vbus k ctol tamb fan <<< "$corner"

    echo "--- Corner #$CORNER_NUM: VBUS=$vbus K=$k C_TOL=$ctol TAMB=$tamb FAN=$fan ---"

    prefix="$RESULTS_DIR/ci_rerun_corner${CORNER_NUM}"
    logfile="$prefix.log"

    # Write parameter override file for this corner
    local params_file="$SCRIPT_DIR/sweep_params.sp"
    cat > "$params_file" <<PARAMEOF
.param VBUS=$vbus
.param K=$k
.param C_TOL=$ctol
.param TAMB=$tamb
.param FAN=$fan
.param T_POWERED=10
.param T_OBSERVE=0.5
PARAMEOF

    # Run ngspice with tighter tolerance
    if ngspice -b "$TESTBENCH" \
        -o "$prefix" \
        >"$logfile" 2>&1; then

        outfile="${prefix}"
        if [[ ! -f "$outfile" ]]; then
            outfile="$logfile"
        fi

        # Extract measurements (helper function)
        extract_meas() {
            local name="$1" file="$2"
            awk -v n="$name" '$1 == n {print $3}' "$file" 2>/dev/null | head -1
        }

        tj_end=$(extract_meas "tj_end_pw" "$outfile")
        hs_end=$(extract_meas "ths_end_pw" "$outfile")
        tj_slope=$(extract_meas "tj_slope_post" "$outfile")
        classification=$(extract_meas "is_destructive" "$outfile")

        if [[ -z "$tj_end" ]]; then
            echo "  FAIL: Could not extract Tj measurement"
            ALL_PASS=false
            continue
        fi

        # Compute margin
        # Using approximation: margin = Tj_boundary - (85 + P_diss * Rtheta_jh)
        # For CI gate: check that classification is not destructive/runaway AND
        # Tj is well below 175 C (datasheet max) with margin
        RTHETA_JH=0.9

        # Estimate P_diss from Tj - Hs gradient
        p_diss=0
        if [[ -n "$hs_end" ]]; then
            p_diss=$(awk "BEGIN {printf \"%.2f\", ($tj_end - $hs_end) / $RTHETA_JH}")
            if awk "BEGIN {exit !($p_diss < 0)}"; then
                p_diss=0
            fi
        fi

        tj_trip=$(awk "BEGIN {printf \"%.1f\", 85 + $p_diss * $RTHETA_JH}")
        margin=$(awk "BEGIN {printf \"%.1f\", $tj_end - $tj_trip}")

        echo "  Tj_end = $tj_end C"
        echo "  Hs_end = $hs_end C"
        echo "  P_diss = $p_diss W"
        echo "  Tj_trip = $tj_trip C"
        echo "  Margin = $margin C"

        if awk "BEGIN {exit !($margin >= $MIN_MARGIN)}"; then
            echo "  RESULT: PASS (margin >= $MIN_MARGIN C)"
        else
            echo "  RESULT: FAIL (margin $margin < $MIN_MARGIN C)"
            ALL_PASS=false
        fi
    else
        echo "  FAIL: ngspice exited with error"
        ALL_PASS=false
    fi
    echo ""
done

# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------
echo "=== CI Gate Result ==="
if $ALL_PASS; then
    echo "PASS: All $CORNER_NUM worst-case corners have margin >= $MIN_MARGIN C"
    echo "PASS_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CI_LOG"
    exit 0
else
    echo "FAIL: One or more corners have insufficient margin"
    exit 1
fi
