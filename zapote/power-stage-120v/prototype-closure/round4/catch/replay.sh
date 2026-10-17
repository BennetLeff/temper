#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
cd "$repo"
src=zapote/power-stage-120v/prototype-closure/round4/catch
out=output/temper-prototype-closure/round4/catch
kicad=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
pcb_python=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
cad_python=/private/tmp/temper-center-sensor-env/bin/python
scratch=$(mktemp -d /private/tmp/temper-catch-replay.XXXXXX)
mkdir -p "$out"
printf '%s\n' '{"status":"INCOMPLETE"}' > "$out/replay.json"
"$pcb_python" "$src/build_bleed.py"
"$kicad" sch erc --format json --output "$out/erc.json" "$src/native/catch-bleed.kicad_sch"
"$kicad" sch export netlist --format kicadxml --output "$out/bleed-netlist.xml" "$src/native/catch-bleed.kicad_sch"
for sample in 1 2 3; do
  "$kicad" pcb drc --all-track-errors --schematic-parity --format json --output "$out/drc-$sample.json" "$src/native/catch-bleed.kicad_pcb"
done
python3 "$src/verify_bleed.py"
"$kicad" pcb export svg --layers F.Cu,F.Silkscreen,Edge.Cuts --mode-single --page-size-mode 2 --exclude-drawing-sheet --output "$out/bleed-front.svg" "$src/native/catch-bleed.kicad_pcb"
"$cad_python" "$src/build_carrier.py"
"$cad_python" "$src/check_assembly.py"
python3 "$src/draw_review.py"
rustc --edition=2021 --test "$src/electrical_screen.rs" -o "$scratch/screen-tests"
"$scratch/screen-tests" > "$out/electrical-screen-tests.txt"
rustc --edition=2021 "$src/electrical_screen.rs" -o "$scratch/screen"
"$scratch/screen" "$out/route-lengths.csv" > "$out/electrical-screen.json"
python3 "$src/freeze_evidence.py"
