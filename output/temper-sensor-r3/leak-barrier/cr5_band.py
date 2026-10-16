"""T3: CR-5 true-glass band, setpoint caps, and passive C1 latch coverage.

Reuse the unmodified leak_checks and rim_limit apparatus. No board values or
firmware thresholds change. --check rebuilds the C library and regenerates
every result before comparing the complete JSON with the committed bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import scipy

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FW = HERE.parent / "firmware"
REPO = HERE.parents[2]
sys.path.insert(0, str(FW))
import leak_checks as LC  # noqa: E402
import rim_limit as RL  # noqa: E402

X, cosim, es = LC.X, LC.cosim, LC.es
BASE = "87edb1b329a39ffff54c4cc13e6a2bbac7f0c0e4"
CAPS = tuple(range(200, 251, 10))
TODAY_BAND = X.CR5_BAND
WIDTH = round(TODAY_BAND[1] - TODAY_BAND[0], 1)
PAN_SETPOINTS = {k: tuple(v["sp"]) for k, v in es.PANS.items()}


def init_worker(lib_path, cap):
    cosim.LIB_PATH, cosim.LIB = lib_path, None
    LC.SP_FRY = cap
    X.CORNERS["nominal"] = (1.0, 1.0)
    for pan, sp in PAN_SETPOINTS.items():
        es.PANS[pan]["sp"] = tuple(min(v, cap) for v in sp)


def run_one(task):
    case, band = task
    X.CR5_BAND = band
    row = LC.run_case(case)
    if "trace" in row:
        trace = row.pop("trace")
        return {"set": case["set"], "kind": case["kind"], "pan": case["pan"],
                "seed": case["seed"], "initial_glass_C": float(case.get("glass0", es.T_AMB)),
                "glass_max_C": max(float(np.max(trace[:, 7])), float(case.get("glass0", es.T_AMB))),
                "firmware_latch": any(k in row["first"] for k in LC.LATCHES),
                "d1_lost": "d1_lost" in row["first"]}
    return LC.leak_row(row) | {"seed": case["seed"], "glass_model": case.get("glass", "offset"),
                               "tau_g_s": case.get("tau_g", X.TAU_G),
                               "glass_at_first_pan_over_300_C": row["first"].get("T_c_over_300", {}).get("glass")}


def map_cases(pool, cases, band):
    return pool.map(run_one, [(c, band) for c in cases], chunksize=1)


def benign_cases(cap):
    # Keep LC's fixed warm-glass starts. Only RL's envelope-derived start
    # scales with the cap, just as its hold and preheated-pan commands do.
    initial_max = round(float(RL.tg_max(cap)), 1)
    cases = [dict(c, set="benign/" + c["set"]) for c in LC.benign_cases(LC.N_SEEDS)]
    stress = RL.stress_benign()
    for c in stress:
        if c["kind"] == "hot_glass":
            c["glass0"] = initial_max
    cases += stress
    for c in cases:
        if "t_hot" in c:
            c["t_hot"] = min(c["t_hot"], cap)
        if "sp_profile" in c:
            c["sp_profile"] = [(t, min(sp, cap)) for t, sp in c["sp_profile"]]
        c["trace_dt"] = es.DT_CTRL
    return cases


def benign_summary(rows, cap):
    hottest = max(rows, key=lambda r: r["glass_max_C"])
    envelope = float(RL.tg_max(cap))
    maximum = max(envelope, hottest["glass_max_C"])
    # Keep the actual transient maximum; the hold envelope alone misses it.
    bound = math.ceil((maximum - 1e-9) * 1e6) / 1e6
    return {"runs": len(rows), "by_set": {s: sum(r["set"] == s for r in rows)
                                          for s in sorted({r["set"] for r in rows})},
            "envelope_glass_C": round(envelope, 6),
            "simulated_glass_max_C": round(hottest["glass_max_C"], 6),
            "hottest_case": hottest,
            "glass_bound_C": bound,
            "rim_hot_tolerance_K": round(float(RL.tol_at(envelope)), 6),
            "rim_reading_limit_C": round(float(envelope + RL.tol_at(envelope)), 6),
            "firmware_latches": sum(r["firmware_latch"] for r in rows),
            "d1_lost": sum(r["d1_lost"] for r in rows)}


def before(row, key):
    mark = row[key]
    t300 = row["t_T_c_over_300_s"]
    return mark is not None and (t300 is None or mark["t_s"] < t300)


def coverage(rows):
    haz = [r for r in rows if r["T_c_steady"] > LC.T_BAR]
    top = [r for r in haz if before(r, "glass_cr5_top")]
    low = [r for r in haz if before(r, "glass_cr5_low")]
    fw = [r for r in haz if r["latched_before_300"]]
    combined = [r for r in haz if before(r, "glass_cr5_top") or r["latched_before_300"]]
    missed = [r for r in haz if not (before(r, "glass_cr5_top") or r["latched_before_300"])]
    return {"runs": len(rows), "hazardous": len(haz), "cr5_top_before_300": len(top),
            "not_steady_hazard_but_crossed_300": sum(r["T_c_steady"] <= LC.T_BAR
                                                     and r["t_T_c_over_300_s"] is not None for r in rows),
            "cr5_low_before_300": len(low), "firmware_before_300": len(fw),
            "combined_before_300": len(combined),
            "combined_pct": round(100.0 * len(combined) / len(haz), 3) if haz else None,
            "cr5_adds_over_firmware": sum(not r["latched_before_300"] for r in top),
            "missed": len(missed), "all_hazardous_stopped": bool(haz) and not missed,
            "hazardous_steady_range_C": [min(r["T_c_steady"] for r in haz), max(r["T_c_steady"] for r in haz)] if haz else None,
            "missed_by_onset": {o: sum(r["onset"] == o for r in missed) for o in LC.ONSETS},
            "missed_example": missed[0] if missed else None}


def cohort_summary(rows):
    return {"all": coverage(rows),
            "by_offset_K": {str(int(d)): coverage([r for r in rows if r["delta"] == d])
                            for d in LC.DELTAS},
            "by_onset": {o: coverage([r for r in rows if r["onset"] == o]) for o in LC.ONSETS}}


def input_hashes():
    paths = set()
    for folder in (REPO / "firmware/components/control", REPO / "firmware/components/sensors"):
        paths.update(folder.rglob("*.c"))
        paths.update(folder.rglob("*.h"))
    paths.add(REPO / "firmware/config.h")
    paths.update(FW / p for p in ("build_lib.sh", "cosim_shim.c", "cosim.py", "ref.py",
                                "leak_checks.py", "rim_limit.py", "xcheck_cosim.py", "rim_ntc.py"))
    paths.update(HERE.parent / p for p in ("screen.py", "contact_model.py", "robustness/shift_kf.py",
                                         "cad/thermal-axisym.json"))
    paths.add(HERE.parent.parent / "temper-sensor-r2/estimator_study.py")
    paths.update(FW / p for p in ("leak-checks.json", "rim-limit.json"))
    paths.update(FW / p for p in ("README.md", "DECISIONS.md"))
    paths.add(HERE.parent / "pcb/DECISIONS.md")
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def regenerate(jobs):
    hashes = input_hashes()
    # The input identity remains reproducible after this study is committed.
    dirty = subprocess.check_output(["git", "diff", "--name-only", BASE, "--", *hashes],
                                    cwd=REPO, text=True).strip()
    if dirty:
        raise RuntimeError("study inputs differ from the requested base: " + dirty)
    source_control = json.loads((FW / "leak-checks.json").read_text())["summary"]["leak"]["all_onsets"]
    source_rim = json.loads((FW / "rim-limit.json").read_text())
    result = {
        "scope": __doc__.strip(),
        "apparatus": {"base_commit": BASE, "input_tree_dirty": False,
                      "input_sha256": hashes,
                      "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                      "compiler": subprocess.check_output([os.environ.get("CC", "cc"), "--version"],
                                                          text=True).splitlines()[0]},
        "assumptions": {
            "caps_C": list(CAPS), "pan_bar_C": LC.T_BAR,
            "today_band_low_top_C": list(TODAY_BAND), "band_width_K": WIDTH,
            "band_centre_definition": "arithmetic midpoint, not the nominal comparator trip",
            "band_resolution_C": 0.1,
            "control_basis": "committed simulated benign maximum 246.5 C and reported margin 15.8 K; analytic hold envelope reported separately at 245.1 C",
            "hazard_definition": "LC.run_case untripped last-100-s mean T_c rounded to 0.1 C > 300 C",
            "stopped_definition": "passive latch or true glass crossing strictly before first T_c > 300; ideal immediate cut, no cooldown or stored-energy model",
            "cold_soak": "not credited: these leaks start during the cook at LC.LEAK_AT",
            "tolerance": {"bead_at_250_K": RL.PCB_BEAD_250_K, "hot_rail_mV": RL.RAIL_LO_MV,
                          "cold_rail_mV": X.STACKS["cold_stack"][1], "hot_self_heat_K": RL.SELF_HEAT_K,
                          "nominal_rail_mV": 3300.0, "nominal_self_heat_K": 0.0,
                          "cold_self_heat_K": X.STACKS["cold_stack"][2],
                          "tol_T_C": list(RL.TOL_T), "tol_K": RL.TOL_K,
                          "cr5_self_heat_already_in_band_K": 1.7},
            "glass": {"w_hi": RL.W_HI, "w_lo": RL.W_LO, "w_lo_hot": RL.W_LO_HOT,
                      "eye_hi_C": RL.T_EYE_HI, "eye_lo_C": RL.T_EYE_LO,
                      "offset_ends_K": list(LC.DELTAS), "benign_tau_s": list(RL.TAU_GS)},
            "cohorts": {
                "control_sweep": "LC.leak_cases at cap 250: original offsets 12/46 K, hot/cold bead, tau 60 s, rail 3300 mV",
                "nominal": "same cases/seeds as sweep hot-bead slots, bead R25/B nominal, rail 3300 mV, tau 60 s; both offsets",
                "worst_corner": "RL.stress_leak: envelope and flat cool-eye glass, cold bead + rail 3367 mV, tau 106 s",
                "offset_worst_corner": "same cases/seeds as sweep cold-bead slots, fixed offset 12 or 46 K, cold bead + rail 3367 mV, tau 106 s"},
            "commands": "all es.PANS setpoints clamped at cap; LC.SP_FRY=cap; water retains 90/100 C",
            "original_pan_setpoints_C": {p: list(sp) for p, sp in PAN_SETPOINTS.items()},
            "setpoint_step_s": es.SP_STEP_T,
            "benign_initial_glass": "LC fixed starts retained, including 200 C glass; RL hot_glass reset to rounded Tg_max(cap); benign maxima include initial Tg",
            "sampling": {"control_dt_s": es.DT_CTRL, "truth_dt_s": es.DT_SIM,
                         "benign_trace_dt_s": es.DT_CTRL, "leak_crossings": "LC marks every control tick"},
            "leak_onset_s": LC.LEAK_AT, "leak_end_s": LC.T_END_LEAK,
            "r_leak_ohm": [round(r, 6) for r in LC.R_LEAKS]},
        "control": {}, "caps": {}, "sensitivity": {}, "board_owner": [],
    }
    margin = None
    with tempfile.TemporaryDirectory(prefix="temper-t3-") as tmp:
        lib_path = subprocess.check_output([str(FW / "build_lib.sh"), tmp], text=True).strip()
        for cap in (250,) + CAPS[:-1]:
            init_worker(lib_path, cap)
            with Pool(jobs, initializer=init_worker, initargs=(lib_path, cap)) as pool:
                benign = benign_summary(map_cases(pool, benign_cases(cap), TODAY_BAND), cap)
                if cap == 250:
                    band = TODAY_BAND
                else:
                    low = math.ceil((benign["glass_bound_C"] + margin - 1e-8) * 10.0) / 10.0
                    band = (low, round(low + WIDTH, 1))
                print(f"cap {cap}: benign {benign['glass_bound_C']:.1f} C; band {band}", flush=True)
                sweep_cases = LC.leak_cases()
                if cap == 250:
                    sweep = map_cases(pool, sweep_cases, band)
                    score = coverage(sweep)
                    control = {"hazardous": score["hazardous"], "top_before_300": score["cr5_top_before_300"],
                               "low_before_300": score["cr5_low_before_300"],
                               "firmware_before_300": score["firmware_before_300"],
                               "hottest_benign_glass_C": round(benign["simulated_glass_max_C"], 1),
                               "envelope_at_250_C": round(benign["envelope_glass_C"], 1),
                               "reported_margin_K": round(TODAY_BAND[0] - round(benign["simulated_glass_max_C"], 1), 1)}
                    expected = {"hazardous": 235, "top_before_300": 0, "low_before_300": 13,
                                "firmware_before_300": 59, "hottest_benign_glass_C": 246.5,
                                "envelope_at_250_C": 245.1, "reported_margin_K": 15.8}
                    if control != expected:
                        raise RuntimeError(f"control mismatch; stopped: {control}, expected {expected}")
                    if (source_control["hazardous_runs"], source_control["hazardous_cr5_band_top_edge_before_300"],
                        source_control["hazardous_cr5_band_low_edge_before_300"]) != (235, 0, 13):
                        raise RuntimeError("committed leak control does not match requested control")
                    if source_rim["cr5"][0]["benign_glass_max_C"] != control["hottest_benign_glass_C"]:
                        raise RuntimeError("committed benign control does not match regenerated control")
                    margin = round(TODAY_BAND[0] - benign["glass_bound_C"], 6)
                    result["control"] = control | {"expected": expected, "reproduced": True,
                                                   "margin_to_benign_bound_K": margin,
                                                   "sweep": cohort_summary(sweep)}
                    print("control reproduced", control, flush=True)
                nominal_cases = [dict(c, corner="nominal") for c in sweep_cases if c["corner"] == "hot"]
                worst_cases = RL.stress_leak()
                offset_worst_cases = [dict(c, corner="cold_stack", tau_g=max(RL.TAU_GS))
                                      for c in sweep_cases if c["corner"] == "cold"]
                extra = map_cases(pool, nominal_cases + worst_cases + offset_worst_cases, band)
                n, w = len(nominal_cases), len(worst_cases)
                nominal, worst, offset_worst = extra[:n], extra[n:n + w], extra[n + w:]
            result["caps"][str(cap)] = {
                "cap_C": cap, "benign": benign,
                "band": {"low_C": band[0], "centre_C": round(sum(band) / 2.0, 1), "top_C": band[1],
                         "width_K": WIDTH, "required_margin_K": margin,
                         "margin_to_benign_bound_K": round(band[0] - benign["glass_bound_C"], 6),
                         "benign_hardware_trips": 0 if benign["simulated_glass_max_C"] < band[0] else 1},
                "nominal": cohort_summary(nominal),
                "worst_corner": {"all": coverage(worst),
                                 "by_glass": {g: coverage([r for r in worst if r["glass_model"] == g])
                                              for g in sorted({r["glass_model"] for r in worst})}},
                "offset_worst_corner": cohort_summary(offset_worst)}
            sn, sw = coverage(nominal), coverage(worst)
            print(f"cap {cap}: nominal top {sn['cr5_top_before_300']}/{sn['hazardous']} "
                  f"low {sn['cr5_low_before_300']} combined {sn['combined_pct']}%; "
                  f"worst top {sw['cr5_top_before_300']}/{sw['hazardous']} "
                  f"low {sw['cr5_low_before_300']} combined {sw['combined_pct']}%", flush=True)
    for cap in CAPS:
        c = result["caps"][str(cap)]
        result["board_owner"].append({"cap_C": cap, **{k: c["band"][k] for k in ("low_C", "centre_C", "top_C")}})
    for delta in LC.DELTAS:
        key = str(int(delta))
        result["sensitivity"][key] = [
            {"cap_C": cap, "benign_glass_bound_C": result["caps"][str(cap)]["benign"]["glass_bound_C"],
             "band": result["caps"][str(cap)]["band"],
             **{cohort: result["caps"][str(cap)][cohort]["by_offset_K"][key]
                for cohort in ("nominal", "offset_worst_corner")}}
            for cap in CAPS]
    result["sensitivity"]["flips"] = {
        metric: {cohort: [cap for cap in CAPS
                          if bool(result["caps"][str(cap)][cohort]["by_offset_K"]["12"][metric])
                          != bool(result["caps"][str(cap)][cohort]["by_offset_K"]["46"][metric])]
                 for cohort in ("nominal", "offset_worst_corner")}
        for metric in ("all_hazardous_stopped", "cr5_top_before_300", "cr5_adds_over_firmware")}
    result["caps"] = {str(cap): result["caps"][str(cap)] for cap in CAPS}
    result["apparatus"]["simulations"] = result["control"]["sweep"]["all"]["runs"] + sum(
        c["benign"]["runs"] + sum(c[k]["all"]["runs"] for k in ("nominal", "worst_corner", "offset_worst_corner"))
        for c in result["caps"].values())
    result["gate"] = {
        "control_reproduced": result["control"]["reproduced"],
        "inputs_unchanged": input_hashes() == hashes,
        "width_and_minimum_margin_preserved": all(c["band"]["width_K"] == WIDTH
                                         and c["band"]["required_margin_K"] == margin
                                         and math.isclose(c["band"]["top_C"] - c["band"]["low_C"], WIDTH, abs_tol=1e-8)
                                         and c["band"]["margin_to_benign_bound_K"] >= margin - 1e-6
                                         and c["band"]["margin_to_benign_bound_K"] < margin + 0.1 + 1e-6
                                         and c["band"]["centre_C"] == round((c["band"]["low_C"] + c["band"]["top_C"]) / 2, 1)
                                         for c in result["caps"].values()),
        "benign_no_hardware_trip": all(not c["band"]["benign_hardware_trips"] for c in result["caps"].values()),
        "benign_no_firmware_latch_or_d1_lost": all(c["benign"]["firmware_latches"] == 0
                                                  and c["benign"]["d1_lost"] == 0 for c in result["caps"].values())}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="regenerate without writing and compare exact JSON")
    ap.add_argument("--out", type=Path, default=HERE / "cr5-band.json")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    args = ap.parse_args()
    try:
        if args.jobs < 1:
            raise ValueError("--jobs must be positive")
        result = regenerate(args.jobs)
        data = json.dumps(result, indent=1, allow_nan=False) + "\n"
        if args.check:
            if not args.out.exists() or args.out.read_text() != data:
                raise RuntimeError("regenerated JSON differs from " + str(args.out))
        else:
            args.out.write_text(data)
        if not all(result["gate"].values()):
            raise RuntimeError("gates failed: " + str(result["gate"]))
    except Exception as e:
        print(f"T3 FAIL: {e}")
        return 1
    print("T3 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
