#!/usr/bin/env python3
"""Environment check for the simulation kit. Run this first; stop if it fails.

    cd zapote/power-stage-120v/validation-plan/sim-kit
    ./models/fetch_models.sh          # once
    python3 smoke_test.py

Each case runs a kit deck with fixed parameters and compares selected results
with the reference values recorded on 2026-09-27 (ngspice 45.2, macOS arm64).
The reference values use placeholder inputs. They prove the kit works; they
are NOT design results. A mismatch beyond tolerance means the environment
differs (ngspice version, model file, options): report it instead of
continuing.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import run  # noqa: E402

CASES = [
    # (deck, params, {measure: (reference, relative tolerance)})
    ("01-switching/leg.cir", {"EVENT_ON": "0", "IL": "37"},
     {"vds_ls_die_pk": (225.6, 0.03), "vgs_hs_die_max": (0.8, 0.5), "id_ls_pk": (37.23, 0.01)}),
    ("01-switching/leg.cir", {"EVENT_ON": "0", "IL": "61"},
     {"vds_ls_die_pk": (283.0, 0.03), "id_ls_pk": (61.25, 0.01)}),
    ("01-switching/leg.cir", {"EVENT_ON": "1", "IL": "20"},
     {"vds_hs_die_pk": (553.5, 0.05), "id_ls_pk": (110.4, 0.05)}),
    ("02-chain/ct_frontend.cir", {"FREQ": "35k", "I0": "37", "SLOPE": "3e6"},
     {"t_ip_trip": (6.344e-6, 0.01), "t_pos_trip": (6.589e-6, 0.01), "sense_max": (3.794, 0.02)}),
    ("02-chain/ocp_frontend.cir", {"SLOPE": "3e6"},
     {"t_i_trip": (61 / 3e6, 0.01)}),
    ("05-tank/tank.cir", {},
     {"i_rms": (32.41, 0.02), "vc_pk": (547.1, 0.02), "p_avg": (2227, 0.03)}),
]


def check(value: float, ref: float, tol: float) -> bool:
    return abs(value - ref) <= tol * abs(ref) + 1e-12


def main() -> int:
    ok = True
    for deck, params, expect in CASES:
        res = run(KIT / deck, params)
        if res["aborted"]:
            print(f"FAIL {deck} {params}: aborted: {res['log_tail'][-2:]}")
            ok = False
            continue
        for name, (ref, tol) in expect.items():
            val = res["meas"].get(name)
            good = val is not None and check(val, ref, tol)
            ok &= good
            print(f"{'ok  ' if good else 'FAIL'} {deck} {params} {name} = {val} (ref {ref:g} +/- {tol*100:.0f} %)")
    # EMI transfer: needs --raw and the post-processor.
    tmp = Path(tempfile.mkdtemp(prefix="simkit-emi-"))
    res = run(KIT / "07-emi/emi_transfer.cir", {"MODE": "1"}, keep=tmp, raw=True)
    out = subprocess.run([sys.executable, str(KIT / "07-emi/post_emi.py"), str(tmp)], capture_output=True, text=True)
    try:
        d = json.loads(out.stdout)
        f = d["freq_hz"]
        i = min(range(len(f)), key=lambda k: abs(f[k] - 30e6))
        good = abs(d["lisn_l_db"][i] - (-54.6)) < 1.0
    except Exception as exc:          # noqa: BLE001
        good = False
        print("emi post-processing error:", exc, out.stderr[-300:])
    ok &= good
    print(f"{'ok  ' if good else 'FAIL'} 07-emi CM transfer at 30 MHz (ref -54.6 dB +/- 1 dB)")
    # Copper solver self-test (Miniforge Python with shapely/scipy).
    py = "/Users/bennet/Miniforge3/bin/python3"
    st = subprocess.run([py, str(KIT / "04-current/sheet_solver.py"), "--selftest"], capture_output=True, text=True)
    good = st.returncode == 0
    ok &= good
    print(f"{'ok  ' if good else 'FAIL'} 04-current solver self-test")
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
