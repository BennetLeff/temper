#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f artifacts.sha256 capture-checks.json process-witness-checks.json attachment-checks.json
CAD_PYTHON=${TEMPER_CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
"$CAD_PYTHON" -c 'import sys, cadquery; print(sys.version); print("CadQuery", cadquery.__version__)' > environment.txt
"$CAD_PYTHON" -u check_capture.py > run.log 2>&1
"$CAD_PYTHON" build_witness.py > witness.log 2>&1
"$CAD_PYTHON" inspect_joints.py > attachment.log 2>&1
sh finalize.sh
