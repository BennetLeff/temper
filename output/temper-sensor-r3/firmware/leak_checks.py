"""DECISIONS.md D-LEAK, D-RIMLIM: element-parallel Pt100 leakage against the firmware's leak checks.

A leakage resistance R_leak in parallel with the Pt100 element reads low and is
electrically invisible to the MAX31865 (pcb/DECISIONS.md D6). The loop then
holds the reading at the setpoint and the pan runs hot. The C1 leak check
(components/control/pan_leak_check.c, through the cosim shim) latches
FAULT_PROBE_LEAKAGE after `cycles` (2) consecutive cross-check suspect ->
PROBE_PASSED cycles, each suspect within gap_s (120 s) of the previous, with
the rim reading not more than rim_fall_k (5 K) lower and the Pt100 reading
not more than pt_rise_k (2 K) higher than at the previous suspect. The
setpoint-relative rim limit (components/control/pan_rim_limit.c, D-RIMLIM)
latches the same fault when the rim is above the glass envelope of
max(setpoint, t_hat) plus the rim's hot tolerance stack, not falling, for 5 s;
it runs passively here too ("rim_limit").

The plant and loop are xcheck_cosim.py's (GlassTruth: glass under the rim NTC
a 60 s lag toward T_c - delta; the rim NTC through the firmware driver at a
bead tolerance corner; the C loop, D1, the supervisor; gain mode
id_measured). Every rule is passive here: the leak latch, the rim NTC's
over-range fault (an existing latch, PROBE_SHORT through the RTD sink) and the
supervisor latches are recorded, not acted on, so the steady pan temperature
is the untripped one and each rule's first time is measured on the same
trajectory. Supervisor stage 1 (non-latching) and D1 (LOST zeroes the power)
act as in the firmware. After a rim fault the loop's rim input falls back to
the reading (main/pan_control.c loop_rim_input), as on the device. The CR-5
hardware rim trip (pcb/DECISIONS.md D6, band 262.3-288.1 degC on the glass)
is outside the firmware and only reported: when the glass first reaches the
band's low and top edges.

Leak sweep: R_leak = 13 log-spaced values 300 ohm .. 10 kohm from t = 250 s
(in the sp1 hold), with three onsets: a step (a sudden breakdown) and the
leak conductance growing linearly from 0 over 120 s and over 600 s (ingress).
The onset changes what the loop and D1 see on the way, not the steady state.
Each onset runs 4 pans x glass delta {12, 46} K x bead corner {hot, cold}.
The frying pans' final setpoint is 250 degC (the highest a user can set), the
water pot keeps its own (100 degC). 1800 s runs; steady T_c = the mean of the
last 100 s.

The bar (owner, D-LEAK): every leak whose untripped steady T_c exceeds
300 degC must latch (the leak check or any existing latch) before T_c first
exceeds 300 degC. The script evaluates it and records the result; it is not
met (D-LEAK gives the numbers and the physical reason) and the gate holds the
recorded status, so a change either way fails the run until DECISIONS.md is
updated (EXPECTED_BAR); the coverage with the rim limit may not fall below the
recorded EXPECTED_BEFORE_300_MIN, nor any hazardous leak go unlatched.

Benign (gated: 0 leak latches, and no other latch or D1 lost):
xcheck_cosim.py's 28 benign runs, and
b5_montecarlo.py's nominal / food / probe-on-intact-contact kinds routed
through the glass and rim model over N_SEEDS seeds at both deltas and
corners, plus kinds that put the reading below a hot rim without a leak:
food_batches (the cooked food replaced by a fresh cold batch every 120 s,
three batches: the benign case closest to a leak's repeated cross-check
cycles), hot_glass (a cold pan placed on glass left at 200 degC) and sp_down (the
setpoint lowered by 60 K at 450 s, the glass lagging the cooling pan).

Writes leak-checks.json. Run: python3 leak_checks.py [--lib path]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cosim  # noqa: E402
import ref  # noqa: E402
import xcheck_cosim as X  # noqa: E402
from ref import es, screen  # noqa: E402

R_LEAKS = tuple(float(r) for r in np.geomspace(300.0, 10000.0, 13))
DELTAS = (12.0, 46.0)
CORNERS = ("hot", "cold")
LEAK_AT = 250.0
# leak onsets: a step (sudden breakdown) and conductance ramps (ingress)
ONSETS = {"step": 0.0, "ramp120": 120.0, "ramp600": 600.0}
T_END_LEAK = 1800.0
SP_FRY = 250.0
T_BAR = 300.0
N_SEEDS = 5
# food_batches: fresh cold batches after the first (s after it): batch searing,
# the benign case closest to a leak's repeated cross-check cycles.
BATCH_GAPS_S = (120.0, 240.0)
EXPECTED_BAR = "not_met"
# D-RIMLIM: the recorded coverage with the setpoint-relative rim limit in the
# loop. A drop fails the run; a gain is reported (update DECISIONS.md).
EXPECTED_BEFORE_300_MIN = 59
EXPECTED_NEVER_MAX = 0
# production hot calibration point (D-LEAK requirement 2): acceptance, K
HOT_CHECK_K = 0.5


def lib():
    L = X.lib()
    if not hasattr(L, "_plc_ready"):
        L.plc_start.argtypes = [ctypes.c_void_p]
        L.plc_start.restype = ctypes.c_int
        L.plc_run.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double]
        L.plc_run.restype = ctypes.c_int
        L.prl_start.argtypes = [ctypes.c_void_p]
        L.prl_start.restype = ctypes.c_int
        L.prl_run.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_int, ctypes.c_double]
        L.prl_run.restype = ctypes.c_int
        L._plc_ready = True
    return L


def run_case(case):
    L_ = lib()
    screen.apply(ref.C1)
    pan = es.PANS[case["pan"]]
    tr = X.GlassTruth(pan, case["h"], 0.82, case["seed"], food_at=case.get("food_at"), delta=case["delta"],
                      tau_g=case.get("tau_g", X.TAU_G), glass_w=case.get("glass_w"), t_eye=case.get("t_eye"),
                      T_hot=case.get("t_hot"))
    if case.get("glass0") is not None:
        tr.Tg = case["glass0"]
    rng = np.random.default_rng(case["seed"] + 1)
    sp1, sp2 = pan["sp"]
    if case.get("sp2") is not None:
        sp2 = case["sp2"]
    t_end = case.get("t_end", es.T_END)
    h = L_.sim_new()
    for key, v in cosim.FW_K.items():
        assert L_.sim_set(h, key.encode(), v) == 0
    assert L_.sim_set(h, b"decay_tau", cosim.FW_K["c_cap"] / cosim.FW_K["g_leak"]) == 0
    assert L_.sim_start(h, es.T_AMB) == 0
    assert L_.sup_start(h) == 0
    assert L_.rim_start(h) == 0
    assert L_.plc_start(h) == 0
    assert L_.prl_start(h) == 0
    out = (ctypes.c_double * len(cosim.OUT))()
    rout = (ctypes.c_double * 3)()
    sup_out = (ctypes.c_double * 3)()
    n_sub = round(es.DT_CTRL / es.DT_SIM)
    force = {int(round(t_ / es.DT_CTRL)) for t_ in case.get("force_probe_at", ())}
    P_cmd, t_hat = 0.0, es.T_AMB
    first = {}
    suspects = []
    tc_tail = []
    tc_max = 0.0
    n = int(t_end / es.DT_CTRL)
    tail_from = n - int(100.0 / es.DT_CTRL)

    def mark(rule, t):
        if rule not in first:
            first[rule] = {"t_s": round(t, 1), "T_c": round(float(tr.T_c()), 1), "glass": round(float(tr.Tg), 1)}

    batches = list(case.get("food_batches_at", ()))
    # rim_limit.py: a decimated trace for offline rule studies
    trace_every = int(round(case["trace_dt"] / es.DT_CTRL)) if case.get("trace_dt") else 0
    trace = []
    for k in range(n):
        t = k * es.DT_CTRL
        p_applied = P_cmd   # the command in force over this period
        if k in force:
            L_.sim_request_probe(h)
        if batches and t >= batches[0]:
            # batch cooking: the cooked batch is replaced by a fresh cold one
            batches.pop(0)
            tr.Tf = tr.food_T0
        for _ in range(n_sub):
            tr.step(P_cmd, case["h"])
        leak = None
        if case.get("r_leak") is not None and t >= LEAK_AT:
            # the leak conductance grows linearly over LEAK_RAMP_S
            ramp = case.get("ramp_s", 0.0)
            leak = case["r_leak"] / (min(1.0, (t - LEAK_AT + es.DT_CTRL) / ramp) if ramp > 0 else 1.0)
        y = X.pt100_read(tr.Tel, leak) + screen.NOISE * rng.standard_normal()
        if case.get("sp_profile"):
            # [(t_from_s, setpoint)], in time order (rim_limit.py stress set)
            sp = [v for t0, v in case["sp_profile"] if t + es.DT_CTRL >= t0][-1]
        elif case.get("sp_down_at") is not None and t >= case["sp_down_at"]:
            sp = sp1 - case["sp_down_k"]
        else:
            sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        L_.rim_step(h, X.node_mv(tr.Tg, case["corner"]), t_hat, rout)
        st, t_rim = int(rout[0]), rout[1]
        # main/pan_control.c loop_rim_input()
        if st == X.RIM_VALID:
            rim_in = t_rim
        else:
            rim_in = t_rim if st == X.RIM_SAT and t_rim < y else y
        L_.sim_step(h, y, rim_in, sp, P_cmd, 0, 1, 1, 0, out)
        o = dict(zip(cosim.OUT, out))
        t_hat = o["t_hat"]
        xs = L_.sim_xcheck(h)
        if xs:
            suspects.append(round(t, 1))
        if L_.plc_run(h, xs, int(o["cc_event"]), y, t_rim if st == X.RIM_VALID else math.nan):
            mark("leak", t)
        # D-RIMLIM: main/pan_control.c feeds the setpoint, t_hat and the rim
        if L_.prl_run(h, sp, o["t_hat"], int(st == X.RIM_VALID), t_rim):
            mark("rim_limit", t)
        if o["cc_event"] == cosim.CC_EVT_LOST:
            mark("d1_lost", t)
        if o["fault"]:
            mark("guard", t)
        if st == X.RIM_FAULT:
            mark("rim_fault", t)
        P_cmd = o["p_cmd"]
        if L_.sup_rate(h, y, int(round(t * 1000))):
            mark("R1", t)
        # bus current of the period that just ended (main/pan_control.c)
        L_.sup_step(h, o["t_hat"], y, sp, P_cmd, p_applied / 120.0, 1, sup_out)
        if sup_out[0]:
            P_cmd = 0.0
        if sup_out[1]:
            mark("R2a" if int(sup_out[1]) == 1 else "R2b", t)
        tc = float(tr.T_c())
        tc_max = max(tc_max, tc)
        if tc > T_BAR:
            mark("T_c_over_300", t)
        # the CR-5 hardware rim trip (pcb/DECISIONS.md D6): reported only
        if tr.Tg >= X.CR5_BAND[0]:
            mark("glass_cr5_low", t)
        if tr.Tg >= X.CR5_BAND[1]:
            mark("glass_cr5_top", t)
        if k >= tail_from:
            tc_tail.append(tc)
        if trace_every and k % trace_every == 0:
            trace.append((t, sp, y, t_hat, st, t_rim, tc, tr.Tg))
    L_.sim_free(h)
    extra = {"trace": np.asarray(trace, dtype=np.float32)} if trace_every else {}
    return {**case, **extra, "first": first, "suspects": len(suspects), "suspect_times_s": suspects[:12],
            "T_c_steady": round(float(np.mean(tc_tail)), 1),
            "T_c_drift_last_100s": round(tc_tail[-1] - tc_tail[0], 2), "T_c_max": round(tc_max, 1)}


def leak_cases():
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    out, i = [], 0
    for pan, (lo, hi) in spread.items():
        sp2 = None if pan == "disc_pot_water_1l5" else SP_FRY
        for delta in DELTAS:
            for corner in CORNERS:
                for onset, ramp in ONSETS.items():
                    for r in R_LEAKS:
                        out.append(dict(kind="leak", pan=pan, h=(lo * hi) ** 0.5, seed=950 + i, delta=delta,
                                        corner=corner, r_leak=r, sp2=sp2, t_end=T_END_LEAK, onset=onset,
                                        ramp_s=ramp))
                i += 1
    return out


def benign_cases(n_seeds):
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    out = [dict(c, set="xcheck28") for c in X.cases() if c["kind"] != "leak"]
    i = 0
    for pan, (lo, hi) in spread.items():
        h_mid = (lo * hi) ** 0.5
        for delta in DELTAS:
            for corner in CORNERS:
                for s in range(n_seeds):
                    seed = 20_000 + 100 * i + s
                    base = dict(pan=pan, delta=delta, corner=corner, set="b5_glass")
                    out.append(dict(base, kind="nominal", h=h_mid, seed=seed))
                    if pan != "disc_pot_water_1l5":
                        out.append(dict(base, kind="food", h=h_mid, seed=seed, food_at=cosim.FOOD_T))
                        out.append(dict(base, kind="food_batches", h=h_mid, seed=seed + 30, food_at=cosim.FOOD_T,
                                        food_batches_at=tuple(cosim.FOOD_T + d for d in BATCH_GAPS_S)))
                    for hh in (lo, hi):
                        out.append(dict(base, kind="probe_intact", h=hh, seed=seed + 50,
                                        force_probe_at=(250.0, 500.0)))
                    out.append(dict(base, kind="hot_glass", h=h_mid, seed=seed + 70, glass0=200.0))
                    out.append(dict(base, kind="sp_down", h=h_mid, seed=seed + 90, sp_down_at=450.0,
                                    sp_down_k=60.0))
                i += 1
    return out


LATCHES = ("leak", "rim_limit", "rim_fault", "guard", "R1", "R2a", "R2b")


def leak_row(r):
    ts = [(r["first"][k]["t_s"], k) for k in LATCHES if k in r["first"]]
    fl = min(ts) if ts else None
    t300 = r["first"].get("T_c_over_300", {}).get("t_s")
    return {"onset": r["onset"], "pan": r["pan"], "delta": r["delta"], "corner": r["corner"],
            "r_leak_ohm": round(r["r_leak"], 1),
            "T_c_steady": r["T_c_steady"], "T_c_drift_last_100s": r["T_c_drift_last_100s"],
            "T_c_max": r["T_c_max"], "t_T_c_over_300_s": t300,
            "suspects": r["suspects"],
            "first_suspect_s": r["suspect_times_s"][0] if r["suspect_times_s"] else None,
            "leak_latch": r["first"].get("leak"), "rim_limit": r["first"].get("rim_limit"),
            "rim_fault": r["first"].get("rim_fault"),
            "d1_lost": r["first"].get("d1_lost"),
            "glass_cr5_low": r["first"].get("glass_cr5_low"),
            "glass_cr5_top": r["first"].get("glass_cr5_top"),
            "first_latch": None if fl is None else {"rule": fl[1], **r["first"][fl[1]]},
            "latched_before_300": fl is not None and (t300 is None or fl[0] < t300)}


def leak_summary(rows):
    haz_rows = [x for x in rows if x["T_c_steady"] > T_BAR]
    missed = [x for x in haz_rows if not x["latched_before_300"]]
    never = [x for x in haz_rows if x["first_latch"] is None]
    by_r = {}
    for x in rows:
        d = by_r.setdefault(str(x["r_leak_ohm"]), {"runs": 0, "T_c_steady_min": 1e9, "T_c_steady_max": -1e9,
                                                   "hazardous": 0, "latched_before_300": 0, "leak_latched": 0,
                                                   "any_latch": 0, "runs_with_suspect": 0, "d1_lost": 0})
        d["runs"] += 1
        d["T_c_steady_min"] = min(d["T_c_steady_min"], x["T_c_steady"])
        d["T_c_steady_max"] = max(d["T_c_steady_max"], x["T_c_steady"])
        d["hazardous"] += x["T_c_steady"] > T_BAR
        d["latched_before_300"] += x["latched_before_300"] and x["T_c_steady"] > T_BAR
        d["leak_latched"] += x["leak_latch"] is not None
        d["any_latch"] += x["first_latch"] is not None
        d["runs_with_suspect"] += x["suspects"] > 0
        d["d1_lost"] += x["d1_lost"] is not None
    leak_lat = [x for x in haz_rows if x["leak_latch"] is not None]
    # A rule gated on the cross-check can meet the bar only where a suspect
    # came before T_c first exceeded 300 degC.
    sus_before = [x for x in haz_rows if x["first_suspect_s"] is not None
                  and (x["t_T_c_over_300_s"] is None or x["first_suspect_s"] < x["t_T_c_over_300_s"])]
    late = [x for x in haz_rows if x["first_latch"] is not None and not x["latched_before_300"]]

    def before_300(x, key):
        return x[key] is not None and (x["t_T_c_over_300_s"] is None or x[key]["t_s"] < x["t_T_c_over_300_s"])

    def rng(vals):
        vals = list(vals)
        return [min(vals), max(vals)] if vals else [None, None]

    # "largest" leak = the most leakage current = the lowest R_leak
    return {"runs": len(rows), "hazardous_runs": len(haz_rows),
            "hazardous_latched_before_300": len(haz_rows) - len(missed),
            "hazardous_latched_after_300": len(missed) - len(never),
            "hazardous_never_latched": len(never),
            "hazardous_leak_check_latched": len(leak_lat),
            "hazardous_leak_check_first": sum(x["first_latch"] is not None and x["first_latch"]["rule"] == "leak"
                                              for x in haz_rows),
            "hazardous_rim_fault_first": sum(x["first_latch"] is not None and x["first_latch"]["rule"] == "rim_fault"
                                             for x in haz_rows),
            "hazardous_rim_limit_first": sum(x["first_latch"] is not None and x["first_latch"]["rule"] == "rim_limit"
                                             for x in haz_rows),
            "hazardous_rim_limit_before_300": sum(before_300(x, "rim_limit") for x in haz_rows),
            "leak_check_latch_T_c_range": rng(x["leak_latch"]["T_c"] for x in leak_lat),
            "hazardous_with_suspect_before_300": len(sus_before),
            "hazardous_cr5_band_low_edge_before_300": sum(before_300(x, "glass_cr5_low") for x in haz_rows),
            "hazardous_cr5_band_top_edge_before_300": sum(before_300(x, "glass_cr5_top") for x in haz_rows),
            "late_first_latch_T_c_max": max((x["first_latch"]["T_c"] for x in late), default=None),
            "late_first_latch_s_after_300_range": rng(round(x["first_latch"]["t_s"] - x["t_T_c_over_300_s"], 1)
                                                      for x in late),
            "hazardous_steady_T_c_max": max((x["T_c_steady"] for x in haz_rows), default=None),
            "lowest_r_hazardous_ohm": min((x["r_leak_ohm"] for x in haz_rows), default=None),
            "highest_r_hazardous_ohm": max((x["r_leak_ohm"] for x in haz_rows), default=None),
            "hazardous_never_latched_rows": never,
            "largest_never_latched_hazardous": min(never, key=lambda x: x["r_leak_ohm"], default=None),
            "largest_not_latched_before_300": min(missed, key=lambda x: x["r_leak_ohm"], default=None),
            "by_r_leak": by_r}


def requirements(every):
    """Numbers behind the insulation and production requirements (D-LEAK)."""
    def err_k(r_p, t=T_BAR):
        return round(t - X.pt100_read(t, r_p), 4)
    # the largest element-parallel resistance a hot calibration point at
    # 300 degC with a +-HOT_CHECK_K acceptance still catches (bisection)
    lo, hi = 1e3, 1e9
    for _ in range(100):
        mid = (lo * hi) ** 0.5
        lo, hi = (mid, hi) if err_k(mid) > HOT_CHECK_K else (lo, mid)
    rows = every["by_r_leak"]
    safe = [float(r) for r, d in rows.items() if d["hazardous"] == 0]
    return {"reading_error_K_at_300C": {"10 Mohm": err_k(10e6), "1.04 Mohm": err_k(1.04e6),
                                        "100 Mohm": err_k(100e6)},
            "highest_hazardous_r_leak_ohm": every["highest_r_hazardous_ohm"],
            "lowest_non_hazardous_r_leak_ohm": min((r for r in safe if r > every["highest_r_hazardous_ohm"]),
                                                   default=None),
            "ratio_10Mohm_to_highest_hazardous": round(10e6 / every["highest_r_hazardous_ohm"]),
            "hot_check_acceptance_K": HOT_CHECK_K,
            "hot_check_detects_parallel_r_below_ohm": round(lo, -3)}


def summarise(leak, benign):
    rows = [leak_row(r) for r in leak]
    every = leak_summary(rows)
    by_onset = {o: leak_summary([x for x in rows if x["onset"] == o]) for o in ONSETS}
    missed = every["hazardous_runs"] - every["hazardous_latched_before_300"]
    bar_met = missed == 0
    benign_latch = [(b["set"], b["kind"], b["pan"], b["delta"], b["corner"], b["seed"],
                     b["first"].get("leak") or b["first"].get("rim_limit"))
                    for b in benign if "leak" in b["first"] or "rim_limit" in b["first"]]
    by_kind = {}
    for b in benign:
        d = by_kind.setdefault(b["set"] + "/" + b["kind"], {"runs": 0, "runs_with_suspect": 0, "suspects": 0,
                                                            "max_suspects": 0, "leak_latches": 0,
                                                            "d1_lost": 0, "other_latches": 0})
        d["runs"] += 1
        d["runs_with_suspect"] += b["suspects"] > 0
        d["suspects"] += b["suspects"]
        d["max_suspects"] = max(d["max_suspects"], b["suspects"])
        d["leak_latches"] += "leak" in b["first"] or "rim_limit" in b["first"]
        d["d1_lost"] += "d1_lost" in b["first"]
        d["other_latches"] += any(k in b["first"] for k in ("rim_fault", "guard", "R1", "R2a", "R2b"))
    return {
        "leak": {"all_onsets": every, "by_onset": by_onset},
        "requirements": requirements(every),
        "bar": {"rule": "every leak with untripped steady T_c > 300 degC latches before T_c first exceeds 300 degC",
                "met": bar_met, "status": "met" if bar_met else "not_met", "expected": EXPECTED_BAR,
                "failing_runs": missed, "of_hazardous": every["hazardous_runs"]},
        "benign": {"runs": len(benign), "leak_latches": len(benign_latch), "latch_examples": benign_latch[:10],
                   "d1_lost": sum(v["d1_lost"] for v in by_kind.values()),
                   "other_latches": sum(v["other_latches"] for v in by_kind.values()),
                   "by_kind": by_kind},
        "_rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "leak-checks.json"))
    ap.add_argument("--seeds", type=int, default=N_SEEDS)
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    lc, bc = leak_cases(), benign_cases(args.seeds)
    with Pool(min(10, os.cpu_count() or 1), initializer=X._init, initargs=(args.lib,)) as pool:
        # the long leak runs first, so the pool stays busy to the end
        rows = pool.map(run_case, lc + bc, chunksize=1)
    leak, benign = rows[:len(lc)], rows[len(lc):]
    summ = summarise(leak, benign)
    rows_out = summ.pop("_rows")
    gate = {"benign_no_leak_latch": summ["benign"]["leak_latches"] == 0,
            "bar_status_as_recorded": summ["bar"]["status"] == EXPECTED_BAR,
            "benign_no_other_latch_or_d1_lost": summ["benign"]["other_latches"] == 0 and summ["benign"]["d1_lost"] == 0,
            "leak_check_latches_some_hazardous_leak": summ["leak"]["all_onsets"]["hazardous_leak_check_latched"] > 0,
            "rim_limit_coverage_as_recorded":
                summ["leak"]["all_onsets"]["hazardous_latched_before_300"] >= EXPECTED_BEFORE_300_MIN
                and summ["leak"]["all_onsets"]["hazardous_never_latched"] <= EXPECTED_NEVER_MAX}
    res = {"scope": __doc__.strip(), "r_leak_ohm": [round(r, 1) for r in R_LEAKS], "leak_at_s": LEAK_AT,
           "t_end_s": T_END_LEAK, "sp_fry_C": SP_FRY, "seeds": args.seeds, "summary": summ, "gate": gate,
           "all_pass": all(gate.values()), "leak_rows": rows_out,
           "benign_rows": [{k: b[k] for k in ("set", "kind", "pan", "delta", "corner", "seed", "suspects")}
                           | {"first": b["first"]} for b in benign]}
    Path(args.out).write_text(json.dumps(res, indent=1, default=float) + "\n")
    for onset, L in summ["leak"]["by_onset"].items():
        print(f"onset {onset}: by R (ohm): runs, steady T_c min..max, hazardous, latched before 300, "
              "leak-check latched, any latch, runs with a suspect, D1 lost")
        for r, d in L["by_r_leak"].items():
            print(f"   {float(r):8.0f}: {d['runs']:2d} {d['T_c_steady_min']:6.1f}..{d['T_c_steady_max']:6.1f} "
                  f"haz {d['hazardous']:2d} before300 {d['latched_before_300']:2d} leak {d['leak_latched']:2d} "
                  f"any {d['any_latch']:2d} suspect {d['runs_with_suspect']:2d} lost {d['d1_lost']:2d}")
        print(f"   hazardous {L['hazardous_runs']}: latched before 300 {L['hazardous_latched_before_300']}, "
              f"after {L['hazardous_latched_after_300']} (first latch {L['late_first_latch_s_after_300_range']} s "
              f"after, T_c <= {L['late_first_latch_T_c_max']}), never {L['hazardous_never_latched']}; "
              f"suspect before 300: {L['hazardous_with_suspect_before_300']}; leak check latched "
              f"{L['hazardous_leak_check_latched']} at T_c {L['leak_check_latch_T_c_range']}; CR-5 band "
              f"low / top edge before 300: {L['hazardous_cr5_band_low_edge_before_300']} / "
              f"{L['hazardous_cr5_band_top_edge_before_300']}")
    A = summ["leak"]["all_onsets"]
    print("hazardous:", A["hazardous_runs"], "latched before 300:", A["hazardous_latched_before_300"],
          "after:", A["hazardous_latched_after_300"], "never:", A["hazardous_never_latched"],
          "; R_leak", A["lowest_r_hazardous_ohm"], "..", A["highest_r_hazardous_ohm"], "ohm")
    print("never latched:", [(x["onset"], x["pan"], x["delta"], x["corner"], x["r_leak_ohm"], x["T_c_steady"])
                             for x in A["hazardous_never_latched_rows"]])
    print("requirements:", summ["requirements"])
    print("BAR", summ["bar"])
    print("benign:", summ["benign"]["runs"], "runs,", summ["benign"]["leak_latches"], "leak latches;",
          "(runs, runs with a suspect, max suspects, leak latches, D1 lost, other latches)",
          {k: (v["runs"], v["runs_with_suspect"], v["max_suspects"], v["leak_latches"], v["d1_lost"],
               v["other_latches"]) for k, v in summ["benign"]["by_kind"].items()})
    print("GATE", gate)
    print("LEAK CHECKS PASS" if res["all_pass"] else "LEAK CHECKS FAILURE")
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
