#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
board=${1:-"$here/../../cad/temper-lcr.kicad_pcb"}
python=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
work=$(mktemp -d /private/tmp/temper-lcr-feedback.XXXXXX)
trap 'rm -rf "$work"' EXIT HUP INT TERM
rm -f "$here/results.json"
"$python" "$here/export_native.py" "$board" > "$here/native-geometry.tsv"
rustc --edition=2021 -O "$here/measure.rs" -o "$work/measure"
"$work/measure" "$here/native-geometry.tsv" > "$work/results.json"
cp "$work/results.json" "$here/results.json"
cat "$here/results.json"
