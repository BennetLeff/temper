#!/bin/zsh
set -euo pipefail

# Convert and audit a full-domain plate mesh made by round 7's
# make_plates_box.py. Run from this round-8 Elmer directory.
if (( $# != 1 )); then
  print -u2 'usage: prepare_plate.sh label'
  exit 2
fi
label="$1"
[[ "$label" =~ '^plates-box0p25-far12-m(20|40|80)$' ]] || { print -u2 'unexpected plate label'; exit 2; }
own_root="$PWD"
raw_root="$own_root/raw/fixtures"
source_root="${R7_D1_ROOT:-$own_root/../../round7/d1-fem}"
elmer_root=/tmp/ps-r6-fem-elmer-install
python_bin=/Users/bennet/Miniforge3/bin/python3
mesh="$raw_root/$label.msh"
test -f "$mesh"
test ! -e "$raw_root/$label-elmer"
export PYTHONPATH=/opt/homebrew/lib
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

"$python_bin" "$source_root/scripts/audit_plate_mesh.py" "$mesh" \
  > "$raw_root/$label-audit.json"
"$python_bin" "$source_root/scripts/convert_mesh_for_elmer_tolerant.py" \
  "$mesh" "$raw_root/$label-ascii.msh" \
  > "$raw_root/$label-conversion.json"
"$elmer_root/bin/ElmerGrid" 14 2 "$raw_root/$label-ascii.msh" \
  -out "$raw_root/$label-elmer" -scale 0.001 0.001 0.001 \
  > "$raw_root/$label-elmergrid.log" 2>&1
"$python_bin" - "$source_root/fixtures/plates-direct.sif" "$raw_root/$label.sif" "$label" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
old_mesh = 'raw/fixtures/plates-near0p15-far4-m20-elmer'
if source.count(old_mesh) != 2 or source.count('Linear System Direct Method = UMFPack') != 1:
    raise SystemExit('unexpected round-7 plate SIF structure')
source = source.replace(old_mesh, f'raw/fixtures/{sys.argv[3]}-elmer')
source = source.replace('Linear System Direct Method = UMFPack',
                        'Linear System Direct Method = Big Umfpack')
Path(sys.argv[2]).write_text(source)
PY
"$python_bin" "$source_root/scripts/check_plate_source.py" \
  "$mesh" "$raw_root/$label.sif" > "$raw_root/$label-source.json"
