#!/bin/sh
set -eu
cd "$(dirname "$0")"
task_independent_build=$(mktemp -d "${TMPDIR:-/tmp}/temper-lcr-independent.XXXXXX")
trap 'rm -rf "$task_independent_build"' EXIT HUP INT TERM
rustc --edition=2021 -O reduce.rs -o "$task_independent_build/reduce"
rm -f independent-5k_dc.dat independent-5k_e.dat independent-5k_f.dat
"${NGSPICE:-ngspice}" -b -o independent-5k.log independent-5k.cir
"$task_independent_build/reduce" independent-5k_e.dat independent-5k_f.dat 100 > results.txt
