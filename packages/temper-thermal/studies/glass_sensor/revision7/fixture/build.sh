#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f results/cad-inputs.sha256
mkdir -p results
work=$(mktemp -d "${TMPDIR:-/tmp}/temper-r7-fixture-cad.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
cad_python=${CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
plot_python=${PLOT_PYTHON:-/Users/bennet/Miniforge3/bin/python3}
"$cad_python" build.py > results/cad-build.txt
MPLCONFIGDIR=${MPLCONFIGDIR:-/private/tmp/temper-glass-mpl} "$plot_python" draw.py
shasum -a 256 build.py draw.py build.sh geometry.json force-displacement-frame.step connected-pressure-cell.step pressure-fluid-domain.step pan-coupon-accessory.step fixture-sections.png results/cad-build.txt > "$work/receipt"
mv "$work/receipt" results/cad-inputs.sha256
