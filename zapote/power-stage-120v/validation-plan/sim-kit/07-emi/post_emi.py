#!/usr/bin/env python3
"""Transfer magnitude from an emi_transfer.cir run (with --raw).

    python3 07-emi/post_emi.py <run dir>  ->  JSON {freq_hz: [...], lisn_l_db: [...], lisn_n_db: [...]}

dB is 20*log10(|V_lisn| / 1 V source). Add the source spectrum in dBuV to get
the predicted emission (see the runbook, task 07).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from run_ngspice import read_raw  # noqa: E402

w = read_raw(Path(sys.argv[1]) / "waves.raw")
f = [abs(x) for x in w["frequency"]]
db = lambda key: [round(20 * math.log10(max(abs(v), 1e-30)), 2) for v in w[key]]
print(json.dumps({"freq_hz": f, "lisn_l_db": db("v(lisn_l)"), "lisn_n_db": db("v(lisn_n)")}))
