#!/bin/sh
# Cal kit r2: generate the board from build_calkit.py (hand-specified tracks, no autorouter),
# audit, and export the JLC package.  No purchasing or uploads.
set -eu
cd "$(dirname "$0")"
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
: "${KICAD_CLI:=kicad-cli}"
mkdir -p build manufacturing/gerbers previews
"$KICAD_PYTHON" build_calkit.py
"$KICAD_CLI" pcb drc --severity-all --all-track-errors --exit-code-violations --format json \
  --output manufacturing/drc.json calkit.kicad_pcb
"$KICAD_CLI" pcb drc --severity-all --all-track-errors --format report \
  --output manufacturing/drc.rpt calkit.kicad_pcb
"$KICAD_PYTHON" check_kelvin.py
cp build/kelvin-audit.json manufacturing/kelvin-audit.json
"$KICAD_CLI" pcb export pos --format csv --units mm --use-drill-file-origin --exclude-dnp \
  --output build/positions.csv calkit.kicad_pcb
rm -f manufacturing/gerbers/*
"$KICAD_CLI" pcb export gerbers --layers F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
  --use-drill-file-origin --output manufacturing/gerbers/ calkit.kicad_pcb
"$KICAD_CLI" pcb export drill --format excellon --drill-origin plot --excellon-units mm \
  --excellon-separate-th --generate-map --map-format pdf \
  --generate-report --report-path manufacturing/drill-report.txt \
  --output manufacturing/gerbers/ calkit.kicad_pcb
rm -f manufacturing/calkit-gerbers.zip
(cd manufacturing/gerbers && zip -q -X ../calkit-gerbers.zip ./*.g?? ./*.gm1 ./*.drl ./*.gbrjob)
"$KICAD_PYTHON" package_calkit.py
if [ "${CALKIT_FETCH_PARTS:-0}" = "1" ]; then python3 fetch_jlc_parts.py; fi
python3 order_estimate.py 5
"$KICAD_CLI" pcb render --side top --width 900 --height 2400 --quality high --background opaque \
  -o previews/render-top.png calkit.kicad_pcb >/dev/null
"$KICAD_CLI" pcb render --side bottom --width 900 --height 2400 --quality high --background opaque \
  -o previews/render-bottom.png calkit.kicad_pcb >/dev/null
"$KICAD_CLI" pcb export svg --layers F.Cu,F.Mask,F.SilkS,Edge.Cuts --mode-single --fit-page-to-board \
  --exclude-drawing-sheet --output previews/front.svg calkit.kicad_pcb >/dev/null
echo "calkit rebuild complete"
