#!/bin/zsh
set -euo pipefail

# Solve a previously generated mesh from this round's raw/fixtures directory.
if (( $# < 1 || $# > 2 )); then
  print -u2 'usage: solve_plates_mesh.sh label [half]'
  exit 2
fi
LABEL="$1"
[[ "$LABEL" =~ '^[A-Za-z0-9_-]+$' ]] || { print -u2 'invalid label'; exit 2; }
MODE="${2:-full}"
[[ "$MODE" == full || "$MODE" == half ]] || { print -u2 'mode must be half'; exit 2; }
ROOT="$PWD"
RAW="$ROOT/raw/fixtures"
MESH="$RAW/$LABEL.msh"
test -f "$MESH" || { print -u2 "missing mesh $MESH"; exit 2; }
test ! -e "$RAW/$LABEL.log" || { print -u2 "already solved $LABEL"; exit 1; }
PY=/Users/bennet/Miniforge3/bin/python3
ELMER=/tmp/ps-r6-fem-elmer-install
export PYTHONPATH=/opt/homebrew/lib

"$PY" scripts/convert_mesh_for_elmer_tolerant.py "$MESH" \
  "$RAW/$LABEL-ascii.msh" > "$RAW/$LABEL-conversion.json"
"$ELMER/bin/ElmerGrid" 14 2 "$RAW/$LABEL-ascii.msh" \
  -out "$RAW/$LABEL-elmer" -scale 0.001 0.001 0.001 \
  > "$RAW/$LABEL-elmergrid.log" 2>&1
if [[ "$MODE" == half ]]; then
  TEMPLATE="$ROOT/fixtures/plates-half.sif"
  OLD='raw/fixtures/plates-half-box0p4-far12-m20-elmer'
else
  TEMPLATE="$ROOT/fixtures/plates-direct.sif"
  OLD='raw/fixtures/plates-near0p15-far4-m20-elmer'
fi
"$PY" - "$TEMPLATE" "$RAW/$LABEL.sif" "$LABEL" "$OLD" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
old = sys.argv[4]
if text.count(old) != 2:
    raise SystemExit('Expected exactly two Elmer mesh path references')
Path(sys.argv[2]).write_text(text.replace(old, f'raw/fixtures/{sys.argv[3]}-elmer'))
PY
SOURCE_FLAGS=()
if [[ "$MODE" == half ]]; then
  SOURCE_FLAGS=(--z-min .25 --z-max .5)
fi
"$PY" scripts/check_plate_source.py "$MESH" "$RAW/$LABEL.sif" "${SOURCE_FLAGS[@]}" \
  > "$RAW/$LABEL-source.json"
ulimit -Ss 65520
ulimit -Ss > "$RAW/$LABEL-stack-kb.txt"
set +e
/usr/bin/time -p env ELMER_HOME="$ELMER" "$ELMER/bin/ElmerSolver" \
  "$RAW/$LABEL.sif" > "$RAW/$LABEL.log" 2> "$RAW/$LABEL-time.log"
RESULT=$?
set -e
print "$RESULT" > "$RAW/$LABEL-exit.txt"
exit "$RESULT"
