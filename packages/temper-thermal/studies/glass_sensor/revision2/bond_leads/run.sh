#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bin_dir=$(mktemp -d /tmp/temper-bond-leads.XXXXXX)
trap 'rm -rf "$bin_dir"' EXIT
mkdir -p results
rustfmt --check model.rs
rustc --edition 2021 -D warnings --test model.rs -o "$bin_dir/tests"
"$bin_dir/tests" > results/tests.txt
rustc --edition 2021 -D warnings -O model.rs -o "$bin_dir/model"
"$bin_dir/model"
{
  printf 'status=SIMULATION_AND_TEST_PREPARATION\nphysical_results=NOT_RUN\nbase_commit=470ac33eced8a46791eff201efc2a8a57d0ee0c9\n'
  rustc --version
  shasum -a 256 model.rs model-inputs.json BOM.csv SOURCES.md
} > results/provenance.txt
cat results/tests.txt
