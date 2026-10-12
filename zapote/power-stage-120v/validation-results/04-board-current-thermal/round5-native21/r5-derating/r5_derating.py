#!/usr/bin/env python3
"""R5 (OCP shunt) derating check at the 28 A ceiling case (DECISIONS item 14, "Still open").

    python3 r5_derating.py            -> results.json (re-runs the B3 p 0.25 solve, about 3 min)
    python3 r5_derating.py --reuse X  -> use a solver output X.json from the same command line (debug only)

Needs the round-5 A4 heat arrays (round5-native21/outputs/*-heat.npz, gitignored; regenerate with
round5-native21/run_cases.py, see README "Reproduce"). Nothing under the unit is modified except results.json.
Control asserts (script exits non-zero if either fails):
  C1  R5 heat row = 29.4^2 x 1 mOhm = 0.86436 W (committed heat file);
  C2  B3 p 0.25 R5 pad-cell max = committed stage-15b mesh-study value 149.1 / 149.2 C within 0.5 K;
  C3  the committed OCP band (68.58-118.74 A before Kelvin, 66.37 after) is reproduced by the band code used.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R5N = HERE.parent
UNIT = R5N.parents[2]
VR = UNIT / "validation-results"
T_AMB = 50.0                      # B3 ambient / design inlet (DECISIONS 14 task 03 D-18: 50 C inside enclosure)

# ---- datasheet: Vishay WSK2512, document 30108, revision 11-Dec-2023 (not committed)
DS = {"doc": "Vishay WSK2512, Document Number 30108, Revision 11-Dec-2023",
      "p_rated_w": 1.0, "p_rated_at_c": 70.0,      # p.1 Standard Electrical Specifications: P70C = 1.0 W
      "derate_zero_c": 170.0,                      # p.3 Derating graph: 100 % to 70 C ambient, linear to 0 % at 170 C
      "t_max_c": 170.0, "t_min_c": -65.0,          # p.2 Technical Specifications: operating temperature range
      "tcr_ppm": 250.0,                            # p.2: +/-250 ppm/C for 0.001 to 0.0029 ohm
      "derate_basis": "ambient temperature (graph x-axis); no terminal/solder-point rule is given"}
PASS_MARGIN = 0.20                # pre-stated: P_diss <= (1 - 0.20) x derated power
T_HEADROOM_K = 10.0               # pre-stated: pad temperature <= t_max - 10 K


def derated_w(t_c):
    return DS["p_rated_w"] * min(1.0, max(0.0, (DS["derate_zero_c"] - t_c) / (DS["derate_zero_c"] - DS["p_rated_at_c"])))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(["git", *a], cwd=UNIT, capture_output=True, text=True).stdout.strip()


def solve(reuse):
    sys.path.insert(0, str(R5N / "b3"))
    import run_study as rs  # committed copper-scaling and heat-file paths
    geom = UNIT / "native-21/verification/native21s16-all-copper.json.gz"
    heat = rs.HEAT_C28
    out = Path(reuse) if reuse else Path(tempfile.mkdtemp()) / "b3_p0p25.json"
    cmd = [sys.executable, str(R5N / "b3/thermal.py"), "--geometry", str(geom), "--case", rs.cases("c28"),
           "--pitch-mm", "0.25", "--h", "25", "--a6-heat", str(heat), "--a6-mode", "nominal", "--output", str(out)]
    if not reuse:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    r = json.loads(out.read_text())
    r5 = next(q for q in r["a6_parts_applied"] if q["ref"] == "R5")
    return r, r5, geom, heat, " ".join(cmd[1:3]) + " ... --pitch-mm 0.25 --h 25 --a6-mode nominal"


def bands(t_r5_rise, kel):
    spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    RT = (0.001, 25e-6)
    m.PARTS.update({"R34": (12.6e3, *RT), "R35": (11.7e3, *RT)})   # stage 15 divider (kelvin/README, ocp_bands.py)

    def band(temps, rise):
        r = [m.exact_corners(t, rise)["shunt_a"] for t in temps]
        return min(x["min"] for x in r), max(x["max"] for x in r)

    out = {}
    for name, temps, rise in (("committed_convention_-10_85C_rise50K", (-10.0, 85.0), 50.0),
                              ("same_ambient_corners_rise_from_B3", (-10.0, 85.0), t_r5_rise),
                              ("design_inlet_50C_rise_from_B3", (50.0,), t_r5_rise),
                              ("design_inlet_50C_committed_rise50K", (50.0,), 50.0)):
        lo, hi = band(temps, rise)
        out[name] = {"ambient_corners_c": list(temps), "r5_rise_k": round(rise, 3),
                     "r5_temp_range_c": [min(temps) + rise, max(temps) + rise],
                     "band_before_kelvin_a": [round(lo, 2), round(hi, 2)],
                     "band_after_kelvin_census_a": [round(lo + kel["e_census"] * kel["a_per_mv"], 2), round(hi, 2)],
                     "band_after_kelvin_bound_a": [round(lo + kel["e_bound"] * kel["a_per_mv"], 2), round(hi, 2)]}
    # nominal trip (all parts nominal, 25 C) and with R5 at the pad temperature, nominal TCR sign +/-
    nom = {k: v[0] for k, v in m.PARTS.items()}
    base = m.thresholds(nom, 2.5, 0.0)[0]
    shift = {}
    for sign in (+1, -1):
        p = dict(nom)
        p["R5"] = nom["R5"] * (1 + sign * DS["tcr_ppm"] * 1e-6 * (T_AMB + t_r5_rise - 25))
        shift[f"{'+' if sign > 0 else '-'}250ppm"] = {"r5_mohm": round(p["R5"] * 1e3, 4),
                                                       "trip_a": round(m.thresholds(p, 2.5, 0.0)[0], 3),
                                                       "trip_change_pct": round((m.thresholds(p, 2.5, 0.0)[0] / base - 1) * 100, 3)}
    return out, {"nominal_trip_a_25c": round(base, 3), "r5_at_pad_max_temperature": shift}, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse")
    a = ap.parse_args()
    res = {"question": "Is R5 (WSK25121L000FEA) within its datasheet derating at 0.86 W with its pad at ~149 C, and does its TCR keep the OCP band above the 64.17 A floor?",
           "git_head": git("rev-parse", "HEAD"), "datasheet": DS,
           "pass_criterion": {"a_power": f"P_diss <= {1 - PASS_MARGIN:.2f} x derated(T_pad_max) (>= {PASS_MARGIN:.0%} margin); derated(T) = {DS['p_rated_w']} W x (170 - T)/100, clipped to 0..1 W",
                              "b_temperature": f"T_pad_max <= {DS['t_max_c']} - {T_HEADROOM_K} C",
                              "c_trip_floor": "low edge of OCP band after Kelvin shift (all-at-max-transfer bound) and R5 TCR >= 64.17 A, ambient corners -10/+85 C with the B3 rise replacing the committed +50 K"}}

    # ---- C1 heat
    heat_p = R5N / "b3/inputs/native21-board-heat-sources-c28.json"
    h = json.loads(heat_p.read_text())
    r5row = next(p for p in h["parts"] if p["ref"] == "R5")
    i_trip = 1.05 * 28.0
    p_trip = i_trip ** 2 * 1e-3
    res["heat"] = {"file": str(heat_p.relative_to(UNIT)), "sha256": sha(heat_p), "r5_row": {k: r5row[k] for k in ("watts_nominal", "watts_worst", "board_fraction", "note")},
                   "i_rms_trip_a": i_trip, "p_at_trip_w": round(p_trip, 5), "p_at_28A_w": round(28.0 ** 2 * 1e-3, 5),
                   "p_at_trip_with_1pct_tol_and_tcr_limit_w": None}
    assert abs(r5row["watts_nominal"] - p_trip) < 1e-6, "C1 failed: R5 heat row != 29.4^2 x 1 mOhm"
    p_diss = r5row["watts_nominal"]

    # ---- C2 thermal
    r, r5, geom, heat, cmd = solve(a.reuse)
    t_max, t_mean = r5["conditional_pad_cell_max_c"], r5["conditional_pad_cell_mean_c"]
    mesh = json.loads((R5N / "stage15b/out/mesh_study.json").read_text())
    ref = {k: v["hottest_parts"][0] for k, v in mesh.items() if k.endswith("|c28|p0.25|h25")}
    assert r["board_sha256"] == json.loads(__import__("gzip").open(R5N / "inputs/power_copper.json.gz", "rt").read())["board_sha256"]
    for k, v in ref.items():
        assert v[0] == "R5" and abs(t_max - v[1]) <= 0.5, f"C2 failed vs {k}: {t_max} vs {v}"
    res["thermal"] = {"command": cmd, "geometry": str(geom.relative_to(UNIT)), "geometry_sha256": sha(geom), "board_sha256": r["board_sha256"],
                      "committed_tool": "round5-native21/b3/thermal.py (2.5-D FV, k_Cu 390, k_FR4 0.3, h 25 W/m2K each face, 50 C ambient)",
                      "pitch_mm": 0.25, "balance_w": r["balance"]["balance_w"], "board_peak": r["peak"],
                      "r5": {k: r5[k] for k in ("watts_to_board", "pad_layer", "pad_cell_count", "conditional_pad_cell_max_c", "conditional_pad_cell_mean_c")},
                      "committed_reference_c": {k: v[1] for k, v in ref.items()}, "control_tolerance_k": 0.5}
    # R5 element heat could be larger than the A4-based row: tolerance + TCR worst case at the pad temperature
    p_hot = i_trip ** 2 * 1e-3 * 1.01 * (1 + DS["tcr_ppm"] * 1e-6 * (t_max - 25))
    res["heat"]["p_at_trip_with_1pct_tol_and_tcr_limit_w"] = round(p_hot, 4)

    # ---- derating
    rows = {}
    for label, t in (("pad_cell_max", t_max), ("pad_cell_mean", t_mean), ("ambient_inlet_50C", T_AMB)):
        d = derated_w(t)
        rows[label] = {"temp_c": round(t, 2), "derated_w": round(d, 4), "utilisation": round(p_diss / d, 3) if d else None,
                       "margin_pct": round((1 - p_diss / d) * 100, 1) if d else None, "meets_20pct_margin": p_diss <= (1 - PASS_MARGIN) * d}
    t_allow = DS["derate_zero_c"] - 100.0 * p_diss / DS["p_rated_w"]
    t_allow_28 = DS["derate_zero_c"] - 100.0 * 28.0 ** 2 * 1e-3 / DS["p_rated_w"]
    t_allow_margin = DS["derate_zero_c"] - 100.0 * p_diss / ((1 - PASS_MARGIN) * DS["p_rated_w"])
    res["derating"] = {"p_diss_w": p_diss, "rows": rows, "max_ref_temp_for_p_diss_c": round(t_allow, 2),
                       "max_ref_temp_for_28A_0p784W_c": round(t_allow_28, 2),
                       "max_ref_temp_for_p_diss_with_20pct_margin_c": round(t_allow_margin, 2),
                       "decisions_D18_local_ambient_gate_c": 100.0, "derated_w_at_100c": derated_w(100.0),
                       "t_pad_headroom_to_170c_k": round(DS["t_max_c"] - t_max, 2)}
    crit_a = rows["pad_cell_max"]["meets_20pct_margin"]
    crit_b = t_max <= DS["t_max_c"] - T_HEADROOM_K

    # ---- TCR / band
    kb = json.loads((VR / "02-protection-timing/kelvin/budget-native21s16.json").read_text())
    kp = json.loads((VR / "02-protection-timing/kelvin/plane-native21s16.json").read_text())
    kel = {"e_census": kb["e_th_mV"], "e_bound": kb["bound_all_at_max_transfer"]["e_th_mV"], "a_per_mv": kp["trip_shift_A_per_mV_at_R35_2"]}
    rise = t_max - T_AMB
    b, nominal, m = bands(rise, kel)
    c0 = b["committed_convention_-10_85C_rise50K"]
    assert c0["band_before_kelvin_a"] == kb["band_before_A"], "C3 failed: band before Kelvin"
    assert c0["band_after_kelvin_census_a"] == kb["band_after_A"], "C3 failed: band after Kelvin"
    floor = 64.17
    chk = b["same_ambient_corners_rise_from_B3"]
    crit_c = chk["band_after_kelvin_bound_a"][0] >= floor
    res["tcr"] = {"tcr_ppm_per_c_max": DS["tcr_ppm"], "reference_temp_c": 25, "reference_temp_note": "datasheet does not state the TCR reference temperature in the pages read; thresholds.py convention (25 C) used",
                  "r5_temp_c_at_pad_max": round(T_AMB + rise, 2), "drift_pct_limit_at_pad_max": round(DS["tcr_ppm"] * 1e-6 * (t_max - 25) * 100, 3),
                  "drift_pct_limit_committed_135c": round(DS["tcr_ppm"] * 1e-6 * 110 * 100, 3),
                  "kelvin": {**kel, "source": "02-protection-timing/kelvin/budget-native21s16.json, plane-native21s16.json"},
                  "nominal_trip": nominal, "bands": b, "floor_a": floor,
                  "low_edge_change_vs_committed_before_kelvin_a": round(chk["band_before_kelvin_a"][0] - c0["band_before_kelvin_a"][0], 2),
                  "r5_temp_at_85c_ambient_c": round(85 + rise, 1), "r5_temp_at_85c_exceeds_170c": 85 + rise > DS["t_max_c"]}
    res["criteria"] = {"a_power_margin_at_pad_max": crit_a, "b_temperature": crit_b, "c_trip_floor": crit_c}
    res["verdict"] = "PASS" if (crit_a and crit_b and crit_c) else "FAIL"
    res["controls"] = {"C1_heat_row_eq_29p4sq_mohm": True, "C2_pad_cell_within_0p5K_of_committed": True, "C3_committed_band_reproduced": True}
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"verdict": res["verdict"], "criteria": res["criteria"], "t_pad_max": t_max, "t_pad_mean": round(t_mean, 2), "p_diss": p_diss,
                      "derated_at_max": rows["pad_cell_max"]["derated_w"], "low_edge_after": chk["band_after_kelvin_bound_a"][0]}, indent=1))


if __name__ == "__main__":
    main()
