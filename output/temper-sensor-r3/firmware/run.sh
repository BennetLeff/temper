#!/bin/sh
# Rerun every sensor-r3 C1 firmware result (about 25 min on the Mac):
#   0. the MAX31865 manual fault-detection timing on the CR-1 board
#      (fault_cycle.py -> fault-cycle.json and firmware/components/temper_hal/
#      mock/mock_max31865_afe.h; gates rtd_service.h; DECISIONS.md D-FCYC), the
#      v3v3 rail reading's error budget (rail_adc.py -> rail-adc.json; gates
#      rail_adc.h; D-RAIL), rim NTC table and channel numbers (rim_ntc.py ->
#      rim-ntc.json and firmware/components/sensors/rim_ntc_table.h), the
#      heatsink NTC table, channel and cold-soak budgets, rail unknown and
#      measured (hs_ntc.py -> hs-ntc.json and
#      firmware/components/sensors/hs_ntc_table.h; gates pan_cold_soak.h) and
#      the CR-7 threshold words (cr7_thresholds.py -> cr7-thresholds.json); all gate
#   1. regenerate the golden vectors (firmware/test/*_vectors.h, vectors-summary.json)
#   2. build + run the C1 host test targets (firmware/test/CMakeLists.txt):
#      loop modules, D1, the contact-lost event, the C1 runtime
#      (supervisor/conversion/current-sense/leak units, state machine +
#      pan_control with and without the input-current sense, MAX31865 C1
#      service through the SPI mock; TEMPER_PAN_CONTROL_C1), the rim and
#      heatsink NTC drivers, and the SIL fault-injection suite in both configurations
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
#   3d. element-parallel Pt100 leakage against the leak check and the
#      setpoint-relative rim limit (leak-checks.json, gates benign runs and the
#      recorded status of the 300 degC bar; DECISIONS.md D-LEAK, D-RIMLIM)
#   3e. the rim limit's glass envelope, tolerance table and trade-off curve
#      (rim-limit.json: margin vs coverage vs false latches, the CR-5 band;
#      gates the firmware constants and the chosen variant's 0 false latches;
#      DECISIONS.md D-RIMLIM), and candidates B/C (leak-alternatives.json,
#      reported only)
#   3f. the cold-soak leakage check through the C (heatsink driver, Pt100
#      conversion, pan_cold_soak.c), rail unknown and rail measured: threshold
#      cross-checks, benign cold starts (gated: 0 latches in both), hazardous
#      leaks caught before heating (cold-soak.json; DECISIONS.md D-SOAK, D-RAIL)
#   4. D1 seed-to-seed Monte Carlo (b5-montecarlo.json, gates safety only)
#   4b. task F1: D1 nuisance cuts on 132 rim-limit stress benign cases per cap
#      (250 / 230 degC; d1-nuisance.py --check; LOST ratchets 2 / 1 because
#      no safe correction was established; full decision and off-time evidence)
#   5. runaway checks: legacy vs C1 rules on false-trip and fault scenarios,
#      with the current-sense checks (runaway-checks.json, gates the C1 rules;
#      DECISIONS.md D-RUN, D-ISENSE, D-OPEN)
#   5b. sensor-failure codes against IEC 60751 and the plant
#      (sensor-fail-codes.json, gates rtd_convert.h; DECISIONS.md D-OPEN)
#   5c. the element-parallel leak barrier (../leak-barrier/leak_barrier.py
#      --check: insulation margin, production-test detection limits,
#      qualification sample plan; SPEC.md)
#   5d. maximum-setpoint cap vs firmware leak coverage under the peak hazard
#      rule (../leak-barrier/setpoint_cap.py --check --caps 250,200: the 250 degC
#      control against leak-checks / rim-limit / cold-soak, plus the 200 degC cap;
#      about 10 min). The full check, every cap (about 30 min), is manual:
#      python3 ../leak-barrier/setpoint_cap.py --check   (NOTES-t2.md)
#   6. plant-gain sensitivity (sensitivity.json, reported only)
# Exits non-zero if any step fails. Build products go to a temp dir.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo="$here/../../.."
export PYTHONDONTWRITEBYTECODE=1
py=${PYTHON:-python3}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "== 0. fault-cycle timing, rail budget, rim and heatsink NTC tables, CR-7 threshold words"
"$py" "$here/fault_cycle.py" > "$tmp/fc.log" || { cat "$tmp/fc.log"; exit 1; }
tail -1 "$tmp/fc.log"
"$py" "$here/rail_adc.py" > "$tmp/rail.log" || { cat "$tmp/rail.log"; exit 1; }
tail -1 "$tmp/rail.log"
"$py" "$here/rim_ntc.py" > "$tmp/rim.log" || { cat "$tmp/rim.log"; exit 1; }
tail -1 "$tmp/rim.log"
"$py" "$here/hs_ntc.py" > "$tmp/hs.log" || { cat "$tmp/hs.log"; exit 1; }
tail -1 "$tmp/hs.log"
"$py" "$here/cr7_thresholds.py" > "$tmp/cr7.log" || { cat "$tmp/cr7.log"; exit 1; }
tail -1 "$tmp/cr7.log"

echo "== 1. golden vectors"
"$py" "$here/export_vectors.py" > /dev/null

echo "== 2. host tests"
cmake -S "$repo/firmware/test" -B "$tmp/build" > /dev/null
cmake --build "$tmp/build" -j 8 --target test_pan_temp_estimator_only \
    test_contact_check_only test_pan_temp_loop_only test_pan_contact_sm_only \
    test_c1_units_only test_c1_runtime_only test_c1_runtime_isense_only test_c1_rtd_service_only \
    test_c1_rim_ntc_only test_c1_hs_ntc_only \
    test_sil_fault_injection test_sil_fault_injection_c1 > /dev/null
(cd "$tmp/build" && ctest --output-on-failure \
    -R '^(pan_temp_estimator|contact_check|pan_temp_loop|pan_contact_sm|c1_units|c1_runtime|c1_runtime_isense|c1_rtd_service|c1_rim_ntc|c1_hs_ntc|sil_fault)_tests(_c1)?$')
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

echo "== 3d. Pt100 leakage"
"$py" "$here/leak_checks.py" --lib "$lib" --out "$here/leak-checks.json" > "$tmp/leak.log" \
    || { cat "$tmp/leak.log"; exit 1; }
grep -E '^(   hazardous|hazardous|never|requirements|BAR|benign|LEAK)' "$tmp/leak.log"

echo "== 3e. rim limit study; energy and cold-soak alternatives"
"$py" "$here/rim_limit.py" --lib "$lib" --out "$here/rim-limit.json" > "$tmp/rl.log" \
    || { grep -vE '^m ' "$tmp/rl.log"; exit 1; }
grep -E '^(baseline|chosen|GATE|RIM LIMIT)' "$tmp/rl.log"
"$py" "$here/leak_alternatives.py" > /dev/null

echo "== 3f. cold-soak leakage check"
"$py" "$here/cold_soak.py" --lib "$lib" --out "$here/cold-soak.json" > "$tmp/cs.log" \
    || { cat "$tmp/cs.log"; exit 1; }
grep -E '^(threshold|benign|baseline|PASS|FAIL|ALL COLD)' "$tmp/cs.log"

echo "== 4. D1 Monte Carlo"
"$py" "$here/b5_montecarlo.py" --lib "$lib" --out "$here/b5-montecarlo.json" > "$tmp/mc.log" \
    || { cat "$tmp/mc.log"; exit 1; }
grep '^==' "$tmp/mc.log"

# Task F1 uses its own fresh build for portable exact evidence verification.
echo "== 4b. D1 nuisance cuts on stressed benign cooking (F1)"
"$py" "$here/d1_nuisance.py" --check > "$tmp/d1n.log" 2>&1 \
    || { cat "$tmp/d1n.log"; exit 1; }
grep -E '^(D1 cap=|D1 nuisance evidence:|D1 NUISANCE)' "$tmp/d1n.log"

echo "== 5. runaway checks"
"$py" "$here/runaway_checks.py" --lib "$lib" --out "$here/runaway-checks.json" > "$tmp/rc.log" \
    || { cat "$tmp/rc.log"; exit 1; }
grep -E '^(legacy false trips|C1 false trips|current sense|CHECKS|ALL RUNAWAY)' "$tmp/rc.log"

echo "== 5b. sensor-failure codes"
"$py" "$here/sensor_fail_codes.py" > "$tmp/sfc.log" || { cat "$tmp/sfc.log"; exit 1; }
tail -1 "$tmp/sfc.log"

echo "== 5c. leak barrier: insulation, production test, qualification (../leak-barrier, T1)"
"$py" "$here/../leak-barrier/leak_barrier.py" --check > "$tmp/lb.log" 2>&1 \
    || { cat "$tmp/lb.log"; exit 1; }
tail -1 "$tmp/lb.log"

echo "== 5d. setpoint cap vs leak coverage, caps 250 and 200 (../leak-barrier, T2)"
"$py" "$here/../leak-barrier/setpoint_cap.py" --check --caps 250,200 > "$tmp/sc.log" 2>&1 \
    || { tail -20 "$tmp/sc.log"; exit 1; }
tail -1 "$tmp/sc.log"

echo "== 6. plant-gain sensitivity (reported, not gated)"
"$py" "$here/sensitivity.py" --lib "$lib" --out "$here/sensitivity.json" > /dev/null
echo "ALL C1 FIRMWARE CHECKS PASS"
