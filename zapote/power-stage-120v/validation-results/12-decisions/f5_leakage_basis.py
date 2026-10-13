#!/usr/bin/env python3 -I
"""F5 leakage budget basis study (stdlib only).  Run: python3 -I f5_leakage_basis.py  (writes f5_result.json).

Model copied (not imported) from 07-conducted-emi/leakage/leakage_budget.py: open-PE touch current per polarity =
omega*C_hot_line*V (all Y caps +20 %) + supply leakage terms; supplies scaled linearly with V and x60/50 for frequency.
Variants follow g01-mains P1, g06 P1 (delete PS1) and P3 (PS2 not in PE path).  Exit 1 if reproduction controls fail.
"""
import json, math, os, sys
W = 2 * math.pi * 60.0
TOL = 1.20

def y_ma(c_f, v): return W * c_f * v * 1e3

# supply leakage (mA per supply) for a given basis
MAX_277 = 0.25            # datasheet "<0.25mA/277Vac", IRM-20-SPEC & IRM-60-SPEC (read: meanwell.com PDFs, spec table)
TYP_240_50 = 0.015        # Simpex test report IRM-20-15: L-FG and N-FG 0.015 mA @ 240 Vac, min load, 25 C, ONE unit
def supply_ma(basis, v, k=1.0):
    if basis == "datasheet_max":
        return MAX_277 * (v / 277.0) * 1.2
    if basis == "measured_typ_x_k":      # measured typical (one unit, IRM-20-15) x spread factor k, scaled to v and 60 Hz
        return k * TYP_240_50 * (v / 240.0) * 1.2
    raise ValueError(basis)

def touch(v, board_y_nF, module_y_nF, ps, basis, k=1.0, coil_pF=31.0):
    y = y_ma((board_y_nF + module_y_nF) * 1e-9 * 1.0, v) * TOL + y_ma(coil_pF * 1e-12, v) * TOL
    return y + sum(supply_ma(basis, v, k) for _ in ps)

# variants: (board Y nF, module Y nF, supplies counted in the PE path)
VARS = {
 "benchmark 19c (as built)":                   (2.2, 6.9, ["PS1", "PS2", "PS3"]),
 "G01 P1 (module Y 4.7+2.2 -> 2.2)":            (2.2, 2.2, ["PS1", "PS2", "PS3"]),
 "G06 P1 (delete PS1)":                         (2.2, 6.9, ["PS2", "PS3"]),
 "G06 P1 + P3 (PS2 not in PE path)":            (2.2, 6.9, ["PS3"]),
 "G06 P3 only":                                 (2.2, 6.9, ["PS1", "PS3"]),
 "G01 P1 + G06 P1":                             (2.2, 2.2, ["PS2", "PS3"]),
 "G01 P1 + G06 P1 + P3 (all three)":            (2.2, 2.2, ["PS3"]),
}
BASES = [("datasheet_max", 1.0), ("measured_typ_x_k", 1.0), ("measured_typ_x_k", 3.0), ("measured_typ_x_k", 5.0), ("measured_typ_x_k", 10.0)]
VOLTS = {"132 V (120+10 %, repo)": 132.0, "127 V (Mexico nominal)": 127.0, "134.6 V (1.06 x 127, IEC-style) [UNVERIFIED test factor]": 127.0 * 1.06}
LIMITS = {"0.5 mA (UL portable)": 0.5, "0.75 mA (UL stationary / IEC 60335-1 portable Class I)": 0.75}

res = {}
for vn, v in VOLTS.items():
    for name, (by, my, ps) in VARS.items():
        for basis, k in BASES:
            t = touch(v, by, my, ps, basis, k)
            key = f"{vn} | {name} | {basis}{'' if basis=='datasheet_max' else ' x%g' % k}"
            res[key] = dict(touch_mA=t, **{f"pct_of_{ln.split()[0]}": 100 * t / lv for ln, lv in LIMITS.items()})

# controls: reproduce repo numbers at 132 V
c1 = touch(132.0, *VARS["benchmark 19c (as built)"], "datasheet_max")
c2 = touch(132.0, *VARS["G01 P1 (module Y 4.7+2.2 -> 2.2)"], "datasheet_max")
c3 = touch(132.0, *VARS["G06 P1 (delete PS1)"], "datasheet_max")
c4 = touch(132.0, *VARS["G06 P1 + P3 (PS2 not in PE path)"], "datasheet_max")
c5 = touch(132.0, *VARS["benchmark 19c (as built)"], "measured_typ_x_k", 1.0)
ok = (abs(c1 - 0.9741) < 5e-4 and abs(c2 - 0.693) < 5e-3 and abs(c3 - 0.831) < 5e-3 and abs(c5 - 0.575) < 1e-2)
# (G06 P1+P3 = 0.688 in repo is with G01 P1 per its text: "0.688 mA with P1" = G01 P1 on 3 supplies minus PS2: check below)
ok = bool(ok and abs(c4 - 0.688) < 5e-3)   # repo G06 P1+P3 = 0.688

# budget capacity: max total Y per line (board+module, nominal, with 1.2x) at limit*frac for each supply basis, V=132, supplies = PS1+PS2+PS3 / PS3-only
def y_allow_nF(limit, frac, v, n_ps, basis, k=1.0):
    avail = limit * frac - n_ps * supply_ma(basis, v, k) - y_ma(31e-12, v) * TOL
    return max(0.0, avail) / (W * v * 1e3 * TOL) * 1e9
allow = {}
for lname, lv in LIMITS.items():
    for frac in (1.0, 0.8, 0.5):
        for n_ps in (3, 2, 1):
            for basis, k in BASES:
                allow[f"{lname.split()[0]} mA x{frac} | {n_ps} supplies | {basis}{'' if basis=='datasheet_max' else ' x%g'%k}"] = y_allow_nF(lv, frac, 132.0, n_ps, basis, k)

out = dict(controls=dict(benchmark_132=c1, g01p1_132=c2, g06p1_132=c3, g06p1_p3_132=c4, benchmark_typ_132=c5), controls_ok=ok,
           supply_per_unit_mA_132V=dict(datasheet_max=supply_ma("datasheet_max", 132.0), typ_x1=supply_ma("measured_typ_x_k", 132.0, 1.0),
                                        typ_x3=supply_ma("measured_typ_x_k", 132.0, 3.0), typ_x5=supply_ma("measured_typ_x_k", 132.0, 5.0), typ_x10=supply_ma("measured_typ_x_k", 132.0, 10.0)),
           max_to_typ_ratio_unscaled=MAX_277/ (TYP_240_50*277/240),
           results=res, y_allowance_nF_per_line_total=allow)
here = os.path.dirname(os.path.abspath(__file__))
json.dump(out, open(os.path.join(here, "f5_result.json"), "w"), indent=2, sort_keys=True)

print("controls (132 V): benchmark %.3f (repo 0.974), G01P1 %.3f (0.693), G06P1 %.3f (0.831), G06P1+P3 %.3f, typ-x1 benchmark %.3f (repo 0.575) -> %s" % (c1, c2, c3, c4, c5, "OK" if ok else "BROKEN"))
print("per-supply leakage at 132 V/60 Hz: max %.3f mA, typ x1 %.4f, x3 %.4f, x5 %.4f, x10 %.4f" % tuple(out["supply_per_unit_mA_132V"][k] for k in ("datasheet_max","typ_x1","typ_x3","typ_x5","typ_x10")))
print("datasheet max is %.1fx the one measured unit (both scaled to 277 V)" % out["max_to_typ_ratio_unscaled"])
for vn in VOLTS:
    print("\n== %s   (mA; pct of 0.5 / of 0.75)" % vn)
    hdr = "%-38s" % "variant" + "".join("%16s" % (b if b == 'datasheet_max' else 'typ x%g' % k)[:15] for b, k in BASES)
    print(hdr)
    for name in VARS:
        row = "%-38s" % name
        for b, k in BASES:
            key = f"{vn} | {name} | {b}{'' if b=='datasheet_max' else ' x%g' % k}"
            row += "%9.3f(%3.0f/%3.0f)" % (res[key]["touch_mA"], res[key]["pct_of_0.5"], res[key]["pct_of_0.75"])
        print(row)
print("\nAllowed total Y per line (nF, nominal, 132 V, coil incl.) at 0.5 mA x 0.8 / x1.0 and 0.75 x 0.8:")
for key in allow:
    if any(s in key for s in ("0.5 mA x0.8 | 3", "0.5 mA x1.0 | 3", "0.75 mA x0.8 | 3", "0.5 mA x0.8 | 1", "0.5 mA x1.0 | 1")) and "x10" not in key:
        print("  %-62s %6.2f" % (key, allow[key]))
sys.exit(0 if ok else 1)
