#!/usr/bin/env python3
"""Round 5 addendum: the enclosure's as-modelled R34 layout (gap at r 84-92 so the J5 centre lead can
drop through it). Coupling by the same FEM as coupling.py; rows are APPENDED to outputs/coupling.json
and coupling.csv as geometry 'd228_gap84', with f_k/f_r against the same reference (basis_d180, 200 mm).

As modelled by the enclosure session (R33 study 09 follow-up): inner spiral r 27.4-82.6 (14.4 turns),
outer r 93.4-112.6 (4.5 turns), 18.9 turns total, bundle Ø2.7; 8 ferrite bars 20 x 4 mm, r 32-118.
Turn shares are 14.4/18.9 and 4.5/18.9 (series, same current). ASSUMED/COMPARATIVE as coupling.py.
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs"
sys.path.insert(0, str(HERE))
import coupling as C  # noqa: E402

G = "d228_gap84"
SECS = [(27.4, 82.6, 14.4 / 18.9), (93.4, 112.6, 4.5 / 18.9)]
FERRITE_R = (32.0, 118.0)


def build(enclosure=True, pan_d_mm=None, mu_pan=100.0):
    m = C.MultiCoil(C.R_GRID, C.Z_GRID)
    fm = m.box(FERRITE_R[0] * C.mm, FERRITE_R[1] * C.mm, 0.0935, 0.0975)
    p = np.minimum(1.0, 8 * 0.020 / (2 * np.pi * m.RC))
    m.mur[fm] = (1 + p * (C.MU_FERRITE - 1))[fm]
    if enclosure:
        m.add_conductor("base", 0.0, 0.221, 0.008, 0.011, C.SIG_AL5052)
        m.add_conductor("roof_ring", 0.158, 0.221, 0.102, 0.105, C.SIG_AL5052)
    if pan_d_mm:
        m.add_conductor("pan", 0.0, pan_d_mm / 2000, 0.110, 0.112, C.SIG_STEEL, mu_pan)
    m.set_sections(SECS)
    return m


def main():
    res = json.loads((OUT / "coupling.json").read_text())
    res["rows"] = [r for r in res["rows"] if r["geom"] != G]
    L1f = build(False).solve(C.F)["L"]
    L1i = build(True).solve(C.F)["L"]
    gi = {"sections_mm": SECS, "ferrite_r_mm": FERRITE_R, "L_per_turn2_free_uH": L1f * 1e6,
          "L_per_turn2_installed_uH": L1i * 1e6, "installed_over_free": L1i / L1f,
          "turns_for_70uH_free": math.sqrt(70e-6 / L1f), "turns_for_80uH_free": math.sqrt(80e-6 / L1f),
          "L_installed_at_18.9_turns_uH": L1i * 18.9 ** 2 * 1e6, "pans": {}}
    ref = res["geoms"][C.REF[0]]["pans"]
    for D in C.PAN_D_MM:
        for mu in C.MU_PANS:
            s = build(True, D, mu).solve(C.F)
            kl, r = s["L"] / L1i, s["R"] / (L1i * 1e6)
            gi["pans"][f"{D}_{int(mu)}"] = {"kl": kl, "r_ohm_per_uH": r}
            rr = ref[f"{C.REF[1]}_{int(mu)}"]
            res["rows"].append({"geom": G, "pan_d_mm": D, "mu_pan": mu, "kl": round(kl, 4),
                                "one_minus_kl": round(1 - kl, 4), "r_ohm_per_uH": round(r, 5),
                                "f_k": round((1 - kl) / (1 - rr["kl"]), 4),
                                "f_r": round(r / rr["r_ohm_per_uH"], 4)})
            print(G, D, mu, round(kl, 4), round(r, 5), flush=True)
    res["geoms"][G] = gi
    (OUT / "coupling.json").write_text(json.dumps(res, indent=1) + "\n")
    with open(OUT / "coupling.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res["rows"][0].keys()))
        w.writeheader()
        w.writerows(res["rows"])
    print({k: v for k, v in gi.items() if k != "pans"})


if __name__ == "__main__":
    main()
