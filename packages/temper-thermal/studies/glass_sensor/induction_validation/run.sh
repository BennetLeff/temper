#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
build_dir=$(mktemp -d /tmp/glass-induction-build.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
rustfmt --check main.rs
rustc --edition=2021 --test main.rs -o "$build_dir/tests"
"$build_dir/tests"
rustc --edition=2021 -O -D warnings main.rs -o "$build_dir/induction"
if [[ $# -eq 0 ]]; then
  "$build_dir/induction" sweep results
  for kind in paired endurance; do
    expected=$(sed -n 's/^raw_sha256=//p' "fixtures/$kind.meta")
    actual=$(shasum -a 256 "fixtures/$kind.csv" | cut -d ' ' -f1)
    [[ "$expected" == "$actual" ]] || { echo 'digest mismatch' >&2; exit 2; }
    "$build_dir/induction" "$kind" "fixtures/$kind.csv" "fixtures/$kind.meta" > "results/synthetic_$kind.txt"
  done
  if "$build_dir/induction" endurance fixtures/not_run.csv fixtures/not_run.meta >results/not_run.txt 2>&1; then
    echo 'ERROR: missing measurements were accepted' >&2; exit 1
  fi
elif [[ $# -eq 3 && ( "$1" == paired || "$1" == endurance ) ]]; then
  expected=$(sed -n 's/^raw_sha256=//p' "$3")
  actual=$(shasum -a 256 "$2" | cut -d ' ' -f1)
  [[ "$expected" == "$actual" ]] || { echo 'digest mismatch' >&2; exit 2; }
  "$build_dir/induction" "$1" "$2" "$3"
else
  echo 'Usage: run.sh [paired|endurance CSV META]' >&2; exit 2
fi
if [[ $# -eq 0 ]]; then
  rustfmt --check hotspots.rs
  rustc --edition=2021 -O -D warnings hotspots.rs -o "$build_dir/hotspots"
  "$build_dir/hotspots"
fi
if [[ $# -eq 0 ]]; then
  rustc --version > results/toolchain.txt
  shasum -a 256 main.rs hotspots.rs ../model.rs > results/source-sha256.txt
  rg -q 'NOT_RUN: missing required measurement touch_current' results/not_run.txt
fi
