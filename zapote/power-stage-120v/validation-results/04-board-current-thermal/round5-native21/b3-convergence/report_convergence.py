#!/usr/bin/env python3
"""Analysis stage: controls, Richardson extrapolation, verdict tables, plots -> results.json, RESULTS-TABLES.md, *.png.

    python3 report_convergence.py        (after run_convergence.py has filled runs/)
Exit status 1 if a control fails.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import thermal_body as tb  # noqa: E402
import body_runs as br  # noqa: E402

RUNS = HERE / "runs"
ROUND5 = tb.ROUND5
CRIT_K = 2.0
PITCHES = (1.0, 0.5, 0.25)
CONFIG_LABEL = {"legacy": "legacy (binary Cu, point deposit)", "binary+network": "binary Cu + package network",
                "fraction+point": "Cu fill-fraction + point deposit", "main": "Cu fill-fraction + package network (new)"}
WINS = json.loads((HERE / "windows.json").read_text()) if (HERE / "windows.json").exists() else []
NESTED = json.loads((HERE / "windows_fine.json").read_text()) if (HERE / "windows_fine.json").exists() else []


def load(name):
    p = RUNS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def tname(op, h, pitch, config, extra=""):
    return f"{op}_h{h}_p{str(pitch).replace('.', 'p')}_{config.replace('+', '-')}{extra}"


# ----------------------------------------------------------------------------------------------------- Richardson
def richardson(levels):
    """levels: [(pitch, value)] coarse -> fine, >= 3 entries. Uses the three finest.
    Returns dict(est, p, delta_fine, status). Pitch ratio is 2 between successive levels."""
    lv = sorted(levels, key=lambda t: -t[0])
    out = {"values": {str(k): v for k, v in lv}}
    if len(lv) < 2:
        return {**out, "status": "insufficient"}
    q = [v for _, v in lv]
    d_fine = q[-1] - q[-2]
    out["delta_fine_k"] = d_fine
    if len(lv) < 3:
        return {**out, "est": q[-1], "p": None, "status": "two_levels"}
    d_prev = q[-2] - q[-3]
    if abs(d_fine) < 1e-9 and abs(d_prev) < 1e-9:
        return {**out, "est": q[-1], "p": None, "uncert_k": 0.0, "status": "flat"}
    if d_fine * d_prev > 0 and abs(d_fine) < abs(d_prev):
        p = math.log2(d_prev / d_fine)
        pc = min(max(p, 0.5), 3.0)
        est = q[-1] + d_fine / (2 ** pc - 1)
        return {**out, "est": est, "p": p, "p_used": pc, "uncert_k": abs(est - q[-1]), "status": "asymptotic"}
    # not asymptotic (oscillating, or increments not shrinking): bound by the geometric series of the last increment
    est = q[-1] + abs(d_fine) * (1 if d_fine >= 0 else 0) + 0.0
    return {**out, "est": q[-1] + max(d_fine, 0.0) * 1.0, "p": None, "uncert_k": abs(d_fine) + abs(d_prev),
            "status": "non_asymptotic"}


def converged_flag(r):
    return r.get("delta_fine_k") is not None and abs(r["delta_fine_k"]) < CRIT_K and \
        r.get("uncert_k", 0.0) < CRIT_K


# ----------------------------------------------------------------------------------------------------- data access
def part_levels(op, h, config="main", suffix=""):
    """{ref: {pitch: row}} from the three global meshes plus the owning 0.125 mm window."""
    out = {}
    for p in PITCHES:
        r = load(tname(op, h, p, config, suffix))
        if not r:
            continue
        for row in r["parts"] + r["fets"]:
            out.setdefault(row["ref"], {})[p] = row
    for w in WINS:
        r = load(tname(op, h, 0.125, "main", f"_{w['id']}"))
        if not r:
            continue
        for row in r["parts"] + r["fets"]:
            if row["ref"] in w["refs"]:
                out.setdefault(row["ref"], {})[0.125] = row
    for w in NESTED:
        r = load(tname(op, h, 0.0625, "main", f"_{w['id']}"))
        if not r:
            continue
        for row in r["parts"] + r["fets"]:
            if row["ref"] in w["refs"]:
                out.setdefault(row["ref"], {})[0.0625] = row
    return out


def series(levels, key):
    return [(p, row[key]) for p, row in levels.items() if key in row]


# ----------------------------------------------------------------------------------------------------- limits
CSS_P0, CSS_T0, CSS_T1 = 5.0, 70.0, 170.0          # Bourns CSS2H terminal derating (screen.py)


def css_derated(t):
    return CSS_P0 * min(max((CSS_T1 - t) / (CSS_T1 - CSS_T0), 0.0), 1.0)


def limit_for(ref, row):
    """(limit_C, basis, quantity the limit applies to, hard) for the verdict."""
    sp = tb.SPECS[row["spec"]]
    k = row["spec"]
    if k in ("recom", "rgw", "dwk14", "dbv5"):
        return sp["tj_limit"], f"Tj max {sp['tj_limit']:.0f} C ({sp['label']} datasheet)", "tj_c", True
    if k == "css2h":
        p = row["watts_into_model"]
        t_full = CSS_T1 - p / CSS_P0 * (CSS_T1 - CSS_T0)           # terminal temperature at which the derated power = P
        t_g6 = CSS_T1 - p / (0.8 * CSS_P0) * (CSS_T1 - CSS_T0)     # with the stage-17 G6 20 % margin
        return min(t_g6, 160.0), (f"terminal derating (5 W at 70 C -> 0 W at 170 C): P = {p:.3f} W allowed up to {t_full:.1f} C "
                                  f"terminal; G6 rule (>= 20 % margin, pad <= 160 C) gives {min(t_g6, 160.0):.1f} C"), "pad_max_cell_c", True
    if k == "chip1206":
        return 155.0, "1206 chip resistor 155 C max (vendor-typical, NOT re-verified here)", "tj_c", False
    if k == "film_mmkp82":
        return 105.0, "MMKP82 film capacitor Top,max 105 C (KNSCHA KNS20200505002 p.4, 40/105/56)", "tj_c", False
    if k == "film_mmkp":
        return 125.0, "MMKP film capacitor Top,max 125 C case (TDK B3264*B June 2026 p.2, p.12)", "tj_c", False
    if k in ("film_radial", "film_hf", "film_4pin"):
        return 105.0, "film capacitor 105 C upper category temperature (TDK, as recorded in round6 README; ripple derating applies below)", "tj_c", False
    if k == "meanwell":
        return 85.0, "IRM-20 85 C AMBIENT max (spec: derating curve); no pin/case limit published", "tj_c", False
    if k == "choke":
        return 125.0, "choke 125 C (UNVERIFIED class value)", "tj_c", False
    raise KeyError(k)


def bench_dependent(ref, row):
    k = row["spec"]
    return (k in ("film_radial", "film_mmkp", "film_mmkp82", "film_hf", "film_4pin", "meanwell", "choke")) or row.get("sink_fraction", 0) > 0


# ----------------------------------------------------------------------------------------------------- controls
def controls():
    c = {}
    # C1: legacy point deposition reproduces the committed ceiling sweep (28 A, h25, 1 mm) and the committed 0.5 mm run
    sweep = json.loads((ROUND5 / "b3/outputs/ceiling_sweep.json").read_text())
    ref28 = [e for e in sweep if e["ceiling_A"] == 28.0][0]["peak"]["temperature_c"]
    leg1 = load(tname("c28", 25, 1.0, "legacy"))
    leg05 = load(tname("c28", 25, 0.5, "legacy"))
    committed05 = json.loads((ROUND5 / "b3/outputs/c28_h25_p0p5.json").read_text())["peak"]["temperature_c"]
    sub = subprocess.run([sys.executable, "-c",
                          "import sys,json,subprocess;sys.path.insert(0,'%s');import run_study as rs;import tempfile,os;"
                          "o=os.path.join(tempfile.mkdtemp(),'a.json');"
                          "subprocess.run([sys.executable,'%s','--geometry',str(rs.GEOM),'--case',rs.cases('c28'),'--pitch-mm','1.0','--h','25',"
                          "'--a6-heat',str(rs.HEAT_C28),'--a6-mode','nominal','--output',o],check=True,stdout=subprocess.DEVNULL);"
                          "print(json.load(open(o))['peak']['temperature_c'])" % (ROUND5 / "b3", ROUND5 / "b3/thermal.py")],
                         capture_output=True, text=True, check=True).stdout.strip()
    sub_peak = float(sub)
    c["C1_legacy_reproduction"] = {
        "committed_sweep_28A_h25_c": ref28, "committed_1mm_peak_location": "R5.4 pad region (39.5, 14.5) F.Cu",
        "this_module_legacy_mode_c": leg1["peak"]["temperature_c"], "diff_k": leg1["peak"]["temperature_c"] - ref28,
        "thermal_py_subprocess_c": sub_peak, "committed_c28_h25_p0p5_c": committed05,
        "this_module_legacy_0p5_c": leg05["peak"]["temperature_c"], "diff_0p5_k": leg05["peak"]["temperature_c"] - committed05,
        "tolerance_k": 0.1}
    c["C1_legacy_reproduction"]["pass"] = (abs(c["C1_legacy_reproduction"]["diff_k"]) < 0.1 and abs(sub_peak - ref28) < 0.1
                                           and abs(c["C1_legacy_reproduction"]["diff_0p5_k"]) < 0.1)
    # C2: energy balance on every run
    worst, n = 0.0, 0
    worst_name = None
    for f in sorted(RUNS.glob("*.json")):
        r = json.loads(f.read_text())
        if "balance" not in r:
            continue
        b = r["balance"]["balance_rel"]
        n += 1
        if abs(b) > worst:
            worst, worst_name = abs(b), f.stem
    c["C2_energy_balance"] = {"runs": n, "max_abs_relative_imbalance": worst, "worst_run": worst_name, "limit": 1e-3,
                              "pass": worst < 1e-3}
    # C3: analytic disc on a fin plate (+ the committed strip / column oracles)
    disc = [tb.analytic_disc(pitch_mm=p) for p in (0.5, 0.25)]
    strip = tb.T.analytic_selftest()
    ctl = [json.loads(f.read_text()).get("control_vs_global_max_abs_k") for f in sorted(RUNS.glob("*ctl.json"))]
    ctl = [x for x in ctl if x is not None]
    c["C3_analytic"] = {"disc": disc, "tolerance": 0.03, "committed_strip_and_column_oracles": strip["status"],
                        "window_vs_global_max_abs_k": ctl,
                        "pass": all(d["mean_rel_err"] < 0.03 and d["junction_rel_err"] < 0.03 and abs(d["balance_rel"]) < 1e-3
                                    for d in disc) and strip["status"] == "PASS"}
    c["C4_window_matches_global_0p25"] = {"max_abs_k_over_windows": max(ctl) if ctl else None, "limit_k": 0.01,
                                          "pass": bool(ctl) and max(ctl) < 0.01}
    return c


# ----------------------------------------------------------------------------------------------------- main
def fmt(x, d=1):
    return "-" if x is None else f"{x:.{d}f}"


def main():
    res = {"criterion": f"|Q(finest) - Q(next finest)| < {CRIT_K} K and Richardson extrapolation uncertainty < {CRIT_K} K, "
                        "for every reported quantity; finest = 0.125 mm window, else 0.25 mm global"}
    res["controls"] = controls()

    # ---- (1) mesh sensitivity of the board peak, four source/copper configurations, two operating points
    ms = {}
    for op, h in (("c28", 25), ("nominal", 25)):
        for cfg in br_configs():
            rows = []
            for p in PITCHES:
                r = load(tname(op, h, p, cfg))
                if r:
                    rows.append({"pitch_mm": p, "peak_c": r["peak"]["temperature_c"], "peak_xy": [r["peak"]["x_mm"], r["peak"]["y_mm"]],
                                 "peak_layer": r["peak"]["layer"], "peak_1mm_block_c": r["peak_1mm_block"]["temperature_c"],
                                 "fet_row_max_c": r["fet_row_max_c"], "runtime_s": r["runtime_s"]})
            ms[f"{op}_h{h}/{cfg}"] = rows
    res["board_peak_vs_mesh"] = ms
    dec = {}
    for part in ("a4only", "partsonly"):
        for cfg in ("legacy", "main"):
            rows = []
            for p in PITCHES:
                r = load(tname("c28", 25, p, cfg, f"_{part}"))
                if r:
                    rows.append({"pitch_mm": p, "peak_c": r["peak"]["temperature_c"], "peak_xy": [r["peak"]["x_mm"], r["peak"]["y_mm"]],
                                 "peak_layer": r["peak"]["layer"], "peak_1mm_block_c": r["peak_1mm_block"]["temperature_c"]})
            dec[f"{part}/{cfg}"] = rows
    res["decomposition_c28_h25"] = dec

    # ---- (2) legacy per-part variation and flux concentration (what drives the non-convergence)
    leg = {}
    for p in PITCHES:
        r = load(tname("c28", 25, p, "legacy"))
        for row in r["parts"]:
            leg.setdefault(row["ref"], {})[p] = row
    drivers = []
    for ref, lv in leg.items():
        mx = [lv[p]["pad_max_cell_c"] for p in PITCHES]
        mn = [lv[p]["pad_mean_c"] for p in PITCHES]
        drivers.append({"ref": ref, "mpn": lv[1.0]["mpn"], "legacy_pad_max_c": mx, "legacy_pad_mean_c": mn,
                        "legacy_max_swing_k": max(mx) - min(mx), "legacy_mean_swing_k": max(mn) - min(mn),
                        "flux_concentration": [lv[p].get("flux_concentration") for p in PITCHES],
                        "deposit_cells": [lv[p].get("point_deposit_cells") for p in PITCHES],
                        "pad_area_mm2": lv[1.0]["pad_area_mm2"], "watts": lv[1.0]["watts_into_model"]})
    drivers.sort(key=lambda d: -d["legacy_max_swing_k"])
    res["legacy_part_drivers"] = drivers

    # ---- (3) converged per-part quantities for each verdict operating point
    verdict = {}
    for op, h in (("c28", 25), ("c28", 10), ("der14", 10)):
        lv = part_levels(op, h)
        rows = []
        for ref, per in lv.items():
            any_row = per[max(per)]
            if "spec" not in any_row and ref not in br.FET_REFS:
                continue
            ent = {"ref": ref, "mpn": any_row.get("mpn"), "watts": any_row.get("watts_into_model"),
                   "levels_available": sorted(per.keys(), reverse=True)}
            for key in ("pad_mean_c", "pad_max_cell_c", "tj_c", "tcase_c"):
                s = series(per, key)
                if len(s) >= 2:
                    rr = richardson(s)
                    rr["converged"] = converged_flag(rr)
                    ent[key] = rr
            if "spec" in any_row:
                ent["spec"] = any_row["spec"]
                ent["sink_fraction"] = any_row.get("sink_fraction", 0.0)
                lim, basis, qty, hard = limit_for(ref, any_row)
                ent["limit_c"], ent["limit_basis"], ent["limit_applies_to"], ent["limit_is_part_datasheet_rating"] = lim, basis, qty, hard
                est = ent[qty]
                top = est["est"] + est.get("uncert_k", abs(est.get("delta_fine_k", 0)))
                ent["estimate_c"], ent["estimate_plus_uncert_c"] = est["est"], top
                ent["margin_k"] = lim - top
                ent["bench_dependent"] = bench_dependent(ref, any_row)
                if ent["bench_dependent"]:
                    ent["verdict"] = "BENCH IR (limit is not a body/junction temperature, or only the board share of the loss is modelled)"
                elif ent["margin_k"] >= 15:
                    ent["verdict"] = "MARGIN"
                elif ent["margin_k"] >= 0:
                    ent["verdict"] = "THIN"
                else:
                    ent["verdict"] = "EXCEEDS"
            rows.append(ent)
        verdict[f"{op}_h{h}"] = rows
    res["per_part"] = verdict

    # ---- (4) board hot spots (single-cell peak does not converge; 1 mm block mean is the mesh-comparable form)
    hs = {}
    for op, h in (("c28", 25), ("c28", 10), ("der14", 10)):
        pk, b1 = [], []
        for p in PITCHES:
            r = load(tname(op, h, p, "main"))
            pk.append((p, r["peak"]["temperature_c"]))
            b1.append((p, r["peak_1mm_block"]["temperature_c"]))
        hs[f"{op}_h{h}"] = {"single_cell_peak": richardson(pk), "peak_1mm_block_mean": richardson(b1),
                            "peak_location_0p25": load(tname(op, h, 0.25, "main"))["peak"],
                            "block_location_0p25": load(tname(op, h, 0.25, "main"))["peak_1mm_block"],
                            "legacy_1mm_peak_c": (load(tname(op, h, 1.0, "legacy"))["peak"]["temperature_c"] if op == "c28" and h == 25 else None)}
    res["board_hotspots"] = hs
    nest = {}
    for op, h in (("c28", 25), ("der14", 10)):
        for w in NESTED:
            r = load(tname(op, h, 0.0625, "main", f"_{w['id']}"))
            if r:
                bx, by = r["peak_1mm_block"]["x_mm"], r["peak_1mm_block"]["y_mm"]
                edge = min(bx - w["x_mm"][0], w["x_mm"][1] - bx, by - w["y_mm"][0], w["y_mm"][1] - by)
                nest[f"{op}_h{h}/{w['id']}"] = {"peak_1mm_block": r["peak_1mm_block"], "peak_cell_0p0625": r["peak"],
                                                "distance_to_window_edge_mm": edge, "usable": edge >= 5.0}
    res["nested_0p0625_hotspots"] = nest

    # ---- (5) package-network sensitivity at 0.5 mm
    base = {r["ref"]: r for r in load(tname("c28", 25, 0.5, "main"))["parts"]}
    sens = {}
    for name in ("all_pins", "r_pad_x0.5", "r_pad_x2", "h_body_x0.5", "gap_path", "air_all"):
        r = load(tname("c28", 25, 0.5, "main", f"_sens-{name}"))
        if not r:
            continue
        rows = {x["ref"]: x for x in r["parts"]}
        sens[name] = {ref: {"d_tj_k": rows[ref]["tj_c"] - base[ref]["tj_c"], "d_pad_mean_k": rows[ref]["pad_mean_c"] - base[ref]["pad_mean_c"]}
                      for ref in ("U41", "U42", "U26", "R5", "U1", "U2", "R58", "PS1", "PS2", "C21", "C5", "L1", "U39")}
    res["network_sensitivity_0p5mm_c28_h25"] = sens

    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    write_tables(res)
    plots(res)
    ok = all(res["controls"][k]["pass"] for k in res["controls"])
    print("controls:", {k: v["pass"] for k, v in res["controls"].items()})
    return 0 if ok else 1


def br_configs():
    return ("legacy", "binary+network", "fraction+point", "main")


# ----------------------------------------------------------------------------------------------------- tables
GROUPS = [("R5 shunt (Bourns CSS2H)", ["R5"]), ("U41/U42 RECOM R24C2T25 module", ["U41", "U42"]), ("U26 TPS7A4700 LDO", ["U26"]),
          ("U1/U2 UCC21550 driver", ["U1", "U2"]), ("U3/U37/U38/U39 TPS70950 LDO", ["U3", "U37", "U38", "U39"]),
          ("Gate resistors (1206)", ["R10", "R12", "R18", "R20", "R53", "R54", "R57", "R58"]),
          ("Other 1206 resistors", ["R22", "R23", "R24", "R25", "R39", "R67", "R68", "R69", "R70"]),
          ("Bank film caps (board share of loss only)", ["C21", "C22", "C23", "C151", "C152"]),
          ("HF film caps C38-C41", ["C38", "C39", "C40", "C41"]), ("C5/C6 resonant film caps", ["C5", "C6"]),
          ("L1 mains choke", ["L1"]), ("PS1 IRM-20-15", ["PS1"]), ("PS2 IRM-20-24", ["PS2"])]


def write_tables(res):
    L = []
    L.append("### Board peak vs mesh (c28 and nominal, h25), single-cell peak [C] and 1 mm block-mean peak [C]\n")
    L.append("| case / model | 1.0 mm | 0.5 mm | 0.25 mm | 1 mm-block peak 1.0 / 0.5 / 0.25 |")
    L.append("|---|---|---|---|---|")
    for k, rows in res["board_peak_vs_mesh"].items():
        if len(rows) < 3:
            continue
        cells = " | ".join(f"{r['peak_c']:.1f} ({r['peak_xy'][0]:.1f},{r['peak_xy'][1]:.1f} {r['peak_layer']})" for r in rows)
        L.append(f"| {k} | {cells} | {' / '.join(f'{r['peak_1mm_block_c']:.1f}' for r in rows)} |")
    L.append("\n### Decomposition (c28 h25): copper Joule heat only / part heat only\n")
    L.append("| run | 1.0 mm | 0.5 mm | 0.25 mm |")
    L.append("|---|---|---|---|")
    for k, rows in res["decomposition_c28_h25"].items():
        L.append(f"| {k} | " + " | ".join(f"{r['peak_c']:.1f} ({r['peak_xy'][0]:.1f},{r['peak_xy'][1]:.1f} {r['peak_layer']})" for r in rows) + " |")
    L.append("\n### Legacy point-deposition: parts ranked by pad-max swing across 1 / 0.5 / 0.25 mm (c28 h25)\n")
    L.append("| ref | W | pad area mm2 | legacy pad max C (1/0.5/0.25) | swing K | legacy pad mean C | deposit cells | true/deposit area |")
    L.append("|---|---|---|---|---|---|---|---|")
    for d in res["legacy_part_drivers"][:14]:
        L.append(f"| {d['ref']} | {d['watts']:.3f} | {d['pad_area_mm2']:.1f} | {' / '.join(f'{v:.0f}' for v in d['legacy_pad_max_c'])} | "
                 f"{d['legacy_max_swing_k']:.0f} | {' / '.join(f'{v:.0f}' for v in d['legacy_pad_mean_c'])} | "
                 f"{' / '.join(str(v) for v in d['deposit_cells'])} | {' / '.join(f'{v:.1f}' for v in d['flux_concentration'])} |")
    for key, rows in res["per_part"].items():
        L.append(f"\n### Per-part converged quantities, {key}\n")
        L.append("Q levels listed 1.0 / 0.5 / 0.25 (/ 0.125 window / 0.0625 nested window). est = Richardson (observed order p, clipped 0.5-3); "
                 "conv = criterion met.\n")
        L.append("| ref | W | pad mean C (levels) | est | conv | pad max-cell C (levels) | est | conv | junction C (levels) | est+-u | conv | limit C | margin K | verdict |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        order = sorted(rows, key=lambda e: -(e.get("estimate_c") or e.get("pad_mean_c", {}).get("est", 0)))
        for e in order:
            def lv(k):
                d = e.get(k)
                return "-" if not d else "/".join(f"{v:.1f}" for _, v in sorted(((float(a), b) for a, b in d["values"].items()), key=lambda t: -t[0]))

            def es(k, u=False):
                d = e.get(k)
                if not d:
                    return "-"
                return f"{d['est']:.1f}" + (f"+-{d.get('uncert_k', 0):.1f}" if u else "")

            def cv(k):
                d = e.get(k)
                return "-" if not d else ("yes" if d["converged"] else "NO")
            L.append(f"| {e['ref']} | {fmt(e.get('watts'), 3)} | {lv('pad_mean_c')} | {es('pad_mean_c')} | {cv('pad_mean_c')} | {lv('pad_max_cell_c')} | "
                     f"{es('pad_max_cell_c')} | {cv('pad_max_cell_c')} | {lv('tj_c')} | {es('tj_c', True)} | {cv('tj_c')} | "
                     f"{fmt(e.get('limit_c'))} | {fmt(e.get('margin_k'))} | {e.get('verdict', '(copper only)')} |")
    L.append("\n### Grouped verdict tables (worst member of each group; est = converged estimate, u = extrapolation uncertainty)\n")
    for key in ("c28_h25", "c28_h10", "der14_h10"):
        L.append(f"\n**{key}**\n")
        L.append("| group | worst ref | W | pad mean C | pad max C | junction / element C (+-u) | body-top C | limit | margin K | all quantities converged | finest mesh | verdict |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        rows = {e["ref"]: e for e in res["per_part"][key]}
        for gname, refs in GROUPS:
            cand = [rows[r] for r in refs if r in rows and "estimate_c" in rows[r]]
            if not cand:
                continue
            e = max(cand, key=lambda x: x["estimate_plus_uncert_c"])
            conv = all(e[q]["converged"] for q in ("pad_mean_c", "pad_max_cell_c", "tj_c"))
            finest = min(float(k) for k in e["tj_c"]["values"])
            tc = e.get("tcase_c")
            L.append(f"| {gname} | {e['ref']} | {e['watts']:.3f} | {e['pad_mean_c']['est']:.1f} | {e['pad_max_cell_c']['est']:.1f} | "
                     f"{e['tj_c']['est']:.1f} +-{e['tj_c'].get('uncert_k', 0):.1f} | {fmt(tc['est'] if tc else None)} | {e['limit_c']:.1f} ({e['limit_applies_to']}) | "
                     f"{e['margin_k']:.1f} | {'yes' if conv else 'NO'} | {finest:g} mm | {e['verdict'].split(' (')[0]} |")
        fe = [r for r in res["per_part"][key] if r["ref"] in br.FET_REFS]
        if fe:
            w = max(fe, key=lambda r: r["pad_max_cell_c"]["est"])
            L.append(f"| FET-lead copper (board side, no rating: laminate Tg 150) | {w['ref']} | - | {w['pad_mean_c']['est']:.1f} | {w['pad_max_cell_c']['est']:.1f} | - | - | 150.0 (Tg) | "
                     f"{150 - w['pad_max_cell_c']['est'] - w['pad_max_cell_c'].get('uncert_k', 0):.1f} | {'yes' if w['pad_max_cell_c']['converged'] else 'NO'} | "
                     f"{min(float(k) for k in w['pad_max_cell_c']['values']):g} mm | copper only |")
    L.append("\n### Board hot spots\n")
    L.append("| case | single-cell peak levels | est / status | 1 mm block-mean peak levels | est / status |")
    L.append("|---|---|---|---|---|")
    for k, v in res["board_hotspots"].items():
        a, b = v["single_cell_peak"], v["peak_1mm_block_mean"]
        L.append(f"| {k} | {' / '.join(f'{x:.1f}' for x in a['values'].values())} | {fmt(a.get('est'))} {a['status']} | "
                 f"{' / '.join(f'{x:.1f}' for x in b['values'].values())} | {fmt(b.get('est'))} {b['status']} |")
    (HERE / "RESULTS-TABLES.md").write_text("\n".join(L) + "\n")


# ----------------------------------------------------------------------------------------------------- plots
COL = {"legacy": "#c0392b", "binary+network": "#8e6bbf", "fraction+point": "#e08a1e", "main": "#1f6feb"}


def plots(res):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, key, ttl in ((axs[0], "c28_h25", "c28 h25: board peak (single cell)"), (axs[1], "nominal_h25", "nominal h25: board peak (single cell)")):
        for cfg in br_configs():
            rows = res["board_peak_vs_mesh"].get(f"{key}/{cfg}", [])
            if rows:
                ax.plot([r["pitch_mm"] for r in rows], [r["peak_c"] for r in rows], "o-", color=COL[cfg], label=CONFIG_LABEL[cfg])
        ax.set_xscale("log")
        ax.invert_xaxis()
        ax.set_xlabel("mesh pitch (mm)")
        ax.set_ylabel("peak temperature (C)")
        ax.set_title(ttl, fontsize=10)
        ax.grid(alpha=0.3)
    for cfg in br_configs():
        rows = res["board_peak_vs_mesh"].get(f"c28_h25/{cfg}", [])
        if rows:
            axs[2].plot([r["pitch_mm"] for r in rows], [r["peak_1mm_block_c"] for r in rows], "o-", color=COL[cfg], label=CONFIG_LABEL[cfg])
    axs[2].set_xscale("log")
    axs[2].invert_xaxis()
    axs[2].set_title("c28 h25: peak of 1 mm x 1 mm block mean", fontsize=10)
    axs[2].set_xlabel("mesh pitch (mm)")
    axs[2].grid(alpha=0.3)
    axs[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "board-peak-vs-mesh.png", dpi=140)
    plt.close(fig)

    # per-part: legacy pad max vs new pad mean / junction for the parts that matter
    lv = part_levels("c28", 25)
    leg = {}
    for p in PITCHES:
        for row in load(tname("c28", 25, p, "legacy"))["parts"]:
            leg.setdefault(row["ref"], {})[p] = row
    refs = ["R5", "U41", "U42", "U26", "PS2", "R58"]
    fig, axs = plt.subplots(2, 3, figsize=(15, 7.5), sharex=True)
    for ax, ref in zip(axs.ravel(), refs):
        ax.plot(PITCHES, [leg[ref][p]["pad_max_cell_c"] for p in PITCHES], "o--", color=COL["legacy"], label="legacy pad-cell max")
        ax.plot(PITCHES, [leg[ref][p]["pad_mean_c"] for p in PITCHES], "s--", color="#e5a09a", label="legacy pad-cell mean")
        per = lv[ref]
        ps = sorted(per, reverse=True)
        ax.plot(ps, [per[p]["pad_mean_c"] for p in ps], "s-", color="#1f6feb", label="new pad-copper area mean")
        ax.plot(ps, [per[p]["pad_max_cell_c"] for p in ps], "^-", color="#6ea8fe", label="new pad-copper max cell")
        if "tj_c" in per[ps[0]]:
            ax.plot(ps, [per[p]["tj_c"] for p in ps], "d-", color="#1a7f37", label="new junction (network)")
        ax.set_xscale("log")
        ax.set_title(ref, fontsize=10)
        ax.grid(alpha=0.3)
    for ax in axs[1]:
        ax.set_xlabel("mesh pitch (mm)")
    axs[0][0].set_ylabel("C")
    axs[1][0].set_ylabel("C")
    axs[0][0].invert_xaxis()
    axs[0][0].legend(fontsize=7)
    fig.suptitle("c28 h25: per-part temperatures vs mesh (0.125 mm = refined window)", fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "parts-vs-mesh.png", dpi=140)
    plt.close(fig)

    # verdict bars
    fig, axs = plt.subplots(1, 2, figsize=(15, 6.5))
    for ax, key in zip(axs, ("c28_h25", "der14_h10")):
        rows = [e for e in res["per_part"][key] if "limit_c" in e]
        rows.sort(key=lambda e: e["estimate_c"])
        # one row per distinct part type: keep the hottest of each spec
        seen, keep = set(), []
        for e in reversed(rows):
            if e["spec"] in seen and e["spec"] not in ("recom",):
                continue
            seen.add(e["spec"])
            keep.append(e)
        keep.sort(key=lambda e: e["estimate_c"])
        for i, e in enumerate(keep):
            ax.barh(i, e["estimate_c"] - 50, left=50, color="#1f6feb" if not e["bench_dependent"] else "#8b949e", height=0.55)
            ax.plot([e["estimate_plus_uncert_c"]] * 2, [i - 0.3, i + 0.3], color="k", lw=1)
            ax.plot([e["limit_c"]] * 2, [i - 0.4, i + 0.4], color="#c0392b", lw=2)
        ax.set_yticks(range(len(keep)))
        ax.set_yticklabels([f"{e['ref']} {tb.SPECS[e['spec']]['label']}" for e in keep], fontsize=8)
        ax.set_xlabel("C (blue/grey: converged estimate; black tick: + extrapolation uncertainty; red: rating limit)")
        ax.set_title(key.replace("_", " ") + ": hottest part of each type, junction/limit quantity", fontsize=10)
        ax.set_xlim(50, 200)
        ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(HERE / "verdict-vs-limits.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
