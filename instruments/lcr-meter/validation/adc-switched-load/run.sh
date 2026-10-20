#!/bin/sh
set -eu
cd "$(dirname "$0")"
export NGSPICE="${NGSPICE:-ngspice}"
task_build_dir=$(mktemp -d "${TMPDIR:-/tmp}/temper-lcr-adc.XXXXXX")
trap 'rm -rf "$task_build_dir"' EXIT HUP INT TERM
rustc --edition=2021 -O generate.rs -o "$task_build_dir/generate"
rustc --edition=2021 -O analyze.rs -o "$task_build_dir/analyze"
"$task_build_dir/generate"
"$task_build_dir/analyze" > results.txt
mkdir -p half
cp .spiceinit half/.spiceinit
for tag in operating stress; do
    rm -f "half/$tag.dat"
    sed -e 's/tran 0.5n 15u 0 0.5n/tran 0.25n 15u 0 0.25n/' -e 's|../../sources/ti/models/|../../../sources/ti/models/|' "$tag.cir" > "half/$tag.cir"
    (cd half && "$NGSPICE" -b -o "$tag.log" "$tag.cir")
done
(cd half && "$task_build_dir/analyze" > results.txt)
