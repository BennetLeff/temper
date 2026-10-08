#!/bin/zsh
set -euo pipefail

# Usage: zsh scripts/run_elmer_coax_refined.sh LABEL PORT_MM VOLUME_MM
# Run from round7/d1-fem. Each label gets independent ignored raw evidence.
if (( $# != 3 )); then
  print -u2 'usage: run_elmer_coax_refined.sh label port_mm volume_mm'
  exit 2
fi
LABEL="$1"
PORT_MM="$2"
VOLUME_MM="$3"
[[ "$LABEL" =~ '^[A-Za-z0-9_-]+$' ]] || { print -u2 'invalid label'; exit 2; }

ROOT="$PWD"
R6="$ROOT/../../round6/d1-fem"
RAW="$ROOT/raw/fixtures"
PY=/Users/bennet/Miniforge3/bin/python3
ELMER=/tmp/ps-r6-fem-elmer-install
MESH="$RAW/$LABEL.msh"
if test -e "$MESH"; then
  print -u2 "refusing to overwrite $MESH"
  exit 1
fi
mkdir -p "$RAW"
export PYTHONPATH=/opt/homebrew/lib

"$PY" scripts/make_coax_portrefined.py "$MESH" \
  --port-size "$PORT_MM" --volume-size "$VOLUME_MM" \
  > "$RAW/$LABEL-mesh.json"
"$PY" "$R6/scripts/convert_mesh_for_elmer.py" \
  "$MESH" "$RAW/$LABEL-ascii.msh" > "$RAW/$LABEL-conversion.json"
"$ELMER/bin/ElmerGrid" 14 2 "$RAW/$LABEL-ascii.msh" \
  -out "$RAW/$LABEL-elmer" -scale 0.001 0.001 0.001 \
  > "$RAW/$LABEL-elmergrid.log" 2>&1
"$PY" "$R6/scripts/check_coax_source.py" "$MESH" \
  > "$RAW/$LABEL-source.json"

"$PY" - "$R6/fixtures/coax-0p25.sif" "$RAW/$LABEL.sif" "$LABEL" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
old = 'raw/coax-0p25-elmer'
if source.count(old) != 2:
    raise SystemExit('Expected exactly two Elmer mesh path references')
Path(sys.argv[2]).write_text(source.replace(old, f'raw/fixtures/{sys.argv[3]}-elmer'))
PY

ulimit -Ss 65520
ulimit -Ss > "$RAW/$LABEL-stack-kb.txt"
set +e
/usr/bin/time -p env ELMER_HOME="$ELMER" "$ELMER/bin/ElmerSolver" \
  "$RAW/$LABEL.sif" > "$RAW/$LABEL.log" 2> "$RAW/$LABEL-time.log"
RESULT=$?
set -e
print "$RESULT" > "$RAW/$LABEL-exit.txt"
if (( RESULT != 0 )); then
  exit "$RESULT"
fi
"$PY" "$R6/scripts/verify_elmer_fixture.py" "$RAW/$LABEL.log" \
  > "$RAW/$LABEL-nominal-verification.json"
