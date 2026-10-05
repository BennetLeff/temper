#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-$(cd ../.. && pwd)}
GEOMETRY=${TEMPER_R7_GEOMETRY:-$UNIT/../mechanical/thermal_geometry.csv}
CHECK=$(mktemp -d /private/tmp/temper-r7-negative.XXXXXX)
trap 'rm -rf "$CHECK"' EXIT
mkdir -p "$CHECK/bad_pin/results" "$CHECK/bad_geometry/results" "$CHECK/bad_test/results"
for CASE in bad_pin bad_geometry bad_test; do
    cp adapter.rs run.sh inputs.sha256 geometry.sha256 "$CHECK/$CASE/"
    printf 'stale prior success\n' > "$CHECK/$CASE/results/run-inputs.sha256"
done
# A broken source pin must invalidate a receipt before any physics can run.
printf '0000000000000000000000000000000000000000000000000000000000000000  model.rs\n' > "$CHECK/bad_pin/inputs.sha256"
if TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" TEMPER_R7_GEOMETRY="$GEOMETRY" "$CHECK/bad_pin/run.sh" > "$CHECK/pin.log" 2>&1; then
    echo 'ERROR: invalid source pin passed'; exit 1
else PIN_STATUS=$?; fi
[ ! -e "$CHECK/bad_pin/results/run-inputs.sha256" ]
[ ! -e "$CHECK/bad_pin/results/comparison.csv" ]
printf '0000000000000000000000000000000000000000000000000000000000000000\n' > "$CHECK/bad_geometry/geometry.sha256"
if TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" TEMPER_R7_GEOMETRY="$GEOMETRY" "$CHECK/bad_geometry/run.sh" > "$CHECK/geometry.log" 2>&1; then
    echo 'ERROR: invalid geometry pin passed'; exit 1
else GEOMETRY_STATUS=$?; fi
[ ! -e "$CHECK/bad_geometry/results/run-inputs.sha256" ]
[ ! -e "$CHECK/bad_geometry/results/comparison.csv" ]
cat >> "$CHECK/bad_test/adapter.rs" <<'RS'
#[cfg(test)]
mod injected_failure {
    #[test]
    fn deliberately_failing_test() { panic!("R7 runner test-failure propagation"); }
}
RS
rustfmt "$CHECK/bad_test/adapter.rs"
if TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" TEMPER_R7_GEOMETRY="$GEOMETRY" "$CHECK/bad_test/run.sh" > "$CHECK/test.log" 2>&1; then
    echo 'ERROR: failing test passed'; exit 1
else TEST_STATUS=$?; fi
[ "$TEST_STATUS" -eq 101 ]
[ ! -e "$CHECK/bad_test/results/run-inputs.sha256" ]
[ ! -e "$CHECK/bad_test/results/comparison.csv" ]
mkdir -p results
printf 'probe,exit_code,new_physics_csv,stale_success_receipt_removed\nbad_source_hash,%s,false,true\nbad_geometry_hash,%s,false,true\ninjected_test_failure,%s,false,true\n' "$PIN_STATUS" "$GEOMETRY_STATUS" "$TEST_STATUS" > results/runner-negative.csv
cat results/runner-negative.csv
