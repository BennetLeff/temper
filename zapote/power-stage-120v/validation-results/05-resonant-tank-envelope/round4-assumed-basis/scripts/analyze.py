#!/usr/bin/env python3
"""Summarise the round-4 assumed-basis grids against the part ratings and protection bands.

Reads outputs/{grid,tol-*,alt-bank-0p50uF}-cases.csv, floor-probe.csv and the digitized
CDE curves; writes outputs/summary.json and outputs/grid-checks.csv. All maxima are
maxima over the evaluated cases, not bounds beyond them.
"""
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import cap_rating as CR  # noqa: E402

OUT = ROOT / "outputs"
CT_BAND = (50.558, 60.014)        # round3/sources/a3-thresholds.json static CT range
SHUNT_BAND = (47.52, 97.98)       # DECISIONS 2026-10-08 Kelvin band (native-21)
VAC_RATED = 430.0                 # 942C 1200 Vdc parts, 60 Hz AC rating (p.3), full to 85 C (p.1)
VDC_RATED = 1200.0
CV = CR.curves()

BANKS = {  # name: list of (ref, part, C_F, I_100k_70C)
    "0.54uF native-21 (C21/C22 942C12P22K-F, C23 942C12P1K-F)":
        [("C21", "942C12P22K-F", 0.22e-6, 10.3), ("C22", "942C12P22K-F", 0.22e-6, 10.3),
         ("C23", "942C12P1K-F", 0.10e-6, 9.2)],
    "0.50uF option: 5 x 942C12P1K-F": [(f"Ca{i}", "942C12P1K-F", 0.10e-6, 9.2) for i in range(5)],
    "0.50uF option: 5 x 942C16P1K-F": [(f"Cb{i}", "942C16P1K-F", 0.10e-6, 11.4) for i in range(5)],
    "0.55uF option: 3 x 942C12P15K-F + 942C12P1K-F":
        [("Cc0", "942C12P15K-F", 0.15e-6, 10.2), ("Cc1", "942C12P15K-F", 0.15e-6, 10.2),
         ("Cc2", "942C12P15K-F", 0.15e-6, 10.2), ("Cc3", "942C12P1K-F", 0.10e-6, 9.2)],
}


def part_bound(i100, f):
    """min(T bound, 0.1 uF-shape, 0.33 uF-shape) at 70 C (see cap_rating.py)."""
    t = i100 * math.sqrt(f / 100e3)
    s01 = i100 * CR.interp_curve(CV, "0.10uF", f) / CV[("0.10uF", 100000)]
    s033 = i100 * CR.interp_curve(CV, "0.33uF", f) / CV[("0.33uF", 100000)]
    return min(t, s01, s033), s033


def bank_check(bank, i_rms, f, tol=0.10):
    tot = sum(c for _, _, c, _ in bank)
    worst_ratio, est_ratio, worst_part = 0.0, 0.0, None
    for ref, part, c, i100 in bank:
        hi = c * (1 + tol)
        share_w = hi / (hi + sum(cc * (1 - tol) for r2, _, cc, _ in bank if r2 != ref))
        b, s033 = part_bound(i100, f)
        rw = i_rms * share_w / b
        re = i_rms * (c / tot) / s033
        if rw > worst_ratio:
            worst_ratio, worst_part = rw, ref
        est_ratio = max(est_ratio, re)
    return worst_ratio, est_ratio, worst_part


def load(name):
    p = OUT / name
    return list(csv.DictReader(open(p))) if p.exists() else []


def fl(r, k):
    return float(r[k])


def maxima(rows, keys):
    out = {}
    for k in keys:
        r = max(rows, key=lambda x: fl(x, k))
        out[k] = {"max": fl(r, k), "case": r.get("case") or f"{r['load']}-{r['corner']}-{r['line_vrms']}V-{r['freq_hz']}Hz"}
    return out


def grid_summary(rows, bank_name):
    bank = BANKS[bank_name]
    checks = []
    for r in rows:
        f = fl(r, "freq_hz")
        w, e, part = bank_check(bank, fl(r, "i_tank_rms_a"), f)
        c = fl(r, "C_bank_uF") * 1e-6
        vc_crest_rms = fl(r, "i_tank_rms_crest_a") / (2 * math.pi * f * c)
        checks.append({
            "case": r["case"], "status": r["status"], "freq_hz": f, "i_tank_rms_a": fl(r, "i_tank_rms_a"),
            "i_tank_pk_a": fl(r, "i_tank_pk_a"),
            "cap_current_over_bound_70C_worstshare": round(w, 3), "cap_worst_part": part,
            "cap_current_over_bound_85C_worstshare": round(w / math.sqrt(20 / 35), 3),
            "cap_current_over_estimate_70C_nomshare": round(e, 3),
            "vc_line_rms_v": fl(r, "vc_rms_v"), "vc_crest_window_rms_v": round(vc_crest_rms, 1),
            "vc_allow_25C_0.33uF_trace_v": round(CR.interp_curve(CV, "0.33uF", f) / (2 * math.pi * f * 0.33e-6), 1),
            "vc_pk_v": fl(r, "vc_pk_v"),
            "i_pk_over_ct_trip_min": round(fl(r, "i_tank_pk_a") / CT_BAND[0], 3),
            "i_pk_over_shunt_trip_min": round(fl(r, "i_tank_pk_a") / SHUNT_BAND[0], 3),
        })
    s = {
        "n_cases": len(rows),
        "status": dict(Counter(r["status"] for r in rows)),
        "freq_range_hz": [min(fl(r, "freq_hz") for r in rows), max(fl(r, "freq_hz") for r in rows)],
        "f_over_fres_min": min(fl(r, "f_over_fres") for r in rows),
        "fha_phase_min_deg": min(fl(r, "fha_phase_deg") for r in rows),
        "i_edge_crest_min_a": min(fl(r, "i_edge_crest_a") for r in rows),
        "maxima": maxima(rows, ["i_tank_rms_a", "i_tank_rms_crest_a", "i_tank_pk_a", "vc_pk_v", "vc_rms_v",
                                "p_tank_w", "i_ps_est_a", "ct_sec_pk_v"]),
        "cap_bound_70C_worstshare_max_ratio": max(c["cap_current_over_bound_70C_worstshare"] for c in checks),
        "cap_bound_70C_worstshare_n_over_1": sum(c["cap_current_over_bound_70C_worstshare"] > 1 for c in checks),
        "cap_bound_85C_worstshare_n_over_1": sum(c["cap_current_over_bound_85C_worstshare"] > 1 for c in checks),
        "cap_estimate_70C_nomshare_max_ratio": max(c["cap_current_over_estimate_70C_nomshare"] for c in checks),
        "cap_estimate_70C_nomshare_n_over_1": sum(c["cap_current_over_estimate_70C_nomshare"] > 1 for c in checks),
        "vc_crest_window_rms_max_v": max(c["vc_crest_window_rms_v"] for c in checks),
        "vc_crest_over_0.33trace_n": sum(c["vc_crest_window_rms_v"] > c["vc_allow_25C_0.33uF_trace_v"] for c in checks),
        "n_ipk_ge_shunt_trip_min": sum(fl(r, "i_tank_pk_a") >= SHUNT_BAND[0] for r in rows),
        "n_ipk_ge_ct_trip_min": sum(fl(r, "i_tank_pk_a") >= CT_BAND[0] for r in rows),
        "min_margin_to_ct_trip_min_a": round(CT_BAND[0] - max(fl(r, "i_tank_pk_a") for r in rows), 3),
        "min_margin_to_shunt_trip_min_a": round(SHUNT_BAND[0] - max(fl(r, "i_tank_pk_a") for r in rows), 3),
    }
    return s, checks


def power_table(rows):
    """Mean / min of total tank power over the three corners, 1710 W request, by class and line."""
    t = {}
    for r in rows:
        if fl(r, "p_request_w") != 1710.0:
            continue
        k = (r["pan_class"], int(fl(r, "line_vrms")))
        t.setdefault(k, []).append((fl(r, "p_tank_w"), fl(r, "p_pan_w"), r["status"]))
    return {f"{k[0]}@{k[1]}V": {"total_w_min": min(x[0] for x in v), "total_w_mean": round(sum(x[0] for x in v) / 3, 1),
                                 "pan_w_min": min(x[1] for x in v), "status": [x[2] for x in v]}
            for k, v in sorted(t.items())}


def main():
    native = "0.54uF native-21 (C21/C22 942C12P22K-F, C23 942C12P1K-F)"
    grid = load("grid-cases.csv")
    main_rows = [r for r in grid if "SYNTHETIC" not in r["pan_class"]]
    supp_rows = [r for r in grid if "SYNTHETIC" in r["pan_class"]]
    summary = {"status": "ASSUMED basis / pre-measurement; maxima are over the evaluated cases only",
               "bands": {"ct_static_trip_a": CT_BAND, "shunt_kelvin_trip_a": SHUNT_BAND}}
    s_main, checks = grid_summary(main_rows, native)
    s_supp, checks_s = grid_summary(supp_rows, native)
    summary["grid_main_135"] = s_main
    summary["grid_supplemental_offset_27"] = s_supp
    summary["power_1710w_request"] = power_table(grid)
    with open(OUT / "grid-checks.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(checks[0].keys()))
        w.writeheader()
        w.writerows(checks + checks_s)
    for tag in ("tol-L0m10-Cm10", "tol-L0p10-Cp10"):
        rows = load(f"{tag}-cases.csv")
        if rows:
            s, _ = grid_summary(rows, native)
            s["n_floor_set_by_1.05fres"] = sum(fl(r, "f_floor_hz") > 35000.5 for r in rows)
            s["f_res_max_hz"] = max(fl(r, "f_res_hz") for r in rows)
            summary[tag] = s
    alt = load("alt-bank-0p50uF-cases.csv")
    if alt:
        alt_main = [r for r in alt if "SYNTHETIC" not in r["pan_class"]]
        summary["alt_bank_0.50uF"] = {}
        for bname in ("0.50uF option: 5 x 942C12P1K-F", "0.50uF option: 5 x 942C16P1K-F"):
            s, _ = grid_summary(alt_main, bname)
            summary["alt_bank_0.50uF"][bname] = s
        summary["alt_bank_0.50uF"]["power_1710w_request"] = power_table(alt)
    # option 0.55 uF evaluated on the native 0.54 uF grid (resonance shift 1.9 %, not re-simulated)
    s55, _ = grid_summary(main_rows, "0.55uF option: 3 x 942C12P15K-F + 942C12P1K-F")
    summary["option_0.55uF_on_0.54uF_grid"] = {k: s55[k] for k in (
        "cap_bound_70C_worstshare_max_ratio", "cap_bound_70C_worstshare_n_over_1", "cap_estimate_70C_nomshare_max_ratio")}
    fp = load("floor-probe.csv")
    if fp:
        summary["floor_probe_unregulated"] = {
            "n": len(fp),
            "max_i_pk": maxima(fp, ["i_tank_pk_a"])["i_tank_pk_a"],
            "max_vc_pk_v": max(fl(r, "vc_pk_v") for r in fp),
            "n_capacitive_at_crest_edge": sum(fl(r, "i_edge_crest_a") < 0 for r in fp),
            "capacitive_cases": [f"{r['load']} {r['line_vrms']}V {r['freq_hz']}Hz" for r in fp if fl(r, "i_edge_crest_a") < 0],
            "no_pan_max_i_pk": max(fl(r, "i_tank_pk_a") for r in fp if r["load"].startswith("no_pan")),
        }
    json.dump(summary, open(OUT / "summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1)[:12000])


if __name__ == "__main__":
    main()
