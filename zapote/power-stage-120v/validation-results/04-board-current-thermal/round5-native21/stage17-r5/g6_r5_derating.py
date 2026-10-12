#!/usr/bin/env python3
"""Stage-17 gate G6 (go/no-go): R5 = Bourns CSS2H-2512R-1L00F derating at the 28 A ceiling case on the
stage-17 board (PLAN-17 section 4, G6).

    python3 g6_r5_derating.py [--tag native21s17] [--control-a4 DIR]   -> g6.json (exit 1 if a control fails)

Solve (committed B3 tool, same command line as ../r5-derating/r5_derating.py): ../b3/thermal.py, c28 case
(29.4 A tank RMS = 1.05 x the 28 A ceiling, 11.1 A inlet), 0.25 mm mesh, h 25 W/m2K, 50 C ambient, geometry
native-21/verification/<tag>-all-copper.json.gz, part heat ../b3/inputs/native21-board-heat-sources-c28.json
(make_heat_sources.py; R5 = 29.4^2 x 1 mOhm = 0.86436 W on the current pads 1 / 4 only, `pad_numbers`), A4
copper heat ../outputs/*-heat.npz (gitignored; regate.sh / run_cases.py regenerate them for the board).

Rule (pre-stated in r5-derating and PLAN-17 G6): P_diss <= 0.80 x derated power at the R5 pad-cell maximum
(margin >= 20 %), pad-cell maximum <= 160 C, OCP low edge after the Kelvin shift (all-at-max-transfer bound)
with the part's TCR >= 64.17 A. CSS2H derating curve and TCR come from screen.py (current Bourns datasheet:
5 W at 70 C terminal, linear to 0 at 170 C; +/-75 ppm/C); the pad cell is taken as the terminal temperature.

Controls (asserted before any verdict):
  A  arithmetic: the current part (WSK25121L000FEA, 1 W, ambient axis, 0 at 170 C) at the committed
     r5-derating pad maximum 149.16 C gives 0.86436 W against 0.2084 W derated: FAIL (-314.7 %), the
     committed ../r5-derating/results.json numbers.
  B  solver (only with --control-a4 DIR = the stage-16 A4 outputs): the stage-16 board with the stage-16
     heat semantics (R5 heat on all four pads) reproduces the committed 149.16 C within 0.05 K, i.e. the
     stage-17 thermal.py change (per-pad heat) leaves earlier solves unchanged.
Sensitivity (reported, not gated): the same solves with the heat on all four R5 pads on the stage-17 board, and
on the WSK's current pads only on the stage-16 board (with --control-a4).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R5N = HERE.parent
UNIT = R5N.parents[2]
VR = UNIT / "validation-results"
MARGIN, T_PAD_LIMIT, FLOOR_A = 0.20, 160.0, 64.17
I_TRIP = 29.4


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def solve(geom, heat, env_a4=None):
    rs = load("run_study", R5N / "b3/run_study.py")
    out = Path(tempfile.mkdtemp()) / "b3_p0p25.json"
    cmd = [sys.executable, str(R5N / "b3/thermal.py"), "--geometry", str(geom), "--case", rs.cases("c28"),
           "--pitch-mm", "0.25", "--h", "25", "--a6-heat", str(heat), "--a6-mode", "nominal", "--output", str(out)]
    env = dict(os.environ)
    if env_a4:
        env["B3_A4_DIR"] = str(env_a4)
    else:
        env.pop("B3_A4_DIR", None)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, env=env)
    r = json.loads(out.read_text())
    return r, next(q for q in r["a6_parts_applied"] if q["ref"] == "R5")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="native21s17b")
    ap.add_argument("--control-a4", help="stage-16 A4 outputs dir (*-heat.npz) for solver control B")
    a = ap.parse_args()
    scr = load("screen", HERE / "screen.py")
    css = next(c for c in scr.CANDS if c["key"] == "CSS2H-2512R-1L00F")
    m = scr.load_thr()
    res17 = json.loads((R5N / "r5-derating/results.json").read_text())

    # ---- control A (arithmetic): the current part's committed FAIL
    t_wsk = res17["thermal"]["r5"]["conditional_pad_cell_max_c"]
    p_rated, pts = scr.CONTROL["curves"][scr.CONTROL["conservative"]]
    d_wsk = p_rated * scr.interp(pts, t_wsk)
    p_trip = I_TRIP ** 2 * 1e-3
    ctrl_a = {"part": "WSK25121L000FEA", "pad_max_c": round(t_wsk, 2), "p_diss_w": round(p_trip, 5),
              "derated_w": round(d_wsk, 4), "margin_pct": round((1 - p_trip / d_wsk) * 100, 1),
              "verdict": "FAIL" if p_trip > (1 - MARGIN) * d_wsk else "PASS"}
    assert ctrl_a["pad_max_c"] == 149.16 and ctrl_a["derated_w"] == 0.2084 and ctrl_a["p_diss_w"] == 0.86436, ctrl_a
    assert ctrl_a["margin_pct"] == res17["derating"]["rows"]["pad_cell_max"]["margin_pct"] and ctrl_a["verdict"] == "FAIL", ctrl_a

    heat = R5N / "b3/inputs/native21-board-heat-sources-c28.json"
    h = json.loads(heat.read_text())
    r5row = next(p for p in h["parts"] if p["ref"] == "R5")
    assert abs(r5row["watts_nominal"] - p_trip) < 1e-9 and r5row.get("pad_numbers") == ["1", "4"], r5row

    # ---- control B (solver, optional): stage-16 board, stage-16 heat semantics
    ctrl_b = None
    if a.control_a4:
        tmp = Path(tempfile.mkdtemp()) / "heat-c28-stage16-semantics.json"
        h16 = json.loads(heat.read_text())
        for p in h16["parts"]:
            if p["ref"] == "R5":
                p.pop("pad_numbers")
        tmp.write_text(json.dumps(h16))
        g16 = UNIT / "native-21/verification/native21s16-all-copper.json.gz"
        r16, q16 = solve(g16, tmp, a.control_a4)
        ctrl_b = {"geometry": str(g16.relative_to(UNIT)), "geometry_sha256": sha(g16), "a4_dir": str(a.control_a4),
                  "a4_npz_sha256": {p.name: sha(p) for p in sorted(Path(a.control_a4).glob("*-pl18-heat.npz"))},
                  "r5_pad_cells": q16["pad_cell_count"], "pad_max_c": round(q16["conditional_pad_cell_max_c"], 2),
                  "committed_c": t_wsk}
        assert abs(q16["conditional_pad_cell_max_c"] - t_wsk) <= 0.05, ctrl_b

    # ---- heat-semantics sensitivity: R5 heat on all four pads (stage-16 semantics) on the stage-17 board, and
    # on the WSK's current pads only on the stage-16 board (needs --control-a4). Separates the part / land change
    # from the modelling change (heat in an isolated sense pad gave stage 16's single hot 0.25 mm cell).
    def heat_variant(pads):
        tmp = Path(tempfile.mkdtemp()) / "heat-c28-variant.json"
        hv = json.loads(heat.read_text())
        for p in hv["parts"]:
            if p["ref"] == "R5":
                p.pop("pad_numbers", None)
                if pads:
                    p["pad_numbers"] = pads
        tmp.write_text(json.dumps(hv))
        return tmp

    def margin(t):
        p_r, pts_c = css["curves"][css["authoritative"]]
        return round((1 - p_trip / (p_r * scr.interp(pts_c, t))) * 100, 1)
    sens = {}
    g17 = UNIT / f"native-21/verification/{a.tag}-all-copper.json.gz"
    _, qa = solve(g17, heat_variant(None))
    sens["stage17_board_heat_on_all_four_pads"] = {"pad_max_c": round(qa["conditional_pad_cell_max_c"], 2),
                                                   "pad_mean_c": round(qa["conditional_pad_cell_mean_c"], 2),
                                                   "css2h_margin_pct": margin(qa["conditional_pad_cell_max_c"])}
    if a.control_a4:
        _, qb = solve(UNIT / "native-21/verification/native21s16-all-copper.json.gz", heat_variant(["1", "4"]), a.control_a4)
        sens["stage16_board_wsk_heat_on_current_pads_1_4"] = {"pad_max_c": round(qb["conditional_pad_cell_max_c"], 2),
                                                              "pad_mean_c": round(qb["conditional_pad_cell_mean_c"], 2),
                                                              "css2h_margin_pct_if_css2h_at_that_temp": margin(qb["conditional_pad_cell_max_c"])}

    # ---- G6 solve on the stage-17 board
    geom = UNIT / f"native-21/verification/{a.tag}-all-copper.json.gz"
    r, q = solve(geom, heat)
    board = json.loads(gzip.open(R5N / "inputs/power_copper.json.gz", "rt").read())["board_sha256"]
    t_max, t_mean = q["conditional_pad_cell_max_c"], q["conditional_pad_cell_mean_c"]
    rows = {}
    for name, (p_r, pts_c) in css["curves"].items():
        d = p_r * scr.interp(pts_c, t_max)
        need = p_trip / (1 - MARGIN) / p_r
        (t0, f0), (t1, f1) = pts_c[-2], pts_c[-1]
        rows[name] = {"p_rated_w": p_r, "derated_w_at_pad_max": round(d, 4),
                      "margin_pct_at_pad_max": round((1 - p_trip / d) * 100, 1),
                      "derated_w_at_pad_mean": round(p_r * scr.interp(pts_c, t_mean), 4),
                      "margin_pct_at_pad_mean": round((1 - p_trip / (p_r * scr.interp(pts_c, t_mean))) * 100, 1),
                      "t_ref_for_20pct_margin_c": round(t0 + (f0 - need) / (f0 - f1) * (t1 - t0), 2),
                      "meets_20pct": bool(p_trip <= (1 - MARGIN) * d)}
    auth = rows[css["authoritative"]]
    p_worst = p_trip * (1 + css["tol"]) * (1 + css["tcr_ppm"] * 1e-6 * (t_max - 25.0))
    d_auth = auth["derated_w_at_pad_max"]
    kb = json.loads((VR / f"02-protection-timing/kelvin/budget-{a.tag}.json").read_text())
    kp = json.loads((VR / f"02-protection-timing/kelvin/plane-{a.tag}.json").read_text())
    kel = {"e_bound": kb["bound_all_at_max_transfer"]["e_th_mV"], "a_per_mv": kp["trip_shift_A_per_mV_at_R35_2"]}
    rise = t_max - 50.0
    lo, hi, lo_k = scr.low_edge(m, 1.0, css["tol"], css["tcr_ppm"], rise, kel)
    crit = {"a_margin_ge_20pct_at_pad_max": auth["meets_20pct"], "b_pad_max_le_160c": t_max <= T_PAD_LIMIT,
            "c_trip_floor": lo_k >= FLOOR_A}
    out = {
        "gate": "G6 (PLAN-17): R5 derating margin >= 20 % at the re-run B3 pad temperature, CSS2H terminal curve",
        "part": {k: css[k] for k in ("mpn", "maker", "lcsc", "tcr_ppm", "tol", "height_mm", "doc")},
        "solve": {"tool": "round5-native21/b3/thermal.py", "case": "c28 (29.4 A tank RMS, 11.1 A inlet)", "pitch_mm": 0.25,
                  "h_w_m2k": 25, "ambient_c": 50.0, "geometry": str(geom.relative_to(UNIT)), "geometry_sha256": sha(geom),
                  "board_sha256": r["board_sha256"], "power_copper_board_sha256": board,
                  "heat_file": str(heat.relative_to(UNIT)), "heat_sha256": sha(heat),
                  "a4_npz_sha256": {p.name: sha(p) for p in sorted((R5N / "outputs").glob("*-pl18-heat.npz"))},
                  "balance_w": r["balance"]["balance_w"], "board_peak": r["peak"]},
        "r5": {"watts_to_board": q["watts_to_board"], "pad_numbers_heated": r5row["pad_numbers"], "pad_cell_count": q["pad_cell_count"],
               "pad_cell_max_c": round(t_max, 2), "pad_cell_mean_c": round(t_mean, 2),
               "vs_stage16_wsk_pad_max_c": t_wsk},
        "p_diss_w": {"at_trip_29p4A": round(p_trip, 5), "at_28A": round(28.0 ** 2 * 1e-3, 4),
                     "worst_1pct_tol_and_75ppm_at_pad_max": round(p_worst, 4),
                     "worst_margin_pct_authoritative": round((1 - p_worst / d_auth) * 100, 1)},
        "derating": rows, "authoritative_curve": css["authoritative"],
        "g6_margin_pct": auth["margin_pct_at_pad_max"],
        "trip_band": {"tcr_ppm": css["tcr_ppm"], "r5_rise_k": round(rise, 2), "before_kelvin_a": [round(lo, 2), round(hi, 2)],
                      "kelvin": {**kel, "source": f"02-protection-timing/kelvin/budget-{a.tag}.json, plane-{a.tag}.json"},
                      "low_after_kelvin_bound_a": round(lo_k, 2), "floor_a": FLOOR_A},
        "criteria": crit, "verdict": "PASS" if all(crit.values()) else "FAIL",
        "heat_semantics_sensitivity": sens,
        "open_vendor_items": ["rating basis (terminal temperature: which point of the copper terminal; current datasheet one curve "
                              "vs older 5 W / 3 W two-curve copy)", "sense-terminal contact: fingers leave the pad lobe; where the "
                              "part's own sense point sits", "element-to-terminal thermal resistance (no figure in the datasheet)"],
        "controls": {"A_arithmetic_current_part_fail": ctrl_a, "B_solver_stage16_reproduced": ctrl_b},
    }
    (HERE / "g6.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"verdict": out["verdict"], "criteria": crit, "pad_max_c": round(t_max, 2), "pad_mean_c": round(t_mean, 2),
                      "derated_w": d_auth, "g6_margin_pct": out["g6_margin_pct"], "low_edge_a": round(lo_k, 2),
                      "control_A": ctrl_a["verdict"], "control_B": ctrl_b and ctrl_b["pad_max_c"], "sensitivity": sens}, indent=1))


if __name__ == "__main__":
    main()
