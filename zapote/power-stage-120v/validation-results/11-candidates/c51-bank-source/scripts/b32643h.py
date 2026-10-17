#!/usr/bin/env python3
"""Lead 1: TDK B32643H8104J000 (B3264*H, 100 nF, 2000 V DC / 700 V AC, 22.5 mm) from the vendor datasheet.

    python3 -I scripts/b32643h.py   -> results/b32643h.json + .md (exit 1 on a failed control)

Source: dl/B32643H/mmkp_b32641h_b32643h.pdf (TDK 'B3264*H', June 2026, 39 pp., supplied by the owner;
sha256 69b56e62c56032229f60dd419c301ba16028da245fcbd56dc440abcf4f8ad663). Charts are vector; rendered with
pdftoppm -r 600 and cropped (render/b3264h/):
  p.19 'Permissible current IRMS versus frequency' 2000 V DC / 700 V AC, 22.5 mm (KMK2906-D), sinusoidal,
       TA = 85 C, dT <= 20 C. crop (2600, 2600, 4500, 3700): x 1e3 / 1e4 / 1e5 / 1e6 Hz at 91.5 / 678.5 / 1264.5 /
       1851.5 px; y 100 / 10 / 1 / 0.1 / 0.01 A at 87.5 / 310.5 / 533.5 / 756.5 / 979.5 px. Curves are ~9 px lines; the
       100 nF and 120 nF curves overlap in the top band from ~10 kHz up (band 15-17 px). 100 nF is the LOWER line of the
       top band: centre = band bottom - 4 px. (Identification: at 100 kHz the band's two line centres read 9.6 / 9.1 A
       = the p.13 table's 120 nF 9.64 A / 100 nF 9.17 A at 85 C.)
  p.21 'Permissible AC voltage VRMS versus frequency' 2000 V, 22.5 mm (KMK2617-9), TA <= 85 C, dT <= 15 C (as printed):
       crop as above; x 1e3..1e6 at 102.5 / 688.5 / 1274.5 / 1861 px; y 1000 / 100 / 10 V at 107.5 / 553.5 / 999.5 px.
       100 nF is the lowest curve. Used as a control on the IRMS read (I = V w C).
  p.22 F_T(TA) (KMK2907-G): crop (520, 1800, 2120, 3800): x 40 / 125 C at 55.5 / 1536.5 px; y 1.3 / 0 at 58 / 1956 px.
  p.13 table (2000 V row, 100 nF): 14.5 x 29.5 x 26.5 mm; IRMS,max 100 kHz 11.03 A at TA 60 C (self-heating <= 30 C),
       9.17 A at TA 85 C (<= 20 C); ESRtyp 10.9 mOhm at 100 kHz. p.15: TR 105 C, Top,max 125 C (case), upper category
       110 C; tan d <= 0.3e-3 (1 kHz), <= 1.0e-3 (100 kHz); VR 2000 V DC / 700 V AC at 105 C, 1.25 %/C derating 105-125 C;
       AEC-Q200D, IEC 60384-16. p.16: dV/dt 3800 V/us, k0 15e6 V^2/us (22.5 mm, 2000 V). p.2: 55/110/56, case UL 94 V-0.
       p.24: damp heat 85 C / 85 % RH at VR,DC and at VR,AC, 1000 h (THB grade).
Self-heating rule (p.18 / p.22): IRMS(TA) = IRMS(85 C) x F_T(TA); i.e. dT_allowed = 20 K x F_T(TA)^2, Top = TA + dT <=
125 C. Checks as bank_air_cand.py / decision_inputs.py, with this rule added as type 'tdk_ft'.
Controls: (1) chart 100 nF at 100 kHz vs the 9.17 A table value within 3 %; (2) Vrms chart I = V w C within 5 % of the
IRMS chart at 35 and 40 kHz; (3) F_T(85) within 0.02 of 1.00 and F_T(60) within 3 % of the table's 11.03 / 9.17;
(4) bank_air_cand's c34 gate 0.967 reproduced through the same path.
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
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
J = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s49/c49/b3-bank-air/jetmix"
REL = ("/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/validation-results/04-board-current-thermal/"
       "round5-native21/b3-ratings/runs")
RND = ROOT / "render/b3264h"
FREQS = (20e3, 30e3, 35e3, 40e3, 50e3, 70e3, 100e3)
STEPS = (18.0, 20.0, 22.0, 24.0, 26.0, 28.0)


def runs(a, x, y0, y1):
    out, s = [], None
    for i in range(y0, y1):
        v = a[i, x]
        if v and s is None:
            s = i
        if (not v) and s is not None:
            out.append((s, i - 1))
            s = None
    return [(p, q) for p, q in out if q - p >= 4]


def read_irms():
    a = np.asarray(Image.open(RND / "h2000_irms_600.png").convert("L")) < 128
    X = lambda f: 678.5 + 586.7 * math.log10(f / 1e4)
    A = lambda y: 10 * 10 ** (-(y - 310.5) / 223.0)
    out = {}
    for f in FREQS:
        vals = []
        for dx in (-8, -5, 5, 8):
            r = runs(a, int(round(X(f))) + dx, 290, 560)
            if r:
                p, q = r[0]                                  # the top band (100 + 120 nF)
                vals.append(A(q - 4))
        out[f"{f / 1e3:g}k"] = round(float(np.median(vals)), 3)
    return out


def read_vrms():
    a = np.asarray(Image.open(RND / "h2000_vrms_600.png").convert("L")) < 128
    X = lambda f: 688.5 + 586.2 * math.log10(f / 1e4)
    V = lambda y: 10 ** (3 - (y - 107.5) / 446.0)
    out = {}
    for f in (35e3, 40e3):
        vals = []
        for dx in (-5, 5):
            r = [(p, q) for p, q in runs(a, int(round(X(f))) + dx, 150, 440) if q - p <= 13]
            if r:
                p, q = r[-1]                                 # the lowest curve = 100 nF
                vals.append(V((p + q) / 2))
        out[f"{f / 1e3:g}k"] = round(float(np.median(vals)), 1)
    return out


def read_ft():
    a = np.asarray(Image.open(RND / "ft_600.png").convert("L")) < 128
    X = lambda T: 55.5 + (T - 40) * (1536.5 - 55.5) / 85
    F = lambda y: (1956 - y) / 146 * 0.1
    pts = []
    for T in range(40, 125, 5):
        vals = []
        for dx in (-12, 12):
            x = int(round(X(T))) + dx
            for p, q in runs(a, x, 0, a.shape[0]):
                if q - p >= 7 and 0.05 < F((p + q) / 2) < 1.3:
                    vals.append(F((p + q) / 2))
        pts.append((float(T), round(float(np.mean(vals)), 3)))
    pts.append((125.0, 0.0))
    return pts


def main():
    irms, vrms, ft = read_irms(), read_vrms(), read_ft()
    FT = lambda t: ft[0][1] if t <= ft[0][0] else next(y0 + (y1 - y0) * (t - x0) / (x1 - x0)
                                                       for (x0, y0), (x1, y1) in zip(ft, ft[1:]) if x0 <= t <= x1) if t < 125 else 0.0
    fails = []
    if abs(irms["100k"] / 9.17 - 1) > 0.03:
        fails.append(f"IRMS chart 100 kHz {irms['100k']} vs table 9.17")
    vi = {k: round(v * 2 * math.pi * float(k[:-1]) * 1e3 * 100e-9, 3) for k, v in vrms.items()}
    for k in vi:
        if abs(vi[k] / irms[k] - 1) > 0.05:
            fails.append(f"Vrms chart {k}: {vi[k]} A vs IRMS chart {irms[k]} A")
    ft85, ft60 = FT(85.0), FT(60.0)
    if abs(ft85 - 1) > 0.02 or abs(ft60 / (11.03 / 9.17) - 1) > 0.03:
        fails.append(f"F_T controls: F_T(85) {ft85:.3f}, F_T(60) {ft60:.3f} vs {11.03 / 9.17:.3f}")

    orig = bac.dT_allowed

    def dT_allowed(c, ta, tpad):
        if c["rule"]["type"] == "tdk_ft":
            return c["dT_v"] * FT(ta) ** 2
        return orig(c, ta, tpad)
    bac.dT_allowed = dT_allowed
    c = {"id": "b32643h", "mpn": "B32643H8104J000", "n": 5, "C_nF": 100, "tol": 0.05, "w": 14.5, "h": 29.5, "l": 26.5,
         "pitch": 15.0, "gap_mm": 0.5, "dT_v": 20.0, "I35": irms["35k"], "I40": irms["40k"], "rule": {"type": "tdk_ft"},
         "top_max": 125.0}
    enc = json.loads((PS / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    e20 = enc["jetmix_base"]["h20"][bac.PATH]
    v0, rise0 = e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"]
    p61, _ = bac.pads_from(f"{J}/bay61/c28_h20_jet100_p0p25.json", f"{J}/bay61/c28_h20_jet100_p0p5.json", 61)
    p55, _ = bac.pads_from(f"{J}/bay55/c28_h15_jet100_p0p25.json", f"{J}/bay55/c28_h15_jet100_p0p5.json", 55)
    prel, srel = bac.pads_from(f"{REL}/c17.5_h10_p0p25.json", f"{REL}/c17.5_h10_p0p5.json", 61)
    pts = [("@61 h20", 61, v0, rise0, p61), ("@55 h15", 55, v0, rise0, p55)]
    s = bac.share(c)

    def gate(i, gap):
        bac.I_TANK = i
        g, rows = bac.run_forced(c, pts, gap_credit=gap, pad_heat=False, k_pad=0.0, p_ref=0.0)
        bac.I_TANK = 28.0
        return g, rows
    g28, rows28 = gate(28.0, False)
    gg28, _ = gate(28.0, True)
    steps = []
    for i in STEPS:
        gs, _ = gate(i, False)
        gg, _ = gate(i, True)
        vr = i * s / c["I35"]
        steps.append({"I_tank_A": i, "vendor_85C": round(vr, 3), "gate": gs["eff"], "gate_gap": gg["eff"],
                      "strict_ok": gs["passes"] and vr <= 0.85, "gap_ok": gg["passes"] and vr <= 0.85})
    rel = {f"{i:g} A": bac.run_still(c, prel, 61, i, 0.0, 0.0, False) for i in (bac.I_REL_TRIP, bac.I_REL)}
    # control 4: c34 through the same (patched) path
    cands = json.loads((ROOT / "data/candidates.json").read_text())["candidates"]
    c34 = dict(next(x for x in cands if x["id"] == "c34"))
    c34.setdefault("gap_mm", round(c34["pitch"] - c34["w"], 2))
    bac.I_TANK = 28.0
    g34, _ = bac.run_forced(c34, pts, gap_credit=False, pad_heat=False, k_pad=0.0, p_ref=0.0)
    if abs(g34["eff"] - 0.967) > 0.002:
        fails.append(f"c34 control {g34['eff']}")
    # voltage rows (as voltage_rows.py; C unchanged 0.50 uF J)
    BV = json.loads((ROOT / "data/bank-voltage-s49.json").read_text())
    f3 = max(r["F3_V"] for r in BV["rows"] if r["reading"] in ("R0", "R1"))
    f3a = max(r["F3_V"] for r in BV["rows"])
    z0 = max(r["Z0max_x_top_V"] for r in BV["rows"])
    vc125 = 2000 * (1 - 0.0125 * (125 - 105))
    volt = {"V 28 A <= 0.8 VR": round(566 / 2000 / 0.8, 3), "no-pan <= 0.8 VC(125 C)": round(775 / vc125 / 0.8, 3),
            "Vrms <= 0.8 VRMS": round(268 / 700 / 0.8, 3), "F3 R0/R1 <= 0.85 VR": round(f3 / 1700, 3),
            "F3 any <= VR": round(f3a / 2000, 3), "Z0 x top <= VR": round(z0 / 2000, 3), "dV/dt": round(BV["dVdt"]["V_per_us"] / 3800, 3)}
    t_air = {"@61": 61 + rise0, "@55": 55 + rise0}
    ta_worst = g28["worst"]["T_A_C"]
    out = {"pdf_sha256": "69b56e62c56032229f60dd419c301ba16028da245fcbd56dc440abcf4f8ad663",
           "irms_chart_100nF_A": irms, "vrms_chart_100nF_V": vrms, "vrms_as_current_A": vi, "F_T": ft,
           "controls": {"irms_100k_over_table_9.17": round(irms["100k"] / 9.17, 3), "F_T_85": round(ft85, 3),
                        "F_T_60_vs_table_ratio": [round(ft60, 3), round(11.03 / 9.17, 3)], "c34_gate": g34["eff"], "failed": fails},
           "V_allow_35k_Vrms": round(irms["35k"] / (2 * math.pi * 35e3 * 100e-9), 1),
           "share": round(s, 4), "I_part_28A_A": round(28 * s, 3),
           "vendor_ratio_85C_35k": round(28 * s / irms["35k"], 3), "vendor_ratio_85C_40k": round(28 * s / irms["40k"], 3),
           "vendor_ratio_FT_credited_at_air": {k: round(28 * s / (irms["35k"] * FT(t)), 3) for k, t in t_air.items()},
           "vendor_ratio_FT_credited_at_bank_air_T_A": round(28 * s / (irms["35k"] * FT(ta_worst)), 3),
           "tank_A_at_0.85_85C": round(0.85 * irms["35k"] / s, 2),
           "bank_air_28A_strict": g28, "bank_air_28A_gap": gg28["eff"], "steps": steps,
           "highest_step_strict": max([x["I_tank_A"] for x in steps if x["strict_ok"]], default=None),
           "highest_step_gap": max([x["I_tank_A"] for x in steps if x["gap_ok"]], default=None),
           "release": {k: {"rad": v["with_radiation"]["eff"], "norad": v["no_radiation"]["eff"],
                           "T_op_rad": v["with_radiation"]["T_op_C"]} for k, v in rel.items()},
           "release_pads_board": srel["p0p25"][1][:8], "voltage_rows": volt}
    (ROOT / "results/b32643h.json").write_text(json.dumps(out, indent=1) + "\n")
    L = [f"B32643H8104J000 (datasheet {out['pdf_sha256'][:16]}):",
         f"- IRMS chart 100 nF (TA 85 C, dT <= 20 K): {irms}",
         f"- Vrms chart 100 nF (dT <= 15 K as printed): {vrms} -> I = {vi}",
         f"- F_T: {ft}",
         f"- V_allow(35 kHz) {out['V_allow_35k_Vrms']} V (need >= 331); share {out['share']}, I part {out['I_part_28A_A']} A",
         f"- vendor ratio at 85 C: 35k {out['vendor_ratio_85C_35k']}, 40k {out['vendor_ratio_85C_40k']} (<= 0.85 needed); "
         f"tank A at 0.85: {out['tank_A_at_0.85_85C']}",
         f"- vendor ratio with F_T at the air temperature (info): {out['vendor_ratio_FT_credited_at_air']}; at bank_air worst T_A "
         f"{ta_worst} C: {out['vendor_ratio_FT_credited_at_bank_air_T_A']}",
         f"- bank_air 28 A strict {g28['eff']} (T_op max {g28['T_op_max_C']} C, worst {g28['worst']['position']} {g28['worst']['point']}), "
         f"gap credit {gg28['eff']}",
         f"- steps: " + "; ".join(f"{x['I_tank_A']:g} A v{x['vendor_85C']} g{x['gate']}/{x['gate_gap']}" for x in steps),
         f"- highest step strict {out['highest_step_strict']} / gap {out['highest_step_gap']}",
         f"- release: {out['release']} (pads board {out['release_pads_board']})",
         f"- voltage rows: {volt}",
         f"- controls: {out['controls']}"]
    (ROOT / "results/b32643h.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
