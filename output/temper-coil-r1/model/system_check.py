"""System check of the coil against the native-21 power stage and the firmware loop.

Tank: series R-L-C, first-harmonic, line-cycle averaged, the same plant the firmware host tests use
(firmware/test/test_tank_freq.c: V1 = 0.9 x V_line, peak = 2.17 x line-RMS tank current).
  C     : 5 x TDK B32643H8104J000 100 nF +/-5 % (prototype lot, power-stage DECISIONS 74) = 0.50 uF (0.475-0.525)
  L, R  : installed loaded L and reflected R from run_pans.py (3D-corrected), f-interpolated, plus the Litz R_ac of the
          winding at 100 C (run_free_air.py)
  loop  : tank_freq.h - start at 60 kHz, step down to the lowest f in 35-60 kHz that keeps
          f >= 1.05 f_res, lag >= zvs_lag_deg (45), tank RMS <= ceiling, delivered power <= hold
  hold  : 11.1 A input at the line voltage x eta 0.93 (round 5's 1239 W at 120 V)
  trips : firmware peak trip min(2.17 c + 3, 62) A; CT band 64.55-76.09 A (stage 15); RMS trip 1.05 c
Two pan bases are run: MODEL (this study's FEM pans, mu low/nominal/high) and PRIORS (coil_mc.rs / round-4 classes:
kL and r = R_pan/L at 40 kHz, R ~ sqrt(f)), so the recommendation does not rest on one set of assumptions.
Run: .venv/bin/python model/system_check.py -> model/results/system.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PANS = json.loads((HERE / "results" / "pans.json").read_text())
FREE = json.loads((HERE / "results" / "free_air.json").read_text())
C_NOM, C_TOL = 0.50e-6, 0.05
ETA = 0.93
F_MIN, F_MAX = 35e3, 60e3
PEAK_PER_RMS = 2.17
CT_BAND = (64.55, 76.09)
PRIORS = {  # coil_mc.rs PANS (kl, r40 ohm/uH of L no-pan) - round-4 assumed basis
    "cast_iron": ((0.74, 0.86), (0.036, 0.052)),
    "carbon_or_430_steel": ((0.66, 0.80), (0.029, 0.041)),
    "triply_clad_GUESS": ((0.66, 0.82), (0.018, 0.032)),
    "low_R_silargan_like": ((0.58, 0.68), (0.020, 0.029)),
    "offset_or_small_pan": ((0.80, 0.90), (0.012, 0.022)),
}


def coil_rac(layout, f, T=100.0):
    rows = [r for r in FREE["candidates"][layout]["rac"] if r["T_C"] == T]
    fs = [r["f_kHz"] * 1e3 for r in rows]
    return float(np.interp(f, fs, [r["R_ac_mohm"] * 1e-3 for r in rows]))


def model_pan(layout, pan, mu_tag, d):
    rows = [r for r in PANS["rows"] if r["layout"] == layout and r["pan"] == pan and r["mu_tag"] == mu_tag and r["pan_d_mm"] == d]
    rows.sort(key=lambda r: r["f_kHz"])
    fs = np.array([r["f_kHz"] * 1e3 for r in rows])
    L = np.array([r["L_uH"] * 1e-6 for r in rows])
    R = np.array([r["R_refl_ohm"] for r in rows])
    if len(rows) == 1:          # single-frequency rows (180 mm lo/hi): use the nominal row's f-shape
        nom = model_pan(layout, pan, "nom", d)
        Ln, Rn = nom(40e3)
        return lambda f: (L[0] * nom(f)[0] / Ln, R[0] * nom(f)[1] / Rn)
    return lambda f: (float(np.exp(np.interp(math.log(f), np.log(fs), np.log(L)))),
                      float(np.exp(np.interp(math.log(f), np.log(fs), np.log(R)))))


def prior_pan(L_inst, kl, r40):
    return lambda f: (L_inst * 1e-6 * kl, r40 * L_inst * math.sqrt(f / 40e3))


def operate(pan_fn, layout, V, C, ceiling, lag_deg=45.0, hold_A=11.1, step=50.0):
    """The firmware loop's end point: lowest f in the window meeting every limit. Returns a dict."""
    v1 = 0.9 * V
    hold_W = hold_A * V * ETA

    def point(f):
        L, Rp = pan_fn(f)
        R = Rp + coil_rac(layout, f)
        w = 2 * math.pi * f
        X = w * L - 1 / (w * C)
        Z = math.hypot(R, X)
        I = v1 / Z
        return dict(f=f, L=L, R=R, R_pan=Rp, X=X, I=I, P=I * I * R, P_pan=I * I * Rp, lag=math.degrees(math.atan2(X, R)),
                    f_res=1 / (2 * math.pi * math.sqrt(L * C)))
    fs = np.arange(F_MAX, F_MIN - 1, -step)
    best, limit = None, "f_min"
    for f in fs:
        p = point(f)
        ok = (f >= 1.05 * p["f_res"]) and p["lag"] >= lag_deg and p["I"] <= ceiling and p["P"] <= hold_W
        if not ok:
            if best is None:
                limit = "over_limit_at_f_max"
                best = p
            else:
                limit = ("zvs_floor" if f < 1.05 * p["f_res"] else "lag" if p["lag"] < lag_deg else
                         "ceiling" if p["I"] > ceiling else "hold")
            break
        best = p
    out = dict(best)
    out.update(limit=limit, V=V, C=C, ceiling=ceiling, lag_rule=lag_deg, hold_W=hold_W,
               full_power=out["P"] >= 0.97 * hold_W and limit != "over_limit_at_f_max",
               I_pk=PEAK_PER_RMS * out["I"], Vc_rms=out["I"] / (2 * math.pi * out["f"] * C),
               Vc_pk=PEAK_PER_RMS * out["I"] / (2 * math.pi * out["f"] * C), fw_peak_trip=min(2.17 * ceiling + 3, 62.0))
    out["f_over_fres"] = out["f"] / out["f_res"]
    return out


def sweep(layout, basis, ceiling, lag_deg=45.0, d=240.0):
    rows = []
    L_inst = FREE["candidates"][layout]["L_installed_uH"]
    pans = []
    if basis == "model":
        for pan in ("ss430", "triply", "cast_iron", "carbon_steel"):
            for tag in ("lo", "nom", "hi"):
                pans.append((pan, tag, model_pan(layout, pan, tag, d)))
    else:
        for pan, (kl, r40) in PRIORS.items():
            for a in (0, 1):
                for b in (0, 1):
                    pans.append((pan, f"kl{kl[a]}_r{r40[b]}", prior_pan(L_inst, kl[a], r40[b])))
    for pan, tag, fn in pans:
        for V in (108.0, 120.0, 132.0):
            for C in (C_NOM * (1 - C_TOL), C_NOM, C_NOM * (1 + C_TOL)):
                o = operate(fn, layout, V, C, ceiling, lag_deg)
                o.update(pan=pan, tag=tag)
                rows.append(o)
    return rows


def summary(rows):
    fp = [r for r in rows if r["full_power"]]
    over = [r for r in rows if r["limit"] == "over_limit_at_f_max"]
    nom120 = [r for r in rows if r["V"] == 120.0 and r["C"] == C_NOM]
    return dict(n=len(rows), full_power_share=len(fp) / len(rows), over_limit_at_fmax=len(over),
                P_min_W=min(r["P"] for r in rows), P_median_W=float(np.median([r["P"] for r in rows])),
                f_op_kHz=[min(r["f"] for r in rows) / 1e3, max(r["f"] for r in rows) / 1e3],
                f_res_kHz=[min(r["f_res"] for r in rows) / 1e3, max(r["f_res"] for r in rows) / 1e3],
                f_over_fres_min=min(r["f_over_fres"] for r in rows), lag_min_deg=min(r["lag"] for r in rows),
                I_pk_max=max(r["I_pk"] for r in rows), Vc_rms_max=max(r["Vc_rms"] for r in rows),
                Vc_pk_max=max(r["Vc_pk"] for r in rows),
                limits={k: sum(1 for r in rows if r["limit"] == k) for k in sorted({r["limit"] for r in rows})},
                per_pan_120V_nomC={f"{r['pan']}/{r['tag']}": dict(P=round(r["P"]), f_kHz=round(r["f"] / 1e3, 2), I=round(r["I"], 1),
                                                                 lag=round(r["lag"], 1), limit=r["limit"]) for r in nom120})


def special_loads(layout):
    """No pan (installed coil), aluminium pan, 180 mm pans: the loop's start at 60 kHz."""
    out = {}
    L_inst = FREE["candidates"][layout]["L_installed_uH"] * 1e-6
    for name, fn in (("no_pan", lambda f: (L_inst, 0.0)), ("aluminium_240", model_pan(layout, "aluminium", "nom", 240.0)),
                     ("aluminium_180", model_pan(layout, "aluminium", "nom", 180.0)),
                     ("carbon_steel_lo_180", model_pan(layout, "carbon_steel", "lo", 180.0))):
        res = {}
        for V in (120.0, 132.0):
            for C in (C_NOM * (1 - C_TOL), C_NOM * (1 + C_TOL)):
                L, R = fn(F_MAX)
                R += coil_rac(layout, F_MAX)
                w = 2 * math.pi * F_MAX
                X = w * L - 1 / (w * C)
                I = 0.9 * V / math.hypot(R, X)
                res[f"{V:.0f}V_C{C * 1e9:.0f}nF"] = dict(I_rms_at_60kHz=I, I_pk=PEAK_PER_RMS * I, f_res_kHz=1 / (2 * math.pi * math.sqrt(L * C)) / 1e3,
                                                        Q=w * L / R, R_total=R)
        out[name] = res
    return out


def main():
    out = dict(assumptions=__doc__)
    for layout in ("R1", "70uH_out6.46", "80uH_out6.46", "R43_21.93"):
        lay = {}
        for basis in ("model", "priors"):
            for ceiling in (17.5, 24.0, 28.0):
                for lag in (45.0, 30.0):
                    rows = sweep(layout, basis, ceiling, lag)
                    lay[f"{basis}_{ceiling:g}A_lag{lag:g}"] = summary(rows)
        lay["special_loads"] = special_loads(layout)
        out[layout] = lay
    (HERE / "results" / "system.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for layout in ("R1", "70uH_out6.46", "80uH_out6.46", "R43_21.93"):
        print(f"== {layout}")
        for k, s in out[layout].items():
            if k == "special_loads":
                continue
            print(f"  {k:24s} full {s['full_power_share'] * 100:5.1f}%  Pmin {s['P_min_W']:5.0f}  Pmed {s['P_median_W']:5.0f}  "
                  f"f {s['f_op_kHz'][0]:.1f}-{s['f_op_kHz'][1]:.1f}  fres {s['f_res_kHz'][0]:.1f}-{s['f_res_kHz'][1]:.1f}  "
                  f"x>= {s['f_over_fres_min']:.2f}  Ipk {s['I_pk_max']:.1f}  Vc {s['Vc_rms_max']:.0f}/{s['Vc_pk_max']:.0f}  "
                  f"over@60k {s['over_limit_at_fmax']}  {s['limits']}")
        for k, v in out[layout]["special_loads"].items():
            print("   ", k, {kk: (round(vv["I_rms_at_60kHz"], 1), round(vv["f_res_kHz"], 1), round(vv["Q"], 1)) for kk, vv in v.items()})


if __name__ == "__main__":
    main()
