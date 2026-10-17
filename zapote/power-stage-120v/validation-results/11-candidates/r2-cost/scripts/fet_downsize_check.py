#!/usr/bin/env python3
"""R2-R1/R2-R2: why the four IPW65R018CFD7 ($40.7 of $234.8) cannot simply be swapped for a cheaper, higher-Rds(on) or IGBT part.

Conduction only (a lower bound on the penalty; switching loss and body-diode loss are not added for the MOSFET options):
    per-FET RMS current I_f = I_tank_rms / sqrt(2)   (full bridge, each FET conducts half the cycle of a sinusoidal tank current)
    P_cond,MOSFET = I_f^2 * Rds25 * k_hot           (k_hot = hot/25C Rds ratio, assumption 1.9 at Tj 125 C; relative results do not depend on it)
    IGBT: P_cond = Vce0 * I_avg + rce * I_f^2 with I_avg = Ipk/pi, Ipk = sqrt(2)*I_tank (device+diode share the half-cycle; upper-bound split)
Budget: DECISIONS.md 2026-10-09 D-18: R_SA <= 0.29 C/W holds for 125.9 W total sink loss at Tj 125 C, 50 C air.  All four FETs share the sink.
Inputs: Rds(on) 18 mohm (IPW65R018CFD7, JLC C3289047 listing 'Infineon IPW65R018CFD7 18 mohm @10V'), 41 mohm (IPW65R041CFD7, RS-Online
listing title, mohm from the part number), IKW40N65H5 Vce(sat) 1.65 V @40 A (JLC C454249), IKW40N65WR5 1.4 V (JLC C108740).
IGBT rce is approximated from Vce(sat)@40A minus a 0.8 V knee: rce = (Vsat-0.8)/40 (assumption, flagged).  Datasheets NOT read for the
IGBTs; this is a screen to show the order of magnitude, not a design.  Run python3 -I fet_downsize_check.py"""
import math, json, os
K_HOT = 1.9
BUDGET_W = 125.9
def mos(r25_mohm, i_tank):
    i_f = i_tank / math.sqrt(2)
    return 4 * i_f ** 2 * r25_mohm * 1e-3 * K_HOT
def igbt(vsat, i_tank, vknee=0.8):
    i_f = i_tank / math.sqrt(2)
    ipk = math.sqrt(2) * i_tank
    iavg = ipk / math.pi
    rce = (vsat - vknee) / 40.0
    return 4 * (vknee * iavg + rce * i_f ** 2)
out = []
for I in (22.0, 28.0):
    base = mos(18, I)
    for name, p in (("IPW65R018CFD7 (as built)", base), ("IPW65R041CFD7 (41 mohm)", mos(41, I)),
                    ("IKW40N65H5 (Vsat 1.65 V), cond. only", igbt(1.65, I)), ("IKW40N65WR5 (Vsat 1.4 V), cond. only", igbt(1.40, I))):
        out.append(dict(i_tank=I, part=name, cond_W=round(p, 1), delta_W=round(p - base, 1), total_if_rest_fixed=round(BUDGET_W + p - base, 1)))
        print("I_tank %4.1f A  %-40s  %5.1f W conduction (4 devices)  delta %+6.1f W  -> sink load %6.1f W vs %.1f W budget" % (I, name, p, p - base, BUDGET_W + p - base, BUDGET_W))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "fet_downsize_check.json"), "w"), indent=1)
