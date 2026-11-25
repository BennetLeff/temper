#!/usr/bin/env python3
"""Candidate 4b: an RC-IGBT at a retuned ~20-30 kHz operating point. What coil and bank, and do 120 V power delivery
and pan coverage survive?

Tool: the coil study's system check (output/temper-coil-r1/model/system_check.py, imported read-only): series R-L-C,
first harmonic, line-cycle averaged, the firmware loop's end point (start at F_MAX, step down while f >= 1.05 f_res,
lag >= 45 deg, I <= ceiling, P <= 1239 W hold), on the study's FEM pans (3D-corrected, 20-60 kHz rows; model basis)
and the round-4 priors. Only its module constants are changed here: the bank C_NOM and the window F_MIN / F_MAX.
Coils: R1 (20.93 t, 81 uH free air) and R43_21.93 (87.7 uH), both solved in the coil model; plus R1 scaled by
turns ratio k (L, R_pan ~ k^2, winding R_ac ~ k): [EST], a trend only, no FEM.
Control: with the module's own constants the R1 model/priors summaries equal the committed results/system.json.

    python3 -I c60_retune.py   -> ../results/retune.json, ../results/retune.md
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, PS, _load  # noqa: E402

COIL = PS.parents[1] / "output/temper-coil-r1/model"
sys.path.insert(0, str(COIL))
S = _load("coil_system_check", COIL / "system_check.py")
REF = json.loads((COIL / "results/system.json").read_text())
KEYS = ("full_power_share", "P_min_W", "P_median_W", "f_op_kHz", "f_res_kHz", "I_pk_max", "Vc_pk_max", "limits")


def control():
    worst = {}
    ok = True
    for basis in ("model", "priors"):
        for ceil in (17.5, 28.0):
            mine = S.summary(S.sweep("R1", basis, ceil, 45.0))
            ref = REF["R1"][f"{basis}_{ceil:g}A_lag45"]
            for k in KEYS:
                a, b = mine[k], ref[k]
                same = (abs(a - b) < 1e-9) if isinstance(a, float) else (
                    all(abs(x - y) < 1e-9 for x, y in zip(a, b)) if isinstance(a, list) else a == b)
                ok &= same
                if not same:
                    worst[f"{basis}_{ceil}_{k}"] = (a, b)
    return {"R1_model_priors_17.5_28A_lag45_identical": ok, "diffs": worst}


def scaled(layout, k):
    """R1 with k x turns [EST]: pan L and reflected R ~ k^2, winding R_ac ~ k (same Litz, longer)."""
    base_pan = S.model_pan
    base_rac = S.coil_rac

    def pan(lay, pan_, tag, d):
        fn = base_pan(layout, pan_, tag, d)
        return lambda f: (fn(f)[0] * k * k, fn(f)[1] * k * k)

    def rac(lay, f, T=100.0):
        return base_rac(layout, f, T) * k
    return pan, rac


def run(layout, C, fmin, fmax, ceil, basis="model", k=None):
    S.C_NOM, S.F_MIN, S.F_MAX = C, fmin, fmax
    saved = (S.model_pan, S.coil_rac)
    if k is not None:
        S.model_pan, S.coil_rac = scaled(layout, k)
    try:
        rows = S.sweep(layout, basis, ceil, 45.0)
        s = S.summary(rows)
        fp = {}
        for r in rows:
            fp.setdefault(r["pan"], []).append(r["full_power"])
        s["full_power_share_by_pan"] = {p: round(sum(v) / len(v), 3) for p, v in fp.items()}
        s["I_rms_max"] = max(r["I"] for r in rows)
        s["operable_share"] = sum(r["limit"] != "over_limit_at_f_max" for r in rows) / len(rows)
        op = [r for r in rows if r["limit"] != "over_limit_at_f_max"]
        s["I_rms_max_operable"] = max((r["I"] for r in op), default=0.0)
        s["Vc_pk_max_operable"] = max((r["Vc_pk"] for r in op), default=0.0)
    finally:
        S.model_pan, S.coil_rac = saved
        S.C_NOM, S.F_MIN, S.F_MAX = 0.50e-6, 35e3, 60e3
    return s


def main():
    c = control()
    print("control", c)
    assert c["R1_model_priors_17.5_28A_lag45_identical"], c
    out = {"control": c, "rows": []}
    md = ["| coil | bank uF | window kHz | ceiling A | basis | full power share | P min / median W | f_op kHz | f_res kHz | "
          "operable share | I_rms max A (operable) | V_C pk max V (operable) | binding limits |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    plan = [("R1", None, 0.5e-6, 35e3, 60e3)]                         # today (control row, 35-60 kHz)
    for lay, k in (("R1", None), ("R43_21.93", None), ("R1", 1.15), ("R1", 1.25)):
        for C in (0.75e-6, 1.0e-6, 1.25e-6, 1.5e-6):
            for fmax in (30e3, 40e3):
                plan.append((lay, k, C, 20e3, fmax))
    for lay, k, C, fmin, fmax in plan:
        for ceil in (17.5, 28.0):
            for basis in ("model", "priors"):
                s = run(lay, C, fmin, fmax, ceil, basis, k)
                name = lay + (f" x{k:g} turns [EST]" if k else "")
                row = {"coil": name, "C_uF": C * 1e6, "window_kHz": [fmin / 1e3, fmax / 1e3], "ceiling_A": ceil,
                       "basis": basis, **{kk: s[kk] for kk in KEYS}, "I_rms_max": s["I_rms_max"], "operable_share": s["operable_share"],
                       "I_rms_max_operable": s["I_rms_max_operable"], "Vc_pk_max_operable": s["Vc_pk_max_operable"],
                       "full_power_share_by_pan": s["full_power_share_by_pan"]}
                out["rows"].append(row)
                md.append(f"| {name} | {C * 1e6:.2f} | {fmin / 1e3:.0f}-{fmax / 1e3:.0f} | {ceil:g} | {basis} | "
                          f"{s['full_power_share'] * 100:.0f} % | {s['P_min_W']:.0f} / {s['P_median_W']:.0f} | "
                          f"{s['f_op_kHz'][0]:.1f}-{s['f_op_kHz'][1]:.1f} | {s['f_res_kHz'][0]:.1f}-{s['f_res_kHz'][1]:.1f} | "
                          f"{s['operable_share'] * 100:.0f} % | {s['I_rms_max_operable']:.1f} | {s['Vc_pk_max_operable']:.0f} | {s['limits']} |")
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/retune.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    (C55 / "results/retune.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
