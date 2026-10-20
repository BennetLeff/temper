#!/bin/sh
set -eu
cd "$(dirname "$0")"
LCR_LOOP_BUILD=$(mktemp -d)
trap 'rm -rf "$LCR_LOOP_BUILD"' EXIT HUP INT TERM
rustc --edition=2021 -Awarnings -O loop_matrix.rs -o "$LCR_LOOP_BUILD/matrix"
rustc --edition=2021 -Awarnings -O internal_loops.rs -o "$LCR_LOOP_BUILD/internal"
rustc --edition=2021 -Awarnings -O invariance_check.rs -o "$LCR_LOOP_BUILD/invariance"
rustc --edition=2021 -Awarnings -O summarize.rs -o "$LCR_LOOP_BUILD/summary"
rustc --edition=2021 --test return_ratio_oracle.rs -o "$LCR_LOOP_BUILD/oracle-tests"
"$LCR_LOOP_BUILD/oracle-tests"
case "${1:---check}" in
  --check) LCR_REUSE=--analyze-only ;;
  --full) LCR_REUSE= ;;
  *) echo 'Usage: sh run.sh --check|--full' >&2; exit 2 ;;
esac
for LCR_MODE in grid corners lead leadwide fda invariance compact fixedgrid fixedcorners fixedlead fixedfda fixedinvariance; do
  "$LCR_LOOP_BUILD/matrix" "final_$LCR_MODE" $LCR_REUSE > "check-$LCR_MODE.log" 2>&1
done
"$LCR_LOOP_BUILD/internal" $LCR_REUSE > check-internal.log 2>&1
"$LCR_LOOP_BUILD/internal" --fixed-local $LCR_REUSE > check-internal-fixed.log 2>&1
"$LCR_LOOP_BUILD/invariance" > bridge-invariance-analysis.log 2>&1
"$LCR_LOOP_BUILD/invariance" --fixed-local > bridge-invariance-fixed.log 2>&1
"$LCR_LOOP_BUILD/summary" > final-summary-progress.log 2>&1
"$LCR_LOOP_BUILD/summary" --fixed-local > fixed-summary-progress.log 2>&1
echo 'Final loop arrays, operating points, invariance, crossing enumeration and expected negative lead control checked.'
