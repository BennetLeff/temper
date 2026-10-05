#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bin_dir=$(mktemp -d /private/tmp/temper-r5-validation.XXXXXX)
trap 'rm -rf "$bin_dir"' EXIT
(
  cd ../thermal
  for required_input in ../../model.rs main.rs ../mechanical/thermal_geometry.csv results/comparison.csv; do
    awk -v required="$required_input" '$2 == required {count++} END {exit(count != 1)}' results/run-inputs.sha256
  done
  shasum -a 256 -c results/run-inputs.sha256
)
rustfmt --check main.rs
rustc --edition=2021 -D warnings --test main.rs -o "$bin_dir/tests"
mkdir -p results
"$bin_dir/tests" | awk 'NF {print}' > results/tests.txt
rustc --edition=2021 -D warnings -O main.rs -o "$bin_dir/analysis"
"$bin_dir/analysis" ../mechanical/thermal_geometry.csv results ../thermal/results/comparison.csv
shasum -a 256 main.rs run.sh ../mechanical/thermal_geometry.csv ../thermal/results/comparison.csv gaps.json templates/*.csv > results/inputs.sha256
