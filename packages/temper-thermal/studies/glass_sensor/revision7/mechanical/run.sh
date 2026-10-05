#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f inputs.sha256
CAD_PYTHON=${CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
"$CAD_PYTHON" -c 'import cadquery; assert cadquery.__version__ == "2.6.1", cadquery.__version__'
"$CAD_PYTHON" build.py > build.log 2>&1
"$CAD_PYTHON" audit.py > audit.log 2>&1
MPLCONFIGDIR=${TMPDIR:-/private/tmp}/temper-r7-matplotlib "$CAD_PYTHON" render.py
shasum -a 256 build.py audit.py render.py run.sh README.md thermal_geometry.csv geometry.json independent-audit.json dependency-pins.json R7-*.step R7-*.svg coupon-cutaways.png > inputs.sha256
