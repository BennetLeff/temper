#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f candidate-artifacts.sha256 bolted-candidate-checks.json fastener-access-checks.json
CAD_PYTHON=${TEMPER_CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
"$CAD_PYTHON" -u bolted_candidate.py > bolted.log 2>&1
"$CAD_PYTHON" fastener_access.py > fastener-access.log 2>&1
sh finalize_candidate.sh
