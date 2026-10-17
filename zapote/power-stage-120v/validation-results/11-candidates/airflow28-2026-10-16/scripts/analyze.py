#!/usr/bin/env python3
"""Tables for results.md from the airflow_search run files: minimum h per ceiling / bay / mode, binding rows, the
enclosure conversion (the jet lane's flat-plate correlation) and the bulk air rise.

    python3 -I analyze.py            -> ../results/analysis.json, prints the tables

Minimum h per row class (all gated = the release rule; laminate = the b3_laminate_margin_K rows; rated parts = every
other gated row, the b3_rated_part_margin_K rows): between the largest solved h where the class fails and the smallest
where it passes, the zero of the class's worst margin, linear in 1/h (the solved bracket is reported with it: 'h_pass'
is a solved, passing h - the defensible number; 'h_zero' the interpolated crossing).

Enclosure conversion (temper-8d airflow-r1 delivery.py 'parallel_flow_alternative', the jet lane's own correlation and
air properties from R43 coil_thermal.py: k 0.0285 W/mK, nu 1.8e-5 m2/s, Pr 0.71, rho 1.09 kg/m3, cp 1005 J/kgK):
flat plate from the leading edge over the flow length L, average Nu_L = 0.664 Re^0.5 Pr^1/3 (laminar) or 0.037 Re^0.8
Pr^1/3 (fully turbulent); h_forced = h (no natural-convection or radiation credit, as delivery.py: h_top = max(10, h)).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import airflow_search as af  # noqa: E402

K_AIR, NU, PR, RHO, CP, CFM = 0.0285, 1.8e-5, 0.71, 1.09, 1005.0, 4.719e-4
BOARD_X, BOARD_Y, BOARD_AREA = 0.290, 0.190, 0.04515        # m, m, m2 (outline bounds and area of native21s47)
PS2_ROW = "PS2:"


def v_for_h(h, L):
    pr3 = PR ** (1 / 3)
    re_l = (h * L / (0.664 * K_AIR * pr3)) ** 2
    re_t = (h * L / (0.037 * K_AIR * pr3)) ** 1.25
    return re_l * NU / L, re_t * NU / L, re_l, re_t


def h_local_lam(v, x):
    """local laminar h at distance x from the leading edge (Nu_x = 0.332 Re_x^0.5 Pr^1/3)."""
    re = v * x / NU
    return 0.332 * re ** 0.5 * PR ** (1 / 3) * K_AIR / x


def ok(v):
    """margin >= 0, with the gate's rounded -0.0 (est a hair over the limit) counted as a FAIL."""
    return v > 0 or (v == 0 and math.copysign(1.0, v) > 0)


def zero_1h(pts):
    """pts {h: margin}: (h_fail, h_pass, h_zero) for the first fail->pass crossing (None if not bracketed)."""
    hs = sorted(pts)
    if ok(pts[hs[0]]):
        return None, hs[0], hs[0]
    for a, b in zip(hs, hs[1:]):
        if not ok(pts[a]) and ok(pts[b]):
            x = 1 / a + (1 / b - 1 / a) * (0 - pts[a]) / (pts[b] - pts[a])
            return a, b, round(1 / x, 1)
    return hs[-1], None, None


def classes(e):
    rows = [r for r in e["rows"] if r["gated"]]
    hdep = [r for r in rows if not r["item"].startswith(PS2_ROW)]
    lam = [r for r in rows if r["item"].startswith("laminate")]
    part = [r for r in rows if not r["item"].startswith("laminate")]
    return {"all": min(r["margin_k"] for r in rows), "hdep": min(r["margin_k"] for r in hdep),
            "laminate": min(r["margin_k"] for r in lam), "parts": min(r["margin_k"] for r in part)}


def series_table(mode, ceil, bay):
    st = af.series_state(ceil, bay, mode)
    if not st:
        return None
    pts = {h: classes(e) for h, e in st.items()}
    out = {"points": {f"{h:g}": {**pts[h], "worst_item": st[h]["worst_item"], "laminate_item": st[h]["laminate_item"],
                                 "parts_item": st[h]["parts_item"], "failing": st[h]["failing"],
                                 "balance": {k: st[h]["balance"][k] for k in ("source_w", "convection_w", "body_air_w",
                                                                             "lead_sink_w")}}
                      for h in sorted(st)}}
    for k in ("all", "laminate", "parts"):
        kk = "hdep" if k == "all" and all(v["all"] >= 0 or v["all"] == v["hdep"] for v in pts.values()) else k
        f, p, z = zero_1h({h: v[kk] for h, v in pts.items()})
        out[k] = {"h_fail": f, "h_pass": p, "h_zero": z}
    hp = out["all"]["h_pass"]
    if hp is not None:
        e = st[hp]
        g = sorted([r for r in e["rows"] if r["gated"]], key=lambda r: r["margin_k"])
        out["at_h_pass"] = [{"item": r["item"], "est_c": r["est_c"], "limit_c": r["limit_c"], "margin_k": r["margin_k"]}
                            for r in g[:8]]
        hf = out["all"]["h_fail"]
        if hf is not None:
            gf = sorted([r for r in st[hf]["rows"] if r["gated"]], key=lambda r: r["margin_k"])
            out["at_h_fail"] = [{"item": r["item"], "margin_k": r["margin_k"]} for r in gf if r["margin_k"] < 0]
    return out


def main():
    res = {"modes": {}}
    for mode in ("uniform", "top", "zone", "zone2", "jet"):
        m = {}
        for bay in (55.0, 61.0):
            for ceil in (18.0, 20.0, 22.0, 24.0, 26.0, 28.0):
                t = series_table(mode, ceil, bay)
                if t:
                    m[f"c{ceil:g}@{bay:g}"] = t
        if m:
            res["modes"][mode] = m
    conv = {}
    for key, t in res["modes"].get("uniform", {}).items():
        h = t["all"]["h_pass"]
        if h is None:
            continue
        row = {"h": h}
        for L, nm in ((0.09, "L90mm"), (BOARD_Y, "L190mm"), (BOARD_X, "L290mm")):
            vl, vt, rl, rt = v_for_h(h, L)
            row[nm] = {"v_laminar_m_s": round(vl, 2), "v_turbulent_m_s": round(vt, 2), "Re_lam": round(rl),
                       "Re_turb": round(rt)}
        bal = t["points"][f"{h:g}"]["balance"]
        q_air = bal["convection_w"] + bal["body_air_w"]
        row["q_to_air_w"] = round(q_air, 2)
        conv[key] = row
    res["conversion"] = conv
    (HERE.parent / "results").mkdir(exist_ok=True)
    (HERE.parent / "results/analysis.json").write_text(json.dumps(res, indent=1) + "\n")
    for mode, m in res["modes"].items():
        print(f"\n== {mode}")
        for k, t in m.items():
            pts = ", ".join(f"h{h} {v['all']:+.1f}" for h, v in t["points"].items())
            print(f"{k:9} all {t['all']}  lam {t['laminate']}  parts {t['parts']}  | {pts}")
            if "at_h_pass" in t:
                print("          binding at h_pass:", "; ".join(f"{r['item'][:34]} {r['margin_k']:+.1f}" for r in t["at_h_pass"][:4]))
    for k, r in conv.items():
        print(k, r)


if __name__ == "__main__":
    main()
