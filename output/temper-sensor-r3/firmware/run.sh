#!/bin/sh
# Rerun every sensor-r3 C1 firmware result (about 7 min on the Mac):
#   1. regenerate the golden vectors (firmware/test/*_vectors.h, vectors-summary.json)
#   2. build + run the seven C1 host test targets (firmware/test/CMakeLists.txt):
#      loop modules, D1, the contact-lost event, and the C1 runtime
#      (supervisor/conversion units, state machine + pan_control, MAX31865 C1
#      service through the SPI mock; TEMPER_PAN_CONTROL_C1)
#   3. build the C1 sources as a host library and run the C-in-the-loop co-sim
#      (cosim-results.json, gates bars B1-B5 in three gain modes, with the
#      runtime runaway supervisor in the loop)
#   3b. h_c steps (64 gated) and oil / water / crud cases through the same C
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

echo "== 1. golden vectors"
"$py" "$here/export_vectors.py" > /dev/null

echo "== 2. host tests"
cmake -S "$repo/firmware/test" -B "$tmp/build" > /dev/null
cmake --build "$tmp/build" -j 8 --target test_pan_temp_estimator_only \
    test_contact_check_only test_pan_temp_loop_only test_pan_contact_sm_only \
    test_c1_units_only test_c1_runtime_only test_c1_rtd_service_only > /dev/null
(cd "$tmp/build" && ctest --output-on-failure \
    -R '^(pan_temp_estimator|contact_check|pan_temp_loop|pan_contact_sm|c1_units|c1_runtime|c1_rtd_service)_tests$')

echo "== 3. co-simulation"
lib=$("$here/build_lib.sh" "$tmp/lib")
"$py" "$here/cosim.py" --lib "$lib" --out "$here/cosim-results.json" > "$tmp/cosim.log" \
    || { cat "$tmp/cosim.log"; exit 1; }
tail -1 "$tmp/cosim.log"

echo "== 3b. h_c steps and contaminated contact"
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
