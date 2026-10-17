#!/usr/bin/env python3
"""Interface thermal comparison for the M11 HOT->PE stack: AlN vs alumina at 2 mm, with the repo's own formulas.

    python3 -I validation-results/11-candidates/c53-astra-results/local/m11/stack-options/interface_thermal.py

Formulas, areas and loads are copied from owner-items/m11/stack_calc.py (see its source list): tab area 151.2-240.1 mm2, grease 0.025-0.040 C/W
(TC-5622 TDS fixture) optimistic and 0.172-0.273 C/W conservative per face, pedestal+joint 0.0161, sink Ts 64.7 C at the 22 A case, FET RthJC 0.28,
low-side loss 7.45 W at 22 A. Ceramic k: AlN 150 W/mK [Kyocera AN216A]; alumina k is NOT established (Fischer AOS 247 listing 9.0, resellers 25,
Boyd 4180G listing 15.06, M11-SOURCING.md): 15 / 24 / 30 are bracketing values, 24 is the repo's own EST.
Tj = Ts + P x (0.28 + Rcs) with the conservative max R, as stack_calc.py; Ts is held at 64.7 C (the 22 A sink load), so this is a screen, not a solve.
Budget: D-36 interface <= 0.7 C/W per FET (the binding check, not Tj; RECOMMENDATION.md section 3).
"""
TAB = (151.2, 240.1)
G_OPT = (0.06 * 100 / TAB[1], 0.06 * 100 / TAB[0])
G_CONS = (0.32 * 0.2 * 645.16 / TAB[1], 0.32 * 0.2 * 645.16 / TAB[0])
TS, RJC, P22 = 64.7, 0.28, 7.45
def ceramic(t_mm, k):
    return (t_mm * 1e-3 / (k * TAB[1] * 1e-6), t_mm * 1e-3 / (k * TAB[0] * 1e-6))
rows = [("AlN 2.0 mm (k 150) [recommended]", 2.0, 150), ("AlN 1.0 mm (k 150)", 1.0, 150),
        ("Alumina 2.0 mm k 30", 2.0, 30), ("Alumina 2.0 mm k 24 (repo EST)", 2.0, 24), ("Alumina 2.0 mm k 15 (Boyd listing)", 2.0, 15)]
print(f"{'stack':40} {'Rcs optimistic':>16} {'Rcs conservative':>18} {'<=0.7 (opt/cons)':>17} {'Tj_LS 22 A cons':>16} {'dTj vs AlN2':>12}")
base = None
for name, t, k in rows:
    c = ceramic(t, k)
    opt = (2 * G_OPT[0] + c[0], 2 * G_OPT[1] + c[1])
    con = (2 * G_CONS[0] + c[0], 2 * G_CONS[1] + c[1])
    tj = TS + P22 * (RJC + con[1])
    base = base if base is not None else tj
    print(f"{name:40} {opt[0]:7.3f}-{opt[1]:6.3f}   {con[0]:8.3f}-{con[1]:6.3f}   {str(opt[1] <= 0.7):>6}/{str(con[1] <= 0.7):<6} {tj:12.1f} C {tj - base:+10.1f} K")
print("\nDelta FET case temperature at the interface, alumina k 24 vs AlN 2 mm (conservative max R x P):")
for label, p in (("22 A tank ceiling", P22), ("18 A first-power ceiling (losses x (18/22)^2)", P22 * (18 / 22) ** 2)):
    a = ceramic(2, 24)[1] - ceramic(2, 150)[1]
    print(f"  {label}: +{p * a:.1f} K (ceramic term only)")
