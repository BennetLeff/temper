#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f artifacts.sha256
CAD_PYTHON=${TEMPER_CAD_PYTHON:-/private/tmp/temper-center-sensor-env/bin/python}
"$CAD_PYTHON" - <<'PY'
import hashlib
import json
from pathlib import Path

import check_capture

a = json.loads(Path("capture-checks.json").read_text())
b = json.loads(Path("process-witness-checks.json").read_text())
c = json.loads(Path("attachment-checks.json").read_text())
valid = (
    a["status"] == "PASS_NOMINAL_GEOMETRY" and not a["failures"]
    and len(a["sampled_states"]) == 21
    and b["status"] == "PASS_NOMINAL_PROCESS_WITNESS_GEOMETRY"
    and len(b["witnesses"]) == 2
    and c["status"] == "OPEN_UPWARD_TENSION_JOINT"
    and len(c["checks"]) == 9
)
exports = [s["export"] for s in a["sampled_states"] if "export" in s] + b["witnesses"]
valid = valid and len(exports) == len({e["step"] for e in exports}) == 8
valid = valid and all(hashlib.sha256(Path(e["step"]).read_bytes()).hexdigest() == e["sha256"] for e in exports)
valid = valid and all(x["source_sha256"] == check_capture.PINS for x in (a, b, c))
if not valid:
    raise SystemExit("Incomplete or inconsistent mechanical evidence; no receipt issued")
PY
shasum -a 256 check_capture.py build_witness.py inspect_joints.py run.sh finalize.sh README.md capture-checks.json process-witness-checks.json attachment-checks.json environment.txt run.log witness.log attachment.log P9-569-OPEN-100.step P9-569-OPEN-150.step R9-M222_control_010-island_02.step R9-M222_control_010-carrier_02.step R9-M222_thin_0075-island_02.step R9-M222_thin_0075-carrier_02.step R9-IST308_thin_0075-island_02.step R9-IST308_thin_0075-carrier_02.step > artifacts.sha256
