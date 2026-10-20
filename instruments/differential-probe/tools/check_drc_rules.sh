#!/bin/sh
# Negative controls for native KiCad's air-clearance and routed-slot creepage rules.
set -eu
cd "$(dirname "$0")/.."
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3}
KICAD=${KICAD:-kicad-cli}
for fixture in clearance slot; do
    directory="build/drc-oracle/$fixture"
    mkdir -p "$directory"
    cp cad/differential-probe.kicad_pro cad/differential-probe.kicad_dru cad/fp-lib-table "$directory/"
    if [ ! -e "$directory/Probe.pretty" ]; then ln -s ../../../cad/Probe.pretty "$directory/Probe.pretty"; fi
    "$KICAD_PYTHON" tools/pcb_bridge.py mutant "$fixture" "$directory/differential-probe.kicad_pcb" > "$directory/native.log" 2>&1
    "$KICAD" pcb drc --all-track-errors --format json -o "$directory/drc.json" "$directory/differential-probe.kicad_pcb" > "$directory/drc.log" 2>&1
done
jq -e 'any(.violations[]; .type == "clearance" and (.description | contains("TIP_P to LV")))' build/drc-oracle/clearance/drc.json > /dev/null
jq -e 'any(.violations[]; .type == "creepage" and (.description | contains("TIP_P to ")) and all(.items[]; .description | contains("of C1 ")))' build/drc-oracle/slot/drc.json > /dev/null
{
    echo 'PASS: GND track 1.875 mm from TIP_P fails the explicit 10 mm air-clearance rule (ordinary 0.2 mm clearance alone would pass).'
    echo 'PASS: removing the C1 routed slot fails the explicit 4 mm segment creepage rule.'
    echo 'Known-bad fixtures live only in ignored build/drc-oracle; canonical board unchanged.'
} > validation/pcb-drc-oracle.txt
cat validation/pcb-drc-oracle.txt
