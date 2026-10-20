#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export NGSPICE=${NGSPICE:-ngspice}
MODE=${1:---check}
case "$MODE" in --check|--full) ;; *) echo 'Usage: ./rerun.sh [--check|--full]' >&2; exit 2;; esac
for tool in op_guard filter_seed make_cases verify_nominal corner_pulse cm_step summarize_corners make_rev_c extended_pulse long_tail check_saved; do
    rustc --edition=2021 -O "$tool.rs" -o "$tool"
done
if [ "$MODE" = --full ]; then
    "$NGSPICE" -b klu-offset-op.cir > klu-offset-op.log 2>&1
    ./op_guard base-offset-op.raw
    ./filter_seed base-offset-op.raw strict-no-probes.cir offset-nodeset.inc
    ./make_cases
    ./make_rev_c
    for deck in pulse5k_*.cir; do
        "$NGSPICE" -b "$deck" > "${deck%.cir}.log" 2>&1
    done
    ./corner_pulse
    ./cm_step
    ./extended_pulse
    ./long_tail
fi
./op_guard
./verify_nominal
./summarize_corners
./check_saved
