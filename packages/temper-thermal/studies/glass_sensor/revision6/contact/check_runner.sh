#!/bin/sh
set -eu
cd "$(dirname "$0")"
UNIT=$(pwd)
STUDY_ROOT=${TEMPER_GLASS_STUDY_ROOT:-$(cd ../.. && pwd)}
CHECK=$(mktemp -d /private/tmp/temper-r6-contact-negative.XXXXXX)
trap 'rm -rf "$CHECK"' EXIT
mkdir -p "$CHECK/source/revision5/thermal" "$CHECK/source/revision5/mechanical" "$CHECK/bad_pin" "$CHECK/bad_test"
cp "$STUDY_ROOT/model.rs" "$CHECK/source/model.rs"
cp "$STUDY_ROOT/revision5/thermal/main.rs" "$CHECK/source/revision5/thermal/main.rs"
cp "$STUDY_ROOT/revision5/mechanical/thermal_geometry.csv" "$CHECK/source/revision5/mechanical/thermal_geometry.csv"
cp adapter.rs run.sh inputs.sha256 "$CHECK/bad_pin/"
printf '\n// deliberate hash corruption\n' >> "$CHECK/source/model.rs"
if TEMPER_GLASS_STUDY_ROOT="$CHECK/source" "$CHECK/bad_pin/run.sh" > "$CHECK/pin.log" 2>&1; then
    echo 'ERROR: bad pin accepted'; exit 1
else
    PIN_STATUS=$?
fi
[ ! -e "$CHECK/bad_pin/results/comparison.csv" ]
[ ! -e "$CHECK/bad_pin/results/run-inputs.sha256" ]
cp adapter.rs run.sh inputs.sha256 "$CHECK/bad_test/"
cat >> "$CHECK/bad_test/adapter.rs" <<'RS'
#[cfg(test)]
mod injected_failure {
    #[test]
    fn deliberately_failing_test() { panic!("R6 runner failure propagation probe"); }
}
RS
rustfmt "$CHECK/bad_test/adapter.rs"
if TEMPER_GLASS_STUDY_ROOT="$STUDY_ROOT" "$CHECK/bad_test/run.sh" > "$CHECK/test.log" 2>&1; then
    echo 'ERROR: failing test accepted'; exit 1
else
    TEST_STATUS=$?
fi
[ "$TEST_STATUS" -eq 101 ]
[ ! -e "$CHECK/bad_test/results/comparison.csv" ]
[ ! -e "$CHECK/bad_test/results/run-inputs.sha256" ]
mkdir -p "$UNIT/results"
printf 'probe,exit_code,new_physics_csv,success_receipt\nbad_source_hash,%s,false,false\ninjected_test_failure,%s,false,false\n' "$PIN_STATUS" "$TEST_STATUS" > "$UNIT/results/runner-negative.csv"
cat "$UNIT/results/runner-negative.csv"
