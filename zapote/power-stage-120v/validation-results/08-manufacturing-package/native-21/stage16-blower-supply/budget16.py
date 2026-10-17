#!/usr/bin/env python3
"""Stage-16 numbers: blower-supply load, module sizing, inlet allowance, harness, fuse, heat.

    python3 budget16.py > out/budget16.txt

Every input is a cited constant below; nothing is measured.
"""
# --- sources -----------------------------------------------------------------------------------
# Delta BFB1012VH-F00 spec (enclosure R33 study 10, BFB1012VH-F00.pdf p.1): 12 V rated, 5.5-13.2 V,
#   1.42 A typ / 2.70 A max, 17.04 W typ / 32.40 W max. Fan law P ~ V^3 (study 10's estimate basis).
V_RATED, I_MAX, P_MAX, P_TYP = 12.0, 2.70, 32.40, 17.04
# Controller C28 (controller-layout DECISIONS; controller_calcs.json blower_supply): buck output
#   11.96-12.40 V at duty 0; ps1_blower_input_W full_max 36.0 W = 32.4 / 0.9, so eta_buck 0.90;
#   PS1 total 14.8 W at the R32 cap with the blower input 10.0 W there -> logic 4.8 W.
V_BUCK_MAX, ETA_BUCK = 12.40, 0.90
P_PS1_AT_CAP, P_BLOWER_IN_AT_CAP = 14.8, 10.0
# Mean Well IRM-60-SPEC 2025-11-21 p.2: IRM-60-15 15 V 4 A 60 W, eff 89 % typ, AC current 1.8 A typ
#   at 115 Vac (full load), inrush 30 A typ cold start at 115 Vac, hold-up 12 ms at 115 Vac full load,
#   overload 115-160 % hiccup, OVP 15.75-20.25 V. p.3 derating: 100 % to 50 C, 75 % at 60 C ("others").
IRM60 = dict(P=60.0, V=15.0, eta=0.89, I_ac_115=1.8, inrush=30.0, ovl=(1.15, 1.60), tol=0.025)
# IRM-45-SPEC 2025-11-21 p.2: IRM-45-15 15 V 3 A 45 W, eff 88.5 %, 1.5 A typ at 115 Vac.
IRM45 = dict(P=45.0, V=15.0, eta=0.885, I_ac_115=1.5)
# IRM-20-SPEC 2025-11-21 p.2: 0.6 A typ at 115 Vac full load (the existing allowance basis).
I_IRM20_115 = 0.6
# Inlet method (power-stage DECISIONS 2026-10-08 input-current entry + correction; firmware
#   input_limits.c cfg: eta_min 0.93, est_error 0.10, aux_max_a 1.3): typical full-load AC current at
#   115 Vac scaled to 108 V; hold = (inlet_target 13.5 - aux) / (1 + e_est); P = hold * 0.93 * V.
V_LOW, V_NOM, TARGET, E_EST, ETA_MIN = 108.0, 120.0, 13.5, 0.10, 0.93
# TPS62933 high-side current limit 4.2-5.8 A (SLUSEA4D, via C28).
I_LIM_HS = (4.2, 5.8)
# Littelfuse 0215 3.15 A (02153.15MXP, LCSC C142723 listing 2026-10-12): 1.5 kA @ 250 VAC, melting I2t 43.255 A2s.
FUSE_I2T = 43.255
# Copper: AWG18 0.823 mm2, AWG20 0.519 mm2; rho_Cu(20 C) 0.01724 ohm mm2/m (IEC 60028).
RHO = 0.01724
AWG = {"AWG18": 0.823, "AWG20": 0.519, "AWG22": 0.326}
# JST VH: 250 V AC/DC, 10 A (eVH.pdf p.1, as cited for J3 in elec/src/parts.ato TcoLoopHeader).
# JST XH: 3 A with AWG22 (eXH.pdf, as cited in controller C28).

print("== blower and supply load")
p12 = P_MAX * (V_BUCK_MAX / V_RATED) ** 3
i12 = I_MAX * (V_BUCK_MAX / V_RATED) ** 2
print(f"blower at Delta max, 12.0 V: {P_MAX:.1f} W, {I_MAX:.2f} A; owner budget 12.4 V x 2.70 A = {12.4 * I_MAX:.1f} W")
print(f"blower at the buck's 12.40 V corner (fan law, estimate): {p12:.1f} W, {i12:.2f} A")
p_design = max(p12, 12.4 * I_MAX)
p_ps3 = p_design / ETA_BUCK
print(f"design blower load {p_design:.1f} W -> PS3 output (buck eta {ETA_BUCK}) {p_ps3:.1f} W")
for name, m in (("IRM-60-15", IRM60), ("IRM-45-15", IRM45)):
    frac = p_ps3 / m["P"]
    t_max = 50 + (1 - frac) / 0.025 if frac > 0.75 else 60 + (0.75 - frac) / 0.024
    print(f"  {name}: {100 * frac:.0f} % of {m['P']:.0f} W; derating allows this load up to ~{t_max:.0f} C ambient "
          f"(IRM-60 p.3 curve: 100 % to 50 C, 75 % at 60 C, then ~2.4 %/C)")
i15 = p_ps3 / (IRM60["V"] * (1 - IRM60["tol"]))
print(f"PS3 15 V current at the -2.5 % output corner: {i15:.2f} A")
print(f"PS1 after the split: logic {P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP:.1f} W of 21 W "
      f"({100 * (P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP) / 21:.0f} %); today at full blower: {P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP + P_MAX / ETA_BUCK:.1f} W")

print("\n== start-up and stall")
lo, hi = (IRM60["P"] * k for k in IRM60["ovl"])
print(f"IRM-60-15 overload protection {lo:.0f}-{hi:.0f} W = {lo / 15:.1f}-{hi / 15:.1f} A at 15 V (hiccup)")
for il in I_LIM_HS:
    pin = V_BUCK_MAX * il / ETA_BUCK
    print(f"  buck at its {il} A current limit, 12.40 V out: {pin:.0f} W in = {pin / 15:.1f} A at 15 V "
          f"-> {'can' if pin > lo else 'cannot'} reach the module's low OCP corner")
i_out_trip = lo * ETA_BUCK / V_BUCK_MAX
print(f"  blower current that reaches the low OCP corner at 12.40 V: {i_out_trip:.1f} A (= {i_out_trip / I_MAX:.2f} x Delta max)")
print("  Delta: locked rotor -> current shutdown (spec p.2), so a stall is not a sustained overload.")

print("\n== inlet allowance (input_limits.c aux_max_a)")
s = V_LOW / 115.0
i20 = I_IRM20_115 * 115 / V_LOW
i60_full = IRM60["I_ac_115"] * 115 / V_LOW
i60_load = i60_full * p_ps3 / IRM60["P"]
cases = {"today (PS1 + PS2 at full load)": 2 * i20,
         "stage 16, PS3 at its 60 W rating (method as written)": 2 * i20 + i60_full,
         "stage 16, PS3 at its design load (recommended)": 2 * i20 + i60_load}
for k, aux in cases.items():
    hold = (TARGET - aux) / (1 + E_EST)
    print(f"  {k}: aux {aux:.2f} A -> hold {hold:.2f} A -> {hold * ETA_MIN * V_NOM:.0f} W tank-side input basis at 120 V"
          f" ({hold * ETA_MIN * V_NOM - 11.1 * ETA_MIN * V_NOM:+.0f} W vs the 1239 W hold)")
print(f"  (aux today rounds to 1.3 A: 2 x {i20:.3f}; PS3 {i60_full:.2f} A at 60 W, {i60_load:.2f} A at {p_ps3:.1f} W)")
for name, pbl in (("blower off", 0.0), ("Delta typ at 12 V", P_TYP), ("design max", p_design)):
    aux = 2 * i20 + i60_full * (pbl / ETA_BUCK) / IRM60["P"]
    print(f"  drive-scheduled aux, {name}: {aux:.2f} A -> hold {(TARGET - aux) / (1 + E_EST):.2f} A")
print(f"PS3 real input power at the design load: {p_ps3 / IRM60['eta']:.1f} W "
      f"(= {p_ps3 / IRM60['eta'] / V_NOM:.2f} A of in-phase real current at 120 V; the RMS allowance above is larger"
      f" because a capacitor-input module draws peaky current)")

print("\n== heat")
loss = p_ps3 * (1 / IRM60["eta"] - 1)
ps1_before = (P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP + P_MAX / ETA_BUCK)
print(f"PS3 dissipation at the design load: {loss:.1f} W (eta {IRM60['eta']} typ, p.2)")
print(f"PS1 output falls from {min(ps1_before, 21):.1f} W (clipped at its rating) to {P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP:.1f} W;"
      f" its loss at eta 0.84 (IRM-20-15 p.2) falls by {(min(ps1_before, 21) - (P_PS1_AT_CAP - P_BLOWER_IN_AT_CAP)) * (1 / 0.84 - 1):.1f} W")

print("\n== harness (PS3 -> controller), round trip 2 x length")
for L in (0.30, 0.45, 0.60):
    for g, a in AWG.items():
        r = 2 * L * RHO / a
        print(f"  {L * 1000:.0f} mm run, {g}: {1000 * r:.1f} mOhm loop -> {1000 * r * i15:.0f} mV and {r * i15 ** 2:.2f} W at {i15:.2f} A")
print("  buck headroom: 12.40 V out needs <= 0.923 duty without foldback (C9 typ) -> VIN >= "
      f"{V_BUCK_MAX / 0.923:.2f} V; PS3 low corner {15 * (1 - IRM60['tol']):.2f} V")

print("\n== branch fuse F2")
i2t_inrush = IRM60["inrush"] ** 2 * 0.002 / 2
print(f"IRM-60 inrush (30 A typ, p.2) as a 2 ms half-sine, ESTIMATE: I2t ~ {i2t_inrush:.2f} A2s vs 0215 3.15 A melting "
      f"{FUSE_I2T} A2s -> ratio {FUSE_I2T / i2t_inrush:.0f}")
print(f"steady input current at 108 V, design load (from the 1.8 A @ 115 V full-load figure): {i60_load:.2f} A "
      f"= {100 * i60_load / 3.15:.0f} % of 3.15 A")
