#!/usr/bin/env python3
"""PROPOSED scorecard producer (bank28): the resonant bank's physical self-heating check at 28 A under the DECLARED
airflow, replacing the vendor-curve ratio as the bank's 28 A metric.

    python3 -I bank_air_metric.py [--ps PS] [--runs RUNS] [--out OUT.json] [--control ../bank_thermal.json]

Metric `bank_air_ratio_28A_35k` (lower is better; <= 1.00 meets TDK's own limit, <= 0.85 keeps the c34 margin):

    max over the declared airflow points and over the column positions (interior C22/C23/C151, ends C21/C152) of
        sqrt( dT_col / (dT_lim x F_T(T_A)^2) )
    dT_col = r35^2 x dT_lim x G_tdk / G_col
      r35    : c34 bank_margin.json ratio_35k of the fitted bank (J worst share, 28 A, the 35 kHz floor)
      dT_lim : the family's curve basis (B3265x 20 K, p.57; B3264*B 15 K, p.24 / p.11 fn 8)
      G_tdk  : the part alone in still air at T_A 85 C (TDK's test), natural convection + radiation eps 0.9
      G_col  : the part in the 0.5 mm-gap column (two h x l faces shadowed for an interior part), forced convection
               at the declared bank velocity, CONSERVATIVE correlation (Incropera Table 7.3 square prism, flat face
               to the flow, Nu = 0.102 Re^0.675 Pr^1/3, D = l), no radiation; plus G_board
      G_board: 0.005 W/K (TDK-implied) and 0.020 + K_air A_bottom / 0.5 mm (B3 lead path + seat gap); worse of the two
      T_A    : the unpowered-dummy temperature (TDK GTI p.30 Fig. 26) = (G_air T_air + G_board T_pad) / (G_air + G_board),
               T_air = bay + the flow path's bulk rise, T_pad = the B3 bank-pad maximum at that airflow point
      F_T^2  : B3265x (110 - T_A) / 25 above 85 C (p.64 fit); B3264*B (125 - T_A) / 40 (p.25 fit); 1 at <= 85 C
Declared airflow (DECISIONS 66 / airflow28 README section 7, the design point): R45 jets + the both-face base flow that
gives h 20 (3.07 m/s over the corner + tank path, results/enclosure.json, tripped flat plate; bulk rise at 10 mm gaps),
at 61 C and at 55 C air (one flow). Pads: the B3 jetmix runs h20 @61 and h15 @55 (conservative at 55 C).
Fields beside the metric: dT_col, T_A, T_op = T_A + dT_col against Top,max, and the curve's still-air
bank_ratio_tdk_28A_35k (unchanged, informational).

Control: --control reproduces bank_thermal.py's correlation-B design-point values (exit 1 on a mismatch > 0.002).
"""
import argparse
import json
import math
import sys
from pathlib import Path

SIGMA, G0, EPS, K_AIR, SEAT = 5.670374e-8, 9.81, 0.9, 0.026, 0.5e-3
FAMILIES = {   # MPN prefix -> (parts json id, dT_lim, F_T end, F_T span, body height used for the end faces)
    "B32654A1104": dict(pid_by_tol={"J": "tdk_a1104j", "K": "tdk_a1104k"}, dT_lim=20.0, ft_end=110.0, ft_span=25.0,
                        top_max=110.0, h_box=24.5, bank_prefix="5 x B32654A1104{T}000"),
    "B32643B8104": dict(pid_by_tol={"J": "tdk_b8104j"}, dT_lim=15.0, ft_end=125.0, ft_span=40.0, top_max=125.0,
                        h_box=29.5, bank_prefix="5 x B32643B8104J (2000 V, 22.5 mm"),
}
# (label, bay C, enclosure base-h key giving the bank velocity and bulk rise, B3 run stem in RUNS/jetmix/bay<bay>/ for
# the pads). The enclosure delivers a FLOW, not an h per air temperature: the design flow is the one that gives base h 20
# (3.07 m/s over the corner + tank path), and it is the same flow at 55 C air. The 55 C point keeps the h15 B3 pads
# (hotter than h20's: conservative for T_A). --declared min reproduces the bank_thermal.py design points (h20 @61, h15 @55).
DECLARED_SETS = {
    "flow": [("design flow (base h20) @61", 61, "h20", "c28_h20_jet100"),
             ("design flow (base h20) @55, h15 pads", 55, "h20", "c28_h15_jet100")],
    "min": [("jets + base h20 @61", 61, "h20", "c28_h20_jet100"),
            ("jets + base h15 @55", 55, "h15", "c28_h15_jet100")],
}
DECLARED = DECLARED_SETS["flow"]
PATH = "corner + tank path along x, 195 mm run, 120 mm wide"
BANK = ("C21", "C22", "C23", "C151", "C152")
POS = {"interior": ("C22", "C23", "C151"), "end": ("C21", "C152")}


def air(t_c):
    t = t_c + 273.15
    mu = 1.846e-5 * (t / 300.0) ** 0.7
    rho = 101325.0 / (287.05 * t)
    return dict(k=0.02624 * (t / 300.0) ** 0.8, nu=mu / rho, pr=0.70, beta=1.0 / t)


def h_vert(dt, H, tf):
    p = air(tf)
    ra = G0 * p["beta"] * dt * H ** 3 / p["nu"] ** 2 * p["pr"]
    return (0.68 + 0.670 * ra ** 0.25 / (1 + (0.492 / p["pr"]) ** (9 / 16)) ** (4 / 9)) * p["k"] / H


def h_up(dt, L, tf):
    p = air(tf)
    ra = G0 * p["beta"] * dt * L ** 3 / p["nu"] ** 2 * p["pr"]
    return (0.54 * ra ** 0.25 if ra < 1e7 else 0.15 * ra ** (1 / 3)) * p["k"] / L


def h_rad(ts, tsur):
    a, b = ts + 273.15, tsur + 273.15
    return EPS * SIGMA * (a * a + b * b) * (a + b)


def faces(p, h_box, pos):
    w, l, h = p["w"] * 1e-3, p["l"] * 1e-3, h_box * 1e-3
    f = {"top": w * l, "front": w * h, "rear": w * h}
    if pos == "isolated":
        f["side"] = 2 * h * l
    elif pos == "end":
        f["side"] = h * l
    return f


def g_board(p, bound):
    return 0.005 if bound == "lo" else 1.0 / 50.0 + K_AIR * p["w"] * p["l"] * 1e-6 / SEAT


def g_tdk(p, fam, gb):
    fc = faces(p, fam["h_box"], "isolated")
    ts, ta = 85.0 + fam["dT_lim"], 85.0
    tf = (ts + ta) / 2
    hv, hr = h_vert(ts - ta, fam["h_box"] * 1e-3, tf), h_rad(ts, ta)
    hu = h_up(ts - ta, fc["top"] / (2 * (p["w"] + p["l"]) * 1e-3), tf)
    return (hv + hr) * (fc["front"] + fc["rear"] + fc["side"]) + (hu + hr) * fc["top"] + gb


def g_col(p, fam, pos, v, t_air):
    fc = faces(p, fam["h_box"], pos)
    pr = air(t_air + 10)
    l = p["l"] * 1e-3
    h = 0.102 * (v * l / pr["nu"]) ** 0.675 * pr["pr"] ** (1 / 3) * pr["k"] / l
    return h * sum(fc.values())


def ft2(fam, ta):
    return 1.0 if ta <= 85.0 else max(0.0, (fam["ft_end"] - ta) / fam["ft_span"])


def metric(ps: Path, runs: Path, mpn: str):
    fam = next(v for k, v in FAMILIES.items() if mpn.startswith(k))
    tol = mpn[len(next(k for k in FAMILIES if mpn.startswith(k)))]
    c34 = ps / "validation-results/11-candidates/c34-bank-margin"
    parts = {}
    for f in ("raw/parts_tdk.json", "raw/parts_tdk_b3264.json"):
        for q in json.loads((c34 / f).read_text())["parts"]:
            parts[q["id"]] = q
    p = parts[fam["pid_by_tol"][tol]]
    bm = json.loads((c34 / "results/bank_margin.json").read_text())
    pre = fam["bank_prefix"].format(T=tol)
    r35 = next(r["ratio_35k"] for r in bm["banks"] if r.get("bank", "").startswith(pre))
    enc = json.loads((ps / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    rows, worst = [], None
    for label, bay, hk, stem in DECLARED:
        e = enc["jetmix_base"][hk][PATH]
        v, t_air = e["v_turbulent_m_s"], bay + e["bulk_rise_K_gap10"]
        r25 = json.loads((runs / "jetmix" / f"bay{bay}" / f"{stem}_p0p25.json").read_text())
        r05 = json.loads((runs / "jetmix" / f"bay{bay}" / f"{stem}_p0p5.json").read_text())
        q25 = {x["ref"]: x["pad_max_padmean_c"] for x in r25["parts"] if x["ref"] in BANK}
        q05 = {x["ref"]: x["pad_max_padmean_c"] for x in r05["parts"] if x["ref"] in BANK}
        pad = {r: q25[r] + 3.0 * abs(q25[r] - q05[r]) + (bay - 50.0) for r in BANK}   # b3_ratings_gate.est
        for pos, refs in POS.items():
            t_pad = max(pad[r] for r in refs)
            for b in ("lo", "hi"):
                gb = g_board(p, b)
                ga = g_col(p, fam, pos, v, t_air)
                dt = r35 ** 2 * fam["dT_lim"] * g_tdk(p, fam, gb) / (ga + gb)
                ta = (ga * t_air + gb * t_pad) / (ga + gb)
                allowed = fam["dT_lim"] * ft2(fam, ta)
                eff = math.sqrt(dt / allowed) if allowed > 0 else float("inf")
                row = dict(point=label, position=pos, g_board_bound=b, v_bank_m_s=v, T_air_C=round(t_air, 1),
                           T_pad_C=round(t_pad, 1), T_A_C=round(ta, 2), dT_col_K=round(dt, 2), dT_allowed_K=round(allowed, 2),
                           T_op_C=round(ta + dt, 1), Top_max_C=fam["top_max"], eff_ratio=round(eff, 4))
                rows.append(row)
                if worst is None or eff > worst["eff_ratio"]:
                    worst = row
    hot = max(rows, key=lambda r: r["T_op_C"])
    return dict(mpn=mpn, ratio_35k_vendor_curve=r35, bank_air_ratio_28A_35k=round(worst["eff_ratio"], 3), worst=worst,
                T_op_max_C=hot["T_op_C"], Top_max_C=fam["top_max"], T_op_margin_K=round(fam["top_max"] - hot["T_op_C"], 1),
                rows=rows, board_sha256_of_pad_runs=r25.get("board_sha256"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps", default="/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
    ap.add_argument("--runs", default="/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/runs")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "bank_air_metric.json"))
    ap.add_argument("--control", default=str(Path(__file__).resolve().parent.parent / "bank_thermal.json"))
    ap.add_argument("--declared", choices=sorted(DECLARED_SETS), default="flow")
    a = ap.parse_args()
    DECLARED[:] = DECLARED_SETS[a.declared]
    if a.declared != "min":                       # the control runs on the bank_thermal.py design points
        DECLARED_SETS["flow"] = list(DECLARED)
    out = {"metric": "bank_air_ratio_28A_35k", "direction": "lower", "declared_air": DECLARED, "declared_set": a.declared,
           "by_mpn": {m: metric(Path(a.ps), Path(a.runs), m) for m in ("B32654A1104J000", "B32643B8104J000")}}
    fails = []
    if a.declared != "min":
        keep = list(DECLARED)
        DECLARED[:] = DECLARED_SETS["min"]
        ctl = {m: metric(Path(a.ps), Path(a.runs), m)["bank_air_ratio_28A_35k"] for m in out["by_mpn"]}
        DECLARED[:] = keep
    else:
        ctl = {m: r["bank_air_ratio_28A_35k"] for m, r in out["by_mpn"].items()}
    if a.control and Path(a.control).exists():
        bt = json.loads(Path(a.control).read_text())
        ref = {"B32654A1104J000": "fitted 5 x B32654A1104J000", "B32643B8104J000": "c34 5 x B32643B8104J000"}
        for m, fname in ref.items():
            want = max(bt["cases"][fname][c]["35k"]["worst"]["eff_ratio"]
                       for c in ("jets + base h20 @61 (design x1.25)", "jets + base h15 @55 (design x1.25)"))
            got = ctl[m]
            out.setdefault("control", {})[m] = {"bank_thermal_py": want, "this": got}
            if abs(want - got) > 0.002:
                fails.append(f"{m}: {got} vs bank_thermal.py {want}")
    out["control_failed"] = fails
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    for m, r in out["by_mpn"].items():
        w = r["worst"]
        print(f"{m}: bank_air_ratio_28A_35k {r['bank_air_ratio_28A_35k']} (vendor curve {r['ratio_35k_vendor_curve']}); "
              f"worst {w['point']} {w['position']} {w['g_board_bound']}: dT {w['dT_col_K']} / {w['dT_allowed_K']} K, T_A {w['T_A_C']}, "
              f"T_op {w['T_op_C']} / {w['Top_max_C']}; hottest T_op {r['T_op_max_C']} (margin {r['T_op_margin_K']} K)")
    print("control:", out.get("control"), "FAILED" if fails else "pass")
    sys.exit(1 if fails else 0)
