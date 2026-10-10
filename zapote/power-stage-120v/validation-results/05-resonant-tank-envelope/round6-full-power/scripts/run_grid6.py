#!/usr/bin/env python3
"""Round 6 ngspice grid: round 4's solver/deck (unchanged), round 5's per-geometry pan classes, swept over the
tank RMS ceiling, the coil inductance and the bank. ASSUMED.

Per configuration: 5 pan classes x low/nom/high corners x 108/120/140 V, 1710 W request (45 cases). Each case
bisects (10 Hz) to the LOWEST frequency in [max(35 kHz, 1.05 f_res), 60 kHz] that keeps the line-cycle tank RMS
<= the ceiling and P <= 11.1 A x 0.93 x V (round 4 envelope). Above resonance power falls monotonically with f,
so this is the maximum-power operating point the limits allow.

Usage: run_grid6.py [--set all|ceiling|bank|alt] [--only name,name] [--workers 4]
Writes outputs/grid6-<config>-cases.csv and outputs/grid6-configs.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from multiprocessing import Pool

import common6 as M


def cfg_name(geom, lfree, c_uf, imax, pan_d):
    return f"{geom}-L{lfree}-C{int(round(c_uf * 100)):03d}-I{int(imax)}-pan{pan_d}"


def configs(which):
    out = {}
    if which in ("all", "ceiling"):
        for lfree in (70, 80, 90):
            for imax in M.CEILINGS:
                for d in M.PAN_D:
                    out[cfg_name(M.GEOM, lfree, 0.50, imax, d)] = (M.GEOM, lfree, 0.50, imax, d)
    if which in ("all", "bank"):
        for lfree, c in ((70, 0.40), (80, 0.40), (80, 0.45), (90, 0.40)):
            for imax in (22.0, 26.0):
                out[cfg_name(M.GEOM, lfree, c, imax, 220)] = (M.GEOM, lfree, c, imax, 220)
    if which in ("all", "alt"):
        for imax in (22.0, 26.0):
            out[cfg_name(M.GEOM_ALT, 70, 0.50, imax, 220)] = (M.GEOM_ALT, 70, 0.50, imax, 220)
    return out


def build_cases(cfg, spec):
    geom, lfree, c_uf, imax, pan_d = spec
    l0 = M.L_INSTALLED[lfree]
    fk, fr = M.coupling(geom, pan_d)
    cases = []
    for name, pan in M.B4.PANS.items():
        for which in ("low", "nom", "high"):
            p = M.pan_params(pan, which, l0, fk, fr)
            for V in M.LINES:
                cases.append({"id": f"{cfg}|{name}-{which}-{int(V)}v", "pan": name, "corner": which, "p": p,
                              "C": c_uf * 1e-6, "V": V, "P_req": M.P_REQ, "imax": imax})
    return cases, fk, fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="all")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()
    assert a.workers <= 4, "rule: at most 4 parallel ngspice workers"
    cfgs = configs(a.set)
    if a.only:
        cfgs = {k: v for k, v in cfgs.items() if k in a.only.split(",")}
    metap = M.OUT / "grid6-configs.json"
    meta = json.loads(metap.read_text()) if metap.exists() else {}
    with Pool(a.workers) as pool:
        for cfg, spec in cfgs.items():
            path = M.OUT / f"grid6-{cfg}-cases.csv"
            if a.skip_done and path.exists():
                continue
            cases, fk, fr = build_cases(cfg, spec)
            t0 = time.time()
            rows = list(pool.imap(M.solve_case, cases))
            for r in rows:
                r["config"] = cfg
            with open(path, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["config"] + [k for k in rows[0] if k != "config"])
                w.writeheader()
                w.writerows(rows)
            geom, lfree, c_uf, imax, pan_d = spec
            meta[cfg] = {"geom": geom, "L_free_uH": lfree, "L0_installed_uH": M.L_INSTALLED[lfree], "C_bank_uF": c_uf,
                         "I_tank_max_A": imax, "pan_d_mm": pan_d, "f_k": fk, "f_r": fr, "n_cases": len(rows),
                         "n_sims": sum(r["n_sims"] for r in rows), "t_s": round(time.time() - t0)}
            metap.write_text(json.dumps(meta, indent=1) + "\n")
            print(cfg, meta[cfg], flush=True)


if __name__ == "__main__":
    main()
