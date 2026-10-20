#!/bin/sh
set -eu
cd "$(dirname "$0")"
rustc --edition=2021 simulate.rs -o /private/tmp/temper-lcr-spice-simulate
/private/tmp/temper-lcr-spice-simulate
/opt/homebrew/bin/ngspice -b model-smoke.cir > model-smoke.log 2>&1
/opt/homebrew/bin/ngspice -b fda.cir > fda.log 2>&1
if rg -i 'error|aborted|timestep too small' model-smoke.log fda.log; then
    exit 1
fi
rustc --edition=2021 analyze.rs -o /private/tmp/temper-lcr-spice-analyze
/private/tmp/temper-lcr-spice-analyze
