#!/bin/sh
# Extract the Rev E board (K1-K3 relay range switching, TIA_SUM summing node) into
# geometry_reve.json, inductance_reve.json, fd_results/*_reve.json and extracted_reve.json,
# and regenerate ../stability-full-chain/reve_extracted.rs (board capacitors + loop L for the
# reverelaycng100 stability mode).  Read-only on CAD.  Rev C / Rev D files are untouched.
# Peak RAM ~5 GB (0.14 mm whole-board solve, 4.1 M unknowns).  A 0.1 mm whole-board solve
# (8.5 M unknowns, ~10 GB) did not fit beside the other jobs on the 32 GB Mac; the whole-board
# solve is instead corrected to 0.05 mm by the zoom-window ratios (assemble_reve.py).
# STAB=1 also reruns the stability modes (needs rustc, ngspice).
set -eu
cd "$(dirname "$0")"
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
PY=${PY:-python3}
export LP_GEOMETRY=geometry_reve.json LP_SUM=TIA_SUM
"$KICAD_PYTHON" export_geometry.py ../../cad/temper-lcr.kicad_pcb
LP_INDUCTANCE=inductance_reve.json $PY inductance_reve.py
export LP_CONDUCTORS=TIA_SUM,DUT_LO,TIA_OUT,DUT_HI,RF100,RF5K,RF100K,LOW_BUF,HIGH_BUF,SOURCE_BUF,RG100,RG5K,RG100K
# grid convergence: U7 zoom, K1 relay zoom, SOURCE_BUF/DUT_HI broadside run
for dx in 0.2 0.14 0.1 0.07; do $PY fd3d.py "$dx" neumann JLC04161H-7628 zoom; done
for dx in 0.2 0.14 0.1 0.07 0.05; do $PY fd3d.py "$dx" neumann JLC04161H-7628 reve_relay; done
for dx in 0.2 0.14 0.1 0.07 0.05 0.04 0.03; do $PY fd3d.py "$dx" neumann JLC04161H-7628 reve_hiside; done
# whole board (window 'reve', covers every conductor with >= 1.4 mm margin; fd3d checks it)
$PY fd3d.py 0.2 neumann JLC04161H-7628 reve
$PY fd3d.py 0.14 neumann JLC04161H-7628 reve
$PY fd3d.py 0.2 neumann JLC04161H-1080 reve
unset LP_GEOMETRY LP_SUM LP_CONDUCTORS
$PY assemble_reve.py
if [ -n "${STAB:-}" ]; then
  cd ../stability-full-chain
  BUILD=$(mktemp -d)
  trap 'rm -rf "$BUILD"' EXIT HUP INT TERM
  rustc --edition=2021 -Awarnings -O loop_matrix.rs -o "$BUILD/matrix"
  for m in reverelaycng100 fixedrelaycng100; do "$BUILD/matrix" "final_$m" > "check-$m.log" 2>&1; done
  $PY reve_summary.py matrix-final_reverelaycng100.md matrix-final_fixedrelaycng100.md
fi
