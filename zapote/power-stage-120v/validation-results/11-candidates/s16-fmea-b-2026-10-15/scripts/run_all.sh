#!/bin/sh
# Rerun every script in dependency order (offline; reads dl/ and inputs/ only). Exit non-zero on the first failure.
set -e
cd "$(dirname "$0")/.."
python3 -I scripts/manifest.py
python3 -I scripts/sources.py          > /dev/null
python3 -I scripts/bands.py            > /dev/null
python3 -I scripts/monitor_fault_sim.py > /dev/null
python3 -I scripts/truth_table.py      > /dev/null
python3 -I scripts/fmea_metric.py      > /dev/null
python3 -I scripts/timing.py           > /dev/null
echo "all scripts ran; results/ written"
