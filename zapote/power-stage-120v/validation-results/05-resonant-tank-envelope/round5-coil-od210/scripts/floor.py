#!/usr/bin/env python3
"""Loaded-inductance acceptance floor and ratio screen for the native-21 coil (spec row 3/3b, section 2).

Derivation (ASSUMED basis; all inputs printed with their source):
  1. Fixed-floor ZVS guarantee (old section-2 method, for reference):
       f_res,max = F_MIN / ZVS = 35 kHz / 1.05;  L_min = 1 / ((2 pi f_res,max)^2 C_worst)
  2. Window-top bound (the binding one for native-21, where CT_ZC enforces f >= 1.05 f_res):
       the controller must be able to hold the 22 A / 11.1 A envelope in continuous mode, i.e. reach
       x_reg = max f/f_res the grid needs, without exceeding F_MAX:
       f_res,max = F_MAX / x_reg;  L_loaded,min(population) = 1 / ((2 pi f_res,max)^2 C_worst)
  3. Transfer to the reference pan: the acceptance test uses one reference pan, not the most strongly
     coupled pan of the population. ratio_pop = kl(population min corner) / kl(reference class nominal),
     both after the Ø228 coupling rescale; L_ref,min = L_loaded,min(population) / ratio_pop.
Writes outputs/floor.json.
"""
import csv
import glob
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs"
sys.path.insert(0, str(HERE))
import run_grid5 as G  # noqa: E402

F_MIN, F_MAX, ZVS = 35e3, 60e3, 1.05
C_NOM, C_TOL = 0.50e-6, 0.10
C_WORST = C_NOM * (1 - C_TOL)
INST_OVER_FREE = 0.95  # R32 66.34/70 = 0.948; FEM d228 0.9498 (coupling.json)


def L_for(f, C):
    return 1 / ((2 * math.pi * f) ** 2 * C)


def main():
    out = {"inputs": {"F_MIN_Hz": F_MIN, "F_MAX_Hz": F_MAX, "ZVS_MARGIN": ZVS, "C_nom_uF": C_NOM * 1e6,
                      "C_tol": C_TOL, "C_worst_uF": C_WORST * 1e6, "installed_over_free": INST_OVER_FREE}}
    # 1. fixed-floor guarantee
    f1 = F_MIN / ZVS
    out["fixed_floor"] = {"f_res_max_Hz": round(f1, 1), "L_loaded_min_uH": round(L_for(f1, C_WORST) * 1e6, 2)}
    # 2. x_reg from the round-5 grid, Ø228 and Ø240 at 66.34 uH, all pan diameters (non-burst cases)
    x = 0.0
    for p in glob.glob(str(OUT / "grid5-d2[24]*-pan*-cases.csv")):
        if "-L" in Path(p).name:
            continue
        for r in csv.DictReader(open(p)):
            if r["status"] != "BURST_REQUIRED":
                x = max(x, float(r["f_over_fres"]))
    x_reg = math.ceil(x * 100) / 100
    f2 = F_MAX / x_reg
    Lpop = L_for(f2, C_WORST)
    # 3. transfer to the reference pan (Ø228 two-section on a 220-260 mm pan; f_k at 220 mm, mu 100)
    fk, _ = G.factors("d228_2sec", 220)
    kl = lambda k: 1 - (1 - k) * fk  # noqa: E731
    pans = G.B4.PANS
    kl_ref = kl(pans["cast_iron"]["kl40"][0])
    kl_ref_max = kl(pans["cast_iron"]["kl40"][2])
    kl_pop_min = min(kl(p["kl40"][1]) for p in pans.values())
    ratio_pop = kl_pop_min / kl_ref
    Lref = Lpop / ratio_pop
    out["window_top"] = {"x_reg_grid_max": round(x, 4), "x_reg_used": x_reg, "f_res_max_Hz": round(f2, 1),
                         "L_loaded_min_population_uH": round(Lpop * 1e6, 2), "f_k_d228_220mm": fk,
                         "kl_ref_cast_iron_nom": round(kl_ref, 4), "kl_ref_cast_iron_max": round(kl_ref_max, 4),
                         "kl_population_min": round(kl_pop_min, 4), "ratio_pop": round(ratio_pop, 4),
                         "L_loaded_min_reference_pan_uH": round(Lref * 1e6, 2)}
    # ratio screen relative to FREE-AIR L (what the incoming test measures first)
    rows = {}
    for Lfree in (70.0, 80.0):
        Linst = Lfree * INST_OVER_FREE
        rows[f"{int(Lfree)}uH"] = {
            "L_installed_nom_uH": round(Linst, 2),
            "L_loaded_ref_nom_uH": round(Linst * kl_ref, 2),
            "L_loaded_ref_at_minus10pct_uH": round(0.9 * Linst * kl_ref, 2),
            "passes_floor_nom": Linst * kl_ref >= Lref * 1e6,
            "passes_floor_minus10pct": 0.9 * Linst * kl_ref >= Lref * 1e6,
            "ratio_loaded_over_free_nom": round(INST_OVER_FREE * kl_ref, 3),
            "ratio_screen_low (floor at L +10 %)": round(Lref * 1e6 / (1.1 * Lfree), 3),
            "ratio_screen_high (cast-iron kl max)": round(INST_OVER_FREE * kl_ref_max, 3),
        }
    out["designs"] = rows
    (OUT / "floor.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
