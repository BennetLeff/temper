#!/bin/sh
# Native KiCad adapter/export pipeline. No purchasing or external uploads.
set -eu
cd "$(dirname "$0")/.."
: "${KICAD_PYTHON:=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
: "${RENDER_PYTHON:=python3}"
mkdir -p build manufacturing/gerbers previews validation
"$KICAD_PYTHON" cad/build_cad.py
"$KICAD_PYTHON" cad/fill_zones.py
kicad-cli sch erc --severity-all --exit-code-violations --format json \
  --output validation/erc.json cad/temper-lcr.kicad_sch
kicad-cli pcb drc --severity-all --all-track-errors --schematic-parity \
  --refill-zones --exit-code-violations --format json \
  --output validation/drc.json cad/temper-lcr.kicad_pcb
kicad-cli sch export netlist --format kicadxml --output build/netlist.xml cad/temper-lcr.kicad_sch
kicad-cli pcb export pos --format csv --units mm --use-drill-file-origin \
  --output build/positions.csv cad/temper-lcr.kicad_pcb
kicad-cli pcb export gerbers \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,Dwgs.User \
  --use-drill-file-origin --output manufacturing/gerbers/ cad/temper-lcr.kicad_pcb
kicad-cli pcb export drill --format excellon --drill-origin plot --excellon-units mm \
  --excellon-separate-th --excellon-oval-format route --generate-map --map-format pdf \
  --generate-report --report-path manufacturing/drill-report.txt \
  --output manufacturing/gerbers/ cad/temper-lcr.kicad_pcb
kicad-cli sch export pdf --output previews/schematic.pdf cad/temper-lcr.kicad_sch
kicad-cli pcb export svg --layers F.Cu,F.SilkS,Edge.Cuts --mode-single \
  --fit-page-to-board --exclude-drawing-sheet --output previews/pcb-front.svg cad/temper-lcr.kicad_pcb
"$KICAD_PYTHON" cad/assembly_preview.py
kicad-cli pcb export svg --layers F.Fab,Edge.Cuts --mode-single \
  --fit-page-to-board --exclude-drawing-sheet \
  --output previews/assembly-top.svg build/assembly-preview.kicad_pcb
# Fabrication drawing (notes, stackup, drill summary, dimensions on Dwgs.User; also a Gerber in the zip)
kicad-cli pcb export pdf --layers Edge.Cuts,Dwgs.User --mode-single --black-and-white --scale 0 \
  --output manufacturing/fab-drawing.pdf cad/temper-lcr.kicad_pcb
# Assembly drawing: every reference on F.Fab (the silk carries only those that fit), DNP parts crossed out
kicad-cli pcb export pdf --layers F.Fab,Edge.Cuts --mode-single --cdnp --black-and-white --scale 0 \
  --output manufacturing/assembly-top.pdf build/assembly-preview.kicad_pcb
"$KICAD_PYTHON" cad/package_cad.py
"$KICAD_PYTHON" cad/audit_dfm.py
DYLD_FALLBACK_LIBRARY_PATH="${LCR_CAIRO_LIBRARY_PATH:-/opt/homebrew/lib}" "$RENDER_PYTHON" cad/render_previews.py
if [ "${LCR_SKIP_ARCHIVE:-0}" != "1" ]; then
  python3 cad/archive_package.py
fi
