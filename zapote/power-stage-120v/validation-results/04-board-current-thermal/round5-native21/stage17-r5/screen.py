#!/usr/bin/env python3
"""Stage-17 R5 replacement screen (planning only; no board, schematic or fab file is read or written).

Control: reproduces the committed FAIL of the current R5 (Vishay WSK25121L000FEA, 1 W, ambient-axis derating)
from ../r5-derating/results.json and asserts it (0.864 W at the 29.4 A trip, derated 0.208 W at the 149.16 C
B3 pad-cell maximum) before any candidate is scored.

For each candidate part (datasheet numbers hand-entered below with document and page) it computes, at the same
B3 pad temperatures (c28 case, 0.25 mm mesh, h 25, 50 C inlet: pad max 149.16 C, pad mean 122.74 C):
  * dissipation at the 29.4 A firmware RMS trip (nominal, and worst with 1 % tolerance + TCR at the pad max),
  * derated power on each datasheet curve and the margin 1 - P/P_derated (pass: >= 20 %),
  * the pad temperature at which the 20 % margin is lost,
  * the trip-band low edge with the part's TCR/tolerance (thresholds.py exact corners, stage-15 divider,
    -10/+85 C ambient, R5 rise from B3, Kelvin shift at the all-at-max-transfer bound) against the 64.17 A floor,
and ranks them. A second table shows what a non-1 mOhm shunt would force on the R34/R35 divider (E96).

Terminal-temperature caveat: the B3 pad temperatures are for the WSK footprint. A different land pattern changes
the pad temperature; the B3 re-run (PLAN-17 gate G6) replaces these numbers. The screen answers 'is it worth
drawing', not 'is it released'.

usage: python3 screen.py        -> screen.json   (exits non-zero if a control fails)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R5N = HERE.parent
UNIT = R5N.parents[2]
VR = UNIT / "validation-results"

I_TRIP = 29.4              # A rms, firmware trip = 1.05 x 28 A (r5-derating README)
I_CEIL = 28.0
FLOOR_A = 64.17            # OCP low-edge floor (DECISIONS stage 15)
MARGIN = 0.20              # pre-stated in r5-derating: P_diss <= 0.80 x derated power
STOCK_DATE = "2026-10-12"  # JLCPCB public part-detail pages (read-only), via stage15-28A/jlc_lookup.py

# ---------------------------------------------------------------- candidates
# curves: name -> (P_rated_W, [(T_C, fraction), ...]) fraction piecewise linear in terminal/ambient temperature.
CANDS = [
    {
        "key": "CSS2H-2512R-1L00F",
        "mpn": "CSS2H-2512R-1L00F", "maker": "Bourns", "lcsc": "C4175647", "stock": 1482, "jlc_class": "extended",
        "terminals": "2 power + 2 sense fingers on the recommended land (Kelvin-capable footprint)",
        "package": "2512 (6.35 x 3.05 mm body), H 0.77 mm max", "aec": "AEC-Q200",
        "r_mohm": 1.0, "tol": 0.01, "tcr_ppm": 75.0, "tcr_note": "+/-75 ppm/C incl. Cu terminals (p.1); LCSC page says 50",
        "curves": {
            "current_rev (Bourns site Jan-2026 and LCSC 2023 PDF: 5 W @70 C terminal, 0 at 170 C)": (5.0, [(-55, 1.0), (70, 1.0), (170, 0.0)]),
            "older_rev_copy (CERN-hosted copy: 3 W @130 C curve, 0 at 170 C; not on the current Bourns/LCSC PDFs)": (3.0, [(-55, 1.0), (130, 1.0), (170, 0.0)]),
        },
        "conservative": "current_rev (Bourns site Jan-2026 and LCSC 2023 PDF: 5 W @70 C terminal, 0 at 170 C)",
        "authoritative": "current_rev (Bourns site Jan-2026 and LCSC 2023 PDF: 5 W @70 C terminal, 0 at 170 C)",
        "doc": "Bourns Model CSS2H-2512 Series Current Sense Resistor, bourns.com PDF (created 27-Jan-2026; 5 pp.; scratch, "
               "not committed): p.1 Electrical Characteristics (1.0 mOhm / 5 W @70 C terminal, TCR +/-75 ppm/C incl. Cu "
               "terminals, AEC-Q200); p.2 Product Dimensions (H 0.77 max for 1L00x) and Recommended Pad Layout (3.40 / "
               "3.40 / 1.80 mm, sense terminals) / Recommended Measurements; p.3 Terminal Temperature Derating Curve. "
               "The LCSC-linked PDF (2023) agrees; a CERN-hosted copy shows an older two-curve (5 W @70 / 3 W @130 C) variant",
        "rthi_k_per_w": None, "height_mm": 0.77, "fit": "in place", "fit_effort": 0,
    },
    {
        "key": "BVS-M-R001-1.0",
        "mpn": "BVS-M-R001-1.0", "maker": "Isabellenhuette", "lcsc": "C466582", "stock": 1607, "jlc_class": "extended",
        "terminals": "2 (Kelvin by sense stubs on the land, not a 4-terminal part)",
        "package": "3920 (10.0 x 5.2 mm), H 0.5 mm plate", "aec": "AEC-Q200",
        "r_mohm": 1.0, "tol": 0.01, "tcr_ppm": 50.0, "tcr_note": "0 +/-50 ppm/K (20-60 C) (p.1/p.3)",
        "curves": {
            "stability<1.0% (4 W P>100C, flat to 110 C, 0 at 170 C)": (4.0, [(-65, 1.0), (110, 1.0), (170, 0.0)]),
            "improved stability<0.5% (4 W, flat to 80 C, 0 at 140 C)": (4.0, [(-65, 1.0), (80, 1.0), (140, 0.0)]),
        },
        "conservative": "stability<1.0% (4 W P>100C, flat to 110 C, 0 at 170 C)",
        "authoritative": "stability<1.0% (4 W P>100C, flat to 110 C, 0 at 170 C)",
        "doc": "Isabellenhuette BVS (3920) datasheet, Issue 24-January-2025 (6 pp., scratch, not committed): p.1 "
               "technical data; p.2 solder pad dimensions (l 11, w 6.2, a 2.7, x 5.6); p.3 electrical table "
               "(BVS-M-R001: Rthi 15 K/W, TCR 0 +/-50, P70 7 W, P>100C 4 W); p.4 'Power derating curve BVS-M-R001' "
               "(x = terminal temperature)",
        "rthi_k_per_w": 15.0, "height_mm": 0.5, "fit": "re-floorplan (R13, R58, Q6 courtyards)", "fit_effort": 2,
    },
    {
        "key": "CSS4J-4026R-1L00F",
        "mpn": "CSS4J-4026R-1L00F", "maker": "Bourns", "lcsc": "C2076400", "stock": 371, "jlc_class": "extended",
        "terminals": "4 (true 4-terminal: 2 solder pads + 2 sense terminals)",
        "package": "4026 (10.06 x 6.60 mm body), H 2.70 mm max", "aec": "AEC-Q200",
        "r_mohm": 1.0, "tol": 0.01, "tcr_ppm": 75.0, "tcr_note": "+/-75 ppm/C (p.1)",
        "curves": {
            "current_rev_8W (Jan-2026 datasheet: 1.0 mOhm / 8 W @70 C terminal)": (8.0, [(-55, 1.0), (70, 1.0), (170, 0.0)]),
            "lcsc_rev_4W (2020 datasheet on the LCSC page: 1.0 mOhm / 4 W)": (4.0, [(-55, 1.0), (70, 1.0), (170, 0.0)]),
        },
        "conservative": "lcsc_rev_4W (2020 datasheet on the LCSC page: 1.0 mOhm / 4 W)",
        "authoritative": "current_rev_8W (Jan-2026 datasheet: 1.0 mOhm / 8 W @70 C terminal)",
        "doc": "Bourns Model CSS4J-4026 Series: bourns.com PDF (5 pp., created 15-Jan-2026): p.1 Electrical "
               "Characteristics (1.0 mOhm / 8 W @70 C terminal; TCR +/-75), p.2 dimensions (H 2.70) and Recommended "
               "Pad Layout (10.60 x 7.30), p.3 Terminal Temperature Derating Curve. LCSC-hosted PDF (2020 revision, "
               "5 pp.): p.1 table gives 1.0 mOhm / 4 W",
        "rthi_k_per_w": None, "height_mm": 2.70, "fit": "re-floorplan (R13, R58, Q6 courtyards; +2.1 mm height)", "fit_effort": 3,
    },
]

# Control = the current part, same arithmetic (WSK2512, Vishay doc 30108 rev 11-Dec-2023, ambient axis)
CONTROL = {
    "key": "WSK25121L000FEA (control)", "mpn": "WSK25121L000FEA", "maker": "Vishay Dale", "lcsc": "C4248455", "stock": 0,
    "r_mohm": 1.0, "tol": 0.01, "tcr_ppm": 250.0,
    "curves": {"ambient axis, 1 W @70 C to 0 at 170 C": (1.0, [(-65, 1.0), (70, 1.0), (170, 0.0)])},
    "conservative": "ambient axis, 1 W @70 C to 0 at 170 C",
}


def interp(points, t):
    if t <= points[0][0]:
        return points[0][1]
    for (t0, f0), (t1, f1) in zip(points, points[1:]):
        if t <= t1:
            return f0 + (f1 - f0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def load_thr():
    spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    RT = (0.001, 25e-6)
    m.PARTS.update({"R34": (12.6e3, *RT), "R35": (11.7e3, *RT)})   # stage-15 divider (stage15-28A/ocp_bands.py)
    return m


def low_edge(m, r_mohm, tol, tcr, rise_k, kel, r34=None, r35=None):
    """Band after Kelvin (bound), ambient -10/+85 C, R5 rise from B3. Same method as r5_derating.bands()."""
    saved = dict(m.PARTS)
    m.PARTS["R5"] = (r_mohm * 1e-3, tol, tcr * 1e-6)
    if r34:
        m.PARTS["R34"] = (r34, 0.001, 25e-6)
    if r35:
        m.PARTS["R35"] = (r35, 0.001, 25e-6)
    try:
        r = [m.exact_corners(t, rise_k)["shunt_a"] for t in (-10.0, 85.0)]
    finally:
        m.PARTS.clear()
        m.PARTS.update(saved)
    lo = min(x["min"] for x in r)
    hi = max(x["max"] for x in r)
    a_per_mv = kel["a_per_mv"] * (1.0 / r_mohm)           # dI/de_th = -2(1-k)/R5
    return lo, hi, lo + kel["e_bound"] * a_per_mv


def evaluate(c, t_max, t_mean, kel, rise_k, m, p_nom):
    out = {"mpn": c["mpn"], "maker": c["maker"], "lcsc": c["lcsc"], "stock": c["stock"]}
    r = c["r_mohm"] * 1e-3
    p_trip = I_TRIP ** 2 * r
    p_28 = I_CEIL ** 2 * r
    p_worst = p_trip * (1 + c["tol"]) * (1 + c["tcr_ppm"] * 1e-6 * (t_max - 25.0))
    out["p_diss_w"] = {"at_trip_29p4A": round(p_trip, 5), "at_28A": round(p_28, 4), "worst_tol_tcr_at_pad_max": round(p_worst, 4)}
    rows = {}
    for name, (p_rated, pts) in c["curves"].items():
        row = {"p_rated_w": p_rated}
        for tag, t in (("pad_max", t_max), ("pad_mean", t_mean)):
            pd = p_rated * interp(pts, t)
            row[tag] = {"temp_c": round(t, 2), "derated_w": round(pd, 4),
                        "margin_pct": round((1 - p_trip / pd) * 100, 1) if pd > 0 else None,
                        "meets_20pct": bool(pd > 0 and p_trip <= (1 - MARGIN) * pd)}
        # temperature at which P_trip == 0.8 x derated (linear tail)
        need = p_trip / (1 - MARGIN) / p_rated
        (t0, f0), (t1, f1) = pts[-2], pts[-1]          # last (falling) segment, extended backwards if need > 1
        t_allow = t0 + (f0 - need) / (f0 - f1) * (t1 - t0)
        row["margin_attainable_at_any_temp"] = bool(need <= 1.0)
        row["t_ref_for_20pct_margin_c"] = round(t_allow, 2)
        row["headroom_k_vs_pad_max"] = round(t_allow - t_max, 1)
        rows[name] = row
    out["derating"] = rows
    cons = rows[c["conservative"]]
    out["conservative_curve"] = c["conservative"]
    out["conservative_margin_pct"] = cons["pad_max"]["margin_pct"]
    out["pass_a_conservative"] = cons["pad_max"]["meets_20pct"]
    out["pass_a_any_curve"] = any(v["pad_max"]["meets_20pct"] for v in rows.values())
    out["authoritative_curve"] = c.get("authoritative", c["conservative"])
    out["authoritative_margin_pct"] = rows[out["authoritative_curve"]]["pad_max"]["margin_pct"]
    out["pass_a_authoritative"] = rows[out["authoritative_curve"]]["pad_max"]["meets_20pct"]
    out["pass_b_pad_le_160c"] = bool(t_max <= 160.0)
    if c.get("rthi_k_per_w"):
        out["element_temp_c_at_trip"] = round(t_max + p_trip * c["rthi_k_per_w"], 1)
    lo, hi, lo_k = low_edge(m, c["r_mohm"], c["tol"], c["tcr_ppm"], rise_k, kel)
    out["trip_band"] = {"tcr_ppm": c["tcr_ppm"], "tol": c["tol"], "r5_rise_k": round(rise_k, 2),
                        "before_kelvin_a": [round(lo, 2), round(hi, 2)],
                        "low_after_kelvin_bound_a": round(lo_k, 2), "floor_a": FLOOR_A,
                        "low_edge_margin_a": round(lo_k - FLOOR_A, 2), "pass_c": bool(lo_k >= FLOOR_A)}
    out["pass_c_trip_floor"] = bool(lo_k >= FLOOR_A)
    return out


E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43, 1.47, 1.50,
       1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
       2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57,
       3.65, 3.74, 3.83, 3.92, 4.02, 4.12, 4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
       5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45,
       8.66, 8.87, 9.09, 9.31, 9.53, 9.76]


def retune_table(m, kel, rise_k):
    """If R5 were not 1 mOhm: nominal OCP trip = (2.5 - 2*th)/R5 with R32 = R33 = 10 k, th = 2.5 R35/(R34+R35).
    Search E96 R34/R35 (9.76-15.0 k) for the nominal trip nearest the committed 92.59 A, then run exact corners."""
    nom0 = {k: v[0] for k, v in m.PARTS.items()}
    target = m.thresholds(nom0, 2.5, 0.0)[0]
    table = []
    for r_mohm in (0.5, 1.0, 1.5, 2.0):
        best = []
        cands = [round(v * 1e3, 1) for v in E96] + [round(v * 1e4, 0) for v in E96]
        cands = sorted({c for c in cands if 9.7e3 <= c <= 15.1e3})
        for r34 in cands:
            for r35 in cands:
                p = dict(nom0)
                p.update({"R5": r_mohm * 1e-3, "R34": r34, "R35": r35})
                best.append((abs(m.thresholds(p, 2.5, 0.0)[0] - target), r34, r35))
        best.sort()
        err, r34, r35 = best[0]
        if r_mohm == 1.0:                       # committed divider (stage 15): no retune
            r34, r35, err = 12.6e3, 11.7e3, 0.0
        lo, hi, lo_k = low_edge(m, r_mohm, 0.01, 75.0, rise_k, kel, r34, r35)
        pb = dict(nom0)
        pb.update({"R5": r_mohm * 1e-3, "R34": r34, "R35": r35})
        nominal_best = round(m.thresholds(pb, 2.5, 0.0)[0], 2)
        p = dict(nom0)
        p.update({"R5": r_mohm * 1e-3})
        trip_unchanged_dividers = m.thresholds(p, 2.5, 0.0)[0]
        table.append({
            "r5_mohm": r_mohm,
            "nominal_trip_with_committed_R34_12k6_R35_11k7_a": round(trip_unchanged_dividers, 1),
            "best_e96_pair_ohm": [r34, r35], "nominal_trip_best_pair_a": nominal_best,
            "nominal_trip_error_a": round(err, 2),
            "band_before_kelvin_a": [round(lo, 2), round(hi, 2)],
            "low_after_kelvin_bound_a": round(lo_k, 2), "floor_margin_a": round(lo_k - FLOOR_A, 2),
            "p_diss_at_trip_w": round(I_TRIP ** 2 * r_mohm * 1e-3, 3),
            "kelvin_sensitivity_a_per_mv": round(kel["a_per_mv"] / r_mohm, 3),
        })
    return {"target_nominal_trip_a": round(target, 3), "rows": table,
            "note": "R5 +/-1 %, TCR 75 ppm for all rows. 1 mOhm needs no divider change; the 0.5 mOhm row doubles the "
                    "Kelvin/offset sensitivity (a_per_mv) and 1.5/2 mOhm raise dissipation 1.5x/2x."}


def main():
    res = json.loads((R5N / "r5-derating/results.json").read_text())
    t_max = res["thermal"]["r5"]["conditional_pad_cell_max_c"]
    t_mean = res["thermal"]["r5"]["conditional_pad_cell_mean_c"]
    rise_k = res["thermal"]["board_peak"]["rise_k"]
    kel = res["tcr"]["kelvin"]
    m = load_thr()

    # ------------------------------------------------------------ control (must reproduce the committed FAIL)
    ctrl = evaluate(CONTROL, t_max, t_mean, kel, rise_k, m, None)
    row = ctrl["derating"][CONTROL["conservative"]]
    rd = res["derating"]
    assert abs(ctrl["p_diss_w"]["at_trip_29p4A"] - rd["p_diss_w"]) < 1e-4, "control: dissipation"
    assert abs(ctrl["p_diss_w"]["at_28A"] - res["heat"]["p_at_28A_w"]) < 1e-9, "control: 28 A dissipation"
    assert abs(ctrl["p_diss_w"]["worst_tol_tcr_at_pad_max"] - res["heat"]["p_at_trip_with_1pct_tol_and_tcr_limit_w"]) < 2e-4, "control: worst-case"
    assert round(row["pad_max"]["temp_c"], 2) == rd["rows"]["pad_cell_max"]["temp_c"] == 149.16, "control: pad max"
    assert round(row["pad_max"]["derated_w"], 4) == rd["rows"]["pad_cell_max"]["derated_w"] == 0.2084, "control: derated W"
    assert row["pad_max"]["margin_pct"] == rd["rows"]["pad_cell_max"]["margin_pct"], "control: margin"
    assert row["pad_mean"]["derated_w"] == round(rd["rows"]["pad_cell_mean"]["derated_w"], 4), "control: mean derated"
    assert row["pad_max"]["meets_20pct"] is False, "control must FAIL"
    assert abs(row["t_ref_for_20pct_margin_c"] - rd["max_ref_temp_for_p_diss_with_20pct_margin_c"]) < 0.05, "control: 20 % ref temp"
    exp_lo = res["tcr"]["bands"]["same_ambient_corners_rise_from_B3"]["band_after_kelvin_bound_a"][0]
    assert abs(ctrl["trip_band"]["low_after_kelvin_bound_a"] - exp_lo) < 0.006, f"control: band low {ctrl['trip_band']['low_after_kelvin_bound_a']} vs {exp_lo}"
    ctrl["control_asserted"] = {"p_diss_w": 0.86436, "derated_w_at_149p16c": 0.2084, "margin_pct": -314.7,
                                "band_low_bound_a": exp_lo, "verdict": "FAIL (reproduces r5-derating/results.json)"}

    # ------------------------------------------------------------ candidates
    results = []
    for c in CANDS:
        r = evaluate(c, t_max, t_mean, kel, rise_k, m, None)
        r.update({k: c[k] for k in ("terminals", "package", "aec", "jlc_class", "tcr_note", "doc", "fit", "fit_effort", "height_mm")})
        r["stock_date"] = STOCK_DATE
        results.append(r)

    # ranking: never overloaded on the most conservative datasheet reading (margin >= 0) and trip floor ok
    # -> fit effort (0 in place ... 3 re-floorplan + height) -> conservative margin. The 20 % rule is a gate (G6), not a rank term.
    def key(r):
        ok = (r["conservative_margin_pct"] or -1e9) >= 0 and r["pass_c_trip_floor"] and r["pass_b_pad_le_160c"]
        return (not ok, r["fit_effort"], -(r["conservative_margin_pct"] or -1e9))
    results.sort(key=key)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    out = {
        "question": "Which >= 2 W Kelvin/4-terminal 1 mOhm shunt replaces R5 (WSK25121L000FEA) so that 0.864 W clears derating with >= 20 % margin at the B3 pad temperatures?",
        "method": {"i_trip_a": I_TRIP, "pad_max_c": round(t_max, 3), "pad_mean_c": round(t_mean, 3), "r5_rise_k": round(rise_k, 3),
                   "margin_rule": "P_diss <= 0.80 x derated power (r5-derating pass criterion a)",
                   "rank_key": "not overloaded on the most conservative datasheet reading (margin >= 0), pad <= 160 C, trip floor -> fit effort (0 in place, 2/3 re-floorplan) -> conservative margin; the 20 % rule is reported as pass_a_authoritative and enforced at gate G6",
                   "caveat": "pad temperatures are the WSK footprint's B3 values; G6 (B3 re-run with the new land pattern) replaces them"},
        "control": ctrl,
        "ranked": results,
        "retune_if_not_1_mohm": retune_table(m, kel, rise_k),
        "stock_snapshot": {"date": STOCK_DATE, "source": "JLCPCB public part-detail (read-only) via stage15-28A/jlc_lookup.py; stock moves daily",
                           "rows": {c["lcsc"]: c["stock"] for c in CANDS + [CONTROL]}},
        "not_ranked": {"WSLP25121L000FEA (Vishay, C844705, stock 5321 on 2026-10-12)": "2-terminal, 3 W, TCR +/-275 ppm (JLC listing) is above the 100 ppm preference; datasheet derating axis not read",
                       "CSS2H-2512R-1L00FE / CSS4J-4026R-1L00FE (mini-reel 'E' suffix)": "same parts, 7-inch reel; stock 0 / 2 on 2026-10-12"},
    }
    (HERE / "screen.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"control OK: {ctrl['p_diss_w']['at_trip_29p4A']} W at trip, derated {row['pad_max']['derated_w']} W at {row['pad_max']['temp_c']} C, margin {row['pad_max']['margin_pct']} %")
    for r in results:
        print(f"{r['rank']}. {r['mpn']:20s} {r['lcsc']:9s} stock {r['stock']:5d}  cons. margin {r['conservative_margin_pct']:6.1f} %  "
              f"authoritative {r['authoritative_margin_pct']} % (>=20: {r['pass_a_authoritative']})  low edge {r['trip_band']['low_after_kelvin_bound_a']} A (floor {FLOOR_A})")


if __name__ == "__main__":
    main()
