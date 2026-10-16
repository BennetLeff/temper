"""Firmware runaway checks with the C1 sensor (DECISIONS.md D-RUN).

The legacy firmware has two checks that C1 trips falsely:

  L-rate  check_runaway_boundary: reading rises > 15 K/s between two 10 ms
          reads -> RUNAWAY latch (any state).
  L-over  state_heating_update: reading > setpoint + 10 K -> FAULT_THERMAL_
          RUNAWAY (armed once PREHEAT hands over at reading >= sp - 10).

C1 builds replace them with components/control/pan_supervisor.c:

  R1      1 s block means of the reading; latch when the block-to-block rise
          exceeds 15 K/s for 5 consecutive blocks;
  R2      stage 1 (non-latching): max(T_hat, reading) > sp + 10 K forces the
          power command to 0; stage 2a: for 0.5 s the bus current exceeds
          0.5 A with the command 0, or exceeds the recent command's current
          (P_cmd / 100 V) by 2.5 A -> latch (power stage not obeying);
          stage 2b: over target with command 0 for rise_hold_s and still
          rising rise_min_k over rise_window_s -> latch (current sensing
          broken too).

Kept in both builds: the absolute 300 degC / non-finite check on every
10 ms read (L-abs). C1 builds (D-OPEN) first classify each conversion with
rtd_convert_classify_failure: a code >= RTD_C1_FAIL_HIGH_CODE (850 degC) or
<= RTD_C1_FAIL_LOW_CODE (-200 degC), or 07h bits D5..D2, is a sensor failure
and goes to the recoverable PROBE_OPEN / PROBE_SHORT path (rtd_fail_code)
instead of the 300 degC RUNAWAY latch (C_abs); every other reading above
300 degC still latches RUNAWAY. The legacy equal-reading ADC_STUCK check (49 equal
10 ms reads, L-stuck) is evaluated here too; C1 builds replace it with the
rtd_service checks: no conversion (DRDY) for 6 ticks, 60 ms (rtd_stale), and
RTD_C1_FROZEN_CONVERSIONS = 250 identical 50 Hz codes, 5 s (rtd_frozen).

The run closes the firmware C1 loop (pan_temp_loop.c, D1 on) and the C
supervisor (stage 1 acting, as main/pan_control.c runs it) around the r2/r3
truth plant. The MAX31865 is modelled as a 50 Hz conversion stream quantised
to the 15-bit code (Rref 430 ohm, ~0.034-0.037 K/LSB) with per-conversion
noise sigma in {0.3 LSB, 1 LSB, 0.2 K (the screens' design noise)}; the
10 ms state-machine tick j reads conversion j // 2; the 100 ms control
period reads the latest conversion. Bus current = P / 120 V.

Scenarios (each at the three noise levels): design (4 pans x h_c extremes),
hot pan placed at sp1 and sp1 + 40 K, h_c steps, food drop, contact loss,
setpoint decrease by 30 K (user TEMP_DOWN), and the faults: power stage
stuck on at 600/1200/1800 W from 250 s with current sensing working and
broken (reads 0), RTD open / short (MAX31865 fault bit, code saturated),
conversions stop (no DRDY), and a reading frozen at 250 s with the setpoint
step at 360 s (the loop then heats a pan it cannot see: a real runaway with
contact).

Bus-current sense plausibility (D-ISENSE, components/control/current_sense_
check.c, through the cosim shim): isense = (a) the command in force has been
>= 300 W for > 0.3 s and the bus current reads <= 0.5 A for 0.5 s;
isense_pulse = (b) the start-up pulse (360 W for 1.0 s at PREHEAT entry, mean
current after 0.3 s must exceed 0.5 A). The pulse is evaluated passively at
t = 0 against the sense as it is at power-up: the plant receives the loop's
command over those 1.1 s, not the pulse's 360 W (the trajectories, and every
number measured on them, stay those of the loop alone). The sense either
works throughout, or reads 0 A from sense_dead_at: = fault_t for the
simultaneous double fault (the existing current_broken runs; stage 2b's
case), 0 (dead at power-up: the pulse) or 100 s (dies mid-cook: (a)) for a
latent sense failure before the stage sticks at fault_t. sense_latent runs
kill the sense with no other fault and measure (a)'s latency per pan; burst
runs repeat every benign non-loss run with the stage in burst mode below its
floor (BURST_FLOOR_W = 160 W, period 20 s, on for P / 160 of it, bus current
160 W / 120 V while on and 0 between).

Every run is passive for the trip rules (they are recorded, not acted on) so
each rule's first-trip time is measured on the same trajectory; fault runs
are repeated with the C1 trips acting (hardware-latched trips cut the power
stage, contact loss zeroes the command) to report the pan peak.

Stage 2b's three parameters are swept on the same runs (one C supervisor
instance per variant, identical inputs) and the chosen values are checked
against every non-fault run.

Run: python runaway_checks.py [--lib path] [--out runaway-checks.json]
Exit 0 iff every C1 check passes (see `checks` in the JSON).
"""
from __future__ import annotations

import argparse
import ctypes
import itertools
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
from ref import es, screen  # noqa: E402

R_REF, R0 = 430.0, 100.0
CVD_A, CVD_B, CVD_C = 3.9083e-3, -5.775e-7, -4.183e-12
SELF_HEATING_K = 0.061
LSB_OHM = R_REF / 32768.0
V_BUS = 120.0
T_ABS = 300.0
NOISES = (("0.3LSB", 0.3), ("1LSB", 1.0), ("0.2K", None))
FAULT_T = 250.0
STUCK_ON_W = (600.0, 1800.0, 1200.0)
# Stage 2b sweep (hold s, window s, rise K); the firmware default is CHOSEN.
SWEEP_HOLD = (5.0, 10.0, 20.0, 30.0, 60.0)
SWEEP_WIN = (5.0, 10.0, 20.0)
SWEEP_RISE = (1.0, 2.0, 4.0)
# Must equal psup_default_params (pan_supervisor.c) and lie on the grid.
CHOSEN = (20.0, 5.0, 2.0)
HW_TRIPS = ("C_abs", "R1", "R2a", "R2b", "rtd_fault", "rtd_fail_code", "rtd_stale", "rtd_frozen", "guard",
            "isense", "isense_pulse")
ISENSE = ("isense", "isense_pulse")
# rtd_convert.h (D-OPEN): sensor-failure codes and 07h input-fault bits.
RTD_C1_FAIL_HIGH_CODE = 29757
RTD_C1_FAIL_LOW_CODE = 1411
RTD_FAULT_INPUT_BITS = 0x3C
# Power stage burst mode below its continuous floor (D-ISENSE false-trip runs).
BURST_FLOOR_W = 160.0
BURST_PERIOD_S = 20.0
# Latent sense failure: the bus-current sense reads 0 from these times.
LATENT_SENSE_AT = (0.0, 100.0)
SENSE_LATENT_AT = (30.0, 100.0, 200.0)
LEGACY = ("L_abs", "L_rate", "L_over", "L_stuck", "L_rtd")
# The legacy rules that respond to each fault (its time budget). L_rate is
# excluded everywhere: no scenario, fault or not, sustains more than 4 K/s
# (r1 margins), so its trips are noise and placement transients, not
# detections.
LEGACY_DETECT = {"fault_stuck_on": ("L_over", "L_abs"), "fault_open": ("L_abs", "L_rtd", "L_over"),
                 "fault_short": ("L_abs", "L_rtd", "L_over"), "fault_nodrdy": ("L_stuck", "L_abs", "L_over"),
                 "fault_frozen": ("L_stuck", "L_abs", "L_over")}
# Where C1 may be later than the legacy budget, and why (DECISIONS.md D-RUN):
ALLOWED_LATER = {
    "fault_stuck_on/current_broken": "double fault (power stage stuck on AND bus-current sense reading 0): "
                                     "stage 2b waits rise_hold_s; bounded by the reported T_c at detection, "
                                     "the absolute 300 degC check and the hardware trips",
    "fault_frozen": "a frozen code is caught after RTD_C1_FROZEN_CONVERSIONS (5 s); the legacy 0.49 s "
                    "equal-reading check false-trips on quantised C1 readings (legacy_false_trips.L_stuck)",
}
# rtd_service.h RTD_C1_FROZEN_CONVERSIONS: 5 s of identical 50 Hz codes.
FROZEN_CONVERSIONS = 250


def r_of_t(t):
    if t >= 0.0:
        return R0 * (1.0 + CVD_A * t + CVD_B * t * t)
    return R0 * (1.0 + CVD_A * t + CVD_B * t * t + CVD_C * (t - 100.0) * t ** 3)


def t_of_code(code):
    """rtd_convert_code_to_c (rtd_convert.c), loading correction off."""
    r = code / 32768.0 * R_REF
    if r <= 0.0:
        return float("nan")
    ratio = r / R0
    disc = CVD_A * CVD_A - 4.0 * CVD_B * (1.0 - ratio)
    t = (-CVD_A + math.sqrt(disc)) / (2.0 * CVD_B)
    if ratio < 1.0:
        for _ in range(8):
            f = 1.0 + CVD_A * t + CVD_B * t * t + CVD_C * (t - 100.0) * t ** 3 - ratio
            df = CVD_A + 2.0 * CVD_B * t + CVD_C * (4.0 * t ** 3 - 300.0 * t * t)
            step = f / df
            t -= step
            if abs(step) < 1e-7:
                break
    return t - SELF_HEATING_K


def code_of(t, rng, sigma_lsb, sigma_k):
    r = r_of_t(t)
    if sigma_k is not None:
        dr = r_of_t(t + 0.5) - r_of_t(t - 0.5)
        noise = sigma_k * dr / LSB_OHM
    else:
        noise = sigma_lsb
    c = int(math.floor(r / LSB_OHM + 0.5 + noise * rng.standard_normal()))
    return min(max(c, 0), 32767)


def rtd_failure(code, fault_status):
    """rtd_convert_classify_failure (rtd_convert.c): True for OPEN or SHORT."""
    return code >= RTD_C1_FAIL_HIGH_CODE or code <= RTD_C1_FAIL_LOW_CODE or bool(fault_status & RTD_FAULT_INPUT_BITS)


def lib():
    L = cosim.lib()
    L.sim_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double]
    L.csc_start.argtypes = [ctypes.c_void_p]
    L.csc_start.restype = ctypes.c_int
    L.csc_run.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
    L.csc_run.restype = ctypes.c_int
    L.csc_pulse_arm.argtypes = [ctypes.c_void_p]
    L.csc_pulse.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                            ctypes.POINTER(ctypes.c_double)]
    L.csc_pulse.restype = ctypes.c_int
    return L


def sense_alive(case, t):
    if case.get("current_ok", True):
        return True
    return t < case.get("sense_dead_at", case.get("fault_t", FAULT_T)) - 1e-9


def pulse_trip(L_, h, alive):
    """(b) at PREHEAT entry, passive: the stage obeys the pulse; the sense reads
    it if alive. Returns the latch time after session start, or None."""
    L_.csc_pulse_arm(h)
    w = ctypes.c_double(0.0)
    applied = 0.0
    for k in range(40):
        st = L_.csc_pulse(h, applied, applied / V_BUS if alive else 0.0, es.P_MAX, ctypes.byref(w))
        if st == 4:
            return round(k * es.DT_CTRL, 2)
        if st == 3:
            return None
        applied = w.value
    raise AssertionError("pulse did not finish")


def sup_variant_params():
    return list(itertools.product(SWEEP_HOLD, SWEEP_WIN, SWEEP_RISE))


def run(case):
    """One run. Returns first-trip times (s) per rule, temperatures at them,
    peaks, and the stage 2b sweep's first-trip times."""
    L_ = lib()
    screen.apply(ref.C1)
    pan = es.PANS[case["pan"]]
    tr = ref.HotTruth(pan, case["h"], case["eta"], case["seed"], food_at=case.get("food_at"),
                      T_hot=case.get("T_hot"))
    rng = np.random.default_rng(case["seed"] + 7)
    sp1, sp2 = pan["sp"]
    sigma_lsb, sigma_k = case["noise_lsb"], case["noise_k"]
    fault = case.get("fault")
    fault_t = case.get("fault_t", FAULT_T)
    acting = case["acting"]

    h = L_.sim_new()
    for key, v in cosim.FW_K.items():
        assert L_.sim_set(h, key.encode(), v) == 0
    assert L_.sim_set(h, b"decay_tau", cosim.FW_K["c_cap"] / cosim.FW_K["g_leak"]) == 0
    for key, v in case.get("params", {}).items():
        assert L_.sim_set(h, key.encode(), v) == 0, key
    assert L_.sim_start(h, es.T_AMB) == 0
    assert L_.sup_start(h) == 0
    assert L_.csc_start(h) == 0
    variants = []
    for hold, win, rise in ([] if case.get("no_sweep") else sup_variant_params()):
        hv = L_.sim_new()
        for key, v in (("sup_rise_hold", hold), ("sup_rise_window", win), ("sup_rise_min", rise)):
            assert L_.sim_set(hv, key.encode(), v) == 0
        assert L_.sup_start(hv) == 0
        variants.append(hv)

    out = (ctypes.c_double * len(cosim.OUT))()
    so = (ctypes.c_double * 3)()
    vo = (ctypes.c_double * 3)()
    first = {}
    after = {}
    at = {}
    trace_tc = []
    same_code = 0
    max_same_code = 0
    prev_code = None
    var_first = [None] * len(variants)
    isense_seen = False

    def trip(rule, t):
        # first: any time (false trips); after: first at or after the fault.
        if rule not in first:
            first[rule] = round(t, 2)
        if fault is not None and t >= fault_t - 1e-9 and rule not in after:
            after[rule] = round(t, 2)
            at[rule] = {"T_c": round(tr.T_c(), 1), "T_mean": round(tr.T_mean(), 1)}

    P_cmd = 0.0
    P_true = 0.0
    h_now = case["h"]
    code = code_of(tr.Tel, rng, sigma_lsb, sigma_k)
    reading = t_of_code(code)
    prev_tick = None
    equal_ticks = 0
    armed = False
    cut = False          # hardware latch: power stage disabled
    cmd_off = False      # contact lost: command 0 (NO_PAN)
    frozen_code = None
    last_fresh_tick = 0
    tick = 0
    peak_tc = peak_tm = -1e9
    force_zero_s = 0.0
    pt = pulse_trip(L_, h, sense_alive(case, 0.0))
    if pt is not None:
        trip("isense_pulse", pt)
        isense_seen = True
    r1_blocks = []
    blk_sum, blk_n = 0.0, 0
    for k in range(int(es.T_END / es.DT_CTRL)):
        t = k * es.DT_CTRL
        sp = sp1 if t + es.DT_CTRL < es.SP_STEP_T else sp2
        if case.get("sp_down_at") is not None and t >= case["sp_down_at"]:
            sp = sp1 - 30.0
        if case.get("loss_at") is not None and t >= case["loss_at"]:
            h_now = 2.0
        if case.get("h_step") is not None and t >= case["h_step"][0]:
            h_now = case["h_step"][1]
        fault_on = fault is not None and t >= fault_t
        fault_status = 0
        fresh_any = False
        p_in_force = 0.0 if (cut or cmd_off) else P_cmd
        p_stage = p_in_force
        if case.get("burst") and 0.0 < p_stage < BURST_FLOOR_W:
            on = (t % BURST_PERIOD_S) < BURST_PERIOD_S * p_stage / BURST_FLOOR_W
            p_stage = BURST_FLOOR_W if on else 0.0
        for _ in range(round(es.DT_CTRL / es.DT_SIM)):
            P_true = cosim.deliver(p_stage, "measured")
            if fault_on and fault[0] == "stuck_on" and not cut:
                P_true = fault[1]
            tr.step(P_true, h_now)
            peak_tc, peak_tm = max(peak_tc, tr.T_c()), max(peak_tm, tr.T_mean())
            new_conv = True
            if fault_on and fault[0] == "open":
                code, fault_status = 32767, 0x80
            elif fault_on and fault[0] == "short":
                code, fault_status = 0, 0x40
            elif fault_on and fault[0] == "nodrdy":
                new_conv = False
            elif fault_on and fault[0] == "frozen":
                frozen_code = code if frozen_code is None else frozen_code
                code = frozen_code
            else:
                code = code_of(tr.Tel, rng, sigma_lsb, sigma_k)
            if new_conv:
                reading = t_of_code(code)
                fresh_any = True
                # rtd_service C1: identical codes for RTD_C1_FROZEN_CONVERSIONS
                same_code = same_code + 1 if code == prev_code else 0
                prev_code = code
                if not fault_on:
                    max_same_code = max(max_same_code, same_code + 1)
                if same_code + 1 >= FROZEN_CONVERSIONS:
                    trip("rtd_frozen", tick * 0.01)
            for _tick in range(2):
                tt = tick * 0.01
                tick += 1
                if new_conv:
                    last_fresh_tick = tick
                # --- legacy rules (passive) ---
                if not math.isfinite(reading) or reading > T_ABS:
                    trip("L_abs", tt)
                    # C1 (D-OPEN): a sensor-failure conversion is PROBE_OPEN /
                    # PROBE_SHORT, every other one above 300 degC RUNAWAY.
                    if rtd_failure(code, fault_status):
                        trip("rtd_fail_code", tt)
                    else:
                        trip("C_abs", tt)
                if prev_tick is not None and math.isfinite(reading) and math.isfinite(prev_tick):
                    if (reading - prev_tick) / 0.01 > 15.0:
                        trip("L_rate", tt)
                equal_ticks = equal_ticks + 1 if reading == prev_tick else 0
                if equal_ticks >= 49:
                    trip("L_stuck", tt)
                prev_tick = reading
                r_ohm = code * LSB_OHM
                if fault_on and fault[0] in ("open", "short") and (r_ohm >= 300.0 or r_ohm <= 10.0):
                    trip("L_rtd", tt)
                if math.isfinite(reading) and reading >= sp - 10.0:
                    armed = True
                if armed and math.isfinite(reading) and reading > sp + 10.0:
                    trip("L_over", tt)
                # --- C1 per-tick rules ---
                if L_.sup_rate(h, reading, int(round(tt * 1000))):
                    trip("R1", tt)
                if math.isfinite(reading):
                    blk_sum += reading
                    blk_n += 1
                if blk_n == 100:
                    r1_blocks.append(blk_sum / blk_n)
                    blk_sum, blk_n = 0.0, 0
                if tick - last_fresh_tick >= 6:
                    trip("rtd_stale", tt)
            if new_conv and fault_status:
                trip("rtd_fault", tick * 0.01)
        if k % 10 == 0:
            trace_tc.append(round(tr.T_c(), 1))
        ntc = tr.sink() + es.NTC_BIAS
        y = reading if math.isfinite(reading) else 0.0
        L_.sim_step(h, y, ntc, sp, P_true, 0, 1 if fresh_any else 0, 1, fault_status, out)
        o = dict(zip(cosim.OUT, out))
        if o["fault"]:
            trip("guard", t)
        if o["cc_event"] == cosim.CC_EVT_LOST:
            trip("contact_lost", t)
        P_cmd = o["p_cmd"]
        i_bus = P_true / V_BUS if sense_alive(case, t) else 0.0
        # D-ISENSE (a): the command in force over this period, the bus
        # current at its end (before this period's command is decided).
        if not isense_seen and L_.csc_run(h, p_in_force, i_bus):
            trip("isense", t)
            isense_seen = True
        L_.sup_step(h, o["t_hat"], reading, sp, P_cmd, i_bus, 1, so)
        if so[0]:
            P_cmd = 0.0
            force_zero_s += es.DT_CTRL
        if so[1] == 1:
            trip("R2a", t)
        if so[1] == 2:
            trip("R2b", t)
        for i, hv in enumerate(variants):
            L_.sup_step(hv, o["t_hat"], reading, sp, P_cmd, i_bus, 1, vo)
            if vo[1] == 2 and var_first[i] is None:
                var_first[i] = round(t, 1)
        if acting:
            if any(r in first for r in HW_TRIPS):
                cut = True
            if "contact_lost" in first:
                cmd_off = True
    L_.sim_free(h)
    for hv in variants:
        L_.sim_free(hv)
    rises = np.diff(np.array(r1_blocks)) if len(r1_blocks) > 1 else np.zeros(1)
    sustained = max((rises[i:i + 5].min() for i in range(max(len(rises) - 4, 1))), default=0.0)
    return {**{k: v for k, v in case.items() if k != "params"}, "first": first, "after": after, "at": at,
            "max_identical_codes": max_same_code, "trace_T_c_1s": trace_tc,
            "peak_T_c": round(peak_tc, 1), "peak_T_mean": round(peak_tm, 1),
            "stage1_s": round(force_zero_s, 1), "r1_max_5block_rise_K_per_s": round(float(sustained), 2),
            "r1_max_block_rise_K_per_s": round(float(rises.max()), 2), "sweep_2b": var_first,
            "sense_dead_at": None if case.get("current_ok", True) else case.get("sense_dead_at", fault_t)}


def scenarios():
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    base = []
    seed = 900
    for pan, (lo, hi) in spread.items():
        for hc in (lo, hi):
            base.append(dict(name=f"design/{pan}/h{hc:.0f}", kind="design", pan=pan, h=hc, eta=0.82, seed=seed))
            seed += 1
    for pan in ("cast_iron_26", "carbon_steel_28", "triply_clad_24"):
        lo, hi = spread[pan]
        for dT in (0.0, 40.0):
            base.append(dict(name=f"hot_pan/{pan}/+{dT:.0f}", kind="hot_pan", pan=pan, h=(lo * hi) ** 0.5, eta=0.82,
                             seed=seed, T_hot=float(es.PANS[pan]["sp"][0]) + dT))
            seed += 1
    for pan in ("carbon_steel_28", "triply_clad_24"):
        for h0, h1 in ((1000.0, 300.0), (300.0, 3000.0)):
            base.append(dict(name=f"h_step/{pan}/{h0:.0f}->{h1:.0f}", kind="h_step", pan=pan, h=h0, eta=0.88,
                             seed=seed, h_step=(cosim.HSTEP_T, h1)))
            seed += 1
    for pan, (lo, hi) in spread.items():
        hm = (lo * hi) ** 0.5
        if pan != "disc_pot_water_1l5":
            base.append(dict(name=f"food/{pan}", kind="food", pan=pan, h=hm, eta=0.82, seed=seed, food_at=cosim.FOOD_T))
        base.append(dict(name=f"loss/{pan}", kind="loss", pan=pan, h=hm, eta=0.82, seed=seed + 1,
                         loss_at=cosim.LOSS_T))
        base.append(dict(name=f"sp_down/{pan}", kind="sp_down", pan=pan, h=hm, eta=0.82, seed=seed + 2,
                         sp_down_at=450.0))
        seed += 3
    benign_base = list(base)
    for pan in ("triply_clad_24", "cast_iron_26"):
        lo, hi = spread[pan]
        for pw in STUCK_ON_W:
            for cur in (True, False):
                base.append(dict(name=f"stuck_on/{pan}/{pw:.0f}W/{'current_ok' if cur else 'current_broken'}",
                                 kind="fault_stuck_on", pan=pan, h=(lo * hi) ** 0.5, eta=0.82, seed=seed,
                                 fault=("stuck_on", pw), current_ok=cur))
                if not cur:
                    # The same double fault with the sense failing first
                    # (latent); same seed, so the same passive trajectory.
                    for at in LATENT_SENSE_AT:
                        base.append(dict(name=f"stuck_on/{pan}/{pw:.0f}W/current_broken_latent_{at:.0f}s",
                                         kind="fault_stuck_on", pan=pan, h=(lo * hi) ** 0.5, eta=0.82, seed=seed,
                                         fault=("stuck_on", pw), current_ok=False, sense_dead_at=at, latent=True,
                                         no_sweep=True))
                seed += 1
    lo, hi = spread["carbon_steel_28"]
    for f in ("open", "short", "nodrdy"):
        base.append(dict(name=f"sensor_{f}/carbon_steel_28", kind=f"fault_{f}", pan="carbon_steel_28",
                         h=(lo * hi) ** 0.5, eta=0.82, seed=seed, fault=(f,)))
        seed += 1
    for pan, (lo, hi) in spread.items():
        base.append(dict(name=f"frozen/{pan}", kind="fault_frozen", pan=pan, h=(lo * hi) ** 0.5, eta=0.82,
                         seed=seed, fault=("frozen",)))
        # frozen mid first heat-up, at full power: the worst rise while the
        # check waits
        base.append(dict(name=f"frozen_ramp/{pan}", kind="fault_frozen", pan=pan, h=(lo * hi) ** 0.5, eta=0.82,
                         seed=seed + 50, fault=("frozen",), fault_t=20.0))
        seed += 1
    for b in benign_base:
        if b["kind"] != "loss":
            base.append({**b, "name": "burst/" + b["name"], "kind": "burst_" + b["kind"], "burst": True})
    for pan, (lo, hi) in spread.items():
        for at in SENSE_LATENT_AT:
            base.append(dict(name=f"sense_latent/{pan}/{at:.0f}s", kind="sense_latent", pan=pan, h=(lo * hi) ** 0.5,
                             eta=0.82, seed=seed, current_ok=False, sense_dead_at=at, no_sweep=True))
            seed += 1
    out = []
    for nname, lsb in NOISES:
        for b in base:
            for acting in ((False, True) if b["kind"].startswith("fault") or b["kind"] == "loss" else (False,)):
                out.append({**b, "fault_t": b.get("fault_t", FAULT_T), "noise": nname, "noise_lsb": lsb if lsb is not None else 0.0,
                            "noise_k": None if lsb is not None else screen.NOISE, "acting": acting})
    return out


def first_of(r, rules):
    ts = [r["after"][k] for k in rules if k in r["after"]]
    return min(ts) if ts else None


def hazardous(r):
    """A sensor fault always must be caught; a stuck-on power stage only if,
    left alone, it takes the pan over the final setpoint + 10 K."""
    if r["kind"] != "fault_stuck_on":
        return True
    return r["peak_T_c"] > es.PANS[r["pan"]]["sp"][1] + 10.0


def analyse(rows):
    params = sup_variant_params()
    passive = [r for r in rows if not r["acting"]]
    benign = [r for r in passive if not r["kind"].startswith("fault") and r["kind"] != "sense_latent"]
    faults = [r for r in passive if r["kind"].startswith("fault")]
    legacy_false = {}
    nonloss = [r for r in benign if r["kind"] != "loss" and not r.get("burst")]
    for rule in ("L_rate", "L_over", "L_stuck", "L_abs"):
        hit = [r["name"] + "@" + r["noise"] for r in nonloss if rule in r["first"]]
        legacy_false[rule] = {"runs": len(hit), "of": len(nonloss), "examples": hit[:12]}
    # C1 false trips: any C1 trip in a benign run (contact loss only counts
    # outside loss runs), or before the fault in a fault run.
    c1_false = [(r["name"], r["noise"], r["first"]) for r in benign
                if any(k in r["first"] for k in HW_TRIPS) or (r["kind"] != "loss" and "contact_lost" in r["first"])]
    def early(r, k):
        # Before the fault, and (for the current-sense rules) before the sense
        # itself failed: a latent sense failure caught early is a detection.
        if k in ISENSE and r["sense_dead_at"] is not None:
            return r["first"][k] < r["sense_dead_at"]
        return r["first"][k] < r["fault_t"]

    c1_false += [(r["name"], r["noise"], r["first"]) for r in faults
                 if any(early(r, k) for k in HW_TRIPS + ("contact_lost",) if k in r["first"])]
    sense_lat = [r for r in passive if r["kind"] == "sense_latent"]
    c1_false += [(r["name"], r["noise"], r["first"]) for r in sense_lat
                 if any(early(r, k) for k in HW_TRIPS + ("contact_lost",) if k in r["first"])]
    broken = [r for r in faults if r["kind"] == "fault_stuck_on" and not r["current_ok"] and hazardous(r)
              and not r.get("latent")]
    benign_sw = [r for r in benign if not r.get("no_sweep")]
    faults_sw = [r for r in faults if not r.get("no_sweep")]
    sweep = []
    for i, (hold, win, rise) in enumerate(params):
        fp = sum(r["sweep_2b"][i] is not None for r in benign_sw) + sum(
            r["sweep_2b"][i] is not None and r["sweep_2b"][i] < r["fault_t"] for r in faults_sw)
        fp_ex = [r["name"] + "@" + r["noise"] for r in benign_sw if r["sweep_2b"][i] is not None][:6]
        det = [(r["sweep_2b"][i], r) for r in broken]
        ok = [(d, r) for d, r in det if d is not None]
        sweep.append({"hold_s": hold, "window_s": win, "rise_k": rise, "false_trips": fp,
                      "detected": len(ok), "of": len(det),
                      "false_trip_examples": fp_ex,
                      "worst_detect_after_fault_s": round(max(d - r["fault_t"] for d, r in ok), 1) if ok else None,
                      "worst_T_c_at_detect": max(r["trace_T_c_1s"][min(int(d), len(r["trace_T_c_1s"]) - 1)]
                                                 for d, r in ok) if ok else None})
    fault_table = []
    for r in faults:
        act = next(a for a in rows if a["acting"] and a["name"] == r["name"] and a["noise"] == r["noise"])
        fc, fl = first_of(r, HW_TRIPS + ("contact_lost",)), first_of(r, LEGACY_DETECT[r["kind"]])
        ft = r["fault_t"]
        fault_table.append({
            "name": r["name"], "kind": r["kind"], "noise": r["noise"], "hazardous": hazardous(r),
            "passive_peak_T_c": r["peak_T_c"],
            "legacy_first_s_after_fault": None if fl is None else round(fl - ft, 2),
            "legacy_rules": {k: round(v - ft, 2) for k, v in r["after"].items() if k in LEGACY},
            "c1_first_s_after_fault": None if fc is None else round(fc - ft, 2),
            "c1_rules": {k: round(v - ft, 2) for k, v in r["after"].items() if k not in LEGACY},
            "at_trip": r["at"],
            "acting_peak_T_c": act["peak_T_c"], "acting_peak_T_mean": act["peak_T_mean"],
            "acting_c1_rules": sorted(k for k in act["after"] if k not in LEGACY),
            "sense_dead_at": r["sense_dead_at"],
            "sense_fault_caught_s": min((r["first"][k] for k in ISENSE if k in r["first"]), default=None),
        })
    loss_rows = [r for r in rows if r["kind"] == "loss" and r["acting"]]
    loss = [{"name": r["name"], "noise": r["noise"], "contact_lost_s_after": None if "contact_lost" not in r["first"]
             else round(r["first"]["contact_lost"] - cosim.LOSS_T, 1),
             "hw_trips": [k for k in HW_TRIPS if k in r["first"]], "peak_T_c": r["peak_T_c"]} for r in loss_rows]
    # D-ISENSE: latent sense failures, and a sense dying with no other fault.
    latent = [{"name": f["name"], "noise": f["noise"], "sense_dead_at": f["sense_dead_at"],
               "caught_s": f["sense_fault_caught_s"], "stuck_on_at_s": FAULT_T,
               "acting_peak_T_c": f["acting_peak_T_c"], "passive_peak_T_c": f["passive_peak_T_c"]}
              for f in fault_table if "latent" in f["name"]]
    simultaneous = [{"name": f["name"], "noise": f["noise"], "hazardous": f["hazardous"],
                     "isense_s_after_fault": f["c1_rules"].get("isense"),
                     "R2b_s_after_fault": f["c1_rules"].get("R2b"),
                     "acting_peak_T_c": f["acting_peak_T_c"]}
                    for f in fault_table if f["name"].endswith("/current_broken")]
    sense_alone = [{"name": r["name"], "noise": r["noise"], "sense_dead_at": r["sense_dead_at"],
                    "latency_s": None if "isense" not in r["first"] else round(r["first"]["isense"] - r["sense_dead_at"], 1)}
                   for r in sense_lat]
    burst = [r for r in benign if r.get("burst")]
    isense = {"latent_before_stuck_on": latent, "simultaneous_double_fault": simultaneous,
              "sense_dies_alone": sense_alone,
              "sense_dies_alone_worst_latency_s": max((x["latency_s"] for x in sense_alone if x["latency_s"] is not None),
                                                       default=None),
              "sense_dies_alone_not_caught_in_run": [x["name"] + "@" + x["noise"] for x in sense_alone
                                                     if x["latency_s"] is None],
              "benign_runs": len([r for r in benign if r["kind"] != "loss" and not r.get("burst")]),
              "burst_runs": len(burst),
              "isense_false_trips": [(r["name"], r["noise"]) for r in benign if any(k in r["first"] for k in ISENSE)]}
    margins = {"r1_benign_max_5block_rise_K_per_s": max(r["r1_max_5block_rise_K_per_s"] for r in benign),
               "r1_benign_max_1block_rise_K_per_s": max(r["r1_max_block_rise_K_per_s"] for r in benign),
               "r1_fault_max_5block_rise_K_per_s": max(r["r1_max_5block_rise_K_per_s"] for r in faults),
               "frozen_threshold_conversions": FROZEN_CONVERSIONS,
               "max_identical_codes_by_noise": {n: max(r["max_identical_codes"] for r in passive if r["noise"] == n)
                                                for n, _ in NOISES}}
    return legacy_false, c1_false, sweep, fault_table, loss, margins, isense


def checks(c1_false, sweep, fault_table, loss, chosen, isense):
    ch = {}
    ch["c1_no_false_trip"] = not c1_false
    ch["isense_no_false_trip_incl_burst"] = not isense["isense_false_trips"] and isense["burst_runs"] > 0
    ch["latent_sense_failure_caught_before_stuck_on"] = bool(isense["latent_before_stuck_on"]) and all(
        x["caught_s"] is not None and x["caught_s"] < x["stuck_on_at_s"] for x in isense["latent_before_stuck_on"])
    row = next(s for s in sweep if (s["hold_s"], s["window_s"], s["rise_k"]) == chosen)
    half = next((s for s in sweep if (s["hold_s"], s["window_s"], s["rise_k"]) == (chosen[0] / 2, chosen[1], chosen[2])),
                None)
    ch["chosen_2b_no_false_trip"] = row["false_trips"] == 0
    ch["chosen_2b_margin_half_hold_no_false_trip"] = half is not None and half["false_trips"] == 0
    ch["chosen_2b_detects_every_hazardous_double_fault"] = row["detected"] == row["of"]
    uncaught, late, hot = [], [], []
    for f in fault_table:
        if not f["hazardous"]:
            continue
        tag = f["name"] + "@" + f["noise"]
        c1, leg = f["c1_first_s_after_fault"], f["legacy_first_s_after_fault"]
        if c1 is None:
            uncaught.append(tag)
            continue
        key = f["kind"] + ("/current_broken" if "current_broken" in f["name"] else "")
        if leg is not None and c1 > leg + 1e-9 and key not in ALLOWED_LATER:
            late.append(tag)
        first_rule = min(f["c1_rules"], key=f["c1_rules"].get)
        if f["at_trip"][first_rule]["T_c"] > T_ABS + 1.0:
            hot.append(tag)
    ch["every_hazardous_fault_caught_by_c1"] = not uncaught
    ch["c1_not_later_than_legacy_except_allowed"] = not late
    ch["c1_trips_before_T_c_exceeds_301"] = not hot
    ch["contact_loss_detected_le_21s"] = all(l["contact_lost_s_after"] is not None and l["contact_lost_s_after"] <= 21.0
                                             for l in loss)
    return ch, uncaught, late, hot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "runaway-checks.json"))
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    chosen = CHOSEN
    cs = scenarios()
    with Pool(min(10, os.cpu_count() or 1), initializer=cosim._init, initargs=(args.lib,)) as pool:
        rows = pool.map(run, cs)
    legacy_false, c1_false, sweep, fault_table, loss, margins, isense = analyse(rows)
    ch, uncaught, late, hot = checks(c1_false, sweep, fault_table, loss, chosen, isense)
    out = {"scope": __doc__.strip(), "chosen_2b": dict(zip(("hold_s", "window_s", "rise_k"), chosen)),
           "allowed_later_than_legacy": ALLOWED_LATER,
           "checks": ch, "all_pass": all(ch.values()), "uncaught": uncaught, "c1_later_than_legacy": late,
           "c1_trip_above_301": hot, "legacy_false_trips": legacy_false, "c1_false_trips": c1_false,
           "margins": margins,
           "stage_2b_sweep": sweep, "current_sense": isense, "faults": fault_table, "contact_loss": loss,
           "rows": [{k: v for k, v in r.items() if k not in ("sweep_2b", "trace_T_c_1s")} for r in rows]}
    Path(args.out).write_text(json.dumps(out, indent=1, default=float) + "\n")
    print("legacy false trips (benign runs):", {k: f"{v['runs']}/{v['of']}" for k, v in legacy_false.items()})
    print("C1 false trips:", c1_false or "none")
    print("margins:", margins)
    print("2b sweep (hold, window, rise): false trips / detected hazardous double faults / worst s / worst T_c")
    for s in sweep:
        mark = " <- chosen" if (s["hold_s"], s["window_s"], s["rise_k"]) == chosen else ""
        print(f"   {s['hold_s']:5.0f} {s['window_s']:4.0f} {s['rise_k']:3.0f}: {s['false_trips']:3d} "
              f"{s['detected']}/{s['of']} {s['worst_detect_after_fault_s']} {s['worst_T_c_at_detect']}{mark}")
    print("faults at 1 LSB (all noises in the JSON; s after fault; legacy -> C1; acting peak T_c):")
    for f in fault_table:
        if f["noise"] != "1LSB":
            continue
        print(f"   {'' if f['hazardous'] else '(not hazardous) '}{f['name']:45s} {f['noise']:6s} legacy {f['legacy_first_s_after_fault']!s:>7} "
              f"C1 {f['c1_first_s_after_fault']!s:>7} {sorted(f['c1_rules'])} peak {f['acting_peak_T_c']}")
    print("current sense (D-ISENSE): benign", isense["benign_runs"], "+ burst", isense["burst_runs"],
          "false trips", isense["isense_false_trips"] or "none")
    for x in isense["latent_before_stuck_on"]:
        if x["noise"] == "1LSB":
            print(f"   latent {x['name']:52s} dead at {x['sense_dead_at']:5.1f} s caught {x['caught_s']} s "
                  f"(stuck on at {x['stuck_on_at_s']:.0f} s) acting peak {x['acting_peak_T_c']}")
    for x in isense["simultaneous_double_fault"]:
        if x["noise"] == "1LSB":
            print(f"   simultaneous {x['name']:40s} isense +{x['isense_s_after_fault']} R2b +{x['R2b_s_after_fault']} "
                  f"acting peak {x['acting_peak_T_c']}")
    print("   sense dies alone: worst latency", isense["sense_dies_alone_worst_latency_s"], "s; not caught in run:",
          isense["sense_dies_alone_not_caught_in_run"] or "none")
    print("contact loss:", [(l["name"], l["noise"], l["contact_lost_s_after"], l["hw_trips"]) for l in loss])
    print("CHECKS", ch)
    print("ALL RUNAWAY CHECKS PASS" if out["all_pass"] else "RUNAWAY CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
