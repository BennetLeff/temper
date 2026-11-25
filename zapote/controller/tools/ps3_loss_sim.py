#!/usr/bin/env python3
"""PS3 / blower-buck / logic-rail behaviour after the J13 rail merge (DECISIONS C49), C51: MPM-90-15ST and the face fan.

    python3 tools/ps3_loss_sim.py [--json OUT]        (stdlib only, deterministic; exit 1 if a check fails)

Behavioural bounds, not SPICE. Datasheet inputs (read 2026-10-18, files not stored in the repo):
  MEAN WELL MPM-90-SPEC 2024-10-30 p.2/p.3: 15 V, 5.67 A / 85.05 W convection, 93.5 W peak (10 s, <= 33 % duty, average
    <= rated); overload "115% ~ 160% rated output power", hiccup, auto-recovery (hiccup timing not stated); voltage
    tolerance +/-2 %; hold-up 10 ms at 115 VAC full load (typ.); setup 1000 ms; derating at 100 VAC: 100 % to 50 C, 75 % at
    60 C, 50 % at 70 C, 25 % at 80 C (graph, read by eye); output derating 80 % at 80 VAC, 100 % from 100 VAC.
  TI TPS62933 SLUSEA4D: I_SS 4.5 / 5.5 / 6.5 uA, VREF 0.8 V, t_SS = C_SS x VREF / I_SS (eq. 6); IHS_LIMIT 4.2 / 5 / 5.8 A;
    hiccup after 256 us in current limit, off for 10.5 x t_SS; VIN UVLO falling 3.1-3.5 V.
Not stated in either datasheet: PS3 hiccup on/off times; the fan's start / lock current (Delta BFB1012VH-F00: 2.70 A max
operating, repo figure). Both are bench items.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller_calcs as cc  # noqa: E402

# ---- PS3 (one table for every calculation: controller_calcs.PS3_PARTS)
PART = "MPM-90-15ST"
P_RATED = cc.PS3_PARTS[PART]["w"]
OCP_FRAC = (cc.PS3_PARTS[PART]["ocp"], 1.60)
V_OUT = 15.0
V_TOL = cc.PS3_PARTS[PART]["tol"]
DERATE = cc.PS3_PARTS[PART]["derate"]      # 15 V curve at 100 VAC, ambient C -> load fraction
HOLDUP_115VAC_MS = cc.PS3_PARTS[PART]["holdup_ms"]
P_FACE_FAN = cc.FAN2_ALLOC_W / 0.90


def derate_frac(t_c):
    if t_c <= DERATE[0][0]:
        return 1.0
    for (t0, f0), (t1, f1) in zip(DERATE, DERATE[1:]):
        if t0 <= t_c <= t1:
            return f0 + (f1 - f0) * (t_c - t0) / (t1 - t0)
    return 0.0


def t_at_frac(frac):
    for (t0, f0), (t1, f1) in zip(DERATE, DERATE[1:]):
        if f1 <= frac <= f0:
            return t0 + (t1 - t0) * (f0 - frac) / (f0 - f1)
    return None


def run():
    b = cc.ps3_budget()
    loop_ohm = b["harness_loop_ohm"]
    i_logic = 4.83 / 15.0
    p_logic = 4.83
    v_hi = cc.blower_supply()["vout_duty0_V"][1]            # 12.40 V: the buck's duty-0 corner
    eta = 0.90
    out = {"inputs": {"p_rated_W": P_RATED, "ocp_W": [P_RATED * f for f in OCP_FRAC], "harness_loop_ohm": loop_ohm,
                      "logic_W": p_logic, "blower_v_out_hi_V": v_hi, "buck_eta": eta}}

    # 1. Load against the derating curve: the continuous PS3 load is the blower at its highest corner, the logic and the face fan.
    p_total = b["ps3_out_W"] + p_logic + P_FACE_FAN
    frac = p_total / P_RATED
    out["continuous"] = {"p_total_W": p_total, "fraction_of_rated": frac, "max_ambient_C": t_at_frac(frac),
                         "at_60C_derated_W": P_RATED * derate_frac(60.0), "fraction_of_60C_derated": p_total / (P_RATED * derate_frac(60.0))}

    # 2. How much fan current can PS3 carry before the overload trips (worst case: low trip point, +2 % ... -2 % supply)?
    def ps3_input_w(i_fan):
        p_out = v_hi * i_fan
        p = p_out / eta + p_logic + P_FACE_FAN
        i = p / (V_OUT * (1 - V_TOL))
        return p + i * i * loop_ohm                     # harness loss in the supply-to-board loop
    lo, hi = 0.0, 20.0
    p_trip_lo = P_RATED * OCP_FRAC[0]
    for _ in range(80):
        mid = (lo + hi) / 2
        if ps3_input_w(mid) < p_trip_lo:
            lo = mid
        else:
            hi = mid
    i_fan_trip = lo
    out["overload"] = {"fan_current_to_trip_lowest_ocp_A": i_fan_trip, "fan_rated_max_A": 2.70,
                       "margin_x_fan_rated_max": i_fan_trip / 2.70,
                       "buck_output_ceiling_A": [4.2 - 0.0, 5.8],      # IHS_LIMIT min / max (peak; average output is a little lower)
                       "note": "PS3 trips only if the 12 V load draws more than fan_current_to_trip_lowest_ocp_A; the buck can pass its own limit "
                               "(4.2-5.8 A peak), so a short is bounded by hiccup, and only a fan drawing >= this current can trip PS3 at start."}

    # 3. Soft-start (TPS62933 eq. 6): CSS 10 nF +/-10 %, ISS 4.5-6.5 uA.
    tss = [0.8 * c / i * 1e3 for c in (9e-9, 11e-9) for i in (6.5e-6, 4.5e-6)]
    c_out = 2 * 22e-6 * 0.8                               # 2 x 22 uF -10 % tolerance, derated again for bias
    i_cap_start = [c_out * v_hi / (t * 1e-3) for t in tss]   # charging the buck output capacitance
    out["soft_start"] = {"tSS_ms_min_max": [min(tss), max(tss)], "output_cap_charge_A": [min(i_cap_start), max(i_cap_start)],
                         "hiccup_off_ms": [10.5 * min(tss), 10.5 * max(tss)]}

    # 4. PS3 lost (hiccup, mains dip, stall): the logic rail runs from the merge bulk until the 3.3 V buck's EN stops it.
    en = cc.en_uvlo()
    v_start = 15 * (1 - V_TOL) - (b["ps3_out_A_at_low_corner"] + i_logic + P_FACE_FAN / V_OUT) * loop_ohm - 0.55    # after the Schottky (VF max)
    c_bulk = 100e-6 * 0.8 + 10e-6 * 0.5 + 0.1e-6          # 100 uF -20 %, 10 uF X7R at 14 V bias (about 50 %), 0.1 uF
    p_in = p_logic
    # constant-power load: dV/dt = -P / (C V)
    v, t = v_start, 0.0
    dt = 1e-6
    while v > en["stop_min_V"] and t < 1.0:
        v -= p_in / (c_bulk * v) * dt
        t += dt
    t_buck_stop = t
    # then the 3.3 V rail decays into its constant-power load
    c3 = 3 * 22e-6 * 0.8
    i3 = p_logic * eta / 3.3
    t_to = {}
    v3 = 3.3
    t3 = 0.0
    marks = {"TPS3703_UV_3.146V": 3.146, "driver_VDDI_UVLO_off_max_2.95V": 2.95, "driver_VDDI_UVLO_off_min_2.55V": 2.55, "MCU_brownout_2.43V": 2.43}
    seen = {}
    while v3 > 2.3 and t3 < 0.1:
        v3 -= i3 / c3 * 1e-6
        t3 += 1e-6
        for k, m in marks.items():
            if k not in seen and v3 <= m:
                seen[k] = t3 * 1e6
    out["ps3_loss"] = {"v_logic_start_V": v_start, "buck_en_stop_V": en["stop_min_V"], "logic_cap_uF": c_bulk * 1e6,
                       "t_buck_stops_ms": t_buck_stop * 1e3, "v3v3_fall_us_after_buck_stop": seen,
                       "gate_drive": "the drivers' VDDI UVLO forces the outputs low within the times above after the buck stops, before the MCU "
                                     "(brown-out about 2.43 V) can drive anything; the PERMIT path (supervisor filter, U37) is independent and not timed here",
                       "ps3_holdup_ms_115VAC": HOLDUP_115VAC_MS}

    # checks
    c = {"fan_must_draw_more_than_rated_max_to_trip_ps3": i_fan_trip > 2.70 * 1.5,
         "continuous_load_below_60C_derated": out["continuous"]["fraction_of_60C_derated"] < 1.0,
         "max_ambient_above_61C_bay": (out["continuous"]["max_ambient_C"] or 0) > 61.0,
         "logic_rail_above_buck_start": v_start >= en["start_max_V"] + 0.5,
         "buck_stops_before_3v3_collapse_into_uvlo_order_known": "driver_VDDI_UVLO_off_max_2.95V" in seen}
    out["checks"] = c
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    r = run()
    txt = json.dumps(r, indent=1)
    print(txt)
    if a.json:
        Path(a.json).write_text(txt + "\n")
    sys.exit(0 if all(r["checks"].values()) else 1)
