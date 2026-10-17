"""T3: CR-5 true-glass band, setpoint caps, and passive C1 latch coverage.

Reuse the unmodified leak_checks and rim_limit apparatus. No board values or
firmware thresholds change. Written by a Codex cloud agent on Linux (2aea71687,
steady hazard rule); ported to the owner's peak hazard rule (2026-10-16:
`leak_checks.hazardous()`, the untripped T_c crosses 300 degC at any time) and
regenerated on the Mac.

    python3 cr5_band.py [--check] [--caps 250,200] [--jobs 5]

--check rebuilds the C library, regenerates every result and compares it with
the committed JSON by content; only the toolchain strings in TOOLCHAIN_KEYS
are exempt. --caps runs a subset (250 always runs first: it is the control
and sets the margin), for --check only. NOTES-t3.md is regenerated with the
JSON.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import leak_checks as LC  # noqa: E402
import rim_limit as RL  # noqa: E402

X, cosim, es = LC.X, LC.cosim, LC.es
# Study inputs must match this revision (within the evidence_compare platform rule for
# generated JSON): sensor-c1-integrate 68ef09729, the sources of the box (reference) evidence.
BASE = "68ef097296db106550b2f357c2fae8336784e5db"
TOOLCHAIN_KEYS = ("python", "numpy", "scipy", "compiler", "machine")
# Benign runs with a D1 LOST (a non-latching contact-loss power cut, not a
# fault) per cap, as recorded on the Mac at the port. The rim-limit
# stress-benign set had never been checked for D1 before T3; DECISIONS.md
# D-BARRIER open item 18. A ratchet: more is a failure, fewer passes.
D1_LOST_RECORDED = {200: 0, 210: 0, 220: 0, 230: 1, 240: 0, 250: 2}
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
                "d1_lost": "d1_lost" in row["first"],
                "d1_lost_first": row["first"].get("d1_lost")}
    return LC.leak_row(row) | {"seed": case["seed"], "glass_model": case.get("glass", "offset"),
                               "tau_g_s": case.get("tau_g", X.TAU_G),
                               "glass_at_first_pan_over_300_C": row["first"].get("T_c_over_300", {}).get("glass")}


def map_cases(pool, cases, band):
    return pool.map(run_one, [(c, band) for c in cases], chunksize=1)


class _Recorder:
    """Forward to the C library; log p_cmd and the D1 event of every control tick."""

    def __init__(self, lib_):
        self._lib, self.p_cmd, self.cc_event = lib_, [], []

    def __getattr__(self, name):
        return getattr(self._lib, name)

    def sim_step(self, *args):
        rc = self._lib.sim_step(*args)
        o = dict(zip(cosim.OUT, args[-1]))
        self.p_cmd.append(float(o["p_cmd"]))
        self.cc_event.append(int(o["cc_event"]))
        return rc


def replay_d1(task):
    """Re-run one benign case and measure its D1 LOST power cut (same seeds, same result)."""
    case, band = task
    X.CR5_BAND = band
    orig = LC.lib
    rec = _Recorder(orig())
    LC.lib = lambda: rec
    try:
        row = LC.run_case(case)
    finally:
        LC.lib = orig
    lost = [k for k, e in enumerate(rec.cc_event) if e == cosim.CC_EVT_LOST]
    k0 = lost[0]
    n10 = int(round(10.0 / es.DT_CTRL))
    k1 = next((k for k in range(k0, len(rec.p_cmd)) if rec.p_cmd[k] > 0.0), None)
    restored = next((k for k in range(k0, len(rec.cc_event)) if rec.cc_event[k] == cosim.CC_EVT_RESTORED), None)
    ident = {k: case[k] for k in ("set", "kind", "pan", "seed", "delta", "corner") if k in case}
    return ident | {"tau_g_s": case.get("tau_g", X.TAU_G), "glass_model": case.get("glass", "offset"),
                    "lost_events": len(lost), "first_lost_t_s": round(k0 * es.DT_CTRL, 1),
                    "first_lost": row["first"]["d1_lost"],
                    # power was being applied before the cut, so the cut is D1's, not the setpoint's
                    "p_cmd_mean_10s_before_lost_W": round(float(np.mean(rec.p_cmd[max(0, k0 - n10):k0])), 1),
                    "power_off_s": round(((k1 if k1 is not None else len(rec.p_cmd)) - k0) * es.DT_CTRL, 1),
                    "power_restored": k1 is not None,
                    "restored_event_t_s": round(restored * es.DT_CTRL, 1) if restored is not None else None,
                    "run_end_s": round(len(rec.p_cmd) * es.DT_CTRL, 1)}


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


def benign_summary(rows, cap, d1_runs):
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
            "d1_lost": sum(r["d1_lost"] for r in rows),
            "d1_lost_runs": d1_runs}


def before(row, key):
    mark = row[key]
    t300 = row["t_T_c_over_300_s"]
    return mark is not None and (t300 is None or mark["t_s"] < t300)


def coverage(rows):
    # The bar's hazard (owner, 2026-10-16): the untripped T_c crosses 300 degC at all.
    haz = [r for r in rows if LC.hazardous(r)]
    top = [r for r in haz if before(r, "glass_cr5_top")]
    low = [r for r in haz if before(r, "glass_cr5_low")]
    fw = [r for r in haz if r["latched_before_300"]]
    combined = [r for r in haz if before(r, "glass_cr5_top") or r["latched_before_300"]]
    missed = [r for r in haz if not (before(r, "glass_cr5_top") or r["latched_before_300"])]
    return {"runs": len(rows), "hazardous": len(haz), "cr5_top_before_300": len(top),
            "steady_rule_hazardous_info": sum(r["T_c_steady"] > LC.T_BAR for r in rows),
            "hazardous_settling_at_or_below_bar": sum(r["T_c_steady"] <= LC.T_BAR for r in haz),
            "cr5_low_before_300": len(low), "firmware_before_300": len(fw),
            "combined_before_300": len(combined),
            "combined_pct": round(100.0 * len(combined) / len(haz), 3) if haz else None,
            "cr5_adds_over_firmware": sum(not r["latched_before_300"] for r in top),
            "missed": len(missed), "all_hazardous_stopped": bool(haz) and not missed,
            "hazardous_steady_range_C": [min(r["T_c_steady"] for r in haz), max(r["T_c_steady"] for r in haz)] if haz else None,
            "hazardous_peak_range_C": [min(r["T_c_max"] for r in haz), max(r["T_c_max"] for r in haz)] if haz else None,
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
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def regenerate(jobs, caps=CAPS):
    hashes = input_hashes()
    # The input identity remains reproducible after this study is committed.
    # Generated evidence inputs that differ from BASE only by the platform's float
    # drift are not dirty (evidence_compare); any source byte change is.
    dirty = " ".join(EC.dirty_inputs(REPO, BASE, list(hashes)))
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
                      "machine": platform.machine(),
                      "compiler": subprocess.check_output([os.environ.get("CC", "cc"), "--version"],
                                                          text=True).splitlines()[0]},
        "assumptions": {
            "caps_C": list(CAPS), "pan_bar_C": LC.T_BAR,
            "today_band_low_top_C": list(TODAY_BAND), "band_width_K": WIDTH,
            "band_centre_definition": "arithmetic midpoint, not the nominal comparator trip",
            "band_resolution_C": 0.1,
            "control_basis": "committed leak-checks.json (hazardous, CR-5 top/low edge and firmware before 300 C) and rim-limit.json cr5[0] (benign glass maximum, margin); analytic hold envelope 245.1 C",
            "hazard_definition": "leak_checks.hazardous(): the untripped T_c crosses 300 C at any time (unrounded first crossing; owner 2026-10-16). The steady rule (last-100-s mean > 300 C) is reported as steady_rule_hazardous_info",
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
        for cap in (250,) + tuple(c for c in CAPS[:-1] if c in caps):
            init_worker(lib_path, cap)
            with Pool(jobs, initializer=init_worker, initargs=(lib_path, cap)) as pool:
                bcases = benign_cases(cap)
                brows = map_cases(pool, bcases, TODAY_BAND)
                d1_runs = pool.map(replay_d1, [(c, TODAY_BAND) for c, r in zip(bcases, brows) if r["d1_lost"]],
                                   chunksize=1)
                benign = benign_summary(brows, cap, d1_runs)
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
                    # The committed evidence is the control, read rather than restated.
                    rim0 = source_rim["cr5"][0]
                    expected = {"hazardous": source_control["hazardous_runs"],
                                "top_before_300": source_control["hazardous_cr5_band_top_edge_before_300"],
                                "low_before_300": source_control["hazardous_cr5_band_low_edge_before_300"],
                                "firmware_before_300": source_control["hazardous_latched_before_300"],
                                "hottest_benign_glass_C": rim0["benign_glass_max_C"],
                                "envelope_at_250_C": 245.1,   # the analytic hold envelope, RL.tg_max(250)
                                "reported_margin_K": rim0["benign_margin_to_band_low_K"]}
                    if list(rim0["band_C"]) != list(TODAY_BAND) or rim0["lower_by_K"] != 0.0:
                        raise RuntimeError("rim-limit.json cr5[0] is not today's band")
                    if control != expected:
                        raise RuntimeError(f"control mismatch; stopped: {control}, expected {expected}")
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
    ran = [c for c in CAPS if c in caps or c == 250]
    for cap in ran:
        c = result["caps"][str(cap)]
        result["board_owner"].append({"cap_C": cap, **{k: c["band"][k] for k in ("low_C", "centre_C", "top_C")}})
    for delta in LC.DELTAS:
        key = str(int(delta))
        result["sensitivity"][key] = [
            {"cap_C": cap, "benign_glass_bound_C": result["caps"][str(cap)]["benign"]["glass_bound_C"],
             "band": result["caps"][str(cap)]["band"],
             **{cohort: result["caps"][str(cap)][cohort]["by_offset_K"][key]
                for cohort in ("nominal", "offset_worst_corner")}}
            for cap in ran]
    result["sensitivity"]["flips"] = {
        metric: {cohort: [cap for cap in ran
                          if bool(result["caps"][str(cap)][cohort]["by_offset_K"]["12"][metric])
                          != bool(result["caps"][str(cap)][cohort]["by_offset_K"]["46"][metric])]
                 for cohort in ("nominal", "offset_worst_corner")}
        for metric in ("all_hazardous_stopped", "cr5_top_before_300", "cr5_adds_over_firmware")}
    result["caps"] = {str(cap): result["caps"][str(cap)] for cap in ran}
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
        "benign_no_firmware_latch": all(c["benign"]["firmware_latches"] == 0 for c in result["caps"].values()),
        # D1 LOST cuts power without a fault (DECISIONS.md open item 18); held at the recorded count.
        "benign_d1_lost_as_recorded": all(c["benign"]["d1_lost"] <= D1_LOST_RECORDED[c["cap_C"]]
                                          for c in result["caps"].values())}
    return result


def comparable(result, caps):
    """The evidence minus the toolchain strings, restricted to the caps that ran."""
    r = json.loads(json.dumps(result, allow_nan=False))
    for k in TOOLCHAIN_KEYS:
        r["apparatus"].pop(k, None)
    keep = sorted(set(caps) | {250})
    if keep != sorted(CAPS):
        # Aggregates over every cap only exist in a full run.
        r["caps"] = {k: v for k, v in r["caps"].items() if int(k) in keep}
        r["board_owner"] = [b for b in r["board_owner"] if b["cap_C"] in keep]
        for key, rows in list(r["sensitivity"].items()):
            if key == "flips":
                continue
            r["sensitivity"][key] = [x for x in rows if x["cap_C"] in keep]
        for key in ("flips",):
            r["sensitivity"].pop(key, None)
        r["apparatus"].pop("simulations", None)
        r.pop("gate", None)
    return r


def _row(cap, c):
    return (f"| {cap} | {c['hazardous']} | {c['cr5_top_before_300']} | {c['cr5_low_before_300']} | "
            f"{c['firmware_before_300']} | {c['combined_before_300']} ({c['combined_pct']}%) | "
            f"{c['cr5_adds_over_firmware']} | {c['missed']} |")


def notes(result):
    """NOTES-t3.md, every number from the regenerated JSON."""
    caps = [int(k) for k in result["caps"]]
    ctl = result["control"]
    head = "| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |\n|---|---|---|---|---|---|---|---|"
    L = ["# T3 — CR-5 band with a setpoint cap", "",
         "A model study, not a board change. `cr5_band.py` imports `firmware/leak_checks.py`, `firmware/rim_limit.py` "
         "and their benign generators and rebuilds the unchanged C apparatus with `firmware/build_lib.sh`. It changes "
         "no firmware, no existing study and nothing in zapote/controller, and computes no resistor values. Every number "
         "below is regenerated into `cr5-band.json`; dotted paths are its keys.", "",
         "**Hazard rule.** A leak run is hazardous when its untripped pan-centre temperature crosses 300 °C at any time "
         "(`leak_checks.hazardous()`, owner 2026-10-16). The cloud run used the steady rule (final-100-s mean > 300 °C); "
         "each coverage row keeps that count as `steady_rule_hazardous_info`, and `hazardous_settling_at_or_below_bar` "
         "counts the hazardous runs that only overshoot.", "",
         "## Reproduce", "",
         "Evidence reference platform: the remote box (linux x86_64; `reference_platform` in the JSON). Regenerate "
         "there; elsewhere `--check` compares counts, flags and gates exactly and floats within "
         "`../evidence_compare.py`'s tolerance (DECISIONS.md D-EVPLAT).", "",
         "```sh", "cd output/temper-sensor-r3/leak-barrier",
         "python3 cr5_band.py --check --caps 250,200   # run.sh step 5e (caps 250 and 200)",
         "python3 cr5_band.py --check                  # every cap (manual; see run.sh header)",
         "python3 cr5_band.py --jobs 8                 # regenerate cr5-band.json and this file (on the box)", "```", "",
         "`--check` compares by content; only the toolchain strings in `TOOLCHAIN_KEYS` are exempt, and off the "
         "reference platform floats follow `evidence_compare.py`. "
         f"A full run is {result['apparatus'].get('simulations', 'n/a')} simulations (`apparatus.simulations`). "
         "`T3 PASS` means the control, input-identity, band-margin and benign gates pass; it does not mean the bar is met.", "",
         "## Control (cap 250 °C, today's band)", "",
         f"Reproduced from the committed evidence (`control`, `control.expected`): {ctl['hazardous']} hazardous runs, "
         f"{ctl['top_before_300']} reach the band top and {ctl['low_before_300']} the band low edge before the bar, "
         f"{ctl['firmware_before_300']} are latched by firmware before the bar; hottest simulated benign glass "
         f"{ctl['hottest_benign_glass_C']} °C, analytic hold envelope {ctl['envelope_at_250_C']} °C, margin "
         f"{ctl['reported_margin_K']} K (full precision {ctl['margin_to_benign_bound_K']} K).", "",
         "## Board-owner table", "",
         "Glass temperatures. Centre is the band midpoint, not a comparator threshold. A proposed band position, not a "
         "resistor or a released circuit (`board_owner`, `caps.<cap>.benign.glass_bound_C`).", "",
         "| Cap °C | Hottest benign bound °C | Low °C | Centre °C | Top °C |", "|---|---|---|---|---|"]
    for b in result["board_owner"]:
        L.append(f"| {b['cap_C']} | {result['caps'][str(b['cap_C'])]['benign']['glass_bound_C']:.3f} | "
                 f"{b['low_C']} | {b['centre_C']} | {b['top_C']} |")
    L += ["", "## Coverage before the bar", "",
          "Counts are hazardous runs stopped before the first pan crossing: the CR-5 top edge (a guaranteed trip), "
          "the low edge (possible only, never credited), any firmware latch, and top OR firmware. **CR-5 adds** is the "
          "number of runs the band top reaches before the bar that firmware had not already latched before the bar.", "",
          "**Nominal sensing, both glass-offset endpoints** (`caps.<cap>.nominal.all`):", "", head]
    L += [_row(c, result["caps"][str(c)]["nominal"]["all"]) for c in caps]
    L += ["", "**Cold stack, high rail, slow glass** (`caps.<cap>.worst_corner.all`, both glass geometries pooled):", "", head]
    L += [_row(c, result["caps"][str(c)]["worst_corner"]["all"]) for c in caps]
    L += ["", "By glass geometry (`caps.<cap>.worst_corner.by_glass.<geometry>`):", "",
          "| Cap °C | Geometry | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in caps:
        for g, v in result["caps"][str(c)]["worst_corner"]["by_glass"].items():
            L.append(_row(c, v).replace(f"| {c} |", f"| {c} | {g} |", 1))
    adds = {c: (result["caps"][str(c)]["nominal"]["all"]["cr5_adds_over_firmware"],
                result["caps"][str(c)]["worst_corner"]["all"]["cr5_adds_over_firmware"],
                result["caps"][str(c)]["offset_worst_corner"]["all"]["cr5_adds_over_firmware"]) for c in caps}
    zero = all(sum(v) == 0 for v in adds.values())
    L += ["", "**Headline: what a retuned CR-5 band adds over firmware.** " + (
        "Zero at every cap in every cohort: each hazardous run whose glass reaches the band top before the bar is one "
        "firmware had already latched before the bar. Lowering the band with a cap buys no timing coverage in this model; "
        "CR-5 keeps its role as the independent hardware trip if the MCU fails." if zero else
        "Not zero everywhere: " + "; ".join(f"{c} °C nominal/worst/offset-worst {a}" for c, a in adds.items()) + "."),
          "", "Per cap, nominal / worst corner / offset worst corner: " +
          ", ".join(f"{c} °C {a[0]}/{a[1]}/{a[2]}" for c, a in adds.items()) +
          " (`caps.<cap>.<cohort>.all.cr5_adds_over_firmware`).", "",
          "Hazardous runs that only overshoot (settle at or below 300 °C), nominal / worst corner: " +
          ", ".join(f"{c} °C {result['caps'][str(c)]['nominal']['all']['hazardous_settling_at_or_below_bar']}/"
                    f"{result['caps'][str(c)]['worst_corner']['all']['hazardous_settling_at_or_below_bar']}" for c in caps) +
          " (`hazardous_settling_at_or_below_bar`).", "",
          "## Glass-offset sensitivity", "",
          "Same band as the board table; the offset is a bench item (`sensitivity.<offset>[]`).", ""]
    for d in ("12", "46"):
        L += [f"**Offset {d} K, nominal sensing:**", "", head]
        L += [_row(x["cap_C"], x["nominal"]["all"] if "all" in x["nominal"] else x["nominal"]) for x in result["sensitivity"][d]]
        L += ["", f"**Offset {d} K, cold stack and slow glass:**", "", head]
        L += [_row(x["cap_C"], x["offset_worst_corner"]["all"] if "all" in x["offset_worst_corner"] else x["offset_worst_corner"])
              for x in result["sensitivity"][d]]
        L.append("")
    if "flips" in result["sensitivity"]:
        L += ["Conclusions that flip between the 12 K and 46 K endpoints (`sensitivity.flips`): " +
              "; ".join(f"`{m}` nominal {v['nominal'] or 'none'}, offset worst corner {v['offset_worst_corner'] or 'none'}"
                        for m, v in result["sensitivity"]["flips"].items()) + ".", ""]
    L += ["## Benign runs: no false latch, but D1 power cuts", "",
          "Benign sets: the leak sweep's 548 and the rim study's stress set, commands capped "
          "(`caps.<cap>.benign.by_set`). Firmware latches: " +
          ", ".join(f"{c} °C {result['caps'][str(c)]['benign']['firmware_latches']}" for c in caps) +
          " (`caps.<cap>.benign.firmware_latches`, gated at zero). D1 LOST runs: " +
          ", ".join(f"{c} °C {result['caps'][str(c)]['benign']['d1_lost']}" for c in caps) +
          " (`caps.<cap>.benign.d1_lost`). D1 LOST is the contact check classifying the pan as lifted: it cuts power "
          "without a fault until a retry probe passes. No existing gate measured it on the stress set; it is held at the "
          "recorded count (`gate.benign_d1_lost_as_recorded`) and is DECISIONS.md D-BARRIER open item 18.", "",
          "| Cap °C | Set | Kind | Pan | Seed | Corner | τ_g s | LOST at s | Mean power 10 s before W | Power off s | Restored | LOST events |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in caps:
        for r in result["caps"][str(c)]["benign"]["d1_lost_runs"]:
            L.append(f"| {c} | {r['set']} | {r['kind']} | {r['pan']} | {r['seed']} | {r.get('corner')} | {r['tau_g_s']} | "
                     f"{r['first_lost_t_s']} | {r['p_cmd_mean_10s_before_lost_W']} | {r['power_off_s']} | {r['power_restored']} | {r['lost_events']} |")
    L += ["", "Power off is measured by replaying the case with the controller output logged: the time from the first "
          "LOST tick until p_cmd is next above zero (`caps.<cap>.benign.d1_lost_runs[]`).", "",
          "## Interpretation", "",
          "The hardware band is expressed in true glass temperature; its spread already includes comparator/NTC "
          "tolerances and self-heating. The software rim tolerance table is a reading error and is carried only "
          "through the firmware comparison, so it is not counted twice. The benign bound is the larger of the analytic "
          "hold envelope and the hottest simulated benign glass at that cap; each lower band keeps today's actual "
          "low-edge margin and today's width.", "",
          "\"Stopped before the bar\" means the band top is reached, or a firmware latch is recorded, strictly before "
          "the first pan crossing, with an ideal immediate cut: comparator and power-cut delay, stored heat and post-cut "
          "rise are not modelled. Cold soak gets no credit here because these leaks start mid-cook. Cohorts have "
          "different case counts and sensor parameters (`assumptions.cohorts`); compare trends within a cohort.", "",
          "## Provenance and bench work", "",
          "Written by a Codex cloud agent on Linux (2aea71687, steady rule); its unchanged script was rerun on the Mac "
          "for the cross-platform comparison recorded in the port's commit message, then ported to the peak rule and "
          "regenerated here. Glass offset and lag, mounting and warp, bead and rail errors, comparator spread at a "
          "shifted band and the full sensing-to-power-off path remain bench items. The insulation, production-test and "
          "qualification requirements (`SPEC.md`, D-BARRIER) carry the bar.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="regenerate without writing; fail on an evidence difference (toolchain strings excepted; cross-platform floats within evidence_compare's rule)")
    ap.add_argument("--caps", default=",".join(str(c) for c in CAPS),
                    help="comma-separated subset of caps (250 always runs); --check only")
    ap.add_argument("--out", type=Path, default=HERE / "cr5-band.json")
    ap.add_argument("--jobs", type=int, default=min(5, os.cpu_count() or 1))
    args = ap.parse_args()
    try:
        if args.jobs < 1:
            raise ValueError("--jobs must be positive")
        caps = sorted({int(c) for c in args.caps.split(",")} | {250})
        if not set(caps) <= set(CAPS):
            raise ValueError(f"--caps must be drawn from {CAPS}")
        if not args.check and caps != sorted(CAPS):
            raise ValueError("a subset of caps is for --check only; regenerate with every cap")
        result = regenerate(args.jobs, caps)
        if args.check:
            committed = json.loads(args.out.read_text())
            res = EC.compare(comparable(committed, caps), comparable(EC.stamp(result), caps), name=args.out.name)
            for o in res.outliers if res.ok else []:
                print(f"T3: allowed cross-platform outlier {o}")
            if not res.ok:
                print("T3 differences:\n  " + "\n  ".join(res.diffs[:20]))
                cand = Path(tempfile.gettempdir()) / f"temper-t3-regenerated-{os.getpid()}.json"
                cand.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
                raise RuntimeError(f"regenerated JSON differs from {args.out}; candidate saved to {cand}")
        else:
            args.out.write_text(json.dumps(EC.stamp(result), indent=1, allow_nan=False) + "\n")
            if args.out == HERE / "cr5-band.json":
                (HERE / "NOTES-t3.md").write_text(notes(result))
        failed = [k for k, v in result["gate"].items() if not v]
        if failed:
            raise RuntimeError("gates failed: " + ", ".join(failed))
    except Exception as e:
        print(f"T3 FAIL: {e}")
        return 1
    print("T3 PASS" + ("" if caps == sorted(CAPS) else f" (caps {','.join(map(str, caps))})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
