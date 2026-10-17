"""Coil terminal (J2-J5) voltage estimate from task-05 retained cases.
V_coil = I_tank * |R_pan(f) + R_coil + j w L|, fundamental (sinusoidal) approximation.
R_pan scales sqrt(f/40 kHz) from r_pan_40 (skin depth); check find_freq.py for the exact law."""
import csv, math, sys
p = sys.argv[1]
rows = list(csv.DictReader(open(p)))
print(f"{'case':28s} {'f kHz':>6s} {'L uH':>5s} {'Irms':>6s} {'Ipk':>6s} {'|Z|':>6s} {'Vrms':>6s} {'Vpk':>6s} {'Vrms@22A':>8s}")
for r in rows:
    f=float(r['frequency_hz']); L=float(r['l_load_h']); R40=float(r['r_pan_40_ohm']); Rc=float(r['r_coil_ohm'])
    R = R40*math.sqrt(f/40e3) + Rc
    X = 2*math.pi*f*L
    Z = math.hypot(R, X)
    ir=float(r['i_rms_a']); ip=float(r['i_pk_a'])
    print(f"{r['run_id']:28s} {f/1e3:6.2f} {L*1e6:5.1f} {ir:6.2f} {ip:6.2f} {Z:6.2f} {ir*Z:6.1f} {ip*Z:6.1f} {22*Z:8.1f}")
# Upper screen at the 22 A RMS tank ceiling (DECISIONS 2026-10-08) for the nominal 70 uH coil, 34-60 kHz:
for f in (35e3, 45e3, 60e3):
    X=2*math.pi*f*70e-6
    print(f"70 uH @ {f/1e3:.0f} kHz: X={X:.2f} ohm; 22 A rms (time) -> {22*X:.0f} V rms; line-crest carrier pk (I_pk = 2*I_rms for sine envelope) -> {44*X:.0f} V pk")
# IEC 60335-1 29.2.4 route (functional insulation short-circuited, Clause 19): J2-J5 shorted leaves
# the bridge driving C21-C23 (0.54 uF) alone. Fundamental of a +/-Vbus square wave = (4/pi)*Vbus peak.
for vl in (108, 120, 132, 140):
    for f in (34e3, 40e3, 60e3):
        xc = 1/(2*math.pi*f*0.54e-6); v1pk = 4/math.pi*vl*math.sqrt(2)
        print(f"shorted coil: {vl} V line, {f/1e3:.0f} kHz: Xc={xc:.2f} ohm, I_pk={v1pk/xc:5.1f} A (line crest), "
              f"I_rms(time)={v1pk/xc/2:5.1f} A; OCP band 47.5-98 A pk, tank ceiling 22 A rms")
# Table 18 (IEC 60335-1:2020) PD3, material group IIIa column, linear interpolation (NOTE 3)
T18 = [(250, 3.2), (400, 5.0), (500, 6.3)]
def t18(v):
    for (v0, d0), (v1, d1) in zip(T18, T18[1:]):
        if v0 <= v <= v1: return d0 + (v - v0) / (v1 - v0) * (d1 - d0)
    return None if v > 500 else 3.2
for label, v in (("retained cases, time-RMS min", 304.7), ("retained cases, time-RMS max", 320.5),
                 ("22 A ceiling at the retained 1710 W frequencies, max", 271.7),
                 ("ASSEMBLY 540 V pk as carrier-crest RMS (540/sqrt2)", 540/math.sqrt(2)),
                 ("retained max 636 V pk as carrier-crest RMS", 636.2/math.sqrt(2)), ("400 V rms row", 400.0)):
    print(f"Table 18 PD3 IIIa creepage for {label} = {v:.0f} V rms: {t18(v):.2f} mm")
# Bound (estimate) on the coil-terminal voltage inside the operating envelope:
#   V_coil = V_drive,1 - V_C  =>  |V_coil| <= |V_drive,1| + |V_C|
#   tank <= 22 A rms (DECISIONS 2026-10-08), f >= highest tank resonance (ORACLE-ANSWER S4):
#   48 uH (lowest loaded L in ORACLE-ANSWER Q2) with 0.54 uF -> f_res; V_C <= I/(w C) at f_res.
#   Drive fundamental on a line-following bus: (4/pi)*sqrt2*V_line peak at line crest; time-RMS 0.9*V_line.
#   Peak current assumes a sinusoidal line envelope: I_pk = 2 * I_rms(time).
fres = 1/(2*math.pi*math.sqrt(48e-6*0.54e-6)); xc = 1/(2*math.pi*fres*0.54e-6)
for vl in (132, 140):
    vrms = 22*xc + 0.9*vl; vpk = 44*xc + 4/math.pi*math.sqrt(2)*vl
    print(f"envelope bound @ {vl} V line: f_res(48 uH)={fres/1e3:.1f} kHz, Xc={xc:.2f} ohm -> V_coil <= {vrms:.0f} V rms (time), "
          f"<= {vpk:.0f} V pk; Table 18 PD3 IIIa at {vrms:.0f} V rms = {t18(vrms):.2f} mm")
