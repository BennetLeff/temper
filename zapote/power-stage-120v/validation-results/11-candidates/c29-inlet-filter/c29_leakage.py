#!/usr/bin/env python3 -I
"""C29 leakage: Y-capacitance budget for an on-board inlet filter (D-22 module function moved onto the power board).

Rerun: python3 -I c29_leakage.py   (stdlib only; writes c29_leakage.json next to this file; exit 1 if a control fails)

Model and constants are copied (not imported, not edited) from
  07-conducted-emi/leakage/leakage_budget.py:14-46   (132 V, 60 Hz, +20 % on every Y, supplies 0.25 mA @ 277 V
                                                       scaled x V/277 x 60/50, coil-to-PE 31 pF at +20 %)
  12-decisions/F5-LEAKAGE-DECISION.md:10-12          (Test A: <= 0.5 mA, datasheet-max supplies;
                                                       Test B: <= 0.40 mA, supplies at 5 x measured typical
                                                       = 5 x 0.015 mA @ 240 V scaled)
Touch current (UL open-PE test, per polarity) = hot line's Y at +20 % + coil 31 pF at +20 % + supply terms.
Supply sets follow the F5 decision record: 3 = as built (PS1, PS2, PS3); 2 = PS1 deleted (g06 P1, in candidate 23);
1 = PS1 deleted and PS2 not in the PE path (g06 P3, a bench claim, not yet a measurement)."""
import json, math, os, sys

V, F, TOL = 132.0, 60.0, 0.20
W = 2 * math.pi * F
COIL_MA = W * 31e-12 * (1 + TOL) * V * 1e3
SUP_MAX = 0.25 * (V / 277.0) * (60.0 / 50.0)          # mA per supply, datasheet max (leakage_budget.py:33-37)
SUP_TYP = 0.015 * (V / 240.0) * (60.0 / 50.0)         # mA per supply, Simpex IRM-20-15 one unit (informational)
MA_PER_NF = W * 1e-9 * (1 + TOL) * V * 1e3             # mA of touch current per nF nominal Y per line, at +20 %


def touch(y_nom_nF, n_sup, basis="max"):
    s = SUP_MAX if basis == "max" else 5 * SUP_TYP
    return y_nom_nF * MA_PER_NF + COIL_MA + n_sup * s


def y_allow(limit_mA, n_sup, basis="max"):
    s = SUP_MAX if basis == "max" else 5 * SUP_TYP
    return max(limit_mA - COIL_MA - n_sup * s, 0.0) / MA_PER_NF


# ---- controls: reproduce the repo's numbers before using the model
ctl = {
    "benchmark 9.1 nF, 3 supplies max = 0.974 mA (leakage_budget.py DESIGN)": (touch(9.1, 3), 0.9741),
    "g01 P1 4.4 nF, 3 max = 0.693 (F5 table)": (touch(4.4, 3), 0.693),
    "g01 P1 + g06 P1: 4.4 nF, 2 max = 0.551 (F5 table)": (touch(4.4, 2), 0.551),
    "g01 P1 + g06 P1 + P3: 4.4 nF, 1 max = 0.408 (F5 table)": (touch(4.4, 1), 0.408),
    "g01 P1 + g06 P1: 4.4 nF, 2 x (5 x typ) = 0.364 (F5 Test B)": (touch(4.4, 2, "typ5"), 0.364),
    "Y allowed 3 max @0.5 = 1.16 nF (leakage_variants.py)": (y_allow(0.5, 3), 1.16),
    "Y allowed 1 max @0.5 = 5.95 nF": (y_allow(0.5, 1), 5.95),
}
ok = all(abs(a - b) < 6e-3 for a, b in ctl.values())

# ---- Q2: allowed total Y per line (board + former-module, nominal nF; with +20 % applied inside)
rows = []
for n_sup, lab in ((3, "3 supplies (as built)"), (2, "PS1 deleted (cand. 23 / g06 P1)"),
                   (1, "PS1 deleted + PS2 off the PE path (g06 P3, bench claim)")):
    for basis, blab in (("max", "datasheet max"), ("typ5", "5 x measured typical")):
        for lim, llab in ((0.5, "0.5 mA limit (Test A)"), (0.40, "0.40 mA (Test B)"), (0.25, "0.25 mA 50 % target")):
            if basis == "max" and lim == 0.40: continue
            if basis == "typ5" and lim == 0.5: continue
            rows.append(dict(supplies=lab, n_sup=n_sup, basis=blab, limit_mA=lim, criterion=llab,
                             supplies_mA=round(n_sup * (SUP_MAX if basis == "max" else 5 * SUP_TYP), 4),
                             y_allowed_nominal_nF_per_line=round(y_allow(lim, n_sup, basis), 3)))

# ---- candidate on-board Y sets (nominal per line) -> touch current on both tests
cands = {
    "benchmark (board 2.2 + module 4.7 + 2.2)": 9.1,
    "g01 P1 (board 2.2 + module HF 2.2)": 4.4,
    "C29-A: 3.3 nF total (e.g. 2.2 + 1.0 or one 3.3 nF Y1)": 3.3,
    "C29-C: 2.7 nF total (2.2 + 0.47 nF)": 2.7,
    "C29-B: 2.2 nF total (board C3/C4 only, the as-built Y1 pair)": 2.2,
    "C29-x: 1.5 nF total": 1.5,
    "C29-D: 1.0 nF total (3-supply Test A ceiling 1.16)": 1.0,
    "C29-x: 0 nF (no Y at all; supplies + coil only)": 0.0,
}
cand_rows = {}
for name, y in cands.items():
    cand_rows[name] = {f"{n}sup_{b}": round(touch(y, n, b), 3) for n in (3, 2, 1) for b in ("max", "typ5")}
    cand_rows[name]["Y_nF"] = y

out = dict(V=V, f=F, tol=TOL, coil_mA=COIL_MA, supply_max_mA_each=SUP_MAX, supply_5typ_mA_each=5 * SUP_TYP,
           mA_per_nF_nominal_Y=MA_PER_NF, controls={k: dict(got=round(a, 4), want=b) for k, (a, b) in ctl.items()},
           controls_ok=ok, y_budget=rows, candidates_touch_mA=cand_rows)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "c29_leakage.json"), "w"), indent=1)

print(f"132 V 60 Hz, +20 % Y: {MA_PER_NF:.4f} mA per nF/line; coil {COIL_MA:.4f} mA; supply {SUP_MAX:.4f} mA (max) / "
      f"{5*SUP_TYP:.4f} mA (5 x typ) each")
for k, (a, b) in ctl.items(): print(f"  control {'OK ' if abs(a-b) < 6e-3 else 'BAD'} {k}: {a:.4f}")
print("\nAllowed total Y per line, nominal nF (board + former module):")
for r in rows:
    print(f"  {r['supplies']:58s} {r['basis']:22s} {r['criterion']:24s} supplies {r['supplies_mA']:.3f} mA -> "
          f"{r['y_allowed_nominal_nF_per_line']:.2f} nF")
print("\nTouch current (mA) of candidate Y sets  [3/2/1 supplies, datasheet max | 5 x typical]:")
for k, v in cand_rows.items():
    print(f"  {k:62s} max {v['3sup_max']:.3f}/{v['2sup_max']:.3f}/{v['1sup_max']:.3f}   "
          f"5typ {v['3sup_typ5']:.3f}/{v['2sup_typ5']:.3f}/{v['1sup_typ5']:.3f}")
print("controls", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
