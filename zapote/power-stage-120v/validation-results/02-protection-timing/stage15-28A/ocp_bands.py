#!/usr/bin/env python3
"""Stage 15 (28 A tank ceiling): shunt-OCP divider R34/R35 and CT reference dividers R43-R46.

Mirrors the committed method exactly:
  * band before the Kelvin shift: task-02 round-3 `thresholds.py` exact_corners() at -10 and +85 C, R5 +50 C,
    imported read-only with PARTS patched in memory (as bom-simplification/calc_protection_bands.py does);
  * Kelvin shift: e_th from kelvin/budget-native21s14.json (census and all-at-max-transfer bound) times
    dI/de_th = -2(1-k)/R5 (kelvin/README sensitivity; -1.029 A/mV at k = 11.7/24.1, plane-native21s14.json);
  * LM4040 cathode current: audit.rs::min_reference_cathode_current_ua with the new R34 + R35 (>= 80 uA).
New requirement inputs (read from committed files, nothing hard-coded beyond the round-6 margin rule):
  * envelope peak at 28 A: round6 outputs/board-side-protection.csv (59.17 A);
  * coil-pickup stack: coil-pickup/sensitivity.json at 31.1 A pk / 31 kHz, SCALED by max(I_pk * f) over the
    round-6 28 A grid cases (EMF = j w Phi, Phi ~ I). DECISIONS item 9's 3.0 A is the unscaled 22 A / 31 kHz value.
  * +2 A detection margin (round-6 board_side.py rule).
usage: python3 ocp_bands.py [UNIT]   -> out/ocp_bands.json, prints tables
Nothing under UNIT is written (bytecode writing is disabled for the import).
"""
from __future__ import annotations

import csv
import glob
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
UNIT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
VR = UNIT / "validation-results"
spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = dict(m.PARTS)
RT = (0.001, 25e-6)          # Yageo RT0603BRD07 / Vishay TNPW..BE: 0.1 %, 25 ppm (thresholds.py RT)
RC = (0.01, 100e-6)

# E96 decade (IEC 60063)
E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43, 1.47, 1.50,
       1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
       2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57,
       3.65, 3.74, 3.83, 3.92, 4.02, 4.12, 4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
       5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45,
       8.66, 8.87, 9.09, 9.31, 9.53, 9.76]


def band(over, key):
    m.PARTS.clear(); m.PARTS.update(BASE); m.PARTS.update(over)
    out = {t: m.exact_corners(t, 50.0)[key] for t in (-10.0, 85.0)}
    m.PARTS.clear(); m.PARTS.update(BASE)
    return min(b["min"] for b in out.values()), max(b["max"] for b in out.values())


def cathode_ua(r34r35, bias_ohm=5600.0):
    """audit.rs::min_reference_cathode_current_ua with R34 + R35 = r34r35."""
    ref_max = 2.520
    i_bias = (4.75 - ref_max) / (bias_ohm * 1.01)
    return (i_bias - (ref_max + 0.15) / (20e3 * 0.999) - ref_max / (r34r35 * 0.999) - ref_max / (150e3 * 0.999)) * 1e6


def requirement():
    prot = {float(r["I_max_A"]): r for r in csv.DictReader(
        open(VR / "05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv"))}
    pk28 = float(prot[28.0]["tank_pk_max_A"])
    pk22 = float(prot[22.0]["tank_pk_max_A"])
    sens = json.loads((VR / "02-protection-timing/coil-pickup/sensitivity.json").read_text())
    key = "pan_bars_31kHz_45Apk|kelvin_A|cluster_drawn|x1.5"
    s = sens[key]
    ref_if = (22.0 * 2 ** 0.5) * 31e3      # loops.py I_ACT x F0
    scale = {}
    for I in (22, 28):
        best = (0.0, None)
        for f in glob.glob(str(VR / f"05-resonant-tank-envelope/round6-full-power/outputs/grid6-d228_gap84-L70-C050-I{I}-pan*-cases.csv")):
            for r in csv.DictReader(open(f)):
                try:
                    v = float(r["i_tank_pk_a"]) * float(r["freq_hz"])
                except (ValueError, KeyError):
                    continue
                if v > best[0]:
                    best = (v, r["case"], float(r["i_tank_pk_a"]), float(r["freq_hz"]))
        scale[I] = {"factor": best[0] / ref_if, "case": best[1], "i_pk_A": best[2], "f_hz": best[3]}
    stacks = {}
    for I in (22, 28):
        k = scale[I]["factor"]
        stacks[I] = {"model_A": s["model"] * k, "fem_phase_A": s["bound_fem_phase"] * k, "any_phase_A": s["bound_any_phase"] * k}
    return pk22, pk28, s, scale, stacks


def kelvin():
    b = json.loads((VR / "02-protection-timing/kelvin/budget-native21s14.json").read_text())
    return b["e_th_mV"], b["bound_all_at_max_transfer"]["e_th_mV"]


def shunt_case(r34, r35, e_census, e_bound):
    lo, hi = band({"R34": (r34, *RT), "R35": (r35, *RT)}, "shunt_a")
    k = r35 / (r34 + r35)
    a_per_mv = -2 * (1 - k)                       # A per mV at R35.2 with R5 = 1 mOhm
    th = 2.5 * k
    return {"R34": r34, "R35": r35, "thresh_V": round(th, 5), "nominal_A": round((2.5 - 2 * th) / 1e-3, 2),
            "band_before_A": [round(lo, 2), round(hi, 2)], "a_per_mV": round(a_per_mv, 4),
            "band_after_census_A": [round(lo + e_census * a_per_mv, 2), round(hi, 2)],
            "band_after_bound_A": [round(lo + e_bound * a_per_mv, 2), round(hi, 2)],
            "thevenin_ohm": round(r34 * r35 / (r34 + r35)), "cathode_uA_min": round(cathode_ua(r34 + r35), 1)}


def ct_case(r_hi_top, r_hi_bot, r_lo_top, r_lo_bot):
    over = {"R43": (r_hi_top, *RT), "R44": (r_hi_bot, *RT), "R45": (r_lo_top, *RT), "R46": (r_lo_bot, *RT)}
    pos = band(over, "ct_pos_a")
    neg = band(over, "ct_neg_a")
    nom_hi = 3.3 * r_hi_bot / (r_hi_top + r_hi_bot)
    return {"R43": r_hi_top, "R44": r_hi_bot, "R45": r_lo_top, "R46": r_lo_bot,
            "ref_hi_V": round(nom_hi, 4), "nominal_A": round((nom_hi - 1.65) / 0.015, 2),
            "pos_band_A": [round(pos[0], 2), round(pos[1], 2)], "neg_band_A": [round(neg[0], 2), round(neg[1], 2)]}


def main():
    pk22, pk28, s, scale, stacks = requirement()
    e_c, e_b = kelvin()
    margin = 2.0
    floors = {
        "A_decisions_unscaled_3A": pk28 + 3.0 + margin,
        "B_fem_phase_scaled": pk28 + stacks[28]["fem_phase_A"] + margin,
        "C_any_phase_scaled": pk28 + stacks[28]["any_phase_A"] + margin,
    }
    print(f"envelope peak 22 A {pk22}  28 A {pk28}")
    for I in (22, 28):
        print(f"pickup scale {I} A: x{scale[I]['factor']:.3f} at {scale[I]['case']}; stacks "
              + ", ".join(f"{k} {v:.2f}" for k, v in stacks[I].items()))
    print("floors:", {k: round(v, 2) for k, v in floors.items()})
    print(f"Kelvin e_th census {e_c} mV, bound {e_b} mV")

    # validation: reproduce today's committed band (49.53-97.77 before shift, 47.33 after)
    base = shunt_case(12.4e3, 11.7e3, e_c, e_b)
    print("baseline 12.4k/11.7k:", base)

    # candidate scan: R35 kept at 11.7 k (stocked TNPW) with R34 from E96 and E192 near; and E96 x E96 pairs
    e192_extra = [11.8, 11.9, 12.0, 12.1, 12.2, 12.3, 12.5, 12.6, 12.8, 12.9, 13.0, 13.2, 13.3]
    cands = []
    for r34k in sorted(set([v * 10 for v in E96 if 1.15 <= v <= 1.35] + e192_extra)):
        cands.append((r34k * 1e3, 11.7e3, "R35 kept 11.7k"))
    for r35 in [v * 10 for v in E96 if 1.00 <= v <= 1.30]:
        for r34 in [v * 10 for v in E96 if 1.00 <= v <= 1.40]:
            k = r35 / (r34 + r35)
            nom = (2.5 - 5 * k) / 1e-3
            if 80 <= nom <= 110:
                cands.append((r34 * 1e3, r35 * 1e3, "E96 pair"))
    rows = []
    seen = set()
    for r34, r35, tag in cands:
        if (round(r34), round(r35)) in seen:
            continue
        seen.add((round(r34), round(r35)))
        k = r35 / (r34 + r35)
        nom = (2.5 - 5 * k) / 1e-3
        if not (70 <= nom <= 115):
            continue
        c = shunt_case(r34, r35, e_c, e_b)
        c["tag"] = tag
        for fk, fv in floors.items():
            c["meets_" + fk] = c["band_after_bound_A"][0] >= fv
        rows.append(c)
    rows.sort(key=lambda r: r["band_before_A"][1])
    print(f"\n{'R34':>7s} {'R35':>7s} {'nom':>7s} {'min_bef':>7s} {'min_aft':>7s} {'max':>7s} {'Ik uA':>6s} A B C  tag")
    for r in rows:
        print(f"{r['R34']:7.0f} {r['R35']:7.0f} {r['nominal_A']:7.2f} {r['band_before_A'][0]:7.2f} "
              f"{r['band_after_bound_A'][0]:7.2f} {r['band_after_bound_A'][1]:7.2f} {r['cathode_uA_min']:6.1f} "
              f"{'Y' if r['meets_A_decisions_unscaled_3A'] else '-'} {'Y' if r['meets_B_fem_phase_scaled'] else '-'} "
              f"{'Y' if r['meets_C_any_phase_scaled'] else '-'}  {r['tag']}")
    best = {}
    for fk in floors:
        ok = [r for r in rows if r["meets_" + fk] and r["cathode_uA_min"] >= 80]
        best[fk] = {"single_change_R35_kept": min((r for r in ok if r["R35"] == 11.7e3), key=lambda r: r["band_before_A"][1], default=None),
                    "any_pair": min(ok, key=lambda r: r["band_before_A"][1], default=None)}
    print("\nbest per floor:")
    for fk, v in best.items():
        for kk, r in v.items():
            if r:
                print(f"  {fk:28s} {kk:22s} R34 {r['R34']:.0f} R35 {r['R35']:.0f}: after-shift band "
                      f"{r['band_after_bound_A'][0]}-{r['band_after_bound_A'][1]} A, nominal {r['nominal_A']}")

    # CT reference dividers: keep 10 k legs (R44/R45), change the 3.32 k legs (R43/R46), E96 0.1 %
    ct_rows = [ct_case(3.32e3, 10e3, 10e3, 3.32e3)]
    for v in [1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32, 2.37, 2.43, 2.49, 2.55]:
        ct_rows.append(ct_case(v * 1e3, 10e3, 10e3, v * 1e3))
    print(f"\n{'R43=R46':>8s} {'REF_HI':>7s} {'nom':>6s} {'pos band':>16s} {'neg band':>16s}")
    for r in ct_rows:
        print(f"{r['R43']:8.0f} {r['ref_hi_V']:7.4f} {r['nominal_A']:6.2f} {str(r['pos_band_A']):>16s} {str(r['neg_band_A']):>16s}")

    res = {"status": "ASSUMED / bounded calc (task-02 round-3 corner model, unchanged)", "unit": str(UNIT),
           "envelope_peak_A": {"22": pk22, "28": pk28},
           "pickup_ref": {"key": "pan_bars_31kHz_45Apk|kelvin_A|cluster_drawn|x1.5", **s},
           "pickup_scale": scale, "pickup_stacks_A": stacks, "floors_A": floors,
           "kelvin_e_th_mV": {"census": e_c, "bound": e_b},
           "baseline_12k4_11k7": base, "shunt_candidates": rows, "best": best, "ct_candidates": ct_rows}
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/ocp_bands.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
