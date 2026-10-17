#!/usr/bin/env python3
"""bank_air physical self-heating check for replacement resonant-bank candidates (stage 49 board, s49 pads).

    python3 -I scripts/bank_air_cand.py [--ps PS] [--runs49 DIR] [--release-runs DIR]   -> results/bank_air_cand.json + .md

Same physics and conventions as PS/validation-results/11-candidates/bank28-air/scripts/bank_air_metric.py (the scorecard
producer of `bank_air_ratio_28A_35k`), generalised to any part:

  per part  r(f)     = I_tank * s_worst / I_allow(f)          vendor curve, the vendor's own dT basis dT_v (T_A <= 85 C)
            P        = r^2 * dT_v * G_vtest                   heat the part makes (G_vtest: the part alone in still air at
                                                              85 C, surface at 85 + dT_v; natural convection + radiation)
            dT_col   = P / (G_col + G_board)                  G_col: the column position under the declared flow,
                                                              correlation B (square prism, Nu = 0.102 Re^0.675 Pr^1/3)
            T_A      = (G_col T_air + G_board T_pad)/(G_col + G_board)    (TDK GTI Fig. 26 dummy)
            eff      = sqrt(dT_col / dT_allowed(vendor rule at T_A, T_pad)), also T_A + dT_col <= Top,max
  Worst over the declared points (design flow 3.07 m/s at 61 C with h20 pads, at 55 C with h15 pads), the column positions
  (interior: two h x l faces shadowed; ends: one) and the two G_board bounds (0.005 W/K; 0.020 + K_air A_bottom / 0.5 mm).
  Vendor rules (dT_allowed):
    tdk     dT_v * F_T(T_A)^2, F_T^2 = (end - T_A)/span above 85 C          (B3265x 110/25, B3264*B 125/40)
    kemet   Th = max(T_A, T_pad) (KEMET: 'the higher of the ambient around the part and the hottest contact point (tracks)');
            dT_lim(Th) from the series chart (R75 p.7: 20 K to Th 85, linear to 0 at 105; R76 p.6: 40 K to Th 60, linear
            to 0 at 110)
    knscha  dT_v = 10 K internal rise at ambient <= 85 C (p.7 remark); above 85 C the sheet gives no current rule, so
            dT_allowed = 10 K * (Top,max - T_A)/(Top,max - 85) (ASSUMED, the TDK-style linear F_T^2) and T_A + dT <= Top,max
  Release case: 17.5 A ceiling at its 18.375 A trip (and 17.5 A), still air, bay 61 C, air at bay + 15 K, pads from the s49
  B3 release solve c17.5_h10, natural convection with radiation (bank28 central) and without.
  Gap: the gate value treats the side faces of an interior part as adiabatic (as the producer does, valid for the 0.5 mm
  c34 gaps). A part thinner than the 15 mm row pitch leaves wider gaps; `gap_credit` adds pressure-driven laminar channel
  flow through each gap (dp = 1.3 * rho v^2 / 2 = 1.5 * rho u^2 / 2 + 12 mu L u / g^2; Nu = 7.54 on D_h = 2 g, fully
  developed, both walls heated; capacity-limited, each part gets one channel's worth): REPORTED, not gated.
  Pad heat: the s49 pads were solved with the c34 bank's heat. A candidate that makes more heat warms its pads by
  k_pad * 0.3 * (P - P_c34) (B3 puts 0.3 of the self-heat into the leads); k_pad comes from the s47 airflow28 pads
  (fitted bank) against the s49 pads (c34 bank) at the same flow point (different boards: an estimate, applied as a bound).
Controls (exit 1 on failure): c34 B32643B8104J000 and fitted B32654A1104J000 reproduce bank_air_metric.py on the s49 pads
(0.967 / 1.308, runs-native21/s49/c49/bank-air.log) with gap credit and pad heat off.
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGMA, G0, EPS, K_AIR, SEAT = 5.670374e-8, 9.81, 0.9, 0.026, 0.5e-3
BANK = ("C21", "C22", "C23", "C151", "C152")
POS = {"interior": ("C22", "C23", "C151"), "end": ("C21", "C152")}
PATH = "corner + tank path along x, 195 mm run, 120 mm wide"
I_TANK, I_REL_TRIP, I_REL = 28.0, 18.375, 17.5


def air(t_c):
    t = t_c + 273.15
    mu = 1.846e-5 * (t / 300.0) ** 0.7
    rho = 101325.0 / (287.05 * t)
    return dict(k=0.02624 * (t / 300.0) ** 0.8, nu=mu / rho, mu=mu, rho=rho, cp=1007.0, pr=0.70, beta=1.0 / t)


def h_vert(dt, H, tf):
    if dt <= 0:
        return 0.0
    p = air(tf)
    ra = G0 * p["beta"] * dt * H ** 3 / p["nu"] ** 2 * p["pr"]
    return (0.68 + 0.670 * ra ** 0.25 / (1 + (0.492 / p["pr"]) ** (9 / 16)) ** (4 / 9)) * p["k"] / H


def h_up(dt, L, tf):
    if dt <= 0:
        return 0.0
    p = air(tf)
    ra = G0 * p["beta"] * dt * L ** 3 / p["nu"] ** 2 * p["pr"]
    return (0.54 * ra ** 0.25 if ra < 1e7 else 0.15 * ra ** (1 / 3)) * p["k"] / L


def h_rad(ts, tsur):
    a, b = ts + 273.15, tsur + 273.15
    return EPS * SIGMA * (a * a + b * b) * (a + b)


def faces(c, pos):
    w, l, h = c["w"] * 1e-3, c["l"] * 1e-3, c["h"] * 1e-3
    f = {"top": w * l, "front": w * h, "rear": w * h}
    if pos == "isolated":
        f["side"] = 2 * h * l
    elif pos == "end":
        f["side"] = h * l
    return f


def g_board(c, bound):
    return 0.005 if bound == "lo" else 1.0 / 50.0 + K_AIR * c["w"] * c["l"] * 1e-6 / SEAT


def g_vtest(c, gb):
    """the part alone in still air at 85 C, surface at 85 + dT_v (TDK's / the vendor's rating condition)."""
    fc = faces(c, "isolated")
    ts, ta = 85.0 + c["dT_v"], 85.0
    tf = (ts + ta) / 2
    hv, hr = h_vert(ts - ta, c["h"] * 1e-3, tf), h_rad(ts, ta)
    hu = h_up(ts - ta, fc["top"] / (2 * (c["w"] + c["l"]) * 1e-3), tf)
    return (hv + hr) * (fc["front"] + fc["rear"] + fc["side"]) + (hu + hr) * fc["top"] + gb


def g_col(c, pos, v, t_air):
    fc = faces(c, pos)
    pr = air(t_air + 10)
    l = c["l"] * 1e-3
    h = 0.102 * (v * l / pr["nu"]) ** 0.675 * pr["pr"] ** (1 / 3) * pr["k"] / l
    return h * sum(fc.values())


def g_gap(c, v, t_air, gap_mm):
    """one gap channel's conductance (shared by the two neighbours: each interior part gets one channel's worth)."""
    if gap_mm <= 0:
        return 0.0
    p = air(t_air + 10)
    g, L, H = gap_mm * 1e-3, c["l"] * 1e-3, c["h"] * 1e-3
    dp = 1.3 * 0.5 * p["rho"] * v * v
    a, b = 1.5 * 0.5 * p["rho"], 12 * p["mu"] * L / g ** 2       # a u^2 + b u = dp
    u = (-b + math.sqrt(b * b + 4 * a * dp)) / (2 * a)
    mcp = p["rho"] * u * g * H * p["cp"]
    hch = 7.54 * p["k"] / (2 * g)
    ntu = hch * 2 * H * L / mcp
    return mcp * (1 - math.exp(-ntu)), u


def dT_allowed(c, ta, tpad):
    r = c["rule"]
    if r["type"] == "tdk":
        f = 1.0 if ta <= 85 else max(0.0, (r["end"] - ta) / r["span"])
        return c["dT_v"] * f
    if r["type"] == "kemet":
        th = max(ta, tpad)
        pts = r["dTlim_vs_Th"]                      # [(Th, dT_lim)] piecewise linear, flat before the first point
        if th <= pts[0][0]:
            return pts[0][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if th <= x1:
                return y0 + (y1 - y0) * (th - x0) / (x1 - x0)
        return 0.0
    if r["type"] == "knscha":
        return c["dT_v"] if ta <= 85 else max(0.0, c["dT_v"] * (c["top_max"] - ta) / (c["top_max"] - 85.0))
    raise KeyError(r["type"])


def share(c):
    n, t = c["n"], c["tol"]
    return (1 + t) / ((1 + t) + (n - 1) * (1 - t))


def pads_from(f25, f05, bay):
    a, b = json.loads(Path(f25).read_text()), json.loads(Path(f05).read_text())
    qa = {x["ref"]: x for x in a["parts"]}
    qb = {x["ref"]: x for x in b["parts"]}
    est = {r: qa[r]["pad_max_padmean_c"] + 3.0 * abs(qa[r]["pad_max_padmean_c"] - qb[r]["pad_max_padmean_c"]) + bay - 50.0
           for r in BANK}
    return est, {"p0p25": [str(f25), a.get("board_sha256")], "p0p5": [str(f05), b.get("board_sha256")],
                 "watts_into_model_per_cap": round(qa["C22"]["watts_into_model"], 4)}


def run_forced(c, pts, gap_credit, pad_heat, k_pad, p_ref):
    r35 = I_TANK * share(c) / c["I35"]
    rows = []
    for label, bay, v, rise, pads in pts:
        t_air = bay + rise
        for pos, refs in POS.items():
            for bnd in ("lo", "hi"):
                gb = g_board(c, bnd)
                p_w = r35 ** 2 * c["dT_v"] * g_vtest(c, gb)
                tpad = max(pads[r] for r in refs) + (k_pad * 0.3 * (p_w - p_ref) if pad_heat else 0.0)
                ga = g_col(c, pos, v, t_air)
                u = None
                if gap_credit and pos == "interior":
                    gg, u = g_gap(c, v, t_air, c["gap_mm"])
                    ga += gg
                elif gap_credit and pos == "end":
                    gg, u = g_gap(c, v, t_air, c["gap_mm"])
                    ga += 0.5 * gg
                dt = p_w / (ga + gb)
                ta = (ga * t_air + gb * tpad) / (ga + gb)
                al = dT_allowed(c, ta, tpad)
                eff = math.sqrt(dt / al) if al > 0 else float("inf")
                rows.append(dict(point=label, position=pos, g_board=bnd, P_W=round(p_w, 3), T_pad_C=round(tpad, 1),
                                 T_A_C=round(ta, 1), dT_K=round(dt, 2), dT_allowed_K=round(al, 2), T_op_C=round(ta + dt, 1),
                                 eff=round(eff, 4), gap_u_m_s=round(u, 2) if u else None))
    w = max(rows, key=lambda r: r["eff"])
    hot = max(rows, key=lambda r: r["T_op_C"])
    return dict(eff=round(w["eff"], 3), worst=w, T_op_max_C=hot["T_op_C"], Top_margin_K=round(c["top_max"] - hot["T_op_C"], 1),
                passes=w["eff"] <= 1.0 and hot["T_op_C"] <= c["top_max"]), rows


def run_still(c, pads, bay, i_a, k_pad, p_ref_rel, pad_heat):
    r = i_a * share(c) / c["I35"]
    t_air = bay + 15.0
    out = {}
    for rad in (True, False):
        worst = None
        for pos, refs in POS.items():
            for bnd in ("lo", "hi"):
                gb = g_board(c, bnd)
                p_w = r ** 2 * c["dT_v"] * g_vtest(c, gb)
                tpad = max(pads[x] for x in refs) + (k_pad * 0.3 * (p_w - p_ref_rel) if pad_heat else 0.0)
                fc = faces(c, pos)
                dt = 5.0
                for _ in range(300):
                    ts = t_air + max(dt, 0.3)
                    tf = (ts + t_air) / 2
                    hv = h_vert(max(dt, 0.3), c["h"] * 1e-3, tf)
                    col_l = c["n"] * c["pitch"] * 1e-3
                    hu = h_up(max(dt, 0.3), col_l * c["l"] * 1e-3 / (2 * (col_l + c["l"] * 1e-3)), tf)
                    hr = h_rad(ts, t_air) if rad else 0.0
                    ga = (hv + hr) * (fc["front"] + fc["rear"] + fc.get("side", 0.0)) + (hu + hr) * fc["top"]
                    ta = (ga * t_air + gb * tpad) / (ga + gb)
                    dtn = p_w / (ga + gb)
                    s_air = ta + dtn - t_air
                    if abs(s_air - dt) < 1e-5:
                        break
                    dt = 0.5 * dt + 0.5 * s_air
                al = dT_allowed(c, ta, tpad)
                eff = math.sqrt(dtn / al) if al > 0 else float("inf")
                row = dict(position=pos, g_board=bnd, P_W=round(p_w, 3), T_pad_C=round(tpad, 1), T_A_C=round(ta, 1),
                           dT_K=round(dtn, 2), dT_allowed_K=round(al, 2), T_op_C=round(ta + dtn, 1), eff=round(eff, 4))
                if worst is None or row["eff"] > worst["eff"]:
                    worst = row
        out["with_radiation" if rad else "no_radiation"] = worst
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps", default="/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
    ap.add_argument("--runs49", default="/Users/bennet/Desktop/temper/worktrees/runs-native21/s49/c49/b3-bank-air/jetmix")
    ap.add_argument("--release-runs", default="/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/"
                    "validation-results/04-board-current-thermal/round5-native21/b3-ratings/runs")
    ap.add_argument("--cands", default=str(ROOT / "data/candidates.json"))
    a = ap.parse_args()
    ps = Path(a.ps)
    enc = json.loads((ps / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    p61, s61 = pads_from(f"{a.runs49}/bay61/c28_h20_jet100_p0p25.json", f"{a.runs49}/bay61/c28_h20_jet100_p0p5.json", 61)
    p55, s55 = pads_from(f"{a.runs49}/bay55/c28_h15_jet100_p0p25.json", f"{a.runs49}/bay55/c28_h15_jet100_p0p5.json", 55)
    prel, srel = pads_from(f"{a.release_runs}/c17.5_h10_p0p25.json", f"{a.release_runs}/c17.5_h10_p0p5.json", 61)
    e20 = enc["jetmix_base"]["h20"][PATH]
    pts = [("design flow (base h20) @61", 61, e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"], p61),
           ("design flow (base h20) @55, h15 pads", 55, e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"], p55)]
    # k_pad: s47 airflow28 pads (fitted bank, 0.27 W into the model per cap) vs s49 (c34 bank, 0.114 W) at h20 @61
    bp = json.loads((ps / "validation-results/11-candidates/bank28-air/results/bank_pads.json").read_text())
    s47 = next(x for x in bp if x["case"] == "jet100 + base h20 @61 (x1.25)")
    dW = s47["bank"]["C22"]["b3_watts_into_model"] - s61["watts_into_model_per_cap"]
    k_pad = max((s47["bank"][r]["pad_max_c"] - p61[r]) / dW for r in BANK)
    p_ref = s61["watts_into_model_per_cap"] / 0.3                      # c34 self-heat the s49 pads were solved with
    p_ref_rel = srel["watts_into_model_per_cap"] / 0.3
    cands = json.loads(Path(a.cands).read_text())["candidates"]
    out = {"inputs": {"pads_28A": {"61": {k: round(v, 2) for k, v in p61.items()}, "55": {k: round(v, 2) for k, v in p55.items()},
                                   "files": [s61, s55]},
                      "pads_release_c17.5_h10_61": {k: round(v, 2) for k, v in prel.items()}, "release_files": srel,
                      "flow": {"v_m_s": e20["v_turbulent_m_s"], "bulk_rise_K": e20["bulk_rise_K_gap10"], "path": PATH},
                      "k_pad_K_per_W_into_model": round(k_pad, 1), "P_ref_c34_28A_W": round(p_ref, 3),
                      "P_ref_c34_release_W": round(p_ref_rel, 3)},
           "candidates": {}}
    fails = []
    for c in cands:
        if not c.get("score", True):
            continue
        c.setdefault("gap_mm", round(c["pitch"] - c["w"], 2))
        s = share(c)
        res = {"mpn": c["mpn"], "n": c["n"], "C_nF": c["C_nF"], "worst_share": round(s, 4),
               "I_part_28A_A": round(I_TANK * s, 3), "I_allow_35k_A": c["I35"], "I_allow_40k_A": c["I40"],
               "ratio_vendor_35k": round(I_TANK * s / c["I35"], 3), "ratio_vendor_40k": round(I_TANK * s / c["I40"], 3),
               "dT_vendor_terms_28A_K": round((I_TANK * s / c["I35"]) ** 2 * c["dT_v"], 1), "dT_v_basis_K": c["dT_v"],
               "tank_A_at_0.85_35k": round(0.85 * c["I35"] / s, 1), "gap_mm": c["gap_mm"]}
        gate, rows = run_forced(c, pts, gap_credit=False, pad_heat=False, k_pad=k_pad, p_ref=p_ref)
        res["bank_air_28A_35k_gate"] = gate
        g2, _ = run_forced(c, pts, gap_credit=False, pad_heat=True, k_pad=k_pad, p_ref=p_ref)
        res["bank_air_28A_35k_with_pad_heat"] = g2
        g3, _ = run_forced(c, pts, gap_credit=True, pad_heat=True, k_pad=k_pad, p_ref=p_ref)
        res["bank_air_28A_35k_gap_credit_and_pad_heat"] = g3
        res["release"] = {f"{i:g} A": run_still(c, prel, 61, i, k_pad, p_ref_rel * (i / I_REL_TRIP) ** 2, True)
                          for i in (I_REL_TRIP, I_REL)}
        res["release_eff_trip_rad"] = res["release"][f"{I_REL_TRIP:g} A"]["with_radiation"]["eff"]
        res["release_eff_trip_norad"] = res["release"][f"{I_REL_TRIP:g} A"]["no_radiation"]["eff"]
        res["rows_gate"] = rows
        if "control_bank_air" in c:
            if abs(gate["eff"] - c["control_bank_air"]) > 0.002:
                fails.append(f"{c['mpn']}: {gate['eff']} vs control {c['control_bank_air']}")
        out["candidates"][c["id"]] = res
    out["control_failed"] = fails
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/bank_air_cand.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["| id | MPN | n x C | gap mm | vendor 35k / 40k | dT vendor terms | bank_air gate | + pad heat | + gap credit | "
         "T_op max / Top,max | release 18.375 A rad / no-rad |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in out["candidates"].items():
        c = next(x for x in cands if x["id"] == k)
        L.append(f"| {k} | {r['mpn']} | {r['n']} x {r['C_nF']:g} nF | {r['gap_mm']} | {r['ratio_vendor_35k']} / "
                 f"{r['ratio_vendor_40k']} | {r['dT_vendor_terms_28A_K']} / {c['dT_v']:g} K | **{r['bank_air_28A_35k_gate']['eff']}** | "
                 f"{r['bank_air_28A_35k_with_pad_heat']['eff']} | {r['bank_air_28A_35k_gap_credit_and_pad_heat']['eff']} | "
                 f"{r['bank_air_28A_35k_with_pad_heat']['T_op_max_C']} / {c['top_max']:g} | {r['release_eff_trip_rad']} / "
                 f"{r['release_eff_trip_norad']} |")
    L += ["", f"k_pad {k_pad:.1f} K/W (into model), P_ref c34 {p_ref:.3f} W at 28 A. Controls: {fails or 'pass'}"]
    (ROOT / "results/bank_air_cand.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
