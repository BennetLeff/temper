#!/bin/zsh
set -euo pipefail

# Re-solve an unchanged, audited round-7 mesh with Elmer's 64-bit UMFPACK.
# The round-7 raw packet and solver install are read only.
if (( $# != 1 )); then
  print -u2 'usage: run_big_umfpack_existing.sh round7-label'
  exit 2
fi
label="$1"
[[ "$label" =~ '^[A-Za-z0-9_-]+$' ]] || { print -u2 'invalid label'; exit 2; }
case "$label" in
  coax-port0p10-vol0p30|coax-port0p08-vol0p25|plates-box0p4-far4-m20) ;;
  *) print -u2 'label is not a selected regression or failure case'; exit 2 ;;
esac

own_root="$PWD"
source_root="${R7_D1_ROOT:-$own_root/../../round7/d1-fem}"
solver_root=/tmp/ps-r6-fem-elmer-install
raw_root="$own_root/raw/fixtures"
src_mesh="$source_root/raw/fixtures/$label-elmer"
dst_mesh="$raw_root/$label-big-elmer"
test -d "$src_mesh"
test ! -e "$dst_mesh"
mkdir -p "$raw_root"
cp -R "$src_mesh" "$dst_mesh"
for suffix in mesh.json source.json audit.json; do
  if test -f "$source_root/raw/fixtures/$label-$suffix"; then
    cp "$source_root/raw/fixtures/$label-$suffix" "$raw_root/$label-big-$suffix"
  fi
done
python_bin=/Users/bennet/Miniforge3/bin/python3
"$python_bin" - "$source_root/raw/fixtures/$label.sif" "$raw_root/$label-big.sif" "$label" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
old_mesh = f"raw/fixtures/{sys.argv[3]}-elmer"
if source.count(old_mesh) != 2 or source.count('Linear System Direct Method = UMFPack') != 1:
    raise SystemExit('unexpected round-7 SIF structure')
source = source.replace(old_mesh, f"raw/fixtures/{sys.argv[3]}-big-elmer")
source = source.replace('Linear System Direct Method = UMFPack',
                        'Linear System Direct Method = Big Umfpack')
Path(sys.argv[2]).write_text(source)
PY

ulimit -Ss 65520
ulimit -Ss > "$raw_root/$label-big-stack-kb.txt"
set +e
/usr/bin/time -l env ELMER_HOME="$solver_root" "$solver_root/bin/ElmerSolver" \
  "$raw_root/$label-big.sif" > "$raw_root/$label-big.log" \
  2> "$raw_root/$label-big-time.log"
result=$?
set -e
print "$result" > "$raw_root/$label-big-exit.txt"
exit "$result"
