"""temper-aux-load-r1: how much of the inlet budget's auxiliary allowance is real?

The power stage regulates the reported inlet current
    inlet = I_ps,est * (1 + e_est) + I_aux <= 13.5 A,
and the firmware sets I_aux from datasheet AC-current figures summed linearly
(blower_aux.c: base 1.3 A = "PS1 + PS2, both IRM-20 at full load", plus the PS3
blower term). This script totals the actual auxiliary loads of the current
design, models each module's AC input current, and measures what adding that
current does to the RMS of the total inlet current.

Design state read (read-only, 2026-10-15):
- power stage s38+ (DECISIONS 47 / 50): PS1 deleted, PS2 = MEAN WELL MPM-20-24
  (HOT side, TCO-switched gate bias + HOT5), PS3 = MPM-65-15ST (controller logic
  over the J13 merge + blower buck).
- PS2 load: ALT-BIAS.md:163 allocation with the adopted RECOM R24C2T25 modules
  (6.81 / 7.45 / 11.10 W at 33 / 40 / 80 kHz, 45 % module efficiency, 740 nC
  edge allowance), plus a HOT5 allocation.
- PS3 load: controller verify (controller-layout 300b8a934, evidence/verify.json):
  logic 4.83 W at datasheet max; blower buck input 39.72 W at the duty-0 corner.

Method:
- Each module = full-bridge rectifier + bulk C + series R + constant-power load.
  C comes from the datasheet hold-up time (70 / 100 V dropout); R is swept
  (0.5 / 2 / 5 ohm). No physical variant reaches the datasheet AC current at
  rated load, so each variant's harmonic content is scaled up (fundamental kept,
  since power balance fixes it) until its full-load RMS equals the datasheet
  figure; the same scale is applied at the actual load. The worst variant is kept.
- The power stage draws a near-sinusoidal current in phase with the line (PF ~ 1
  on the unsmoothed bus, DECISIONS 2026-10-08); a 3rd-harmonic content h3 is
  swept with the worst sign.
- The aux increment is RMS(i_ps + i_aux) - RMS(i_ps) at the operating point.
  To first order it is the aux real-power current P_in/V; the aux harmonics add
  only (I_rms^2 - I_1^2)/(2 I_ps).

Every number in the JSON comes from this file. Run: python3 aux_load.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

F_LINE = 60.0
LINES_V = (108.0, 120.0, 132.0)       # low / nominal / high (power-stage DECISIONS 2026-10-08)
INLET_TARGET_A = 13.5                  # firmware regulation point (DECISIONS 2026-10-08 correction)
E_EST = 0.10                           # provisional estimator error
VD = 0.9                               # bridge diode drop, V each (two conduct)

# ---------------------------------------------------------------- datasheets
# MEAN WELL MPM-20-SPEC 2024-10-30 p.2 (sha256 24d3a6bb642d74ea) and
# MPM-65-SPEC 2024-10-30 p.2 (sha256 3d324f12a4153a71), downloaded 2026-10-15.
SUPPLIES = {
    "PS2 MPM-20-24": dict(p_rated=21.6, eta_typ=0.87, i_ac_typ_115=0.75, holdup_s=0.010,
                          src="MPM-20-SPEC 2024-10-30 p.2: 21.6 W, eff 87 % typ, AC 0.75 A/115 VAC typ, "
                              "hold-up 10 ms/115 VAC full load, no-load < 0.1 W"),
    "PS3 MPM-65-15ST": dict(p_rated=65.0, eta_typ=0.925, i_ac_typ_115=1.5, holdup_s=0.012,
                            src="MPM-65-SPEC 2024-10-30 p.2: 65 W convection, eff 92.5 % typ, "
                                "AC 1.5 A/115 VAC typ, hold-up 12 ms/115 VAC full load, no-load < 0.1 W"),
}
NO_LOAD_W = 0.1      # both sheets: no-load power consumption < 0.1 W
ETA_WORST_PENALTY = 0.05   # no minimum efficiency is published; worst corner takes typ - 5 points
LIGHT_LOAD_FIXED_W = 0.3   # typical-corner fixed loss (assumption; > the 0.1 W no-load figure)

# ---------------------------------------------------------------- loads (W)
# PS2, HOT side. ALT-BIAS.md:163 (power-stage validation-results/08-manufacturing-package/
# native-21/sourcing/alt-circuits-2026-10-09): A1 bias allocation, 45 % module efficiency.
PS2_BIAS_W = {33e3: 6.81, 40e3: 7.45, 80e3: 11.10}
# HOT5 (TPS70950 from V15_LS): AMC1311 high side, 2x TLV3201, SN74LVC1G10, CA-IS3720HW side 1,
# TPS3700 on V15_LS. The chain from 24 V is linear, so the 24 V current ~ the 5 V current.
# Allocation 20 mA (bound used here) / 12 mA (typical estimate) at 24 V. Not itemised from
# datasheets: it is < 1 % of the aux total either way.
PS2_HOT5_W = {"worst": 0.020 * 24.0, "typical": 0.012 * 24.0}

# PS3 logic, controller verify v3v3 (controller-layout 300b8a934):
#   peak 1050.7 mA at 3.3 V = ESP32 500 mA (WROOM supply requirement, not draw) + other controller
#   41.4 mA (datasheet max) + native-21 on J4.3 49.3 mA + OLED 340 mA (100 % on, max) + UI 120 mA
#   allocation; p3 = 3.465 V * I / 0.85; p_v15_direct 0.548 W. p_total 4.831 W.
LOGIC_MAX_W = 4.831
# Typical estimate (labelled): ESP32-S3 DS v2.2 Table 5-7 RX 91 mA (HT40) + Table 5-9 modem-sleep
# dual core 160 MHz 64.1 mA -> 155 mA average while associated (TX bursts 283-340 mA peak are
# short); OLED NHD-3.12-25664UCW2 IDD 310 mA typ at 100 % on -> 30 % pixels lit ~ 93 mA;
# other controller + native-21 loads kept at their datasheet max (90.7 mA); UI logic 30 mA,
# buzzer off.
LOGIC_TYP_MA_3V3 = 155.0 + 0.30 * 310.0 + (541.389 - 500.0) + 49.345 + 30.0
LOGIC_TYP_W = 3.3 * LOGIC_TYP_MA_3V3 / 1e3 / 0.85 + 0.548

# Blower: Delta BFB1012VH-F00 12 V, 1.42 A typ / 2.70 A max (17 / 32.4 W), fan law V^3,
# buck 0.90; C28 output envelope vout = 12.40 - 6.57 * duty (blower_aux.c).
BLOWER = dict(p_typ_w=17.04, p_max_w=32.4, v_rated=12.0, vout_max=12.40, slope=6.57, eta_buck=0.90)


def blower_in_w(duty: float | None, which: str) -> float:
    """Blower buck input power; duty None = off."""
    if duty is None:
        return 0.0
    v = BLOWER["vout_max"] - BLOWER["slope"] * duty
    p = BLOWER["p_typ_w" if which == "typ" else "p_max_w"] * (v / BLOWER["v_rated"]) ** 3
    return p / BLOWER["eta_buck"]


# ---------------------------------------------------------------- firmware allowance today
def firmware_allowance_a(duty: float | None) -> float:
    """blower_aux.c as merged (15289dc75): base 1.3 A + PS3 blower model at 108 V."""
    base, idle, margin = 1.3, 0.05, 0.15
    pf = (60.0 / 0.89) / (115.0 * 1.8)            # IRM-60-15 figures
    def model(v):
        return 32.4 * (v / 12.0) ** 3 / 0.90 / (0.89 * pf * 108.0)
    worst = base + model(12.40)
    if duty is None:
        return min(worst, base + idle)
    return min(worst, base + (1 + margin) * model(12.40 - 6.57 * duty) + idle)


# ---------------------------------------------------------------- rectifier model
N_STEP = 4000      # per line cycle
N_CYC = 14         # settle; the last cycle is analysed


def rectifier(p_in: float, v_rms: float, c: float, r: float) -> np.ndarray:
    """Line current over one steady-state cycle (A), constant-power load p_in (W)."""
    dt = 1.0 / F_LINE / N_STEP
    vpk = math.sqrt(2) * v_rms
    vc = vpk - 2 * VD
    out = np.empty(N_STEP)
    for k in range(N_STEP * N_CYC):
        ph = 2 * math.pi * (k % N_STEP) / N_STEP
        v = vpk * math.sin(ph)
        i = max(0.0, (abs(v) - 2 * VD - vc) / r)
        vc += (i - p_in / max(vc, 20.0)) * dt / c
        if k >= N_STEP * (N_CYC - 1):
            out[k % N_STEP] = math.copysign(i, v)
    return out


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)))


def fundamental_in_phase(x: np.ndarray) -> float:
    ph = 2 * np.pi * np.arange(N_STEP) / N_STEP
    return float(2 * np.mean(x * np.sin(ph)) / math.sqrt(2))


def c_from_holdup(p_in: float, t: float, v_rms: float, v_drop: float) -> float:
    """Bulk C that holds p_in for t from the line peak down to v_drop."""
    v0 = math.sqrt(2) * v_rms - 2 * VD
    return 2 * p_in * t / (v0**2 - v_drop**2)


def split_fundamental(x: np.ndarray) -> np.ndarray:
    """The 60 Hz component of x (sine and cosine), as a waveform."""
    ph = 2 * np.pi * np.arange(N_STEP) / N_STEP
    a1 = 2 * np.mean(x * np.sin(ph))
    b1 = 2 * np.mean(x * np.cos(ph))
    return a1 * np.sin(ph) + b1 * np.cos(ph)


def calibrate(sup: dict, c: float, r: float) -> dict:
    """Harmonic inflation factor k for this (C, R): at full load, 115 V, the model's
    harmonic content is scaled by k so the module RMS equals the datasheet AC current.
    The fundamental is left alone (power balance fixes it). The datasheet figure is
    above every physical variant tried, so k > 1 and the result stays conservative."""
    w = rectifier(sup["p_rated"] / sup["eta_typ"], 115.0, c, r)
    f = split_fundamental(w)
    h = w - f
    target = sup["i_ac_typ_115"]
    k = math.sqrt(max(target**2 - rms(f) ** 2, 0.0)) / rms(h)
    return {"C_uF": round(c * 1e6, 1), "R_ohm": r, "model_rms_A": round(rms(w), 4),
            "harmonic_scale_k": round(k, 4), "datasheet_A": target, "C": c}


def module_current(sup_cal: dict, p_in: float, v_rms: float) -> np.ndarray:
    w = rectifier(p_in, v_rms, sup_cal["C"], sup_cal["R_ohm"])
    f = split_fundamental(w)
    return f + sup_cal["harmonic_scale_k"] * (w - f)


def eta(sup: dict, p_out: float, corner: str) -> float:
    full_loss = sup["p_rated"] * (1 / sup["eta_typ"] - 1)
    if corner == "worst":
        e = sup["eta_typ"] - ETA_WORST_PENALTY
        return p_out / (p_out / e + NO_LOAD_W)
    k = max(0.0, (full_loss - LIGHT_LOAD_FIXED_W) / sup["p_rated"])
    return p_out / (p_out + LIGHT_LOAD_FIXED_W + k * p_out)


def ps_current(i_ps: float, h3: float, sign: float) -> np.ndarray:
    ph = 2 * np.pi * np.arange(N_STEP) / N_STEP
    w = np.sin(ph) + sign * h3 * np.sin(3 * ph)
    return w * (i_ps / rms(w))      # scaled so the power-stage RMS is i_ps


def aux_increment(i_ps: float, aux: np.ndarray, h3: float) -> float:
    """Increase in total RMS when aux is added to the power-stage current (worst sign of h3)."""
    out = []
    for s in ((1.0,) if h3 == 0 else (1.0, -1.0)):
        ip = ps_current(i_ps, h3, s)
        out.append(rms(ip + aux) - rms(ip))
    return max(out)


def solve_hold(aux: np.ndarray, h3: float) -> tuple[float, float]:
    """Hold current I_ps with (13.5 - dI(I_ps)) / (1 + e) = I_ps; returns (hold, dI)."""
    i_ps = 11.0
    for _ in range(30):
        d = aux_increment(i_ps, aux, h3)
        new = (INLET_TARGET_A - d) / (1 + E_EST)
        if abs(new - i_ps) < 1e-5:
            break
        i_ps = new
    return i_ps, d


# ---------------------------------------------------------------- run
def main() -> None:
    # Variants: C from the hold-up time (70 / 100 V dropout) x series R (NTC, fuse, line).
    variants = [(vd, r) for vd in (70.0, 100.0) for r in (0.5, 2.0, 5.0)]
    cal = {}
    for name, sup in SUPPLIES.items():
        p_in = sup["p_rated"] / sup["eta_typ"]
        cal[name] = [{"v_dropout_V": vd, **calibrate(sup, c_from_holdup(p_in, sup["holdup_s"], 115.0, vd), r)}
                     for vd, r in variants]
    r_sweep = variants

    blower_states = {"off": None, "drive_0.5": 0.5, "full": 0.0}
    corners = {
        "typical": dict(line=120.0, bias_f=40e3, logic=LOGIC_TYP_W, blower="typ", h3=0.0),
        "worst": dict(line=108.0, bias_f=80e3, logic=LOGIC_MAX_W, blower="max", h3=0.2),
    }
    results = {}
    for cname, cn in corners.items():
        for bname, duty in blower_states.items():
            p_out = {
                "PS2 MPM-20-24": PS2_BIAS_W[cn["bias_f"]] + PS2_HOT5_W[cname],
                "PS3 MPM-65-15ST": cn["logic"] + blower_in_w(duty, cn["blower"]),
            }
            best = None
            # sweep the calibration variants; keep the one giving the largest increment
            for idx in range(len(r_sweep)):
                aux = np.zeros(N_STEP)
                per = {}
                for name, sup in SUPPLIES.items():
                    row = cal[name][idx]
                    e = eta(sup, p_out[name], cname)
                    p_in = p_out[name] / e
                    i = module_current(row, p_in, cn["line"])
                    aux += i
                    per[name] = {"P_out_W": round(p_out[name], 2), "eta": round(e, 3),
                                 "P_in_W": round(p_in, 2), "I_rms_A": round(rms(i), 3),
                                 "I_1_in_phase_A": round(fundamental_in_phase(i), 3)}
                hold, d = solve_hold(aux, cn["h3"])
                cand = {"calibration_variant": {"v_dropout_V": r_sweep[idx][0], "R_ohm": r_sweep[idx][1]}, "per_supply": per,
                        "aux_I_rms_A": round(rms(aux), 3),
                        "aux_I_1_A": round(fundamental_in_phase(aux), 3),
                        "linear_sum_module_rms_A": round(sum(v["I_rms_A"] for v in per.values()), 3),
                        "rms_increment_at_hold_A": round(d, 3),
                        "hold_A": round(hold, 3)}
                if best is None or d > best["rms_increment_at_hold_A"]:
                    best = cand
            fw = firmware_allowance_a(duty)
            fw_hold = (INLET_TARGET_A - fw) / (1 + E_EST)
            best["firmware_allowance_A"] = round(fw, 3)
            best["firmware_hold_A"] = round(fw_hold, 3)
            best["recoverable_allowance_A"] = round(fw - best["rms_increment_at_hold_A"], 3)
            best["hold_gain_A"] = round(best["hold_A"] - fw_hold, 3)
            best["power_gain_W_at_120V_pf1"] = round(120.0 * (best["hold_A"] - fw_hold), 0)
            best["line_V"] = cn["line"]
            best["ps2_bias_frequency_Hz"] = cn["bias_f"]
            best["h3"] = cn["h3"]
            results[f"{cname}/{bname}"] = best

    # Datasheet-figure linear sum, the power stage's method, for the current modules.
    ds_linear_108 = {n: round(s["i_ac_typ_115"] * 115.0 / 108.0, 3) for n, s in SUPPLIES.items()}

    # Line sweep for the worst corner at full blower (does the answer move with line?)
    sweep = {}
    for v in LINES_V:
        worst = None
        for idx in range(len(r_sweep)):
            aux = np.zeros(N_STEP)
            for name, sup in SUPPLIES.items():
                row = cal[name][idx]
                p_out = (PS2_BIAS_W[80e3] + PS2_HOT5_W["worst"]) if name.startswith("PS2") \
                    else LOGIC_MAX_W + blower_in_w(0.0, "max")
                aux += module_current(row, p_out / eta(sup, p_out, "worst"), v)
            hold, d = solve_hold(aux, 0.2)
            row_out = {"calibration_variant": list(r_sweep[idx]), "aux_I_rms_A": round(rms(aux), 3),
                       "aux_I_1_A": round(fundamental_in_phase(aux), 3),
                       "rms_increment_A": round(d, 3), "hold_A": round(hold, 3)}
            if worst is None or d > worst["rms_increment_A"]:
                worst = row_out
        sweep[f"{v:.0f}"] = worst

    out = {
        "scope": __doc__.strip(),
        "datasheets": {n: s["src"] for n, s in SUPPLIES.items()},
        "loads_W": {
            "PS2_bias_allocation_by_frequency": {f"{int(k / 1e3)}k": v for k, v in PS2_BIAS_W.items()},
            "PS2_HOT5_allocation": PS2_HOT5_W,
            "PS3_logic_max": LOGIC_MAX_W,
            "PS3_logic_typical_estimate": round(LOGIC_TYP_W, 3),
            "PS3_logic_typical_3V3_mA": round(LOGIC_TYP_MA_3V3, 1),
            "PS3_blower_buck_input": {s: {"typ": round(blower_in_w(d, "typ"), 2), "max": round(blower_in_w(d, "max"), 2)}
                                      for s, d in blower_states.items()},
        },
        "calibration": {n: [{k: v for k, v in r.items() if k != "C"} for r in rows] for n, rows in cal.items()},
        "datasheet_linear_sum_at_108V_A": {**ds_linear_108, "total": round(sum(ds_linear_108.values()), 3)},
        "firmware_allowance_today_A": {s: round(firmware_allowance_a(d), 3) for s, d in blower_states.items()},
        "results": results,
        "worst_full_blower_line_sweep": sweep,
        "notes": [
            "firmware base 1.3 A still assumes PS1 + PS2 IRM-20 at full load; PS1 was deleted at s38 and the "
            "logic moved onto PS3, which the firmware PS3 model does not count (it models the blower only)",
            "aux increment = RMS(i_ps + i_aux) - RMS(i_ps) at the hold point; worst calibration variant kept",
            "the gain applies only where the inlet limit binds; tank-current-limited pans see none",
            "a higher hold raises bus current through R5 / C40: re-check the B3 c22 cases (s41: laminate "
            "22.3 A, laminate + film 21.1 A still-air) before adopting",
        ],
    }
    path = Path(__file__).with_name("aux-load.json")
    path.write_text(json.dumps(out, indent=1) + "\n")
    print("calibration:")
    for n, rows in cal.items():
        for r in rows:
            print(f"  {n:16s} dropout {r['v_dropout_V']:5.0f} V  C {r['C_uF']:6.1f} uF  R {r['R_ohm']:4.1f}  "
                  f"model {r['model_rms_A']:.3f} A  ds {r['datasheet_A']}  k {r['harmonic_scale_k']:.3f}")
    print("datasheet linear sum at 108 V:", out["datasheet_linear_sum_at_108V_A"])
    print(f"{'case':22s} {'P2out':>6s} {'P3out':>6s} {'Irms':>6s} {'I1':>6s} {'lin':>6s} {'dI':>6s} "
          f"{'fw':>6s} {'recov':>6s} {'hold':>6s} {'fwhold':>6s} {'+W@120':>7s}")
    for k, r in results.items():
        p = r["per_supply"]
        print(f"{k:22s} {p['PS2 MPM-20-24']['P_out_W']:6.2f} {p['PS3 MPM-65-15ST']['P_out_W']:6.2f} "
              f"{r['aux_I_rms_A']:6.3f} {r['aux_I_1_A']:6.3f} {r['linear_sum_module_rms_A']:6.3f} "
              f"{r['rms_increment_at_hold_A']:6.3f} {r['firmware_allowance_A']:6.3f} "
              f"{r['recoverable_allowance_A']:6.3f} {r['hold_A']:6.3f} {r['firmware_hold_A']:6.3f} "
              f"{r['power_gain_W_at_120V_pf1']:7.0f}")
    print("worst/full line sweep:", sweep)


if __name__ == "__main__":
    main()
