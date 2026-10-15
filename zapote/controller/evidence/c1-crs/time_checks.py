#!/usr/bin/env python3
"""Wall time of the slow verifier sections (review aid)."""
import json
import sys
import time
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(UNIT / "tools"))
import verify_controller as vc  # noqa: E402
from netlist import attach_resolved, read_netlist  # noqa: E402

nl = attach_resolved(read_netlist(UNIT / "frozen/default.net"), UNIT / "frozen/resolved-components.json")
calcs = json.loads((UNIT / "evidence/controller_calcs.json").read_text())
for name, fn in (("trip", lambda r: vc.check_trip(r, nl, calcs)), ("capmode", lambda r: vc.check_capmode(r, nl, calcs))):
    rep = vc.Report()
    t0 = time.time()
    fn(rep)
    print(name, round(time.time() - t0, 1), "s", rep.failed)
