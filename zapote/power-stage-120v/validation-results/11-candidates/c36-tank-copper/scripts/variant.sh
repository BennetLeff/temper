#!/bin/bash
# build one stage-41 variant on the s40 base and export its copper: variant.sh NAME
set -e
V=$1; R=${S41_RUNS:?set S41_RUNS to the run root}; U=$(cd "$(dirname "$0")/../../../.." && pwd)
KP=${KPY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
cd $U
python3 -I validation-results/11-candidates/c36-tank-copper/scripts/pours41.py --variant $V | tail -1
sh validation-results/11-candidates/c36-tank-copper/passes41.sh $R/base-s40.json $R/v-$V > $R/v-$V.log 2>&1
cat $R/v-$V.log
B=$R/v-$V/j1/section.kicad_pcb
$KP tools/export_power_copper.py $B $R/v-$V/power_copper.json.gz >/dev/null 2>&1
$KP validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py $B $R/v-$V/all-copper.json.gz >/dev/null 2>&1
ls -la $R/v-$V/*.gz
