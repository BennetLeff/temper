#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
cd "$root"
base=zapote/power-stage-120v/prototype-closure/round4/coupled-model
out=${1:?Provide a fresh output directory}
case_name=${2:-all}
model=${3:-$base/reduced.cir}
rustc --edition=2021 --test "$base/runner.rs" -o /private/tmp/temper-r4-model-tests
/private/tmp/temper-r4-model-tests
rustc --edition=2021 --test "$base/coordination.rs" -o /private/tmp/temper-r4-coordination-tests
/private/tmp/temper-r4-coordination-tests
rustc --edition=2021 -O "$base/runner.rs" -o /private/tmp/temper-r4-model
/private/tmp/temper-r4-model "$out" "$case_name" "$model"
