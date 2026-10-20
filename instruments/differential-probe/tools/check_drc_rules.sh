#!/bin/sh
# Negative controls for native KiCad's air-clearance and routed-slot creepage rules.
set -eu
cd "$(dirname "$0")/.."
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3}
KICAD=${KICAD:-kicad-cli}
for fixture in clearance slot interleg-none interleg-short opposing-pass opposing-fail; do
    directory="build/drc-oracle/$fixture"
    mkdir -p "$directory"
    cp cad/differential-probe.kicad_pro cad/differential-probe.kicad_dru cad/fp-lib-table "$directory/"
    if [ ! -e "$directory/Probe.pretty" ]; then ln -s ../../../cad/Probe.pretty "$directory/Probe.pretty"; fi
    "$KICAD_PYTHON" tools/pcb_bridge.py mutant "$fixture" "$directory/differential-probe.kicad_pcb" > "$directory/native.log" 2>&1
    "$KICAD" pcb drc --all-track-errors --format json -o "$directory/drc.json" "$directory/differential-probe.kicad_pcb" > "$directory/drc.log" 2>&1
done
jq -e 'any(.violations[]; .type == "clearance" and (.description | contains("TIP_P to LV")))' build/drc-oracle/clearance/drc.json > /dev/null
jq -e 'any(.violations[]; .type == "creepage" and (.description | contains("TIP_P to ")) and all(.items[]; .description | contains("of C1 ")))' build/drc-oracle/slot/drc.json > /dev/null
jq -e 'any(.violations[]; .type == "creepage" and (.description | contains("TIP_P to TIP_N")))' build/drc-oracle/interleg-none/drc.json > /dev/null
jq -e '(any(.violations[]; .type == "creepage" and (.description | contains("TIP_P to TIP_N"))) | not) and any(.violations[]; .type == "creepage" and (.description | test("P_SEG1 to N_SEG1|P_SEG2 to N_SEG2")))' build/drc-oracle/interleg-short/drc.json > /dev/null
jq -e '(.violations | length) == 0 and (.unconnected_items | length) == 0' build/drc-oracle/opposing-pass/drc.json > /dev/null
jq -e 'any(.violations[]; .type == "clearance" and (.description | contains("TIP_P to TIP_N"))) and any(.violations[]; .type == "creepage" and (.description | contains("TIP_P to TIP_N")))' build/drc-oracle/opposing-fail/drc.json > /dev/null
{
    echo 'PASS: GND track 6 mm from the TIP_P landing fails the explicit 10 mm air-clearance rule (ordinary 0.2 mm clearance alone would pass).'
    echo 'PASS: removing the C1 routed slot fails the explicit 4 mm section creepage rule.'
    echo 'PASS: removing the long inter-leg slot fails TIP_P to TIP_N 20 mm creepage (facing resistor rows are 12.65 mm apart).'
    echo 'PASS: shortening the inter-leg slot to end at x = 40 mm keeps the tips covered but fails rank-4/rank-3 opposite-leg creepage around the slot end.'
    echo 'PASS: isolated opposing TIP pads with 20.5 mm edge spacing pass the revised 10/20 mm rules; the old 40 mm surface rule would reject this fixture.'
    echo 'PASS: isolated opposing TIP pads with 8 mm edge spacing fail both revised air and surface rules.'
    echo 'Known-bad fixtures live only in ignored build/drc-oracle; canonical board unchanged.'
} > validation/pcb-drc-oracle.txt
cat validation/pcb-drc-oracle.txt
