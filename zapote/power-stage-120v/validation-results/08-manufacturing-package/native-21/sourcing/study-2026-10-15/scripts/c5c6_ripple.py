#!/usr/bin/env python3
"""C5/C6 DC-link ripple self-heating against TDK's permitted dT, at 22 / 26 / 28 A tank RMS, for the B32676G drop-ins.
    python3 -I scripts/c5c6_ripple.py results/b32676_irms_curves.json results/c5c6_ripple.json
Method = TDK B3267* (6/26) p.29: dT = ESR_typ(f) * I^2 / G; permitted dT(T_A) = Factor(T_A)^2 * 20 K, Factor 1.0 at 70 C
and 0.7 at 85 C (p.29 worked example). Between 70 and 85 C the factor is interpolated linearly (ASSUMPTION; the p.29 rule
only states the end points). Table data: p.10 (750 / 875 V, 37.5 mm): IRMS 70 C 10 kHz, ESR_typ 10 kHz; G from p.28.
ESR(f): TDK's p.25 permissible-current curve is a constant-dT rule, so ESR(f)/ESR(10k) = (I(10k)/I(f))^2. The digitised
curve (digitize_b32676_irms.py) is flat within -2.3/+4.3 % from 10 to 95 kHz; we take ESR factor = max(1, (I10/I90)^2).
Current: repo worst C5 current 12.4 A at I_tank 22 A (ALT-C5C6.md s4 A, ripple-tr100: Al-clad pan, low-R corner,
140 V, 45.5 kHz), scaled linearly with I_tank (i_bus = i_tank * sgn(v)). Control: B32676G1905 at 22 A / 85 C = 0.80 (repo).
Spectrum check: i_bus for a sinusoidal tank current at the phase that gives the repo's 21.4 A HF total at 22 A; the
share of the AC power above 100 kHz (outside TDK's chart) is reported, and a sensitivity where ESR rises as sqrt(f/95k)
above 95 kHz (skin effect) is applied to that share."""
import json, math, sys
import numpy as np
curves = json.load(open(sys.argv[1]))["parts"]
PARTS = {  # name: (C uF, VR85, box, G mW/K, ESR mOhm 10k, IRMS 70C 10k, ESL nH, curve key, page)
 "B32676G1905K000 (fitted)": (9.0, 750, "30x45x42", 100, 5.1, 19.5, 12.0, "9uF/750V B32676G1905"),
 "B32676G1106K000": (10.0, 750, "30x45x42", 100, 4.7, 20.5, 13.0, "10uF/750V B32676G1106"),
 "B32676G1126K000": (12.0, 750, "33x48x42", 110, 4.0, 23.0, 14.0, "12uF/750V B32676G1126"),
 "B32676G8106K000": (10.0, 875, "33x48x42", 110, 4.3, 22.5, 14.0, "10uF/875V B32676G8106K000"),
 "B32676G8755K000": (7.5, 875, "30x45x42", 100, 5.4, 19.0, 13.0, "7.5uF/875V B32676G8755"),
}
I22 = 12.4                       # A rms in C5 at 22 A tank (repo worst)
def factor(TA):
    return 1.0 if TA <= 70 else max(0.0, 1.0 - 0.3 * (TA - 70) / 15.0)
# spectrum of i_bus = i_tank * sgn(v): phase from the repo's 21.4 A HF total at 22 A
cphi = math.sqrt((1 - (21.4 / 22) ** 2) * math.pi ** 2 / 8)
phi = math.acos(cphi); N = 4096; th = np.arange(N) * 2 * math.pi / N
ib = math.sqrt(2) * np.sin(th - phi) * np.sign(np.sin(th))
X = np.fft.rfft(ib) / N; P = 2 * np.abs(X[1:]) ** 2          # power per harmonic of f_sw (index k -> k*f_sw)
fsw = 45.5e3; ks = np.arange(1, len(P) + 1); fr = ks * fsw
hf = P.sum(); above = P[fr > 95e3].sum() / hf
skin = (P * np.where(fr > 95e3, np.sqrt(fr / 95e3), 1.0)).sum() / hf   # ESR multiplier, ideal-source spectrum
# the repo found 9.6-10.4 of 12.4 A below 600 kHz -> cap the HF tail at the repo's split instead of the ideal spectrum
skin_repo = ((10.0 / 12.4) ** 2 * (P[(fr > 95e3) & (fr <= 600e3)] * np.sqrt(fr[(fr > 95e3) & (fr <= 600e3)] / 95e3)).sum()
             / P[fr <= 600e3].sum() + (1 - (10.0 / 12.4) ** 2) * math.sqrt(1e6 / 95e3))
res = {"basis": {"I_C5_at_22A": I22, "cos_phi": round(cphi, 3), "f_sw_kHz": 45.5, "share_above_95kHz": round(above, 3),
                 "esr_mult_sqrt_skin_ideal_spectrum": round(skin, 3), "esr_mult_sqrt_skin_repo_split": round(skin_repo, 3)},
       "parts": {}}
print(f"spectrum: cos phi {cphi:.3f}; {above:.1%} of HF power above 95 kHz; sqrt-skin ESR multiplier {skin:.2f} (ideal) / {skin_repo:.2f} (repo split, tail at 1 MHz)")
for name, (C, VR, box, G, ESR, Irat, ESL, key) in PARTS.items():
    r90 = curves[key]["ratio_to_10k"]["90k"]; fesr = max(1.0, (1 / r90) ** 2)
    row = {"C_uF": C, "VR85_V": VR, "box": box, "G_mW_K": G, "ESR10k_mOhm": ESR, "ESL_nH": ESL, "esr_factor_90k": round(fesr, 3)}
    for It in (22, 26, 28):
        I = I22 * It / 22
        for TA in (70, 75, 80, 85):
            allow = factor(TA) ** 2 * 20
            dT = ESR * fesr * I ** 2 / G
            row[f"use_{It}A_{TA}C"] = round(dT / allow, 3)
            row[f"use_{It}A_{TA}C_skin"] = round(dT * skin_repo / allow, 3)
        row[f"dT_{It}A_K"] = round(ESR * fesr * I ** 2 / G, 2)
    # hottest ambient at which 28 A stays within the allowance (vendor basis, no skin term)
    dT28 = ESR * fesr * (I22 * 28 / 22) ** 2 / G
    TAmax = None
    for TA10 in range(700, 851):
        if dT28 <= factor(TA10 / 10) ** 2 * 20: TAmax = TA10 / 10
    row["max_ambient_28A_C"] = TAmax
    res["parts"][name] = row
    print(f"{name:26s} C {C:4.1f} G {G} ESR {ESR}x{fesr:.2f}: 85C use 22/26/28 A = {row['use_22A_85C']:.2f} / {row['use_26A_85C']:.2f} / {row['use_28A_85C']:.2f}"
          f"  (skin {row['use_28A_85C_skin']:.2f});  75C 28 A {row['use_28A_75C']:.2f};  28 A ok to {TAmax} C")
ctl = res["parts"]["B32676G1905K000 (fitted)"]["use_22A_85C"]
res["control_repo_0p80"] = ctl
json.dump(res, open(sys.argv[2], "w"), indent=1)
sys.exit(0 if abs(ctl - 0.80) <= 0.01 else 1)
