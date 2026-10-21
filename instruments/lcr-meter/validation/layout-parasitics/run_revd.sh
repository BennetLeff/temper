#!/bin/sh
# Extract the as-built Rev D board (R94 fitted, TIA_SUM net) into geometry_revd.json,
# inductance_revd.json and fd_results/*_revd.json, then reassemble extracted.json
# (key rev_d_board).  Read-only on CAD.  ~40 min; the Rev C inputs stay untouched.
set -eu
cd "$(dirname "$0")"
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3}
PY=${PY:-python3}
export LP_GEOMETRY=geometry_revd.json LP_SUM=TIA_SUM
"$KICAD_PYTHON" export_geometry.py ../../cad/temper-lcr.kicad_pcb
LP_INDUCTANCE=inductance_revd.json $PY inductance.py
export LP_CONDUCTORS=TIA_SUM,DUT_LO,TIA_OUT,DUT_HI,RF100,RF5K,RF100K,LOW_BUF,HIGH_BUF
$PY fd3d.py 0.1 neumann JLC04161H-7628 afe
$PY fd3d.py 0.1 neumann JLC04161H-1080 afe
$PY fd3d.py 0.07 neumann JLC04161H-7628 afe
unset LP_GEOMETRY LP_SUM LP_CONDUCTORS
$PY assemble.py
