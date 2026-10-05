#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f results/integration-inputs.sha256
mkdir -p results
work=$(mktemp -d "${TMPDIR:-/tmp}/temper-r7-fixture-integration.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
cad_python=${CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
mechanical_dir=${1:-../mechanical}
"$cad_python" integrate.py "$mechanical_dir" > results/integration.txt
shasum -a256 integrate.py integrate.sh integration.json results/integration.txt > "$work/receipt"
mv "$work/receipt" results/integration-inputs.sha256
