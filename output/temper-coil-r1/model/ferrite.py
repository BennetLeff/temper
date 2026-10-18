"""Ferrite bar flux density against saturation, and core loss, from the 3D discrete-bar solves (fem3d).

B per amp (peak B per peak A) comes from the 3D results for the chosen 80 uH layout (free80_h0.7, pan80_430_h0.7) and for
R43 (free_h0.5, pan430_h0.7). The bars are linear in the model (mu 2500), so B scales with current until the material
nears saturation; above ~0.8 Bs the real L falls and B is overstated by the linear model (the bench pulse test decides).
Currents (peak at the line crest):
  firmware ceiling c -> line-RMS tank current c, crest peak 2.17 c (tank_freq.h TANK_PEAK_PER_RMS, round 6)
  firmware peak trip min(2.17 c + 3, 62) A; CT trip band 64.55-76.09 A (stage 15); spec row 7 asks 98 A (stage-13 band)
Saturation: TDK PC95 typical Bs 410 mT at 100 C, 530 mT at 25 C (TDK ferrite material characteristics; cited in
docs/evidence/2026-10-10-coil-manufacturing-review.md). The bars bought are SELLER-labelled PC95: unverified.
Core loss: Steinmetz Pv = k f^1.4 B^2.6, anchored at 350 kW/m^3 at 100 kHz / 200 mT / 100 C (TDK PC95 class; ESTIMATE
+-50 %), time-averaged over the line cycle (|sin| envelope: <|sin|^2.6> = 0.452). Bar volume 10 x 90 x 15 x 5 = 67.5 cm^3.
Run: .venv/bin/python model/ferrite.py -> model/results/ferrite.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R3 = HERE / "fem3d" / "results"
BS100, BS25 = 0.410, 0.530
PV0, F0, B0, ALPHA, BETA = 350e3, 100e3, 0.200, 1.4, 2.6
SIN_AVG = float(np.mean(np.abs(np.sin(np.linspace(0, np.pi, 20001))) ** BETA))
BAR_VOL_PER_BIN = 10 * 7.5e-3 * 15e-3 * 5e-3       # 10 bars x 7.5 mm radial bin x 15 x 5 mm


def per_amp(case):
    d = json.loads((R3 / f"{case}.json").read_text())
    return d["B_bar_max_mT_per_A"] * 1e-3, d["bar_profile"]


def core_loss(profile, I_pk, f):
    P = 0.0
    for b in profile:
        B = b["B_mean_mT_per_A"] * 1e-3 * I_pk
        w = (b["r_mm"][1] - b["r_mm"][0]) / 7.5
        P += PV0 * (f / F0) ** ALPHA * (B / B0) ** BETA * BAR_VOL_PER_BIN * w
    return P * SIN_AVG


def main():
    out = dict(SIN_AVG=SIN_AVG, Bs_100C_T=BS100, Bs_25C_T=BS25, cases={})
    currents = {"ceiling_17.5A_crest": 2.17 * 17.5, "ceiling_24A_crest": 2.17 * 24, "ceiling_28A_crest": 2.17 * 28,
                "fw_peak_trip_cap_62A": 62.0, "CT_band_high_76A": 76.09, "spec_row7_98A": 98.0}
    for layout, free, pan in (("80uH_out6.46", "free80_h0.7", "pan80_430_h0.7"), ("R43_21.93", "free_h0.5", "pan430_h0.7")):
        for cond, case in (("no_pan", free), ("pan_430", pan)):
            bmax, prof = per_amp(case)
            rows = {}
            for k, I in currents.items():
                B = bmax * I
                rows[k] = dict(I_pk_A=I, B_max_mT=B * 1e3, frac_Bs_100C=B / BS100, frac_Bs_25C=B / BS25)
            loss = {f"{c}A_rms_{int(f / 1e3)}kHz_W": core_loss(prof, 2.0 * c, f) for c in (17.5, 28.0) for f in (35e3, 45e3, 60e3)}
            I_sat100 = BS100 / bmax
            out["cases"][f"{layout}/{cond}"] = dict(B_max_mT_per_A=bmax * 1e3, I_pk_at_Bs100_A=I_sat100,
                                                    I_pk_at_075Bs100_A=0.75 * I_sat100, points=rows, core_loss=loss)
    (HERE / "results" / "ferrite.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out["cases"].items():
        print(f"{k:24s} {v['B_max_mT_per_A']:.2f} mT/A  Bs(100C) at {v['I_pk_at_Bs100_A']:.0f} A pk, 0.75 Bs at {v['I_pk_at_075Bs100_A']:.0f} A pk; "
              + ", ".join(f"{p}: {r['B_max_mT']:.0f} mT ({r['frac_Bs_100C']:.2f})" for p, r in v["points"].items()))
        print("     core loss", {kk: round(vv, 1) for kk, vv in v["core_loss"].items()})


if __name__ == "__main__":
    main()
