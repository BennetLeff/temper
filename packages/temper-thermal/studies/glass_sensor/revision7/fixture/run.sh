#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f results/run-inputs.sha256
work=$(mktemp -d "${TMPDIR:-/tmp}/temper-r7-fixture.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
mkdir -p results
rustfmt --check main.rs
rustc --edition=2021 -D warnings --test main.rs -o "$work/tests"
"$work/tests" > "$work/test-output.txt"
awk '{ lines[NR]=$0 } END { n=NR; while(n>0 && lines[n]=="") n--; for(i=1;i<=n;i++) print lines[i] }' "$work/test-output.txt" > results/tests.txt
rustc --edition=2021 -D warnings main.rs -o "$work/model"
clippy-driver --edition=2021 -D warnings main.rs -o "$work/lint-model"
"$work/model" results
shasum -a 256 main.rs run.sh results/pressure_bounds.csv results/metrology_capability.csv results/combined_budget.csv results/summary.txt results/tests.txt > "$work/receipt"
mv "$work/receipt" results/run-inputs.sha256
