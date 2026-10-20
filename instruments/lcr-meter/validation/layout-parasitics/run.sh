#!/bin/sh
# Reproduce every number in README.md / extracted.json.  Read-only on CAD.
# Needs: KiCad 10 bundled Python (pcbnew) for the export; python3 with numpy,
# scipy, shapely>=2, pyamg, matplotlib for the rest.
# Runtime ~1 h on an M-series Mac, peak RAM ~8 GB (the 0.04 mm zoom and 0.07 mm
# whole-AFE FD solves dominate).  Set QUICK=1 to skip the fine FD grids.
set -eu
cd "$(dirname "$0")"
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3}
PY=${PY:-python3}

"$KICAD_PYTHON" export_geometry.py ../../cad/temper-lcr.kicad_pcb
$PY riso_variant.py
$PY closed_form.py
LP_GEOMETRY=geometry_riso.json $PY closed_form.py
$PY headers.py
$PY inductance.py
$PY proximity.py

RISO_ENV="LP_GEOMETRY=geometry_riso.json LP_CONDUCTORS=TIA_SUM,DUT_LO,TIA_OUT,DUT_HI,RF100,RF5K,RF100K,LOW_BUF,HIGH_BUF"
$PY fd_validate.py 0.1 0.07 0.05
$PY fd3d.py 0.1 neumann JLC04161H-7628 zoom
$PY fd3d.py 0.1 neumann JLC04161H-7628 afe
$PY fd3d.py 0.1 neumann JLC04161H-1080 afe
env $RISO_ENV $PY fd3d.py 0.1 neumann JLC04161H-7628 afe
env $RISO_ENV $PY fd3d.py 0.1 neumann JLC04161H-1080 afe
if [ -z "${QUICK:-}" ]; then
  for dx in 0.07 0.05 0.04; do $PY fd3d.py "$dx" neumann JLC04161H-7628 zoom; done
  $PY fd3d.py 0.07 neumann JLC04161H-7628 afe
  env $RISO_ENV $PY fd3d.py 0.07 neumann JLC04161H-7628 afe
fi

$PY assemble.py
$PY plot_layout.py
