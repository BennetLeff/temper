"""sensor-r3 C-in-the-loop co-simulation.

The firmware's C1 loop (firmware/components/control/pan_temp_loop.c: guard,
KF, a-identification, rate PID, D1, power authority), built as a host shared
library by build_lib.sh, closes the loop around the sensor-r2/r3 Python truth
plant (screen.Truth, unchanged). The per-step order copies screen.run().

Gain modes (how the controller and D1 get a = eta / C_total):
  true          fixed to the truth value, as the r2/r3 screens did
  id_measured   identified online; input power measured (bus sense), the coil
                delivers what is commanded
  id_estimated  identified online from the power COMMAND; the coil really
                delivers P_cmd * (1.10 - 0.20 P_cmd/P_MAX), i.e. +10 % at low
                power to -10 % at full (native-21's ~10 % estimate,
                temper-coil-driver-r1 RECOMMENDATIONS item 2)

Cases: the 16 C1 design cases and 12 stress cases of screen.py (same seeds),
loss / food / nominal D1 runs (same seeds), a probe forced on intact contact
in both holds (4 pans x both h_c extremes), a preheated pan placed on the hob,
and h_c steps 1000->300 and 300->3000 at 250 s. D1 is ON in every run
(production configuration). Seed-to-seed robustness of D1 is in
b5_montecarlo.py. A Python double-precision shadow KF with the same
constants as the C filter runs on the identical readings for the parity bar.

Run: python cosim.py [--lib path] [--out cosim-results.json]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ref  # noqa: E402
from ref import es, screen  # noqa: E402

LIB = None
LIB_PATH = str(HERE / "build" / "libpantemp.so")
OUT = ["t_hat", "p_cmd", "p_pid", "a", "a_valid", "sp_eff", "cc_state", "cc_event", "fault", "diag", "ui", "src_mask",
       "d", "d_exp", "decay_rms", "decay_change"]
CC_EVT_SUSPECT, CC_EVT_LOST = 1, 3
LOSS_T, FOOD_T, HSTEP_T = 250.0, 250.0, 250.0

# Firmware defaults for the cartridge (pte_default_params). The truth plant is
# screen.py's C1 (C_cap 39.7 mJ/K); the firmware carries the as-designed budget
# value 40.4 mJ/K (HANDOFF C.1) - a deliberate 1.8 % model mismatch.
FW_K = dict(c_cap=0.0404, c_el=0.008175, g_bond=0.0612, g_leak=0.0008, area=45.4e-6, h_nom=1300.0)


def lib():
    global LIB
    if LIB is None:
        L = ctypes.CDLL(LIB_PATH)
        L.sim_new.restype = ctypes.c_void_p
        L.sim_free.argtypes = [ctypes.c_void_p]
        L.sim_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double]
        L.sim_set.restype = ctypes.c_int
        L.sim_start.argtypes = [ctypes.c_void_p, ctypes.c_double]
        L.sim_start.restype = ctypes.c_int
        L.sim_request_probe.argtypes = [ctypes.c_void_p]
        L.sim_step.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        LIB = L
    return LIB


def deliver(p_cmd, power_mode):
    if power_mode == "estimated":
        return p_cmd * (1.10 - 0.20 * p_cmd / es.P_MAX)
    return p_cmd


def run_case(case):
    """One closed-loop run. case: dict(kind, pan, h, eta, seed, gain, [loss_at, food_at, h_step, T_hot, params])."""
    L_ = lib()
    screen.apply(ref.C1)
    pan = es.PANS[case["pan"]]
    tr = ref.HotTruth(pan, case["h"], case["eta"], case["seed"], food_at=case.get("food_at"), T_hot=case.get("T_hot"))
    rng = np.random.default_rng(case["seed"] + 1)
    sp1, sp2 = pan["sp"]
    a_true = case["eta"] / (tr.C.sum() + tr.Cw)
    gain = case["gain"]
    power_mode = "estimated" if gain == "id_estimated" else "measured"

    h = L_.sim_new()
    k_fw = dict(FW_K)
    for key, v in k_fw.items():
        assert L_.sim_set(h, key.encode(), v) == 0
    assert L_.sim_set(h, b"decay_tau", k_fw["c_cap"] / k_fw["g_leak"]) == 0
    if gain == "true":
        assert L_.sim_set(h, b"identify", 0) == 0
        assert L_.sim_set(h, b"fixed_a", a_true * case.get("a_scale", 1.0)) == 0
    for key, v in case.get("params", {}).items():
        assert L_.sim_set(h, key.encode(), v) == 0, key
    assert L_.sim_start(h, es.T_AMB) == 0
    shadow = ref.KFRef(es.T_AMB, screen.NOISE, k_fw)

    out = (ctypes.c_double * len(OUT))()
    P_cmd = 0.0
    n_sub = round(es.DT_CTRL / es.DT_SIM)
    log_, shadow_d, a_log = [], [], []
    suspect_at = detected_at = None
    probes = lost_events = 0
    faults = []
    probe_log = []
    prev_cc = 0
    max_rise_rate = 0.0
    y_prev = None
    h_now = case["h"]
    force_ticks = {int(round(t_ / es.DT_CTRL)) for t_ in case.get("force_probe_at", ())}
    for k in range(int(es.T_END / es.DT_CTRL)):
        t = k * es.DT_CTRL
        if case.get("loss_at") is not None and t >= case["loss_at"]:
            h_now = 2.0
        if case.get("h_step") is not None and t >= case["h_step"][0]:
            h_now = case["h_step"][1]
        if k in force_ticks:
            L_.sim_request_probe(h)
        P_true = deliver(P_cmd, power_mode)
        for _ in range(n_sub):
            tr.step(P_true, h_now)
        y = tr.Tel + screen.NOISE * rng.standard_normal()
        ntc = tr.sink() + es.NTC_BIAS
        sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        p_applied = P_true if power_mode == "measured" else P_cmd
        src = 0 if power_mode == "measured" else 1
        L_.sim_step(h, y, ntc, sp, p_applied, src, 1, 1, 0, out)
        o = dict(zip(OUT, out))
        shadow_d.append(o["t_hat"] - shadow.step(y, (P_cmd, ntc)))
        if y_prev is not None:
            max_rise_rate = max(max_rise_rate, (y - y_prev) / es.DT_CTRL)
        y_prev = y
        if o["cc_event"] == CC_EVT_SUSPECT:
            probes += 1
            suspect_at = t if suspect_at is None else suspect_at
        if o["cc_event"] == CC_EVT_LOST:
            lost_events += 1
            detected_at = t if detected_at is None else detected_at
        if o["cc_state"] != prev_cc and prev_cc in (1, 3):   # a probe / retry just ended
            probe_log.append((round(t, 1), round(o["d"], 4), round(o["d_exp"], 4), round(o["decay_rms"], 3),
                              round(o["decay_change"], 2), int(o["cc_state"])))
        prev_cc = o["cc_state"]
        if o["fault"] and not faults:
            faults.append((round(t, 1), int(o["fault"]), int(o["diag"])))
        P_cmd = o["p_cmd"]
        a_log.append((o["a"] / a_true, o["a_valid"], o["src_mask"]))
        log_.append((t + es.DT_CTRL, sp, o["t_hat"], tr.T_c(), tr.T_mean(), y, P_cmd, h_now, float("nan")))
    L_.sim_free(h)

    L = np.array(log_)
    m = screen.metrics(L, case.get("loss_at"))
    A = np.array(a_log)
    t_reach = m["t_reach_sp1_minus2K_s"]
    i_end1 = int(round(t_reach / es.DT_CTRL)) - 1 if np.isfinite(t_reach) else len(A) - 1
    sd = np.array(shadow_d)
    row = {**{k: v for k, v in case.items() if k != "params"}, "params": case.get("params", {}), **m,
           "suspect_at": suspect_at, "detected_at": detected_at, "probes": probes, "lost_events": lost_events,
           "faults": faults, "probe_log": probe_log, "max_reading_rise_K_per_s": round(max_rise_rate, 1),
           "a_ratio_end_ramp1": round(float(A[min(max(i_end1, 0), len(A) - 1), 0]), 3),
           "a_valid_end_ramp1": bool(A[min(max(i_end1, 0), len(A) - 1), 1]),
           "a_ratio_end": round(float(A[-1, 0]), 3), "a_src_mask_end": int(A[-1, 2]),
           "shadow_rms_K": float(np.sqrt(np.mean(sd**2))), "shadow_max_K": float(np.abs(sd).max())}
    sp_hi = pan["sp"][1]
    b3_lim = 1.5 if sp_hi <= 100 else 3.0
    kind = case["kind"]
    if kind in ("design", "stress", "hot_pan", "h_step"):
        row["B1"] = m["est_err_c_max_K"] <= 3.0
        row["B2"] = m["overshoot_K"] <= 5.0
        row["B3"] = max(abs(x) for x in m["hold_err_c_K"]) <= b3_lim
    if kind == "loss":
        row["B5_suspect_s"] = None if suspect_at is None else round(suspect_at - case["loss_at"], 1)
        row["B5_confirm_s"] = None if detected_at is None else round(detected_at - case["loss_at"], 1)
        row["B5_Tc_over_sp_K"] = m["Tc_max_over_sp_after_loss_K"]
    row["false_latch"] = kind != "loss" and detected_at is not None
    return row


def cases(gains=("true", "id_measured", "id_estimated"), params=None, kinds=None):
    """The screen.py C1 case list (same seeds) plus hot-pan and h-step runs."""
    c = ref.C1
    screen.apply(c)
    spread = screen.h_spread(c)
    base = []
    i = 0
    for pan, (lo, hi) in spread.items():
        for h in (lo, hi):
            for eta in es.ETA_SWEEP:
                base.append(dict(kind="design", pan=pan, h=h, eta=eta, seed=100 + i))
                i += 1
    for pan in es.PANS:
        for h in screen.STRESS_H:
            base.append(dict(kind="stress", pan=pan, h=h, eta=0.82, seed=300 + i))
            i += 1
    for pan, (lo, hi) in spread.items():
        h_mid = (lo * hi) ** 0.5
        base.append(dict(kind="loss", pan=pan, h=h_mid, eta=0.82, seed=500 + i, loss_at=LOSS_T))
        base.append(dict(kind="nominal", pan=pan, h=h_mid, eta=0.82, seed=500 + i))
        if pan != "disc_pot_water_1l5":
            base.append(dict(kind="food", pan=pan, h=h_mid, eta=0.82, seed=500 + i, food_at=FOOD_T))
        i += 1
    for j, (pan, (lo, hi)) in enumerate(spread.items()):
        # A probe forced on intact contact in each hold (as the rim cross-check
        # would request): it must never latch, on any pan or contact extreme.
        for h in (lo, hi):
            base.append(dict(kind="probe_intact", pan=pan, h=h, eta=0.82, seed=600 + 2 * j + (h == hi),
                             force_probe_at=(250.0, 500.0)))
    for j, pan in enumerate(("cast_iron_26", "carbon_steel_28", "triply_clad_24")):
        lo, hi = spread[pan]
        base.append(dict(kind="hot_pan", pan=pan, h=(lo * hi) ** 0.5, eta=0.82, seed=700 + j,
                         T_hot=float(es.PANS[pan]["sp"][0])))
    j = 0
    for pan in ("carbon_steel_28", "triply_clad_24"):
        for h0, h1 in ((1000.0, 300.0), (300.0, 3000.0)):
            base.append(dict(kind="h_step", pan=pan, h=h0, eta=0.88, seed=800 + j, h_step=(HSTEP_T, h1)))
            j += 1
    out = []
    for g in gains:
        for b in base:
            if kinds is None or b["kind"] in kinds:
                out.append({**b, "gain": g, "params": dict(params or {})})
    return out


def summarise(rows):
    s = {}
    for g in sorted({r["gain"] for r in rows}):
        R = [r for r in rows if r["gain"] == g]
        d = {}
        for kind in ("design", "stress", "hot_pan", "h_step"):
            G = [r for r in R if r["kind"] == kind]
            if G:
                d[kind] = {"cases": len(G), "B1_pass": sum(r["B1"] for r in G), "B2_pass": sum(r["B2"] for r in G),
                           "B3_pass": sum(r["B3"] for r in G),
                           "worst_est_err_K": max(r["est_err_c_max_K"] for r in G),
                           "worst_overshoot_K": max(r["overshoot_K"] for r in G),
                           "worst_T_mean_overshoot_K": max(r["T_mean_overshoot_K"] for r in G),
                           "probes": sum(r["probes"] for r in G), "false_latches": sum(r["false_latch"] for r in G),
                           "faults": sum(bool(r["faults"]) for r in G)}
        loss = [r for r in R if r["kind"] == "loss"]
        if loss:
            d["loss"] = {"cases": len(loss), "detected": sum(r["detected_at"] is not None for r in loss),
                         "worst_suspect_s": max((r["B5_suspect_s"] or 1e9) for r in loss),
                         "worst_confirm_s": max((r["B5_confirm_s"] or 1e9) for r in loss),
                         "worst_Tc_over_sp_K": max(r["B5_Tc_over_sp_K"] for r in loss)}
        for kind in ("food", "nominal", "probe_intact"):
            G = [r for r in R if r["kind"] == kind]
            if G:
                d[kind] = {"cases": len(G), "probes": sum(r["probes"] for r in G),
                           "false_latches": sum(r["false_latch"] for r in G), "faults": sum(bool(r["faults"]) for r in G)}
        ident = [r for r in R if r["kind"] == "design"]
        if g != "true" and ident:
            d["a_ratio_end_ramp1_design"] = [min(r["a_ratio_end_ramp1"] for r in ident),
                                             max(r["a_ratio_end_ramp1"] for r in ident)]
            d["a_valid_end_ramp1_design"] = sum(r["a_valid_end_ramp1"] for r in ident)
            d["a_ratio_end_design"] = [min(r["a_ratio_end"] for r in ident), max(r["a_ratio_end"] for r in ident)]
        d["shadow_parity"] = {"worst_rms_K": max(r["shadow_rms_K"] for r in R),
                              "worst_max_K": max(r["shadow_max_K"] for r in R)}
        s[g] = d
    return s


def bars(summary):
    """DECISIONS.md section 1 bars as HANDOFF C states them, per gain mode."""
    out = {}
    for g, d in summary.items():
        b = {
            "B1_design_ge_15of16": d["design"]["B1_pass"] >= 15,
            "B2_design_16of16": d["design"]["B2_pass"] == 16,
            "B3_design_16of16": d["design"]["B3_pass"] == 16,
            "B5_detected_4of4": d["loss"]["detected"] == d["loss"]["cases"],
            "B5_suspect_le_3s": d["loss"]["worst_suspect_s"] <= 3.0,
            "B5_Tc_le_sp_plus_15K": d["loss"]["worst_Tc_over_sp_K"] <= 15.0,
            "B5_confirm_le_21s": d["loss"]["worst_confirm_s"] <= 21.0,
            "no_false_latch_nominal_food": d["nominal"]["false_latches"] == 0 and d["food"]["false_latches"] == 0,
            "no_false_latch_design": d["design"]["false_latches"] == 0,
            "no_false_latch_probe_on_intact_contact": d["probe_intact"]["false_latches"] == 0,
            "C_vs_Python_rms_le_0p05K": d["shadow_parity"]["worst_rms_K"] <= 0.05,
        }
        if g != "true":
            lo, hi = d["a_ratio_end_ramp1_design"]
            b["a_within_30pct_end_ramp1"] = lo >= 0.7 and hi <= 1.3 and d["a_valid_end_ramp1_design"] == 16
        out[g] = b
    return out


def main():
    global LIB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "cosim-results.json"))
    args = ap.parse_args()
    LIB_PATH = args.lib
    os.environ["PANTEMP_LIB"] = LIB_PATH
    main_cases = cases()
    with Pool(min(10, os.cpu_count() or 1), initializer=_init, initargs=(LIB_PATH,)) as pool:
        main_rows = pool.map(run_case, main_cases)
    summ = summarise(main_rows)
    b = bars(summ)
    gate_modes = ("true", "id_measured", "id_estimated")
    all_pass = all(all(v for v in b[g].values()) for g in gate_modes)
    out = {"scope": __doc__.strip(), "firmware_cartridge_constants": FW_K,
           "truth_cartridge": ref.c1_constants(), "summary": summ, "bars": b, "all_bars_pass": all_pass,
           "rows": main_rows}
    Path(args.out).write_text(json.dumps(out, indent=1, default=float) + "\n")
    for g in gate_modes:
        print(f"== {g}")
        for k, v in summ[g].items():
            print("   ", k, v)
        print("    BARS", b[g])
    print("ALL BARS PASS" if all_pass else "BAR FAILURE")
    return 0 if all_pass else 1


def _init(path):
    global LIB_PATH
    LIB_PATH = path


if __name__ == "__main__":
    sys.exit(main())
