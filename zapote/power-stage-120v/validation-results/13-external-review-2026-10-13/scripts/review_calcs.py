#!/usr/bin/env python3
"""Desk checks for the 2026-10-13 external review (claims 2, 3, 4, 9, 10, 11).

Pure arithmetic and a small ODE integration; no repo files are read or written
except the JSON written next to this script (../results.json).  Every input is
stated inline with its source.  Run:  python3 -I review_calcs.py
"""
import json, math, os

out = {}

# ---------------------------------------------------------------- bus and bleed
# Netlist (native-21/frozen/default.net + resolved-components.json, stage 22):
#   R3, R4  RC1206FR-07220KL 220 k in series, BUS_P -> BUSBLEED_MID -> HV_RET
#   R26..R29 4 x 470 k + R30 15.8 k  BUS_P -> VSENSE_IN -> OCP_KELVIN_P (bus divider, also a bleed)
#   C5, C6  B32676G1905K000 9 uF +/-10 %;  C38..C41 B32652A0104K000 0.1 uF +/-10 %
R_BLEED = 2 * 220e3
R_DIV = 4 * 470e3 + 15.8e3
R_PAR = 1 / (1 / R_BLEED + 1 / R_DIV)
C_NOM = 2 * 9e-6 + 4 * 0.1e-6
bleed = {"R_bleed_only_ohm": R_BLEED, "R_divider_ohm": R_DIV, "R_parallel_ohm": round(R_PAR)}
for tag, c in (("nominal", C_NOM), ("+10% C", 1.1 * C_NOM)):
    for rtag, r in (("R3/R4 alone (reviewer basis)", R_BLEED), ("R3/R4 || divider (as built)", R_PAR),
                    ("option N1: 2 x 100 k || divider", 1 / (1 / 200e3 + 1 / R_DIV))):
        tau = r * c
        bleed[f"{rtag}, {tag}"] = {
            "tau_s": round(tau, 2),
            "t_198V_to_60V_s": round(tau * math.log(198 / 60), 2),   # 140 V rms crest
            "t_280V_to_60V_s": round(tau * math.log(280 / 60), 2),   # OVP-corner bus
            "t_198V_to_34V_s": round(tau * math.log(198 / 34), 2),
        }
bleed["R3/R4 220k power at 198 V each (W)"] = round((198 / 2) ** 2 / 220e3, 4)
bleed["R3/R4 100k power at 198 V each (W)"] = round((198 / 2) ** 2 / 100e3, 4)
out["claim10_bleed"] = bleed

# ---------------------------------------------------------------- inrush
# Plug-in (or switched-inlet closure) at the line crest into a discharged bus.
# Series R-L-C, bridge conducting, diode drop 2 x 1.0 V subtracted from the source.
# Integrated until the current returns to zero (bridge blocks reverse current).
def inrush(v0, L, R, C, vd=2.0, dt=1e-8):
    i = 0.0; vc = 0.0; t = 0.0; ipk = 0.0; i2t = 0.0
    while True:
        di = (v0 - vd - vc - R * i) / L
        i += di * dt
        if i < 0 and t > 0:
            break
        vc += i / C * dt
        i2t += i * i * dt
        ipk = max(ipk, i)
        t += dt
        if t > 5e-3:
            break
    return ipk, i2t, t, vc

C_MAX = 1.1 * C_NOM
cases = {}
for vline in (132.0, 140.0):
    v0 = vline * math.sqrt(2)
    for L, R, tag in ((2e-6, 0.0, "2 uH lossless (repo ALT-C5C6 bound)"),
                      (10e-6, 0.0, "10 uH lossless"),
                      (2e-6, 0.06, "2 uH + 60 mOhm (cord 1.8 m 14 AWG round trip ~30 mOhm + bridge/ESR/traces ~30 mOhm, ESTIMATE)"),
                      (100e-6, 0.06, "100 uH DM inlet module (DECISIONS item 20 requirement) + 60 mOhm")):
        ipk, i2t, t, vc = inrush(v0, L, R, C_MAX)
        cases[f"{vline:.0f} V rms, {tag}"] = {"I_peak_A": round(ipk, 1), "I2t_A2s": round(i2t, 3),
                                               "pulse_us": round(t * 1e6, 1), "Vbus_end_V": round(vc, 1)}
limits = {"KLDR025 melting I2t (A2s), repo F1-RECOMMENDATION": 226.0,
          "GBJ2510 I2t (A2s), Diodes DS21221": 510.0,
          "GBJ2510 IFSM 8.3 ms half-sine (A)": 350.0,
          "B32676G1905K000 pulse: 85 V/us x 9 uF per part (A), TDK B3267* p.10 / ALT-C5C6": 765.0}
worst = max(cases.values(), key=lambda d: d["I2t_A2s"])
out["claim9_inrush"] = {"C_bus_max_F": C_MAX, "cases": cases, "limits": limits,
                        "worst_I2t_fraction_of_F1_melt": round(worst["I2t_A2s"] / 226.0, 4),
                        "worst_I2t_fraction_of_BR1": round(worst["I2t_A2s"] / 510.0, 4)}

# ---------------------------------------------------------------- PF with an unsmoothed 18.4 uF bus
# Inverter modelled as a constant conductance on the bus (P proportional to V^2),
# which is what a fixed-frequency resonant tank near-resistive load does to first order.
# Ideal 60 Hz source + series L, ideal bridge (2 x 1 V).  Steady state after 3 cycles.
def pf_sim(p_target, vline=120.0, L=20e-6, C=C_NOM, f=60.0, dt=2e-7):
    vpk = vline * math.sqrt(2)
    G = p_target / vline ** 2
    i = 0.0; vc = 0.0
    n = int(round(1 / f / dt)); samples = []
    for k in range(6 * n):
        t = k * dt
        vs = vpk * math.sin(2 * math.pi * f * t)
        a = abs(vs)
        if i > 0 or a - 2.0 > vc:
            di = (a - 2.0 - vc) / L
            i = max(0.0, i + di * dt)
        vc += (i - G * vc) / C * dt
        if k >= 3 * n:
            samples.append((vs, math.copysign(i, vs)))
    p = sum(v * c for v, c in samples) / len(samples)
    irms = math.sqrt(sum(c * c for _, c in samples) / len(samples))
    vrms = math.sqrt(sum(v * v for v, _ in samples) / len(samples))
    # 3rd/5th harmonic magnitudes (rms) by DFT over 3 cycles
    N = len(samples); h = {}
    for order in (1, 3, 5, 7):
        re = sum(c * math.cos(2 * math.pi * order * f * (j * dt)) for j, (_, c) in enumerate(samples))
        im = sum(c * math.sin(2 * math.pi * order * f * (j * dt)) for j, (_, c) in enumerate(samples))
        h[order] = math.hypot(re, im) * 2 / N / math.sqrt(2)
    return {"P_W": round(p, 1), "I_rms_A": round(irms, 3), "PF": round(p / (vrms * irms), 4),
            "I3_over_I1": round(h[3] / h[1], 4), "I5_over_I1": round(h[5] / h[1], 4), "I7_over_I1": round(h[7] / h[1], 4)}
pf = {}
for P in (160.0, 600.0, 1330.0, 1800.0):
    pf[f"{P:.0f} W @120 V, L 20 uH"] = pf_sim(P)
pf["1330 W @120 V, L 100 uH (inlet module)"] = pf_sim(1330.0, L=100e-6)
pf["note"] = ("Constant-conductance load is an idealisation; crest-clipping FM (round 6) and burst mode "
              "draw differently, and the repo's own round-6 FM study reports PF down to 0.95. Bench is the evidence.")
pf["reviewer_arithmetic_1800W_PF0.95_120V_A"] = round(1800 / (120 * 0.95), 2)
pf["repo_inlet_regulation_A"] = 13.5
pf["repo_power_stage_hold_A"] = 11.1
out["claim2_pf"] = pf

# ---------------------------------------------------------------- BR1 dissipation
# GBJ2510 VF max 1.05 V per element at 12.5 A (Diodes DS21221 p.2; repo losses.py uses 1.05 V).
for I in (11.1, 13.5, 15.0):
    out.setdefault("claim3_br1_W", {})[f"{I} A rms sine"] = round(2 * 1.05 * (2 * math.sqrt(2) / math.pi) * I, 2)

# ---------------------------------------------------------------- J1 rating margin
# Phoenix 1711725 data sheet (MKDS 3/2-5,08, Phoenix PDF dated 2025-03-21 p.8):
#   cULus E60425: use group B 300 V 15 A (AWG 30-12 screw); use group D 300 V 10 A
#   CSA 13631:   use group B 300 V 10 A; use group D 300 V 10 A;  IEC 24 A / 400 V
j1 = {}
for tag, i in (("inlet regulated (adapter inlet_target_a)", 13.5), ("inlet trip", 15.0),
               ("recorded 28 A-tank input envelope (F1-J3-PARTS)", 16.5)):
    j1[tag] = {"I_A": i, "vs_cULus_B_15A": round(i / 15.0, 3), "vs_CSA_10A": round(i / 10.0, 3),
               "vs_IEC_24A": round(i / 24.0, 3)}
out["claim4_11_j1"] = j1

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "..", "results.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps(out, indent=1))
