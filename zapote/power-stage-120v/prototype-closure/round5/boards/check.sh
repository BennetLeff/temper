#!/bin/sh
# Run from repository root. Native KiCad may require macOS process permission.
set -eu
base=zapote/power-stage-120v/prototype-closure/round5/boards
out=output/temper-prototype-closure/round5/boards
for name in central catch bus line pre out tank iproof iline; do
 if [ "$name" = central ]; then
  native="$base/central/native/supervisor"
  schematic_pdf="$out/central-schematic.pdf"
 else
  native="$base/native/$name-sensor/$name-sensor"
  schematic_pdf="$out/$name-sensor.pdf"
 fi
 kicad-cli sch erc --format json --output "$out/$name-erc.json" "$native.kicad_sch" >"/private/tmp/temper-r5-$name-erc.log" 2>&1
 kicad-cli sch export netlist --format kicadxml --output "$out/$name-netlist.xml" "$native.kicad_sch" >"/private/tmp/temper-r5-$name-netlist.log" 2>&1
 for sample in 1 2 3; do
  kicad-cli pcb drc --schematic-parity --all-track-errors --format json --output "$out/$name-drc-$sample.json" "$native.kicad_pcb" >"/private/tmp/temper-r5-$name-drc-$sample.log" 2>&1
 done
 if [ "$name" = central ]; then cp "$out/$name-drc-1.json" "$out/central-routed-drc.json"; else cp "$out/$name-drc-1.json" "$out/$name-drc-parity.json"; fi
 kicad-cli sch export pdf --output "$schematic_pdf" "$native.kicad_sch" >"/private/tmp/temper-r5-$name-schpdf.log" 2>&1
 kicad-cli pcb export pdf --mode-single --layers F.Cu,F.Fab,Edge.Cuts --scale 0 --output "$out/$name-board.pdf" "$native.kicad_pcb" >"/private/tmp/temper-r5-$name-boardpdf.log" 2>&1
 printf '%s checked\n' "$name"
done
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 "$base/verify_native.py" >"/private/tmp/temper-r5-native-oracle.log" 2>&1
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 "$base/review_manifest.py" >"/private/tmp/temper-r5-inventory.log" 2>&1
python3 "$base/write_checkpoint.py"
