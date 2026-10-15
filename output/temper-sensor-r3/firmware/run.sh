#!/bin/sh
# Rerun every sensor-r3 C1 firmware result (about 4 min on the Mac):
#   1. regenerate the golden vectors (firmware/test/*_vectors.h, vectors-summary.json)
#   2. build + run the four C1 host test targets (firmware/test/CMakeLists.txt)
#   3. build the C1 sources as a host library and run the C-in-the-loop co-sim
#      (cosim-results.json, gates bars B1-B5 in three gain modes)
#   4. D1 seed-to-seed Monte Carlo (b5-montecarlo.json, gates safety only)
#   5. plant-gain sensitivity (sensitivity.json, reported only)
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
    test_contact_check_only test_pan_temp_loop_only test_pan_contact_sm_only > /dev/null
(cd "$tmp/build" && ctest --output-on-failure \
    -R '^(pan_temp_estimator|contact_check|pan_temp_loop|pan_contact_sm)_tests$')

echo "== 3. co-simulation"
lib=$("$here/build_lib.sh" "$tmp/lib")
"$py" "$here/cosim.py" --lib "$lib" --out "$here/cosim-results.json" > "$tmp/cosim.log" \
    || { cat "$tmp/cosim.log"; exit 1; }
tail -1 "$tmp/cosim.log"

echo "== 4. D1 Monte Carlo"
"$py" "$here/b5_montecarlo.py" --lib "$lib" --out "$here/b5-montecarlo.json" > "$tmp/mc.log" \
    || { cat "$tmp/mc.log"; exit 1; }
grep '^==' "$tmp/mc.log"

echo "== 5. plant-gain sensitivity (reported, not gated)"
"$py" "$here/sensitivity.py" --lib "$lib" --out "$here/sensitivity.json" > /dev/null
echo "ALL C1 FIRMWARE CHECKS PASS"
