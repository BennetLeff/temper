#!/usr/bin/env python3
"""G04 bank options: thermal margin (TDK I_RMS curve), loss and slot fit for the TDK B32654 1600 V bank.

Reuses (read-only) the digitised TDK p.57 1600 V curves committed by round 6
(05-resonant-tank-envelope/round6-full-power/outputs/tdk-p57-1600v.csv) and the round-6 worst-share rule
(common6.worst_share: one part at +tol, all others at -tol). TDK p.22/23 table values (100 kHz) are typed below.

Controls (asserted): 5 x B32654A1104 K reproduces round 6's 24.8 / 25.3 / 26.1 / 27.3 A at 35/40/45/50 kHz.
Run: python3 -I bank_options.py   -> writes ../results/bank_options.json
"""
import csv, itertools, json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VR = HERE.parents[2]                         # validation-results
CSV = VR / "05-resonant-tank-envelope/round6-full-power/outputs/tdk-p57-1600v.csv"
rows = list(csv.DictReader(open(CSV)))
CURVE = {int(k[2:-2]): [(float(r["f_hz"]), float(r[k])) for r in rows] for k in rows[0] if k.startswith("I_")}

# TDK MKP_B32651_658.pdf (6/26) p.22-23, lead spacing 27.5 mm, 1600 V DC: nF -> (body w mm, IRMS 85C 100 kHz A, ESR typ 100 kHz mOhm)
T1600 = {47: (11.0, 4.6, 38.7), 100: (14.0, 7.3, 19.3), 150: (18.0, 9.5, 13.8), 220: (21.0, 12.0, 10.3)}
SLOT_MM, GAP_MM = 81.8, 0.5                  # round6 README: slot about 81.8 mm; installed pitch 14.5 mm for 14 mm bodies


def limit(nf, f):
    pts = CURVE[nf]
    for (f0, i0), (f1, i1) in zip(pts, pts[1:]):
        if f0 <= f <= f1:
            t = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
            return math.exp(math.log(i0) + t * (math.log(i1) - math.log(i0)))
    raise ValueError(f)


def shares(parts, tol):
    """worst (highest) current share of each part: itself at +tol, others at -tol."""
    out = []
    for i, c in enumerate(parts):
        oth = sum(parts) - c
        out.append(c * (1 + tol) / (c * (1 + tol) + oth * (1 - tol)))
    return out


def evaluate(parts, tol, freqs=(35e3, 40e3, 45e3, 50e3), i_tank=28.0):
    sh = shares(parts, tol)
    res = {"parts_nF": parts, "tol": tol, "C_nom_uF": sum(parts) / 1000, "n": len(parts),
           "body_row_mm": round(sum(T1600[p][0] + GAP_MM for p in parts), 1)}
    res["fits_slot"] = res["body_row_mm"] <= SLOT_MM
    for f in freqs:
        # tank current at which the worst part reaches its p.57 85 C curve
        res[f"tank_A_at_curve_{int(f/1e3)}k"] = round(min(limit(p, f) / s for p, s in zip(parts, sh)), 1)
    f = 40e3
    res["ratio_to_curve_28A_40k"] = round(max(i_tank * s / limit(p, f) for p, s in zip(parts, sh)), 3)
    res["ratio_to_curve_29p4A_40k"] = round(max(29.4 * s / limit(p, f) for p, s in zip(parts, sh)), 3)
    # nominal-C loss (ESR typ @100 kHz is the only ESR number on the sheet; same convention as the B3 bank rows)
    ctot = sum(parts)
    res["loss_W_28A_esr100k"] = round(sum((i_tank * p / ctot) ** 2 * T1600[p][2] * 1e-3 for p in parts), 3)
    return res


def main():
    out = {"controls": {}, "baseline": {}, "enumeration": []}
    base_k = evaluate([100] * 5, 0.10)
    exp = {35e3: 24.8, 40e3: 25.3, 45e3: 26.1, 50e3: 27.3}
    for f, v in exp.items():
        got = base_k[f"tank_A_at_curve_{int(f/1e3)}k"]
        assert abs(got - v) <= 0.1, (f, got, v)
    out["controls"] = {"round6_5x100nF_K": {str(int(f/1e3)) + "k": v for f, v in exp.items()}, "reproduced": True}
    out["baseline"]["5x100nF_K(+-10%)"] = base_k
    out["baseline"]["5x100nF_J(+-5%)"] = evaluate([100] * 5, 0.05)
    # enumerate bank combinations from the 1600 V values, 0.45-0.55 uF nominal, <= 5 parts, any tolerance
    seen = []
    vals = sorted(T1600)
    for n in range(2, 6):
        for combo in itertools.combinations_with_replacement(vals, n):
            c = sum(combo)
            if not 450 <= c <= 550:
                continue
            for tol, nm in ((0.10, "K"), (0.05, "J")):
                r = evaluate(list(combo), tol)
                r["tol_code"] = nm
                seen.append(r)
    seen.sort(key=lambda r: (-r["tank_A_at_curve_35k"]))
    out["enumeration"] = seen
    out["slot_mm"] = SLOT_MM
    # 2000 V sibling (B32654A2104, p.23 table): 100 nF, 22.0 x 36.5 mm body, 10.0 A, 12.6 mOhm
    w2000 = 22.0
    out["B32654A2104_2000V"] = {"body_w_mm": w2000, "row_5x_mm": 5 * (w2000 + GAP_MM), "slot_mm": SLOT_MM,
                                "fits": 5 * (w2000 + GAP_MM) <= SLOT_MM, "IRMS_100k_A": 10.0, "ESR_mOhm": 12.6,
                                "IRMS_ratio_vs_1600V_100nF_at_100k": round(10.0 / 7.3, 2),
                                "loss_ratio_vs_1600V_100nF_same_I": round(12.6 / 19.3, 3),
                                "peak_V_double_fault_1702_over_2000": round(1702.4 / 2000, 3)}
    (HERE.parent / "results" / "bank_options.json").write_text(json.dumps(out, indent=1) + "\n")
    print("baseline K:", {k: v for k, v in base_k.items() if k.startswith(("tank", "ratio", "loss"))})
    j = out["baseline"]["5x100nF_J(+-5%)"]
    print("baseline J:", {k: v for k, v in j.items() if k.startswith(("tank", "ratio", "loss"))})
    print("top combos by tank A at 35 kHz (fitting slot):")
    for r in [r for r in seen if r["fits_slot"]][:10]:
        print(r["parts_nF"], r["tol_code"], r["tank_A_at_curve_35k"], r["tank_A_at_curve_40k"], r["ratio_to_curve_28A_40k"], r["loss_W_28A_esr100k"], r["n"])
    print(out["B32654A2104_2000V"])


if __name__ == "__main__":
    main()
