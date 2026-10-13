#!/usr/bin/env python3
"""R2-01: bus peak after a gate-off with NO TVS clamp (D3/D17 deleted), bus C = 2 x B32676G1905K000.

Closed form (reproduces ALT-D3 sec 1.1/1.2 within 3 V, see the self-check): at gate-off the tank returns energy E_t to
the bus capacitor C, then the mains line inductance L_line (current I0) keeps pushing into C from a source at Vs.
    V1   = sqrt(V0^2 + 2*E_t/C)                      (tank energy, lossless: upper bound)
    Vpk  = Vs + sqrt((V1-Vs)^2 + (L/C)*I0^2)   (the series-L/C ring around the source; the bridge keeps conducting until I0 has rung to zero)
Inputs (all from ALT-D3.md, 08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/):
    E_t  = 0.475 J  worst tank energy returned (no pan +10 %, 77 uH)       [ALT-D3 s1.1 table]
    L/I0 = 500 uH / 30 A and 250 uH / 21 A line cases                      [ALT-D3 s1.2]
    V0   = 198 V (127 V +10 % crest) and 286 V (static OVP corner)         [ALT-D3 s1.1]
    C    = 18.4 uF nominal; capacitor tolerance -10 % (K grade) and a further -10 % for ageing/temperature (assumption)
Compared with: ALT-D3 published no-clamp values (18.4 uF: 359 V tank only at V0 286; 387 V tank+500uH; 356/386/410 V DM
surge 1/2/4 kV, simulated, not re-run here), the repo screen 520 V die-VDS target (DECISIONS item 14, ALT-D3) and the
650 V FET rating.  Run: python3 -I bus_peak_no_clamp.py   -> ../results/bus_peak_no_clamp.json"""
import json, math, os
E_T = 0.475
def vpk(C, V0, L, I0, Vs=198.0, Et=E_T):
    V1 = math.sqrt(V0 ** 2 + 2 * Et / C)
    if L == 0:
        return V1
    return Vs + math.sqrt((V1 - Vs) ** 2 + (L / C) * I0 ** 2)
rows = []
for Cname, C in (("18.4 uF nominal", 18.4e-6), ("-10 % (K tol.)", 16.56e-6), ("-19 % (tol. + 10 % ageing)", 14.9e-6), ("5.8 uF (pre-stage-14 basis)", 5.8e-6)):
    for V0 in (198.0, 286.0):
        for (Ln, L, I0) in (("no line L", 0, 0), ("250 uH/21 A", 250e-6, 21), ("500 uH/30 A", 500e-6, 30)):
            rows.append(dict(C=Cname, V0=V0, line=Ln, vpk=round(vpk(C, V0, L, I0), 1)))
for r in rows:
    print("%-30s V0 %3.0f  %-12s -> %6.1f V" % (r["C"], r["V0"], r["line"], r["vpk"]))
chk = {r["C"] + "|" + str(r["V0"]) + "|" + r["line"]: r["vpk"] for r in rows}
alt = {"18.4 uF nominal|198.0|500 uH/30 A": 387, "18.4 uF nominal|286.0|no line L": 359, "5.8 uF (pre-stage-14 basis)|198.0|500 uH/30 A": 578}
print("self-check vs ALT-D3 (published sim values):")
ok = True
for k, v in alt.items():
    print("  %-48s ours %6.1f  ALT-D3 %s" % (k, chk[k], v))
worst = max(r["vpk"] for r in rows if r["C"].startswith(("18.4", "-10", "-19")))
print("worst no-clamp bus peak with stage-14 caps (excl. surge): %.1f V; screen 520 V; FET 650 V" % worst)
json.dump(dict(rows=rows, worst_stage14_no_clamp=worst, alt_d3_selfcheck=alt), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "bus_peak_no_clamp.json"), "w"), indent=1)
