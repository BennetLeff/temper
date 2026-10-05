#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Invalidate the old success receipt before any check can fail.
rm -f results/run-inputs.sha256
rustfmt --check main.rs
TEMPER_BUILD=$(mktemp -d /private/tmp/temper-r6-observer.XXXXXX)
trap 'rm -rf "$TEMPER_BUILD"' EXIT
rustc --edition=2021 -O -D warnings main.rs -o "$TEMPER_BUILD/study"
rustc --edition=2021 --test -O -D warnings main.rs -o "$TEMPER_BUILD/tests"
mkdir -p results
"$TEMPER_BUILD/tests" > "$TEMPER_BUILD/tests.txt"
cp "$TEMPER_BUILD/tests.txt" results/tests.txt
clippy-driver --edition=2021 -O -D warnings main.rs -o "$TEMPER_BUILD/clippy"
"$TEMPER_BUILD/study"
shasum -a 256 main.rs run.sh results/comparison.csv results/plant_parameters.csv > results/run-inputs.sha256
