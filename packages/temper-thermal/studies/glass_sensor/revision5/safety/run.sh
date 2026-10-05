#!/bin/sh
set -eu
cd "$(dirname "$0")"
out=$(mktemp -d /private/tmp/temper-r5-safety.XXXXXX)
trap 'rm -f "$out/tests" "$out/model" "$out/lint" "$out/tests.raw"; rmdir "$out"' EXIT
rustfmt --check model.rs
rustc --edition=2021 -D warnings --test model.rs -o "$out/tests"
mkdir -p results
"$out/tests" > "$out/tests.raw"
awk 'NF{print}' "$out/tests.raw" > results/tests.txt
rustc --edition=2021 -D warnings model.rs -o "$out/model"
"$out/model" results > results/summary.txt
clippy-driver --edition=2021 -D warnings model.rs -o "$out/lint"
