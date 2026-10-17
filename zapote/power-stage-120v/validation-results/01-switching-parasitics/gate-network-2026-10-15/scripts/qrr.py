#!/usr/bin/env python3
"""Body-diode reverse recovery of each device model in the datasheet fixture (round17 D3 deck, read-only),
to place each model's recovery charge against its datasheet (typ / max) before trusting its S4 dv/dt.

Fixture = validation-results/01-switching-parasitics/round17/delegation/out-D3/recovery.cir (400 V, clamped inductive,
equal gate resistors RG on the DUT and the switch). D3's metrics (terminal current zero crossing, peak, 10 % end).
Cases: CFD7 018 at its Table 7 condition (IF 58.2 A, RG 730 ohm, D3's ~100 A/us calibration; control: D-24 TT 50 ns
gives Qrr 1.739 uC); the CFD7 018 at TT 125 ns (control: 2.356 uC); IPW60R016CM8 (C8 600 V vendor model) and the
CM8W proxy at the IPW65R018CM8 Table 7 condition (IF 29.7 A, 100 A/us), RG swept to bracket 100 A/us.

python3 -I qrr.py [--workers 1]  -> ../results/qrr.json
"""
import argparse
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("gn", HERE / "gn.py")
gn = importlib.util.module_from_spec(_s)
_s.loader.exec_module(gn)
D3 = gn.PS / "validation-results/01-switching-parasitics/round17/delegation/out-D3"
OUT = HERE.parent / "sims" / "_qrr"


def deck(model: str, tt: str | None = None, c8tt: str | None = None) -> str:
    t = (D3 / "recovery.cir").read_text()
    assert t.count("IPW65R018CFD7_L1") == 2
    extra = ""
    if tt and model == "IPW65R018CFD7_L1":
        tech = gn.subckt_text("cool_tech_w3").replace(".SUBCKT cool_tech_w3 ", ".SUBCKT cool_tech_w3_tt ").replace(
            ".PARAM  fpar20=50e-9", f".PARAM  fpar20={tt}")
        dev = gn.subckt_text("IPW65R018CFD7_L1").replace(".SUBCKT IPW65R018CFD7_L1", ".SUBCKT DUT_TT").replace(
            "cool_tech_w3 PARAMS", "cool_tech_w3_tt PARAMS")
        extra, name = tech + "\n" + dev, "DUT_TT"
    elif model == "CM8W_L1":
        extra, name = gn.cm8_wrapper(), "CM8W_L1"
    elif model == "IPW60R016CM8_L1":
        tech = gn.subckt_text("cool_C8_600_var", gn.C8LIB)
        if c8tt:
            tech = tech.replace(".PARAM  fpar19=25e-9", f".PARAM  fpar19={c8tt}")
        extra, name = tech + "\n" + gn.subckt_text(model, gn.C8LIB), model
    else:
        name = model
    t = t.replace("IPW65R018CFD7_L1", name)
    return t.replace(".include IFX_CFD7_650V.lib", ".include IFX_CFD7_650V.lib\n" + extra, 1)


def crossing(t, y, level, start, rising):
    c = np.where((y[start:-1] < level) & (y[start + 1:] >= level) if rising else
                 (y[start:-1] > level) & (y[start + 1:] <= level))[0]
    k = start + int(c[0])
    return float(t[k] + (level - y[k]) * (t[k + 1] - t[k]) / (y[k + 1] - y[k])), k + 1


def metrics(w):
    t = np.array(w["time"])
    cur = np.array(w["i(vprobe)"])
    start = int(np.searchsorted(t, 2e-6))
    zero, k = crossing(t, cur, 0, start, True)
    p = k + int(np.argmax(cur[k:]))
    end, e = crossing(t, cur, cur[p] * .1, p, False)
    tt = np.r_[zero, t[k:e], end]
    ii = np.r_[0, cur[k:e], cur[p] * .1]
    m = (t > zero - 20e-9) & (t < zero + 20e-9)
    return dict(Irrm_A=float(cur[p]), Qrr_uC=float(np.trapezoid(ii, tt) * 1e6), trr_ns=(end - zero) * 1e9,
                slew_A_per_us=float(np.polyfit(t[m] - zero, cur[m], 1)[0] / 1e6),
                forward_A=float(-np.interp(1.9e-6, t, cur)))


def one(job):
    tag, model, tt, ifwd, rg, tj = job
    out = OUT / tag
    out.mkdir(parents=True, exist_ok=True)
    p = out / "recovery.cir"
    p.write_text(deck(model, tt, c8tt=(tt if model == "IPW60R016CM8_L1" else None)))
    r = gn.run_d2.run(p, {"RG": str(rg), "TJ": str(tj), "STEP": "0.2n", "IFWD": str(ifwd)}, keep=out, raw=True)
    row = {"tag": tag, "model": model, "tt": tt, "IF_A": ifwd, "RG": rg, "TJ": tj, "aborted": r["aborted"]}
    if not r["aborted"]:
        w = gn.run_d2.read_raw(out / "waves.raw") if hasattr(gn.run_d2, "read_raw") else None
        if w is None:
            sys.path.insert(0, str(gn.run_d2.KIT / "common"))
            from run_ngspice import read_raw
            w = read_raw(out / "waves.raw")
        row.update(metrics(w))
        (out / "waves.raw").unlink(missing_ok=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    jobs = [("cfd7_018_tt50_cal730", "IPW65R018CFD7_L1", None, 58.2, 730, 25),
            ("cfd7_018_tt125_cal730", "IPW65R018CFD7_L1", "125e-9", 58.2, 730, 25)]
    for model, nm in (("IPW60R016CM8_L1", "c8_016"), ("CM8W_L1", "cm8w")):
        for rg in (400, 730, 1000, 1400):
            jobs.append((f"{nm}_rg{rg}", model, None, 29.7, rg, 25))
    for tt in ("60e-9", "80e-9"):
        for rg in (400, 730):
            jobs.append((f"c8_016_tt{tt[:2]}_rg{rg}", "IPW60R016CM8_L1", tt, 29.7, rg, 25))
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, jobs))
    ref = {"IPW65R018CFD7 Rev 2.0 Table 7 (400 V, 58.2 A, 100 A/us, 25 C)": {"Qrr_uC": [2.30, 4.60], "trr_ns": [236, 354], "Irrm_A": [15, None]},
           "IPW65R018CM8 Rev 2.1 Table 7 (400 V, 29.7 A, 100 A/us, 25 C)": {"Qrr_uC": [1.54, 2.31], "trr_ns": [180, 225], "Irrm_A": [16.4, None]},
           "IPW60R016CM8 Rev 2.1 Table 7 (same condition)": {"Qrr_uC": [1.54, 2.31], "trr_ns": [180, 225], "Irrm_A": [16.4, None]},
           "D-24 map (control)": {"TT50_Qrr_uC": 1.73882, "TT125_Qrr_uC": 2.35560}}
    (HERE.parent / "results" / "qrr.json").write_text(json.dumps({"datasheet": ref, "rows": rows}, indent=1) + "\n")
    for r in rows:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
