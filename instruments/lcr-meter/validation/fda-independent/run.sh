#!/bin/sh
set -eu
cd "$(dirname "$0")"
task_fda_build=$(mktemp -d "${TMPDIR:-/tmp}/temper-lcr-fda.XXXXXX")
trap 'rm -rf "$task_fda_build"' EXIT HUP INT TERM
rustc --edition=2021 -O run.rs -o "$task_fda_build/run"
"$task_fda_build/run" > results.txt
