#!/usr/bin/env python3
"""Lead 2: P37.5 2 kV 100 nF parts (TDK B32656J / B32656T / B32686A, KEMET R76UW) as 5 x 100 nF banks, plus the fit of a
column moved left (RES_A pins x 153, SW_B x 190.5) on the s51 board.

    python3 -I scripts/lead2_p375.py   -> results/lead2_p375.json + .md (exit 1 on a failed control)

Sources
  TDK B3265*A/G/J/T, June 2026 (dl/TDK_B32651_658/MKP_B32651_658.pdf, sha256 c32e3754787fa19b2e256e007c98a24755ae18eb52830cce430ffd6b177afdd3,
  the same file round 6 / c34 cite; fetched 2026-10-16 from tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf).
    p.31: 2000 V DC / 700 V AC, 37.5 mm: B32656J2104 14.0 x 25.0 x 42.0 mm, B32656T2104 24.0 x 15.0 x 42.0 mm, both IRMS 7.4 A
          (85 C, 100 kHz, dT <= 20 K), ESRtyp 25.4 mOhm (100 kHz); B32656J2683 12 x 22 x 42, 5.7 A; J2154 18 x 32.5 x 42, 9.8 A.
    p.35: TR 85 C, VDC derating 1.25 %/C above 85 C, Top,max 110 C, upper category 100 C; tan d (27 nF..0.1 uF) <= 0.8e-3
          (1 kHz), 1.0e-3 (10 kHz), 3.0e-3 (100 kHz); AEC-Q200; humidity 56 d 60 C / 95 % RH (85/85 on request).
    p.36/37: 37.5 mm, 2000 V / 700 V AC: dV/dt 700 V/us, k0 2.8e6 V^2/us.
    p.60: IRMS vs f, 37.5 mm, 2000 V DC (KMK2719-4), TA <= 85 C, dT <= 20 K: curves 68 / 150 / 330 / 560 nF (100 nF NOT
          plotted). Rendered -r 600, crop (560, 1480, 2280, 3660) = render/b3265/b32656_2000_irms_600.png; x 1e2 / 1e3 / 1e4 /
          1e5 Hz at 71.5 / 600.5 / 1129 / 1658 px; y 100 / 10 / 1 / 0.1 A at 63.5 / 741 / 1418.5 / 2096 px. Curves top-down
          560 / 330 / 150 / 68 nF.
    100 nF = ESTIMATE as c34 tdk_interp: the shape I(f)/I(100 kHz) interpolated in log C between 68 and 150 nF, times the
    p.31 table 7.4 A.
  KEMET R76UW3100SE30J: F3034_R76 p.22 row R76UW3100(1)30: 13 x 24 x 41.5 mm, P37.5, dV/dt 1500 V/us, k0 6e6, ESR 11 mOhm,
    8.4 A (100 kHz, 85 C), Rth 25 K/W; 35/40 kHz from the options28 ESR model x its 0.973 control factor (ESTIMATE; the R76
    2000 V chart plots 0.47 uF at 37.5 mm only).
  B32686A2104J000 (TDK B3268x, DigiKey 42 x 20 x 32.5 mm): body 20 mm thick, five do not fit the column; not rated here.
Stock (DigiKey in-stock list 2026-10-16 ~18:05-18:35Z, snapshots/digikey-2026-10-16.json): B32656J2104J000 413,
  B32656T2104K000 759, B32686A2104J000 410, R76UW3100SE30J 354.
Checks as b32643h.py / decision_inputs.py: vendor row at 85 C (<= 0.85; V_allow >= 331 V), bank_air 28 A strict / gap,
  steps, release 18.375 A, voltage rows. Fit: results of scripts/fit37_query.py and col2-feasibility/scripts/dist.py
  (KiCad python, read-only) on runs-native21/s51/c51/section.kicad_pcb, in fit37/.
Controls: chart 68 / 150 nF at 100 kHz within 3 % of the p.31 table (5.7 / 9.8 A); c34 gate 0.967 reproduced.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bac", ROOT / "scripts/bank_air_cand.py")
bac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bac)
o28s = importlib.util.spec_from_file_location("o28", ROOT / "scripts/options28.py")
o28 = importlib.util.module_from_spec(o28s)
o28s.loader.exec_module(o28)
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
J = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s49/c49/b3-bank-air/jetmix"
REL = ("/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/validation-results/04-board-current-thermal/"
       "round5-native21/b3-ratings/runs")
STEPS = (18.0, 20.0, 22.0, 24.0, 26.0, 28.0)
FREQS = (30e3, 35e3, 40e3, 50e3, 100e3)


def read_b32656():
    a = np.asarray(Image.open(ROOT / "render/b3265/b32656_2000_irms_600.png").convert("L")) < 128
    X = lambda f: 1129 + 528.8 * math.log10(f / 1e4)
    A = lambda y: 100 * 10 ** (-(y - 63.5) / 677.7)
    out = {}
    for f in FREQS:
        per = []
        for dx in (-6, 6):
            x = int(round(X(f))) + dx
            if x >= a.shape[1] - 1:
                x = a.shape[1] - 2
            rr, s = [], None
            for i in range(100, 1700):
                v = a[i, x]
                if v and s is None:
                    s = i
                if (not v) and s is not None:
                    if i - 1 - s >= 6:
                        rr.append(A((s + i - 1) / 2))
                    s = None
            if len(rr) >= 4:
                per.append(rr[:4])
        m = np.median(np.array(per), axis=0)
        out[f"{f / 1e3:g}k"] = {"560": round(m[0], 3), "330": round(m[1], 3), "150": round(m[2], 3), "68": round(m[3], 3)}
    return out


def main():
    cur = read_b32656()
    fails = []
    for c_nf, tab in (("68", 5.7), ("150", 9.8)):
        if abs(cur["100k"][c_nf] / tab - 1) > 0.03:
            fails.append(f"chart {c_nf} nF at 100 kHz {cur['100k'][c_nf]} vs table {tab}")
    t = math.log(100 / 68) / math.log(150 / 68)

    def i100(f):
        s68 = cur[f"{f / 1e3:g}k"]["68"] / cur["100k"]["68"]
        s150 = cur[f"{f / 1e3:g}k"]["150"] / cur["100k"]["150"]
        return 7.4 * math.exp(math.log(s68) + t * (math.log(s150) - math.log(s68)))
    r76 = {"mpn": "R76UW3100SE30J", "C_nF": 100, "ESR100k_mOhm": 11, "I100k_table_A": 8.4}
    parts = {
        "b32656j": {"mpn": "B32656J2104J000", "w": 14.0, "h": 25.0, "l": 42.0, "dT_v": 20.0,
                    "I35": i100(35e3), "I40": i100(40e3), "rule": {"type": "tdk", "end": 110.0, "span": 25.0}, "top_max": 110.0,
                    "VC_top": 1375.0, "VRMS": 700, "dvdt": 700, "k0": 2.8e6, "stock_digikey": 413, "basis": "ESTIMATE (p.60 interp, p.31 table)"},
        "r76uw3100": {"mpn": "R76UW3100SE30J", "w": 13.0, "h": 24.0, "l": 41.5, "dT_v": 20.0,
                      "I35": o28.esr_model(r76, 35e3) * o28.CTRL_FACTOR, "I40": o28.esr_model(r76, 40e3) * o28.CTRL_FACTOR,
                      "rule": {"type": "kemet", "dTlim_vs_Th": [[60, 40], [110, 0]]}, "top_max": 110.0, "VC_top": 1375.0,
                      "VRMS": 700, "dvdt": 1500, "k0": 6e6, "stock_digikey": 354, "basis": "ESTIMATE (ESR model x control factor)"},
    }
    enc = json.loads((PS / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    e20 = enc["jetmix_base"]["h20"][bac.PATH]
    v0, rise0 = e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"]
    p61, _ = bac.pads_from(f"{J}/bay61/c28_h20_jet100_p0p25.json", f"{J}/bay61/c28_h20_jet100_p0p5.json", 61)
    p55, _ = bac.pads_from(f"{J}/bay55/c28_h15_jet100_p0p25.json", f"{J}/bay55/c28_h15_jet100_p0p5.json", 55)
    prel, srel = bac.pads_from(f"{REL}/c17.5_h10_p0p25.json", f"{REL}/c17.5_h10_p0p5.json", 61)
    pts = [("@61 h20", 61, v0, rise0, p61), ("@55 h15", 55, v0, rise0, p55)]
    cands = json.loads((ROOT / "data/candidates.json").read_text())["candidates"]
    c34 = dict(next(x for x in cands if x["id"] == "c34"))
    c34.setdefault("gap_mm", round(c34["pitch"] - c34["w"], 2))
    bac.I_TANK = 28.0
    g34, _ = bac.run_forced(c34, pts, gap_credit=False, pad_heat=False, k_pad=0.0, p_ref=0.0)
    if abs(g34["eff"] - 0.967) > 0.002:
        fails.append(f"c34 control {g34['eff']}")
    BV = json.loads((ROOT / "data/bank-voltage-s49.json").read_text())
    f3 = max(r["F3_V"] for r in BV["rows"] if r["reading"] in ("R0", "R1"))
    f3a = max(r["F3_V"] for r in BV["rows"])
    z0 = max(r["Z0max_x_top_V"] for r in BV["rows"])
    out = {"chart_b32656_2000V_A": cur, "controls": {"c34_gate": g34["eff"], "failed": fails}, "parts": {}}
    for pid, p in parts.items():
        c = {"mpn": p["mpn"], "n": 5, "tol": 0.05, "w": p["w"], "h": p["h"], "l": p["l"], "pitch": 15.0,
             "gap_mm": round(15.0 - p["w"], 2), "dT_v": p["dT_v"], "I35": p["I35"], "I40": p["I40"], "rule": p["rule"],
             "top_max": p["top_max"]}
        s = bac.share(c)
        res = {"mpn": p["mpn"], "basis": p["basis"], "dims_mm": [p["w"], p["h"], p["l"]], "I35_A": round(p["I35"], 3),
               "I40_A": round(p["I40"], 3), "V_allow_35k": round(p["I35"] / (2 * math.pi * 35e3 * 1e-7), 1),
               "vendor_35k": round(28 * s / p["I35"], 3), "vendor_40k": round(28 * s / p["I40"], 3),
               "tank_A_at_0.85": round(0.85 * p["I35"] / s, 2), "stock_digikey": p["stock_digikey"]}
        steps = []
        for i in STEPS:
            bac.I_TANK = i
            g, _ = bac.run_forced(c, pts, gap_credit=False, pad_heat=False, k_pad=0.0, p_ref=0.0)
            gg, _ = bac.run_forced(c, pts, gap_credit=True, pad_heat=False, k_pad=0.0, p_ref=0.0)
            vr = i * s / p["I35"]
            steps.append({"I": i, "vendor": round(vr, 3), "gate": g["eff"], "gate_gap": gg["eff"], "T_op": g["T_op_max_C"],
                          "strict_ok": g["passes"] and vr <= 0.85, "gap_ok": gg["passes"] and vr <= 0.85})
        bac.I_TANK = 28.0
        rel = bac.run_still(c, prel, 61, bac.I_REL_TRIP, 0.0, 0.0, False)
        res.update({"gate_28A": steps[-1]["gate"], "gate_gap_28A": steps[-1]["gate_gap"], "T_op_28A": steps[-1]["T_op"],
                    "steps": steps, "highest_step_strict": max([x["I"] for x in steps if x["strict_ok"]], default=None),
                    "highest_step_gap": max([x["I"] for x in steps if x["gap_ok"]], default=None),
                    "release_rad": rel["with_radiation"]["eff"], "release_norad": rel["no_radiation"]["eff"],
                    "voltage": {"V 28 A": round(566 / 1600, 3), "no-pan": round(775 / (0.8 * p["VC_top"]), 3),
                                "Vrms": round(268 / (0.8 * p["VRMS"]), 3), "F3 R0/R1": round(f3 / 1700, 3), "F3 any": round(f3a / 2000, 3),
                                "Z0 x top": round(z0 / 2000, 3), "dV/dt": round(BV["dVdt"]["V_per_us"] / p["dvdt"], 3),
                                "k0 F3 sine (info)": round(math.pi * 2 * math.pi * 35e3 * f3 ** 2 / 1e6 / p["k0"], 3)}})
        out["parts"][pid] = res
    # fit summary from the read-only board queries
    q = json.loads((ROOT / "fit37/query.json").read_text())
    d = json.loads((ROOT / "fit37/dist.json").read_text())
    rules = {"tank": {"res_a", "sw_b", ""}, "selv": {"v3v3", "selv_gnd", "v24_raw", "n_ls"}}
    viol = []
    for r in d:
        if not r["pt"].startswith("RA_"):
            continue
        for dist, layer, net, kind in r["near"]:
            if net in rules["tank"] or layer == "HOLE":
                continue
            need = 12.6 if net in ("v3v3", "selv_gnd") else 5.0
            if dist < need:
                viol.append({"pad": r["pt"], "layer": layer, "net": net, "dist_mm": dist, "need_mm": need})
    out["fit_left_x153"] = {"board": "runs-native21/s51/c51/section.kicad_pcb (9afc509b)", "res_a_x": 153.0, "sw_b_x": 190.5,
                            "body_x": [150.75, 192.75], "violations_res_a_pins": viol,
                            "H10_hole_courtyard": next(f["box"] for f in q["fps_near"] if f["ref"] == "H10"),
                            "T1_courtyard": next(f["box"] for f in q["fps_near"] if f["ref"] == "T1"),
                            "copper_in_x145_163_band": q["copper_band"]}
    out["b32643h_26A"] = next(x for x in json.loads((ROOT / "results/b32643h.json").read_text())["steps"] if x["I_tank_A"] == 26.0)
    (ROOT / "results/lead2_p375.json").write_text(json.dumps(out, indent=1) + "\n")
    L = [f"B32656 2000 V chart (A): {cur}"]
    for pid, r in out["parts"].items():
        L.append(f"- {r['mpn']} ({r['basis']}): dims {r['dims_mm']}, I35/I40 {r['I35_A']}/{r['I40_A']} A, V_allow {r['V_allow_35k']} V, "
                 f"vendor {r['vendor_35k']}/{r['vendor_40k']}, gate 28 A {r['gate_28A']} / gap {r['gate_gap_28A']} (T_op {r['T_op_28A']}), "
                 f"steps strict {r['highest_step_strict']} / gap {r['highest_step_gap']}, release {r['release_rad']}/{r['release_norad']}, "
                 f"voltage {r['voltage']}, DigiKey {r['stock_digikey']}")
    L.append(f"- fit x153: {len(viol)} res_a pin clearance violations: " + "; ".join(
        f"{v['pad']} {v['layer']} {v['net']} {v['dist_mm']}<{v['need_mm']}" for v in viol))
    L.append(f"- B32643H at 26 A: {out['b32643h_26A']}")
    L.append(f"- controls: {out['controls']}")
    (ROOT / "results/lead2_p375.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
