"""Option A (per-device catalogue insulators): thermal Rcs per TO-247 and inter-device joint creepage.
Same assumptions as m11/stack_calc.py: TAB 151.2-240.1 mm2, 1-D through the ceramic (no spreading credit),
grease optimistic = DOWSIL TC-5622 0.06 C-cm2/W per interface, conservative = TIC1000A proxy 0.32 C/W TO-220 over 0.2 in2.
"""
IN2 = 645.16
TAB = (151.2, 240.1)
def cm2(r): return (r*100/TAB[1], r*100/TAB[0])
g_opt = cm2(0.06)
g_cons = (0.32*0.2*IN2/TAB[1], 0.32*0.2*IN2/TAB[0])
def cer(t, k): return (t*1e-3/(k*TAB[1]*1e-6), t*1e-3/(k*TAB[0]*1e-6))
def add(*r): return (sum(x[0] for x in r), sum(x[1] for x in r))
cases = [("AlN 1.0 mm, k 150", 1.0, 150), ("AlN 1.0 mm, k 170", 1.0, 170),
         ("AlN 2.0 mm, k 150", 2.0, 150), ("AlN 2.0 mm, k 170", 2.0, 170),
         ("Al2O3 1.0 mm, k 24 (stack_calc EST)", 1.0, 24), ("Al2O3 1.0 mm, k 9 (Digi-Key AOS 247 listing)", 1.0, 9),
         ("Al2O3 2.03 mm, k 15 (4180G listing)", 2.032, 15)]
P_LS = 6.78*(22/21.47)**2 + 0.33
Ts = 64.7
print("Rcs per TO-247 incl. 2 grease interfaces (C/W): optimistic | conservative   [D-36 limit 0.7]")
for n, t, k in cases:
    o = add(cer(t, k), g_opt, g_opt); c = add(cer(t, k), g_cons, g_cons)
    print(f"{n:45s} ceramic {cer(t,k)[0]:.3f}-{cer(t,k)[1]:.3f} | opt {o[0]:.3f}-{o[1]:.3f} | cons {c[0]:.3f}-{c[1]:.3f} "
          f"| <=0.7 cons: {c[1] <= 0.7} | Tj_LS cons {Ts + P_LS*(0.28 + c[1]):.1f} C")

# Inter-device joint creepage (method of RECOMMENDATION 4.1 tile-joint row: a + t + g >= 8.0)
# a = tab-metal edge -> joint along the tile face = plastic margin 0.675 (min (E-E1)/2) + half body gap
print("\nJoint creepage, per-device tiles, joint at mid-gap: need groove half-width g = 8.0 - a - t")
gaps = {"Q5|Q6": (17.95, 19.95), "Q6|Q3": (35.95, 42.05), "Q3|Q2": (58.05, 60.05), "Q2|BR1": (76.05, 79.6)}
for t in (1.0, 2.0):
    for k, (l, r) in gaps.items():
        gap = r - l; a = 0.675 + gap/2; g = max(0.0, 8.0 - a - t)
        under_metal = max(0.0, g - a)   # how far the groove edge reaches under the tab metal
        print(f"t={t} {k}: gap {gap:.2f} mm, a {a:.3f}, groove width {2*g:.2f} mm, reaches {under_metal:.2f} mm under the tab metal")
