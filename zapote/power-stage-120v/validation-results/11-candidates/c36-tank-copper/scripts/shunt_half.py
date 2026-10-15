#!/usr/bin/env python3
"""Candidate 36, option R5 -> 0.5 mOhm: what the OCP / Kelvin / pickup gates do with Bourns CSS2H-2512R-L500F.

    python3 -I shunt_half.py   -> ../results/shunt_half.json

Part (Bourns CSS2H-2512 REV. 06/17/20 p.1, the ledger's copy, sha256 ae54630a6a212aae): CSS2H-2512R-L500x 0.5 mOhm,
6 W at 70 C terminal / 3 W at 130 C, TCR +/-100 ppm/C including the copper terminals, -55..+170 C, same 2512 Kelvin land
and footprint as the fitted -1L00F (5 W / 3 W, +/-75 ppm/C).
Method (the committed one, stage17-r5/ocp_band17.py): task-02 round-3 thresholds.py exact_corners() at -10 and +85 C
ambient with R5 +50 K, R32 = R33 = 10 k, LM4040 +/-20 mV, comparator Vos +/-4 mV, input bias; the threshold divider
R34 / R35 (0.1 %, 25 ppm) re-chosen from E192 for the nominal trip of the fitted 1 mOhm / 12.6 k / 11.7 k design.
Control: the fitted tuple reproduces kelvin_budget.BAND_BEFORE (69.89, 116.44).
Kelvin shift: the s38 census e_th (budget-native21s38.json) times dI/de_th = -(2 - 2k) / Rs (kelvin_plane.py).
Pickup: run_ocp.py converts every loop EMF to amps through 1/Rs (KEL = 1.03 A/mV, node / threshold 2 A/mV at 1 mOhm),
so the same EMF on the same copper gives twice the amps.
"""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VR = HERE.parents[2]
spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RT = (0.001, 25e-6)
E192 = [100, 101, 102, 104, 105, 106, 107, 109, 110, 111, 113, 114, 115, 117, 118, 120, 121, 123, 124, 126, 127, 129,
        130, 132, 133, 135, 137, 138, 140, 142, 143, 145, 147, 149, 150, 152, 154, 156, 158, 160, 162, 164, 165, 167,
        169, 172, 174, 176, 178, 180, 182, 184, 187, 189, 191, 193, 196, 198]   # 100..198 (E192 decade, as used)
L500 = (0.0005, 0.01, 100e-6)
FLOOR = 64.17      # kelvin_budget.FLOOR (59.17 A envelope peak + 3.0 A pickup stack + 2 A)
GATE_PICKUP = 6.5  # scorecard ocp_pickup_stack_pan60_A gate


def band(shunt, r34, r35):
    m.PARTS.update({"R5": shunt, "R34": (r34, *RT), "R35": (r35, *RT)})
    r = [m.exact_corners(t, 50.0)["shunt_a"] for t in (-10.0, 85.0)]
    nominal = m.thresholds({k: v[0] for k, v in m.PARTS.items()}, 2.5, 0.0)[0]
    return round(min(x["min"] for x in r), 2), round(max(x["max"] for x in r), 2), round(nominal, 3)


def main():
    ctrl = band(m.SHUNT_CSS2H, 12.6e3, 11.7e3)
    assert ctrl[:2] == (69.89, 116.44), ctrl
    target = ctrl[2]
    best = []
    for r35 in (11.7e3, 11.8e3, 12.0e3, 12.1e3):
        for d in range(2):
            for v in E192:
                r34 = v * 10 ** (2 + d)
                if not 10e3 <= r34 <= 14e3:
                    continue
                k = r35 / (r34 + r35)
                nom = (2.5 * (1 - 2 * k)) / L500[0]
                if nom > 0:
                    best.append((abs(nom - target), r34, r35, nom))
    best.sort()
    rows = []
    for _, r34, r35, _ in best[:4]:
        lo, hi, nom = band(L500, r34, r35)
        rows.append({"R34": r34, "R35": r35, "band_before_kelvin_A": [lo, hi], "nominal_A": nom})
    pick = rows[0]
    k = pick["R35"] / (pick["R34"] + pick["R35"])
    s38 = json.loads((VR / "02-protection-timing/kelvin/budget-native21s38.json").read_text())
    plane = json.loads((VR / "02-protection-timing/kelvin/plane-native21s38.json").read_text())
    a_per_mv_1m = plane["trip_shift_A_per_mV_at_R35_2"]
    a_per_mv = -(2 - 2 * k) / L500[0] / 1000.0
    shift = s38["e_th_mV"] * a_per_mv
    shift_bound = s38["bound_all_at_max_transfer"]["e_th_mV"] * a_per_mv
    # the divider that meets the 64.17 A floor after the bound Kelvin shift with the lowest upper edge
    floor_opt = None
    for _, r34, r35, nom in sorted(best, key=lambda t: t[3]):
        if nom < FLOOR:
            continue
        lo_, hi_, nom_ = band(L500, r34, r35)
        kk = r35 / (r34 + r35)
        if lo_ + s38["bound_all_at_max_transfer"]["e_th_mV"] * (-(2 - 2 * kk) / L500[0] / 1000.0) >= FLOOR:
            floor_opt = {"R34": r34, "R35": r35, "band_before_kelvin_A": [lo_, hi_], "nominal_A": nom_,
                         "upper_edge_vs_fitted_A": round(hi_ - ctrl[1], 2)}
            break
    pk = json.loads((VR / "02-protection-timing/coil-pickup/s21b/result-s38.json").read_text())
    row = pk["rows"]["f60|pan_bars_31kHz_45Apk|base_A|cluster_drawn"]
    lo = pick["band_before_kelvin_A"][0]
    out = {
        "part": {"mpn": "CSS2H-2512R-L500F", "R_mohm": 0.5, "tol": 0.01, "tcr_ppm": 100, "P_70C_term_W": 6.0,
                 "P_130C_term_W": 3.0, "T_max_C": 170, "source": "Bourns CSS2H-2512 REV. 06/17/20 p.1 (ledger copy, sha256 ae54630a...)"},
        "control_fitted_1mohm": {"R34": 12.6e3, "R35": 11.7e3, "band_before_kelvin_A": list(ctrl[:2]), "nominal_A": ctrl[2]},
        "divider_options": rows,
        "picked": pick,
        "kelvin": {"e_th_mV_s38": s38["e_th_mV"], "A_per_mV_1mohm": a_per_mv_1m, "A_per_mV_0p5mohm": round(a_per_mv, 4),
                   "trip_shift_A": round(shift, 3), "trip_shift_bound_A": round(shift_bound, 3),
                   "band_after_A": [round(lo + shift, 2), pick["band_before_kelvin_A"][1]],
                   "floor_A": FLOOR, "meets_floor": lo + shift >= FLOOR, "meets_floor_at_bound": lo + shift_bound >= FLOOR,
                   "band_after_1mohm_s38_A": s38["band_after_A"]},
        "floor_meeting_divider": floor_opt,
        "pickup": {"stack_any_phase_x1p5_A_1mohm": round(row["stack_any_phase_x1p5_A"], 3),
                   "stack_any_phase_x1p5_A_0p5mohm": round(2 * row["stack_any_phase_x1p5_A"], 3), "gate_A": GATE_PICKUP,
                   "passes": 2 * row["stack_any_phase_x1p5_A"] <= GATE_PICKUP},
        "r5_power_W": {"c22_23p1A": round(23.1 ** 2 * 0.5e-3, 3), "c28_29p4A": round(29.4 ** 2 * 0.5e-3, 3),
                       "c22_1mohm": round(23.1 ** 2 * 1e-3, 3), "c28_1mohm": round(29.4 ** 2 * 1e-3, 3)},
        "sense_signal_at_trip_mV": {"0p5mohm": round(pick["nominal_A"] * 0.5, 1), "1mohm": round(ctrl[2], 1),
                                    "vos_equivalent_A_0p5mohm": round(2 * 4e-3 / 0.5e-3, 1), "vos_equivalent_A_1mohm": round(2 * 4e-3 / 1e-3, 1)},
    }
    (HERE.parent / "results").mkdir(exist_ok=True)
    (HERE.parent / "results/shunt_half.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
