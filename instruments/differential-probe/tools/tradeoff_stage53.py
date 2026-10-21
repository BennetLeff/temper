#!/usr/bin/env python3
"""Cost-down HV-resistor trade at stage-53 operating points (docs/cost-down.md, "At stage 53").

Run from the probe directory: python3 tools/tradeoff_stage53.py > validation/tradeoff-stage53.txt
Std-only. Ideal 5-section divider per leg, nodal-free series form H = Zb / (sum Zi + Zb).
Compares the 1 % HV12 string (100 ppm/C) with the 0.1 % HVCB string (25 ppm/C) on the errors
they actually cause when measuring the stage-53 bank (RES_A - SW_B) at 35-60 kHz, and puts them
next to the NP0/C0G capacitor tempco, which both strings share. Linear TCR, worst-case signs.
"""
import cmath, math

N, R, C = 5, 2.0e6, 33e-12
RB, CB = N * R / 1999, C / N * 1999          # ideal compensated bottom (2000:1)
FC = 1 / (2 * math.pi * N * R * C / N)       # resistive/capacitive crossover
FREQS = (35e3, 60e3)
THETA = 85.0                                 # K/W, upper end of cost_down.rs section 4
BUS = 170.0                                  # stage-53 unfiltered bus peak, SW_B swings 0..BUS
# Bank peak voltages from stage-53 records (bank-voltage-s52.md): design 28 A, no pan, OCP-trip fault.
POINTS = (("design case, 28 A", 566.0), ("no pan", 775.0), ("OCP-trip fault (transient)", 1790.0))
PARTS = (("HVCB2512BDE2M00 (0.1 %, 25 ppm/C)", 25e-6, 60.5e-6),
         ("HV121WF2004T4E (1 %, 100 ppm/C)", 100e-6, 254.0e-6))  # TCR, leg-to-leg mismatch (cost-down.txt s3)
NP0_TCR = 30e-6                               # Yageo / KEMET NP0-C0G limit, 0 +/- 30 ppm/C
DT_AMB = 10.0                                 # ambient change after trim, C


def h(f, rs, cs, rb=RB, cb=CB):
    w = 2 * math.pi * f
    z = lambda r, c: r / (1 + 1j * w * r * c)
    zt = sum(z(r, c) for r, c in zip(rs, cs))
    return z(rb, cb) / (zt + z(rb, cb))


def err(f, dr=0.0, dc_top=0.0, dc_bot=0.0):
    """Complex relative error of one leg when every upper R moves by dr, upper C by dc_top, bottom C by dc_bot."""
    h0 = h(f, [R] * N, [C] * N)
    h1 = h(f, [R * (1 + dr)] * N, [C * (1 + dc_top)] * N, RB, CB * (1 + dc_bot))
    return h1 / h0 - 1


def fmt(e):
    return f"{abs(e) * 1e6:7.1f} ppm ({20 * math.log10(abs(e)) if e else -999:6.1f} dB), phase {math.degrees(cmath.phase(1 + e)):+.4f} deg"


print(__doc__.strip().splitlines()[0])
print(f"Divider: {N} x 2 MOhm || 33 pF per leg, 2000:1, crossover {FC:.1f} Hz. Bus {BUS:.0f} V peak; theta <= {THETA:.0f} K/W.\n")

print("A. Leg-to-leg ratio mismatch after a 10 C ambient change from the trim temperature (worst-case datasheet TCR).")
print("   This is both a differential gain error and the common-mode leak.")
for name, _, mis in PARTS:
    print(f"   {name}:")
    print(f"      DC   : {fmt(err(1e-3, dr=mis * DT_AMB))}")
    for f in FREQS:
        print(f"      {f / 1e3:.0f} kHz: {fmt(err(f, dr=mis * DT_AMB))}")
def cap_mis(f):
    """Leg-to-leg: leg P top +30 / bottom -30 ppm/C, leg N the reverse (worst case within the NP0 limit)."""
    d = NP0_TCR * DT_AMB
    return err(f, dc_top=d, dc_bot=-d) - err(f, dc_top=-d, dc_bot=d)


print("   NP0/C0G capacitors, leg to leg (both options, +/-30 ppm/C, worst signs):")
for f in FREQS:
    print(f"      {f / 1e3:.0f} kHz: {fmt(cap_mis(f))}")

print("\nB. Common-mode leak of SW_B switching (0..170 V square; fundamental 4/pi x 85 V) through the A mismatch,")
print("   referred to the input, as a fraction of the design-case 566 V bank reading.")
vcm = 4 / math.pi * BUS / 2
for name, _, mis in PARTS:
    for f in FREQS:
        e = abs(err(f, dr=mis * DT_AMB))
        print(f"   {name:<36} {f / 1e3:.0f} kHz: {vcm * e * 1e3:7.1f} mV = {vcm * e / 566 * 100:.4f} % of 566 V")
cap = max(abs(cap_mis(f)) for f in FREQS)
print(f"   {'NP0/C0G capacitors (shared)':<36} worst : {vcm * cap * 1e3:7.1f} mV = {vcm * cap / 566 * 100:.4f} % of 566 V")
for name, _, mis in PARTS:
    e = abs(err(1e-3, dr=mis * DT_AMB))
    print(f"   DC offset from the {BUS / 2:.0f} V average of SW_B, {name}: {BUS / 2 * e * 1e3:.1f} mV (DC only; not in the AC reading)")

print("\nC. Self-heating of the TIP+ leg (RES_A) at each operating point, if held: P per body = (Vpk/sqrt2/5)^2 / 2 MOhm.")
for label, vpk in POINTS:
    v = vpk / math.sqrt(2) / N
    p = v * v / R
    rise = p * THETA
    print(f"   {label:<28} {vpk:6.0f} Vpk: {v:5.0f} V rms/body, {p * 1e3:5.1f} mW, rise <= {rise:4.2f} K")
    for name, tcr, _ in PARTS:
        es = [abs(err(f, dr=tcr * rise)) for f in FREQS]
        print(f"      {name:<36} gain error <= {max(es) * 1e6:5.1f} ppm at 35-60 kHz")

print("\nD. Difference the cost-down makes, design case, 10 C ambient: worst A at 35 kHz (HV12 minus HVCB) vs the shared capacitor term.")
d = abs(err(35e3, dr=PARTS[1][2] * DT_AMB)) - abs(err(35e3, dr=PARTS[0][2] * DT_AMB))
print(f"   added by HV12: {d * 1e6:.0f} ppm; shared NP0/C0G: {cap * 1e6:.0f} ppm; ratio {d / cap:.2f}.")


# E. Numbers for the CMRR procedure (docs/qualification.md section 4). All linear in the
# temperature change, so each window is the 60 dB (1000 ppm) target divided by the per-C term.
print("\nE. CMRR procedure: how far from the calibration temperature, and how much leg-to-leg gradient, 60 dB allows.")
GOAL = 1e-3  # 60 dB
def cap_mis_dt(f, dt):
    d = NP0_TCR * dt
    return err(f, dc_top=d, dc_bot=-d) - err(f, dc_top=-d, dc_bot=d)
for f in FREQS:
    per_c = abs(cap_mis_dt(f, 1.0))
    r_c = abs(err(f, dr=PARTS[1][2]))
    print(f"   {f / 1e3:.0f} kHz: NP0/C0G worst {per_c * 1e6:6.1f} ppm per C of uniform ambient change -> 60 dB within +/-{GOAL / per_c:.1f} C of calibration;"
          f" with the HV12 resistor term ({r_c * 1e6:.1f} ppm/C) added: +/-{GOAL / (per_c + r_c):.1f} C.")
# One leg warmer than the other by dt: that leg's top C0G at +30 ppm/C, its bottom at -30 (worst),
# its upper string at +100 ppm/C against the 25 ppm/C bottom resistor at -25.
for f in FREQS:
    g = abs(err(f, dr=(100e-6 + 25e-6), dc_top=NP0_TCR, dc_bot=-NP0_TCR))
    print(f"   {f / 1e3:.0f} kHz: leg-to-leg gradient {g * 1e6:6.1f} ppm per C (one leg warmer; worst C0G and resistor signs) -> 60 dB needs < {GOAL / g:.1f} C,"
          f" or < {GOAL / g / 2:.1f} C to leave half the budget for everything else.")
