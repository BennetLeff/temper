#!/bin/sh
# Rev E parasitic extraction (K1-K3 relay range switching, TIA_SUM summing node).  Read-only on CAD;
# Rev C / Rev D files are untouched.  Boards are taken from git so each variant is reproducible:
#   reve       board 2f6486c4 (commit 1438ecbc9): first relay layout
#   reve_r104  board cf379f85 (commit a04880a87): + R104 47 ohm between U6A (net SRC_DRV) and
#              SOURCE_BUF, SOURCE_BUF moved to In2 x 185.5
# Usage: sh run_reve.sh [reve|reve_r104|all]   (default all).  STAB=1 also reruns the stability modes.
# Writes geometry_<v>.json, inductance_<v>.json, fd_results/*_<v>.json, extracted_<v>.json and
# ../stability-full-chain/<v>_extracted.rs (board capacitors + loop L for loop_matrix.rs).
# Peak RAM ~5 GB (0.14 mm whole-board solve, ~4 M unknowns).  A 0.1 mm whole-board solve
# (8.5 M unknowns, ~10 GB) did not fit beside the other jobs on the 32 GB Mac; the whole-board
# solve is instead corrected to 0.05 mm by zoom-window ratios (assemble_reve.py).
set -eu
cd "$(dirname "$0")"
KICAD_PYTHON=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
PY=${PY:-python3}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
NETS=TIA_SUM,DUT_LO,TIA_OUT,DUT_HI,RF100,RF5K,RF100K,LOW_BUF,HIGH_BUF,SOURCE_BUF,RG100,RG5K,RG100K

export_board() {  # $1 variant, $2 commit
  # the .kicad_pro carries the design rules the exporter's zone-refill check needs
  for f in kicad_pcb kicad_pro; do git show "$2:instruments/lcr-meter/cad/temper-lcr.$f" > "$TMP/temper-lcr.$f"; done
  LP_GEOMETRY="geometry_$1.json" "$KICAD_PYTHON" export_geometry.py "$TMP/temper-lcr.kicad_pcb"
  LP_GEOMETRY="geometry_$1.json" LP_SUM=TIA_SUM LP_INDUCTANCE="inductance_$1.json" $PY inductance_reve.py
}

fd() {  # $1 variant, $2 conductors, then dx stackup window
  v=$1; c=$2; shift 2
  LP_GEOMETRY="geometry_$v.json" LP_SUM=TIA_SUM LP_CONDUCTORS="$c" $PY fd3d.py "$1" neumann "$2" "$3"
}

run_reve() {
  export_board reve 1438ecbc9
  # grid convergence: U7 zoom, K1 relay zoom, SOURCE_BUF/DUT_HI broadside run
  for dx in 0.2 0.14 0.1 0.07; do fd reve $NETS "$dx" JLC04161H-7628 zoom; done
  for dx in 0.2 0.14 0.1 0.07 0.05; do fd reve $NETS "$dx" JLC04161H-7628 reve_relay; done
  for dx in 0.2 0.14 0.1 0.07 0.05 0.04 0.03; do fd reve $NETS "$dx" JLC04161H-7628 reve_hiside; done
  # whole board (window 'reve' covers every conductor with >= 1.4 mm margin; fd3d checks it)
  fd reve $NETS 0.2 JLC04161H-7628 reve
  fd reve $NETS 0.14 JLC04161H-7628 reve
  fd reve $NETS 0.2 JLC04161H-1080 reve
  LP_VARIANT=reve $PY assemble_reve.py
}

run_reve_r104() {
  export_board reve_r104 a04880a87
  # The K1-relay and U7 zoom series are reused from 'reve' (identical copper and In1 fill in
  # those windows, see assemble_reve.py); only the moved SOURCE_BUF/DUT_HI run is re-zoomed.
  for dx in 0.14 0.1 0.07 0.05; do fd reve_r104 $NETS,SRC_DRV "$dx" JLC04161H-7628 reve_hiside_r104; done
  fd reve_r104 $NETS,SRC_DRV 0.2 JLC04161H-7628 reve_r104
  fd reve_r104 $NETS,SRC_DRV 0.2 JLC04161H-1080 reve_r104
  fd reve_r104 $NETS,SRC_DRV 0.14 JLC04161H-7628 reve_r104
  LP_VARIANT=reve_r104 $PY assemble_reve.py
}

case "${1:-all}" in
  reve) run_reve ;;
  reve_r104) run_reve_r104 ;;
  all) run_reve; run_reve_r104 ;;
  *) echo 'Usage: sh run_reve.sh [reve|reve_r104|all]' >&2; exit 2 ;;
esac

if [ -n "${STAB:-}" ]; then
  cd ../stability-full-chain
  rustc --edition=2021 -Awarnings -O loop_matrix.rs -o "$TMP/matrix"
  for m in reverelaycng100 reverelaycng100_r104 fixedrelaycng100; do "$TMP/matrix" "final_$m" > "check-$m.log" 2>&1; done
  $PY reve_summary.py matrix-final_reverelaycng100.md matrix-final_reverelaycng100_r104.md matrix-final_fixedrelaycng100.md
fi
