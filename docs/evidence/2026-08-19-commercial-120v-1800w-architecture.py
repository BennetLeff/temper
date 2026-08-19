#!/usr/bin/env python3
# provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
"""Companion arithmetic for docs/evidence/2026-08-19-commercial-120v-1800w-architecture.md

Pure stdlib.  Reads NO repo state and loads no compiled extension, so
`make venv-isolate` is NOT required -- stated explicitly per the task's
environment rule.  Every input is either a published figure (cited in the
companion document) or a value already committed in this repository; nothing
here is a new measurement and nothing here is a datasheet value that was
reconstructed rather than read.

Run:  python3 docs/evidence/2026-08-19-commercial-120v-1800w-architecture.py
"""

import math

# ---------------------------------------------------------------------------
# Inputs.  Provenance tag on every one.
# ---------------------------------------------------------------------------

V_LINE_US = 120.0        # [regulatory] US nominal utilisation voltage
I_BRANCH_15 = 15.0       # [regulatory] 15 A branch circuit
NAMEPLATE_W = 1800.0     # [sourced] Vollrath 6950020, Breville CMC850BSS USA

# Repo's committed tank, all from elec/src/main.ato as quoted in
# docs/evidence/2026-08-19-bus-capacitance-selection.md Sec 2.3.
L_LOADED = 88e-6 * 0.68  # [repo] main.ato:365,434 -> 59.84 uH
C_TANK = 300e-9          # [repo] main.ato:385
R_EQ_LOW = 3.55          # [repo] committed first-harmonic value
R_EQ_HIGH = 5.31         # [repo] the same doc's own power anchor
V_BUS_STIFF = 340.0      # [repo] main.ato:49 doubler bus
F_PLL_MIN = 44_000.0     # [repo] main.ato:269 ZVS floor
F_NOM = 47_000.0         # [repo] nominal operating point
ETA = 0.90               # [repo] main.ato eta_min

# Commercial dc-link capacitances, per the document's Sec 4.
C_DCLINK_COMMERCIAL = {
    "cheap 1.8 kW single-hob, 120 V (Hackaday teardown)": 8e-6,
    "8 kW 4-zone cooktop, 230 V, per half-bridge (Kaizer / HVF)": 4e-6,
}
C_TEMPER_PER_HALF = 3600e-6          # [repo] modules.ato, 2 x 1800 uF
C_TEMPER_EFFECTIVE = C_TEMPER_PER_HALF / 2   # two banks in series across the bus


def v1_rms(v_bus):
    """Fundamental rms of the half-bridge switch-node square wave.

    Amplitude V_bus/2 square wave -> first harmonic sqrt(2)*V_bus/pi.
    Infineon AN2014-01 Sec 3.3.1.1 (FHA).
    """
    return math.sqrt(2.0) * v_bus / math.pi


def reactance(f):
    w = 2.0 * math.pi * f
    return w * L_LOADED - 1.0 / (w * C_TANK)


def power_fha(v_bus_sq_mean, f, r_eq):
    """Cycle-mean output power under FHA, given mean(V_bus^2) over the line cycle."""
    x = reactance(f)
    return (2.0 / math.pi**2) * v_bus_sq_mean * r_eq / (r_eq**2 + x**2)


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# 1.  Input or output?  The line current a 1800 W plate implies, both ways.
# ---------------------------------------------------------------------------
rule("1. What line current does an 1800 W nameplate imply, read as INPUT vs OUTPUT?")

print(f"{'PF':>6} | {'INPUT reading':>16} | {'OUTPUT reading (eta 0.90)':>26} | within 15 A?")
print("-" * 78)
for pf in (1.00, 0.98, 0.95, 0.90, 0.76, 0.70, 0.60):
    i_in = NAMEPLATE_W / (V_LINE_US * pf)
    i_out = (NAMEPLATE_W / ETA) / (V_LINE_US * pf)
    ok_in = "input yes" if i_in <= I_BRANCH_15 else "input NO "
    ok_out = "output yes" if i_out <= I_BRANCH_15 else "output NO"
    print(f"{pf:6.2f} | {i_in:14.2f} A | {i_out:24.2f} A | {ok_in} / {ok_out}")

pf_needed_input = NAMEPLATE_W / (V_LINE_US * I_BRANCH_15)
pf_needed_output = (NAMEPLATE_W / ETA) / (V_LINE_US * I_BRANCH_15)
print()
print(f"PF required to stay within 15.00 A, INPUT reading : {pf_needed_input:.4f}")
print(f"PF required to stay within 15.00 A, OUTPUT reading: {pf_needed_output:.4f}  "
      f"({'IMPOSSIBLE' if pf_needed_output > 1 else 'ok'})")
print()
print("Manufacturer spec sheets state 1800 W AND 15 A for the same unit.")
print("W = V*A exactly only under the INPUT reading at PF = 1.000.")
print("Under the OUTPUT reading the manufacturer's own 15 A figure would be")
print(f"wrong by {100*(pf_needed_output-1):.1f}% -- the unit would draw "
      f"{(NAMEPLATE_W/ETA)/V_LINE_US:.2f} A at unity PF.")


# ---------------------------------------------------------------------------
# 2.  Stiff doubler bus vs line-following bridge bus: mean(V_bus^2)
# ---------------------------------------------------------------------------
rule("2. mean(V_bus^2) over the line cycle -- the quantity that sets FHA power")

v_pk_bridge_120 = math.sqrt(2.0) * V_LINE_US
mean_sq_bridge = v_pk_bridge_120**2 / 2.0      # |sin| squared averages to 1/2
mean_sq_stiff = V_BUS_STIFF**2

print(f"Line-following bridge on 120 V: V_pk = {v_pk_bridge_120:.1f} V, "
      f"mean(V^2) = {mean_sq_bridge:,.0f} V^2")
print(f"Stiff doubler bus (as built)  : V    = {V_BUS_STIFF:.1f} V, "
      f"mean(V^2) = {mean_sq_stiff:,.0f} V^2")
print(f"Ratio: the stiff bus is worth {mean_sq_stiff/mean_sq_bridge:.2f}x more power "
      f"into the SAME tank.")


# ---------------------------------------------------------------------------
# 3.  What the committed tank delivers from a line-following 120 V bus
# ---------------------------------------------------------------------------
rule("3. The committed tank on a line-following 120 V bridge bus")

print(f"{'R_eq':>8} | {'P at 44 kHz (ZVS floor)':>24} | {'P at f_res 37.56 kHz':>22}")
print("-" * 62)
f_res = 1.0 / (2.0 * math.pi * math.sqrt(L_LOADED * C_TANK))
for r in (R_EQ_LOW, R_EQ_HIGH):
    p44 = power_fha(mean_sq_bridge, F_PLL_MIN, r)
    pres = power_fha(mean_sq_bridge, f_res, r)
    print(f"{r:6.2f} O | {p44:20.0f} W | {pres:18.0f} W")
print()
print(f"(f_res,loaded = {f_res:,.0f} Hz -- reproduces main.ato:96)")
print("Sanity check against the repo's own anchor, stiff 340 V bus:")
for r in (R_EQ_LOW, R_EQ_HIGH):
    print(f"  P(340 V, 47 kHz, R={r:.2f} O) = {power_fha(mean_sq_stiff, F_NOM, r):.0f} W")


# ---------------------------------------------------------------------------
# 4.  What tank a line-following 120 V half-bridge would need for 1800 W
# ---------------------------------------------------------------------------
rule("4. The tank a line-following 120 V HBSR would need to reach 1800 W mean")

# At resonance X = 0, so P_mean = (2/pi^2) * mean(V^2) / R_eq.
r_needed = (2.0 / math.pi**2) * mean_sq_bridge / NAMEPLATE_W
print(f"R_eq required at resonance: {r_needed:.3f} ohm "
      f"(committed value is {R_EQ_LOW:.2f} ohm -- a {R_EQ_LOW/r_needed:.2f}x reduction)")

v1_pk = v1_rms(v_pk_bridge_120)
i_tank_at_line_peak = v1_pk / r_needed
i_tank_cycle_rms = i_tank_at_line_peak / math.sqrt(2.0)
print(f"Tank current at the line peak : {i_tank_at_line_peak:.1f} A rms")
print(f"Tank current, line-cycle rms  : {i_tank_cycle_rms:.1f} A rms "
      f"(repo's committed operating point is 22.5 A)")
print(f"Instantaneous output at the line peak: {2*NAMEPLATE_W:.0f} W "
      f"(2x the mean, because P ~ V_bus^2 ~ sin^2)")
print()
print("And this is AT resonance, i.e. zero ZVS margin.  Any real design sits")
print("above resonance, so R_eq must be lower still, or the coil must change.")


# ---------------------------------------------------------------------------
# 5.  ZVS commutation time is first-order INVARIANT with bus voltage
# ---------------------------------------------------------------------------
rule("5. Does a rippling bus break ZVS in a series-resonant half-bridge?")

C_SNUB = 12e-9   # [datasheet] Infineon AN2014-01 Sec 4.2 worked example, 12 nF total

print("Dead-time commutation: the lagging tank current must move charge")
print("Q = C_snub * V_bus to swing the switch node.  Under FHA the tank current")
print("scales linearly with V_bus, so:")
print()
print(f"{'V_bus':>8} | {'I_tank (R=3.55 O, 47 kHz)':>26} | {'t_comm = C*V/I':>16}")
print("-" * 58)
x47 = reactance(F_NOM)
z47 = math.sqrt(R_EQ_LOW**2 + x47**2)
for vb in (340.0, 240.0, 170.0, 120.0, 60.0, 20.0):
    i_t = v1_rms(vb) / z47
    t_c = C_SNUB * vb / (i_t * math.sqrt(2.0))   # peak current approximation
    print(f"{vb:6.0f} V | {i_t:22.2f} A | {t_c*1e9:12.1f} ns")
print()
print("t_comm is CONSTANT across a 17x bus swing.  Both the required charge and")
print("the current available to move it are proportional to V_bus, so they cancel.")
print("ZVS in a series-resonant half-bridge is set by the tank's PHASE")
print("(f_sw > f_res), which is a property of L, C and R_eq only -- V_bus does")
print("not appear in it.  A rippling bus does not, by itself, cost ZVS.")
print()
print("Residual hard-switching energy if ZVS were lost entirely at some V_bus:")
for vb in (340.0, 60.0, 20.0):
    e = 0.5 * C_SNUB * vb**2
    print(f"  0.5*C*V^2 at {vb:5.0f} V = {e*1e6:8.2f} uJ "
          f"-> {e*F_NOM:7.2f} W if it happened every cycle")


# ---------------------------------------------------------------------------
# 6.  dc-link capacitance: this design vs the commercial figures
# ---------------------------------------------------------------------------
rule("6. dc-link capacitance, this design vs published teardowns")

print(f"{'design':<58} | {'C_dclink':>12}")
print("-" * 74)
for name, c in C_DCLINK_COMMERCIAL.items():
    print(f"{name:<58} | {c*1e6:9.1f} uF")
print(f"{'Temper, per half-bus (2 x 1800 uF)':<58} | {C_TEMPER_PER_HALF*1e6:9.1f} uF")
print(f"{'Temper, effective across the bus (two banks in series)':<58} "
      f"| {C_TEMPER_EFFECTIVE*1e6:9.1f} uF")
print()
for name, c in C_DCLINK_COMMERCIAL.items():
    print(f"  ratio vs {name.split(',')[0]}: {C_TEMPER_EFFECTIVE/c:,.0f}x")

print("\nDone.")
