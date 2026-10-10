#!/usr/bin/env python3
"""Round 5: round-4 tank grid (1710 W request, 108/120/140 V, all five pan classes x low/nom/high
corners) re-run for candidate coil geometries (R34 two-section r 26-114 vs R32 uniform r 22-116), on the 0.50 uF bank (5 x TDK B32654A1104K000).

ASSUMED. The load model, envelope, solver and ngspice deck are round 4's, imported unchanged
(../round4-assumed-basis/scripts/run_grid.py: solve(), sim(), tank_basis.cir). What changes:

  * pan classes: round 4's (basis.py PANS) rescaled per geometry and pan diameter with the FEM
    coupling ratios of scripts/coupling.py (central mu = 100):
        kl' = 1 - (1 - kl) * f_k        r40' = r40 * f_r
  * L0 is the INSTALLED no-pan inductance (R32: 66.34 uH), not round 4's 70 uH design value;
  * coil R_ac at 40 kHz is absolute (not per uH): low 0.168 ohm (onsemi q 0.0024 x 70 uH, cold),
    nom 0.21 ohm, high 0.25 ohm (the accepted R32 requirement, winding at 100 C); R ~ f^0.55;
  * bank 0.50 uF (DECISIONS 2026-10-09).

Usage: run_grid5.py [--configs a,b,...] [--workers 4]
Writes outputs/grid5-<config>-cases.csv and outputs/grid5-configs.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
R4 = ROOT.parent / "round4-assumed-basis" / "scripts"
sys.path.insert(0, str(R4))
import run_grid as RG  # noqa: E402  (round 4, unchanged)
import basis as B4  # noqa: E402

C_BANK = 0.50e-6
L_INST = 66.34
LINES = [108.0, 120.0, 140.0]
P_REQ = 1710.0
R_COIL_40K = {"low": 0.168, "nom": 0.21, "high": 0.25}
MU = "100"

# name: (geometry, pan diameter mm, installed L0 uH)
CONFIGS = {
    "basis-d180-pan200": ("basis_d180", 200, L_INST),
    # R34 candidate: two-section r 26-68 / gap / r 76-114 (enclosure R33 study 09)
    "d228-2sec-pan180": ("d228_2sec", 180, L_INST),
    "d228-2sec-pan220": ("d228_2sec", 220, L_INST),
    "d228-2sec-pan260": ("d228_2sec", 260, L_INST),
    # R32 uniform winding r 22-116
    "d240-pan180": ("d240_cont", 180, L_INST),
    "d240-pan220": ("d240_cont", 220, L_INST),
    "d240-pan260": ("d240_cont", 260, L_INST),
    # L-target sweep on the R34 geometry; 53 and 70 also bracket the Control Freak estimate
    "d228-L53-pan220": ("d228_2sec", 220, 53.0),
    "d228-L58-pan220": ("d228_2sec", 220, 58.0),
    "d228-L75-pan220": ("d228_2sec", 220, 75.0),
    "d228-L82-pan220": ("d228_2sec", 220, 82.0),
    # Ø210 (ruled out by cooling, R33 study 09): one comparison row
    "d210-2sec-pan220": ("d210_2sec", 220, L_INST),
    # Addendum: as-modelled R34 with the gap at r 84-92 (scripts/addendum_gap84.py); 70 uH (66.5 installed,
    # enclosure study 09) and the 80 uH alternate (~76 installed); plus the r 68-76 case at 76 uH to compare
    "gap84-pan180": ("d228_gap84", 180, 66.5),
    "gap84-pan220": ("d228_gap84", 220, 66.5),
    "gap84-pan260": ("d228_gap84", 260, 66.5),
    "gap84-L76-pan180": ("d228_gap84", 180, 76.0),
    "gap84-L76-pan220": ("d228_gap84", 220, 76.0),
    "gap84-L76-pan260": ("d228_gap84", 260, 76.0),
    "d228-L76-pan180": ("d228_2sec", 180, 76.0),
    "d228-L76-pan220": ("d228_2sec", 220, 76.0),
    "d228-L76-pan260": ("d228_2sec", 260, 76.0),
}

def factors(geom, pan_d):
    rows = json.loads((ROOT / "outputs" / "coupling.json").read_text())["rows"]
    for r in rows:
        if r["geom"] == geom and r["pan_d_mm"] == pan_d and str(int(r["mu_pan"])) == MU:
            return r["f_k"], r["f_r"]
    raise KeyError((geom, pan_d))


def pan_params(pan, which, l0, fk, fr):
    i = {"nom": 0, "low": 1, "high": 2}[which]
    kl = 1 - (1 - pan["kl40"][i]) * fk
    return {"L0U": l0, "KL40": kl, "BETA": B4.COIL["beta_kl"][0], "Q40": R_COIL_40K[which] / l0,
            "GAMMA": B4.COIL["gamma_coil"][0], "R40": pan["r40"][i] * fr, "ALPHA": pan["alpha"]}


def build_cases(cfg):
    geom, pan_d, l0 = CONFIGS[cfg]
    fk, fr = factors(geom, pan_d)
    cases = []
    for name, pan in B4.PANS.items():
        for which in ("low", "nom", "high"):
            p = pan_params(pan, which, l0, fk, fr)
            for V in LINES:
                cases.append({"id": f"{cfg}|{name}-{which}-{int(V)}v", "pan": name, "corner": which,
                              "p": p, "C": C_BANK, "V": V, "P_req": P_REQ})
    return cases, fk, fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    assert a.workers <= 4, "rule: at most 4 parallel ngspice workers"
    meta = {}
    for cfg in a.configs.split(","):
        cases, fk, fr = build_cases(cfg)
        t0 = time.time()
        with Pool(a.workers) as pool:
            rows = list(pool.imap(RG.solve, cases))
        for r in rows:
            r["config"] = cfg
        with open(ROOT / "outputs" / f"grid5-{cfg}-cases.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["config"] + [k for k in rows[0] if k != "config"])
            w.writeheader()
            w.writerows(rows)
        geom, pan_d, l0 = CONFIGS[cfg]
        meta[cfg] = {"geom": geom, "pan_d_mm": pan_d, "L0_installed_uH": l0, "f_k": fk, "f_r": fr,
                     "C_bank_uF": C_BANK * 1e6, "n_cases": len(rows),
                     "n_sims": sum(r["n_sims"] for r in rows), "t_s": round(time.time() - t0)}
        print(cfg, meta[cfg], flush=True)
    p = ROOT / "outputs" / "grid5-configs.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(meta)
    p.write_text(json.dumps(old, indent=1) + "\n")


if __name__ == "__main__":
    main()
