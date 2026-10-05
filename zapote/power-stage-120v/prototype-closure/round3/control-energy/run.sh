#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
src="$root/zapote/power-stage-120v/prototype-closure/round3/control-energy"
if [ "$#" -ne 1 ]; then
  echo 'Usage: sh .../control-energy/run.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
out=$1
if [ -e "$out" ]; then
  echo 'Refusing to overwrite an existing output directory' >&2
  exit 2
fi
cd "$root"
shasum -a 256 -c "$src/source-inputs.sha256"
build=$(mktemp -d "${TMPDIR:-/tmp}/temper-control-energy.XXXXXX")
trap 'rm -rf "$build"' EXIT HUP INT TERM
rustc --edition=2021 --test "$src/study.rs" -o "$build/study-tests"
"$build/study-tests"
rustc --edition=2021 --test "$src/verify.rs" -o "$build/verify-tests"
"$build/verify-tests"
rustc --edition=2021 -O "$src/study.rs" -o "$build/study"
rustc --edition=2021 -O "$src/verify.rs" -o "$build/verify"
"$build/study" "$src" "$out"
"$build/verify" "$out"
