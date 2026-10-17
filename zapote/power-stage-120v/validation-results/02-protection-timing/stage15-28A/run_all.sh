#!/bin/sh
# Stage 15 planning calculations. usage: sh run_all.sh <UNIT> <copper-dump.json> <section.kicad_pcb>
# (copper dump in the copper_dump format: zones/tracks/vias/pads/edges, as the incr21 iteration writes)
set -e
cd "$(dirname "$0")"
UNIT=${1:-$(cd ../../.. && pwd)}
python3 ocp_bands.py "$UNIT"            > out/ocp_bands.log
python3 band_contrib.py "$UNIT" 12600 11700 > out/band_contrib.log
python3 fault_check.py "$UNIT"          > out/fault_check.log
python3 thermal_scale.py "$UNIT"        > out/thermal_scale.log
python3 sw_widths.py "$2" "$3" "$UNIT"  > out/sw_widths.log
python3 neck_fin.py                     > out/neck_fin.log
python3 proposals.py "$2" "$3" "$UNIT"  > out/proposals.log
echo done
