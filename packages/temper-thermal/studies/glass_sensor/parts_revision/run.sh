#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
build=$(mktemp -d /tmp/temper-selected-parts.XXXXXX)
trap 'rm -rf "$build"' EXIT
mkdir -p results
shasum -a 256 -c source-inputs.sha256
rustfmt --check selected.rs
rustc --edition=2021 --test selected.rs -o "$build/tests"
"$build/tests" | tee results/tests.txt
rustc --edition=2021 -O selected.rs -o "$build/selected"
"$build/selected"
"${CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}" cad_revision.py
