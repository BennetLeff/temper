#!/bin/sh
# Stage-47 FMEA: control rerun of the DECISIONS 59 study copy, sources check, then the s47 analysis. Offline.
set -e
cd "$(dirname "$0")/.."
(cd s16copy && sh scripts/run_all.sh)
python3 -I scripts/sources47.py > /dev/null
python3 -I scripts/fmea47.py    > /dev/null
echo "fmea-s47: results/ written"
