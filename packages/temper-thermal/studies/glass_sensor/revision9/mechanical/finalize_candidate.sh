#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f candidate-artifacts.sha256
CAD_PYTHON=${TEMPER_CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
"$CAD_PYTHON" - <<'PY'
import hashlib
import json
from pathlib import Path

import check_capture

a = json.loads(Path("bolted-candidate-checks.json").read_text())
b = json.loads(Path("fastener-access-checks.json").read_text())
valid = (a["status"] == "PASS_NOMINAL_BOLTED_CANDIDATE" and not a["failures"]
         and len(a["states"]) == 3 and b["status"] == "PASS_MINIMUM_FASTENER_ACCESS_GEOMETRY"
         and len(b["checks"]) == 9 and len(b["sequential_bracket_with_other_fasteners"]) == 18
         and not any(r["hits"] for r in b["checks"] + b["sequential_bracket_with_other_fasteners"]))
exports = [s["export"] for s in a["states"]]
valid = valid and all(hashlib.sha256(Path(e["step"]).read_bytes()).hexdigest() == e["sha256"] for e in exports)
valid = valid and all(x["source_sha256"] == check_capture.PINS for x in (a, b))
if not valid:
    raise SystemExit("Incomplete or inconsistent candidate evidence; no receipt issued")
PY
shasum -a 256 bolted_candidate.py fastener_access.py check_capture.py run_candidate.sh finalize_candidate.sh bolted-candidate.md bolted-candidate-checks.json fastener-access-checks.json bolted.log fastener-access.log C9-BOLTED-M222-control-rest.step C9-BOLTED-M222-control-combined.step C9-BOLTED-M222-control-housing-capture.step > candidate-artifacts.sha256
