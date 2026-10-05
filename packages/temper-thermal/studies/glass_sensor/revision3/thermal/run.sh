#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
shasum -a 256 -c inputs.sha256
build_dir=$(mktemp -d /tmp/temper-r3-model.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
mkdir -p results
rustfmt --check main.rs
rustc --edition=2021 -D warnings --test main.rs -o "$build_dir/tests"
"$build_dir/tests" > "$build_dir/tests.log"
awk 'NF {last=NR} {lines[NR]=$0} END {for(i=1;i<=last;i++) print lines[i]}' "$build_dir/tests.log" > results/tests.txt
rustc --edition=2021 -D warnings -O main.rs -o "$build_dir/model"
"$build_dir/model"
cat results/tests.txt
