"""sensor-r3 rim NTC in the loop: the Pt100-vs-rim cross-check (D-XCHK) against a rim truth signal.

Why a separate co-sim. cosim.py feeds the loop the r2 plant's leak sink,
25 + 50 (1 - exp(-t/300)) degC + 3 K, as "the rim NTC". That never exceeds
78 degC, below the rim channel's saturation (87-97 degC, rim-ntc.json), so the
real channel would read SATURATED for every cosim.py run and the cross-check
could never fire there. cosim.py is left unchanged.

This co-sim gives the plant a rim:
  - Glass under the rim NTC: a first-order lag toward T_c - delta, with
    delta 12 or 46 K (the glass underside 12-46 K below the pan, study 08 as
    cited in pcb/DECISIONS.md D6) and tau_g 60 s (assumption: no transient
    glass data exists). The truth cartridge leaks to that glass, so the KF's
    sink is the same physical temperature the NTC reads.
  - Rim NTC: the 104GT-2 table (extrapolated above its 300 degC top with
    the last segment's beta) at the R25/B tolerance corners (hot: R25 -3 %,
    B +2 %, reads high; cold: R25 +3 %, B -2 %, reads low). The node is
    3300 mV x R/(R + 1 k), rounded to whole mV by the shim's mock ADC, and goes
    through the firmware driver (components/sensors/rim_ntc.c). It maps onto
    the loop input as main/pan_control.c loop_rim_input() does.
  - The C loop, D1 and the supervisor as in cosim.py (gain mode id_measured).

Cases:
  benign  4 pans (h_mid) x nominal/food x delta {12, 46} x corner {hot, cold}.
          Gate: no D1 contact-lost latch, no guard or rim fault, no supervisor
          latch. Cross-check suspects are probes on intact contact and are
          reported, not gated (D-B5: such probes never latch).
  leak    Pt100 element-parallel leakage from t = 250 s (R_leak 1 k and 3 k
          ohm; pcb/DECISIONS.md D6: it reads low and is electrically
          invisible), 4 pans x delta {12, 46}, cold corner. Reported: first
          cross-check suspect, what D1 concluded, the pan peak, and whether
          the glass reaches the CR-5 hardware rim trip band (262.3-288.1 degC).

Writes xcheck-cosim.json. Run: python3 xcheck_cosim.py [--lib path]
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
import rim_ntc  # noqa: E402
from ref import es, screen  # noqa: E402

TAU_G = 60.0
LEAK_AT = 250.0
CR5_BAND = (262.3, 288.1)
CORNERS = {"hot": (0.97, 1.02), "cold": (1.03, 0.98)}
RIM_VALID, RIM_SAT, RIM_FAULT = 1, 2, 3
CC_LOST = 2
A, B = 3.9083e-3, -5.775e-7


class GlassTruth(ref.HotTruth):
    """The plant with a glass node under the rim NTC; the cartridge leaks to it.

    The glass lags toward T_c - delta. With glass_w set it lags instead toward
    glass_w * T_c + (1 - glass_w) * t_eye: the glass under the bead as a
    weighted mean of the pan and the coil-eye air (rim_limit.py derives the
    weights from cad/thermal-axisym.json and study 08)."""

    def __init__(self, *a, delta, tau_g=TAU_G, glass_w=None, t_eye=None, **k):
        super().__init__(*a, **k)
        self.delta, self.tau_g, self.Tg = delta, tau_g, es.T_AMB
        self.glass_w, self.t_eye = glass_w, t_eye

    def sink(self):
        return self.Tg

    def step(self, P_in, h_c):
        super().step(P_in, h_c)
        if self.glass_w is None:
            target = max(es.T_AMB, self.T_c() - self.delta)
        else:
            target = self.glass_w * self.T_c() + (1.0 - self.glass_w) * self.t_eye
        self.Tg += es.DT_SIM * (target - self.Tg) / self.tau_g


_T_TOP = max(rim_ntc.GT2_104_KOHM)
_T_NEXT = sorted(rim_ntc.GT2_104_KOHM)[-2]
# Above the 104GT-2 table top (300 degC): the table's last-segment beta. A
# glass hotter than 300 degC only arises with a leaking or uncontrolled
# probe; clamping it at 300 degC (as this model did before D-LEAK) hid the
# rim channel's over-range fault from those runs.
_B_TOP = math.log(rim_ntc.r_table(_T_NEXT) / rim_ntc.r_table(_T_TOP)) / (
    1 / (_T_NEXT + 273.15) - 1 / (_T_TOP + 273.15))


def r_ntc(t):
    if t <= _T_TOP:
        return rim_ntc.interp_r(max(t, -50.0))
    return rim_ntc.r_table(_T_TOP) * math.exp(_B_TOP * (1 / (t + 273.15) - 1 / (_T_TOP + 273.15)))


# Whole-stack corners (rim_limit.py): the bead corner, the true v3v3 while the
# driver assumes 3300 mV (no MCP3202 CH1 driver yet; TPS62933 3242-3367 mV),
# and the bead's still-air self-heating (D-RIM: at most 4.53 K) on the hot side.
STACKS = {"hot_stack": ("hot", 3242.0, 4.53), "cold_stack": ("cold", 3367.0, 0.0)}


def node_mv(t_rim, corner):
    rail, sh = 3300.0, 0.0
    if corner in STACKS:
        corner, rail, sh = STACKS[corner]
        t_rim = t_rim + sh
    rs, bs = CORNERS[corner]
    r = r_ntc(t_rim) * rs
    r *= math.exp(rim_ntc.B25_85_K * (bs - 1) * (1 / (t_rim + 273.15) - 1 / 298.15))
    return rail * r / (r + 1000.0)


def pt100_read(t_el, r_leak):
    """Reading of a Pt100 shunted by r_leak (IEC 60751, T >= 0)."""
    r = 100.0 * (1 + A * t_el + B * t_el * t_el)
    if r_leak is not None:
        r = r * r_leak / (r + r_leak)
    return (-A + math.sqrt(A * A - 4 * B * (1 - r / 100.0))) / (2 * B)


def lib():
    L = cosim.lib()
    if not hasattr(L, "_rim_ready"):
        L.rim_start.argtypes = [ctypes.c_void_p]
        L.rim_start.restype = ctypes.c_int
        L.rim_step.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
        L.sim_xcheck.argtypes = [ctypes.c_void_p]
        L.sim_xcheck.restype = ctypes.c_int
        L._rim_ready = True
    return L


def run_case(case):
    L_ = lib()
    screen.apply(ref.C1)
    pan = es.PANS[case["pan"]]
    tr = GlassTruth(pan, case["h"], 0.82, case["seed"], food_at=case.get("food_at"), delta=case["delta"])
    rng = np.random.default_rng(case["seed"] + 1)
    sp1, sp2 = pan["sp"]
    h = L_.sim_new()
    for key, v in cosim.FW_K.items():
        assert L_.sim_set(h, key.encode(), v) == 0
    assert L_.sim_set(h, b"decay_tau", cosim.FW_K["c_cap"] / cosim.FW_K["g_leak"]) == 0
    assert L_.sim_start(h, es.T_AMB) == 0
    assert L_.sup_start(h) == 0
    assert L_.rim_start(h) == 0
    out = (ctypes.c_double * len(cosim.OUT))()
    rout = (ctypes.c_double * 3)()
    sup_out = (ctypes.c_double * 3)()
    n_sub = round(es.DT_CTRL / es.DT_SIM)
    P_cmd, t_hat = 0.0, es.T_AMB
    xs, lost_at, rim_fault, guard_fault, sup_latch = [], None, None, None, None
    rim_states = {RIM_VALID: 0, RIM_SAT: 0}
    tc_max = tc_max_after = tg_max = 0.0
    probes = 0
    prev_cc = 0
    err_max = 0.0
    for k in range(int(es.T_END / es.DT_CTRL)):
        t = k * es.DT_CTRL
        p_applied = P_cmd   # the command in force over this period
        for _ in range(n_sub):
            tr.step(P_cmd, case["h"])
        leak = case.get("r_leak") if t >= LEAK_AT else None
        y = pt100_read(tr.Tel, leak) + screen.NOISE * rng.standard_normal()
        sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        L_.rim_step(h, node_mv(tr.Tg, case["corner"]), t_hat, rout)
        st, t_rim = int(rout[0]), rout[1]
        rim_states[st] = rim_states.get(st, 0) + 1
        # main/pan_control.c loop_rim_input()
        if st == RIM_VALID:
            rim_in = t_rim
        else:
            rim_in = t_rim if st == RIM_SAT and t_rim < y else y
        L_.sim_step(h, y, rim_in, sp, P_cmd, 0, 1, 1, 0, out)
        o = dict(zip(cosim.OUT, out))
        t_hat = o["t_hat"]
        if L_.sim_xcheck(h):
            xs.append(round(t, 1))
        if o["cc_state"] != prev_cc and o["cc_state"] == 1:
            probes += 1
        prev_cc = o["cc_state"]
        if o["cc_event"] == cosim.CC_EVT_LOST and lost_at is None:
            lost_at = round(t, 1)
        if o["fault"] and guard_fault is None:
            guard_fault = (round(t, 1), int(o["diag"]))
        if st == RIM_FAULT and rim_fault is None:
            rim_fault = (round(t, 1), int(rout[2]))
        P_cmd = 0.0 if st == RIM_FAULT else o["p_cmd"]
        L_.sup_rate(h, y, int(round(t * 1000)))
        # bus current of the period that just ended (main/pan_control.c reads
        # it before deciding the new command)
        L_.sup_step(h, o["t_hat"], y, sp, P_cmd, p_applied / 120.0, 1, sup_out)
        if sup_out[0]:
            P_cmd = 0.0
        if sup_out[1] and sup_latch is None:
            sup_latch = (round(t, 1), int(sup_out[1]))
        tc = tr.T_c()
        tc_max = max(tc_max, tc)
        if t >= LEAK_AT:
            tc_max_after = max(tc_max_after, tc - sp)
        tg_max = max(tg_max, tr.Tg)
        if 10 <= t and (case.get("r_leak") is None or t < LEAK_AT):
            err_max = max(err_max, abs(t_hat - tc))
    L_.sim_free(h)
    row = {**case, "xcheck_suspects": len(xs), "xcheck_first_s": xs[0] if xs else None, "d1_probes": probes,
           "d1_lost_at": lost_at, "guard_fault": guard_fault, "rim_fault": rim_fault, "sup_latch": sup_latch,
           "rim_valid_frac": round(rim_states.get(RIM_VALID, 0) / (k + 1), 3),
           "Tc_max_C": round(tc_max, 1), "glass_max_C": round(tg_max, 1),
           "est_err_c_max_K": round(err_max, 2)}
    if case["kind"] == "leak":
        row["Tc_over_sp_after_leak_K"] = round(tc_max_after, 1)
        row["xcheck_first_after_leak_s"] = (round(xs[0] - LEAK_AT, 1) if xs and xs[0] >= LEAK_AT else None)
        row["glass_reaches_cr5_band"] = tg_max >= CR5_BAND[0]
    return row


def cases():
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    out, i = [], 0
    for pan, (lo, hi) in spread.items():
        h_mid = (lo * hi) ** 0.5
        for delta in (12.0, 46.0):
            for corner in ("hot", "cold"):
                out.append(dict(kind="nominal", pan=pan, h=h_mid, seed=900 + i, delta=delta, corner=corner))
                if pan != "disc_pot_water_1l5":
                    out.append(dict(kind="food", pan=pan, h=h_mid, seed=900 + i, delta=delta, corner=corner,
                                    food_at=cosim.FOOD_T))
                i += 1
            for r_leak in (1000.0, 3000.0):
                out.append(dict(kind="leak", pan=pan, h=h_mid, seed=950 + i, delta=delta, corner="cold",
                                r_leak=r_leak))
                i += 1
    return out


def _init(path):
    cosim.LIB_PATH = path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "xcheck-cosim.json"))
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    cs = cases()
    with Pool(min(10, os.cpu_count() or 1), initializer=_init, initargs=(args.lib,)) as pool:
        rows = pool.map(run_case, cs)
    benign = [r for r in rows if r["kind"] != "leak"]
    leak = [r for r in rows if r["kind"] == "leak"]
    summ = {
        "benign": {"runs": len(benign), "d1_lost_latches": sum(r["d1_lost_at"] is not None for r in benign),
                   "guard_faults": sum(r["guard_fault"] is not None for r in benign),
                   "rim_faults": sum(r["rim_fault"] is not None for r in benign),
                   "sup_latches": sum(r["sup_latch"] is not None for r in benign),
                   "runs_with_xcheck_suspect": sum(r["xcheck_suspects"] > 0 for r in benign),
                   "xcheck_suspects": sum(r["xcheck_suspects"] for r in benign),
                   "worst_est_err_K_nominal": max(r["est_err_c_max_K"] for r in benign if r["kind"] == "nominal"),
                   "worst_est_err_K_food": max(r["est_err_c_max_K"] for r in benign if r["kind"] == "food"),
                   "xcheck_suspect_runs": [(r["kind"], r["pan"], r["delta"], r["corner"], r["xcheck_first_s"])
                                           for r in benign if r["xcheck_suspects"] > 0]},
        "leak": {"runs": len(leak),
                 "xcheck_detected": sum(r["xcheck_first_after_leak_s"] is not None for r in leak),
                 "xcheck_first_after_leak_s": sorted(r["xcheck_first_after_leak_s"] for r in leak
                                                     if r["xcheck_first_after_leak_s"] is not None),
                 "d1_lost_latches": sum(r["d1_lost_at"] is not None for r in leak),
                 "worst_Tc_over_sp_after_leak_K": max(r["Tc_over_sp_after_leak_K"] for r in leak),
                 "glass_reaches_cr5_band_low": sum(r["glass_reaches_cr5_band"] for r in leak),
                 "glass_reaches_cr5_band_top": sum(r["glass_max_C"] >= CR5_BAND[1] for r in leak),
                 "worst_Tc_over_sp_after_leak_K_by_r_leak": {
                     str(int(rl)): max(r["Tc_over_sp_after_leak_K"] for r in leak if r["r_leak"] == rl)
                     for rl in (1000.0, 3000.0)}},
    }
    b = summ["benign"]
    gate = {"benign_no_d1_lost": b["d1_lost_latches"] == 0, "benign_no_guard_fault": b["guard_faults"] == 0,
            "benign_no_rim_fault": b["rim_faults"] == 0, "benign_no_supervisor_latch": b["sup_latches"] == 0}
    res = {"scope": __doc__.strip(), "tau_g_s": TAU_G, "leak_at_s": LEAK_AT, "cr5_band_C": CR5_BAND,
           "summary": summ, "gate": gate, "all_pass": all(gate.values()), "rows": rows}
    Path(args.out).write_text(json.dumps(res, indent=1, default=float) + "\n")
    for k, v in summ.items():
        print(k, v)
    for r in leak:
        print("  leak", r["pan"], r["r_leak"], r["delta"], "first xcheck +", r["xcheck_first_after_leak_s"],
              "lost", r["d1_lost_at"], "Tc-sp", r["Tc_over_sp_after_leak_K"], "glass", r["glass_max_C"])
    print("GATE", gate)
    print("XCHECK COSIM PASS" if res["all_pass"] else "XCHECK COSIM FAILURE")
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
