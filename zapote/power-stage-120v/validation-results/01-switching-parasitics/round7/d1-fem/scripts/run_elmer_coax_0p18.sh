#!/bin/zsh
set -euo pipefail

# Direct Elmer fallback on a finer coax mesh. Run from round7/d1-fem.
HERE="$PWD"
R6="$HERE/../../round6/d1-fem"
RAW="$HERE/raw/fixtures"
mkdir -p "$RAW"
export PYTHONPATH=/opt/homebrew/lib
PY=/Users/bennet/Miniforge3/bin/python3
ELMER=/tmp/ps-r6-fem-elmer-install

"$PY" "$R6/scripts/make_coax.py" "$RAW/coax-0p18.msh" --size 0.18 \
  > "$RAW/coax-0p18-mesh.json"
"$PY" "$R6/scripts/convert_mesh_for_elmer.py" \
  "$RAW/coax-0p18.msh" "$RAW/coax-0p18-ascii.msh" \
  > "$RAW/coax-0p18-conversion.json"
"$ELMER/bin/ElmerGrid" 14 2 "$RAW/coax-0p18-ascii.msh" \
  -out "$RAW/coax-0p18-elmer" -scale 0.001 0.001 0.001 \
  > "$RAW/coax-0p18-elmergrid.log" 2>&1
"$PY" "$R6/scripts/check_coax_source.py" "$RAW/coax-0p18.msh" \
  > "$RAW/coax-0p18-source.json"

"$PY" - "$R6/fixtures/coax-0p25.sif" "$RAW/coax-0p18.sif" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
old = 'raw/coax-0p25-elmer'
if source.count(old) != 2:
    raise SystemExit('Expected exactly two Elmer mesh path references')
Path(sys.argv[2]).write_text(source.replace(old, 'raw/fixtures/coax-0p18-elmer'))
PY

ELMER_HOME="$ELMER" /usr/bin/time -l "$ELMER/bin/ElmerSolver" \
  "$RAW/coax-0p18.sif" > "$RAW/coax-0p18.log" \
  2> "$RAW/coax-0p18-time.log"
"$PY" "$R6/scripts/verify_elmer_fixture.py" "$RAW/coax-0p18.log" \
  > "$RAW/coax-0p18-nominal-verification.json"
