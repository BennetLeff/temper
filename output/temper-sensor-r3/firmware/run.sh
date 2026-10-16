#!/bin/sh
# Rerun every sensor-r3 C1 firmware result (about 7 min on the Mac):
#   0. rim NTC table and channel numbers (rim_ntc.py -> rim-ntc.json and
#      firmware/components/sensors/rim_ntc_table.h) and the CR-7 threshold
#      words (cr7_thresholds.py -> cr7-thresholds.json); both gate
#   1. regenerate the golden vectors (firmware/test/*_vectors.h, vectors-summary.json)
#   2. build + run the eight C1 host test targets (firmware/test/CMakeLists.txt):
#      loop modules, D1, the contact-lost event, the C1 runtime
#      (supervisor/conversion units, state machine + pan_control, MAX31865 C1
#      service through the SPI mock; TEMPER_PAN_CONTROL_C1), the rim NTC
#      driver, and the SIL fault-injection suite in both configurations
#      (legacy and C1) with its coverage gate (DECISIONS.md D-SIL)
#   3. build the C1 sources as a host library and run the C-in-the-loop co-sim
#      (cosim-results.json, gates bars B1-B5 in three gain modes, with the
#      runtime runaway supervisor in the loop)
#   3b. rim NTC in the loop: the cross-check against a rim truth signal
#      (xcheck-cosim.json, gates benign runs; DECISIONS.md D-RIM)
#   3c. h_c steps (64 gated) and oil / water / crud cases through the same C
#      loop (../robustness/hc_cosim.py --after-only: hc-cosim.json, gates
#      robustness/DECISIONS.md R-HS / R-CT; the "before" baseline rows are
#      kept from the last full run)
#   4. D1 seed-to-seed Monte Carlo (b5-montecarlo.json, gates safety only)
#   5. runaway checks: legacy vs C1 rules on false-trip and fault scenarios
#      (runaway-checks.json, gates the C1 rules; DECISIONS.md D-RUN)
#   6. plant-gain sensitivity (sensitivity.json, reported only)
# Exits non-zero if any step fails. Build products go to a temp dir.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo="$here/../../.."
export PYTHONDONTWRITEBYTECODE=1
py=${PYTHON:-python3}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "== 0. rim NTC table, CR-7 threshold words"
"$py" "$here/rim_ntc.py" > "$tmp/rim.log" || { cat "$tmp/rim.log"; exit 1; }
tail -1 "$tmp/rim.log"
"$py" "$here/cr7_thresholds.py" > "$tmp/cr7.log" || { cat "$tmp/cr7.log"; exit 1; }
tail -1 "$tmp/cr7.log"

echo "== 1. golden vectors"
"$py" "$here/export_vectors.py" > /dev/null

echo "== 2. host tests"
cmake -S "$repo/firmware/test" -B "$tmp/build" > /dev/null
cmake --build "$tmp/build" -j 8 --target test_pan_temp_estimator_only \
    test_contact_check_only test_pan_temp_loop_only test_pan_contact_sm_only \
    test_c1_units_only test_c1_runtime_only test_c1_rtd_service_only test_c1_rim_ntc_only \
    test_sil_fault_injection test_sil_fault_injection_c1 > /dev/null
(cd "$tmp/build" && ctest --output-on-failure \
    -R '^(pan_temp_estimator|contact_check|pan_temp_loop|pan_contact_sm|c1_units|c1_runtime|c1_rtd_service|c1_rim_ntc|sil_fault)_tests(_c1)?$')
"$py" "$repo/firmware/test/test_sil_coverage.py" --gate > "$tmp/cov.log" 2>&1 \
    || { cat "$tmp/cov.log"; exit 1; }
grep '^SUMMARY' "$tmp/cov.log"

echo "== 3. co-simulation"
lib=$("$here/build_lib.sh" "$tmp/lib")
"$py" "$here/cosim.py" --lib "$lib" --out "$here/cosim-results.json" > "$tmp/cosim.log" \
    || { cat "$tmp/cosim.log"; exit 1; }
tail -1 "$tmp/cosim.log"

echo "== 3b. rim NTC cross-check co-simulation"
"$py" "$here/xcheck_cosim.py" --lib "$lib" --out "$here/xcheck-cosim.json" > "$tmp/xc.log" \
    || { cat "$tmp/xc.log"; exit 1; }
tail -1 "$tmp/xc.log"
echo "== 3c. h_c steps and contaminated contact"
"$py" "$here/../robustness/hc_cosim.py" --lib "$lib" --after-only > "$tmp/hc.log" \
    || { grep -E '^(BARS|FAIL)' "$tmp/hc.log"; exit 1; }
tail -1 "$tmp/hc.log"

echo "== 4. D1 Monte Carlo"
"$py" "$here/b5_montecarlo.py" --lib "$lib" --out "$here/b5-montecarlo.json" > "$tmp/mc.log" \
    || { cat "$tmp/mc.log"; exit 1; }
grep '^==' "$tmp/mc.log"

echo "== 5. runaway checks"
"$py" "$here/runaway_checks.py" --lib "$lib" --out "$here/runaway-checks.json" > "$tmp/rc.log" \
    || { cat "$tmp/rc.log"; exit 1; }
grep -E '^(legacy false trips|C1 false trips|CHECKS|ALL RUNAWAY)' "$tmp/rc.log"

echo "== 6. plant-gain sensitivity (reported, not gated)"
"$py" "$here/sensitivity.py" --lib "$lib" --out "$here/sensitivity.json" > /dev/null
echo "ALL C1 FIRMWARE CHECKS PASS"
