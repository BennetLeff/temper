#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
cd "$repo"
src=zapote/power-stage-120v/prototype-closure/round5/protection
out=output/temper-prototype-closure/round5/protection
mkdir -p "$out"
printf '%s\n' '{"status":"INCOMPLETE"}' > "$out/replay.json"
scratch=$(mktemp -d /private/tmp/temper-r5-protection-replay.XXXXXX)
rustc --edition=2021 --test "$src/coordination.rs" -o "$scratch/tests"
"$scratch/tests" > "$out/calculation-tests.txt"
rustc --edition=2021 "$src/coordination.rs" -o "$scratch/calc"
"$scratch/calc" "$out"
"${CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}" "$src/build_hardware.py"
python3 "$src/freeze_evidence.py"
