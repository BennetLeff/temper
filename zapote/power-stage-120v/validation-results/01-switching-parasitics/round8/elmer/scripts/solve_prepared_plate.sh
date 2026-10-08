#!/bin/zsh
set -euo pipefail

if (( $# != 1 )); then
  print -u2 'usage: solve_prepared_plate.sh label'
  exit 2
fi
label="$1"
[[ "$label" =~ '^plates-box0p25-far12-m(20|40|80)$' ]] || { print -u2 'unexpected plate label'; exit 2; }
raw_root="$PWD/raw/fixtures"
elmer_root=/tmp/ps-r6-fem-elmer-install
test -f "$raw_root/$label.sif"
test -f "$raw_root/$label-source.json"
test ! -e "$raw_root/$label.log"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
ulimit -Ss 65520
ulimit -Ss > "$raw_root/$label-stack-kb.txt"
set +e
/usr/bin/time -l env ELMER_HOME="$elmer_root" "$elmer_root/bin/ElmerSolver" \
  "$raw_root/$label.sif" > "$raw_root/$label.log" \
  2> "$raw_root/$label-time.log"
result=$?
set -e
print "$result" > "$raw_root/$label-exit.txt"
exit "$result"
