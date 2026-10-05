#!/bin/sh
set -eu
cd "$(dirname "$0")"
shasum -a 256 -c inputs.sha256
rustfmt --check main.rs
TEMP_DIR=$(mktemp -d /private/tmp/temper-r5-thermal.XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT
rustc --edition=2021 -O -D warnings main.rs -o "$TEMP_DIR/study"
rustc --edition=2021 --test -O -D warnings main.rs -o "$TEMP_DIR/tests"
mkdir -p results
"$TEMP_DIR/tests" > "$TEMP_DIR/tests.log"
awk 'NF{print}' "$TEMP_DIR/tests.log" > results/tests.txt
clippy-driver --edition=2021 -O -D warnings main.rs -o "$TEMP_DIR/clippy"
"$TEMP_DIR/study"
shasum -a 256 ../../model.rs main.rs ../mechanical/thermal_geometry.csv results/comparison.csv > results/run-inputs.sha256
