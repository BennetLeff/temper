#!/usr/bin/env python3
"""Committed calculations behind every numeric claim in the controller docs.

Standard library only. Each block names its vendor sources (document, table)
and labels anything that is a design allocation or an assumption, not a
vendor limit. Writes evidence/controller_calcs.json and exits non-zero if a
design check fails.

Usage: python3 tools/controller_calcs.py [--quiet]
"""
from __future__ import annotations

import json
import math
import sys
from itertools import product
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
OUT = UNIT / "evidence" / "controller_calcs.json"

CONTRACT = (3.135, 3.465)          # interlock / FAULT-INTERFACE.md v3v3 contract
TEMP_SPAN_K = 60.0                 # 25 C -> 85 C board, for 25 ppm/C resistor drift
SOURCES = {
    "TPS62933": "TI SLUSEA4D 8.5: VFB 788-812 mV (TJ 0-85 C), 784-816 mV (-40-150 C); "
                "VEN_RISE 1.21 typ/1.28 max, VEN_FALL 1.10 min/1.17 typ; Ip 0.7 uA; Ih 1.4 uA; "
                "f 450-550 kHz (RT open); tOFF_MIN 140 ns typ; 98 % max duty with foldback",
    "TPS3703A4330": "TI SBVS344D (TPS3703A4330DSERQ1, fitted; same as SBVS249B commercial): thresholds 3.3 V +/-4 %, accuracy +/-0.7 %, VHYS 0.3-0.8 %, "
                    "tD 7-13 ms (CT open), UVLO 1.2-1.7 V",
    "IRM-20-15": "Mean Well IRM-20-SPEC 2025-11-21: 15 V, 1.4 A, 21 W, tolerance +/-2.5 % "
                 "(set-up + line + load), ripple 200 mVp-p",
    "MAX31865": "ADI MAX31865 datasheet: VBIAS 1.95-2.06 V; BIAS IOUT 0.2-5.75 mA; 30 mV/mA load reg",
    "TLV3201": "TI SBOS561C: VIO 5 mV max at 25 C, 4 mV max -40..125 C row; 1.2 mV input hysteresis",
    "Pt100": "IEC 60751 Callendar-Van Dusen, A = 3.9083e-3, B = -5.775e-7 (T >= 0 C)",
    "ESP32-S3": "Espressif ESP32-S3 datasheet v2.2 Tables 5-5/5-6: SAR ADC 100 kSPS max; "
                "ATTEN2 0-1600 mV +/-10 mV, ATTEN3 0-2900 mV +/-50 mV (25 C, DC, 100 nF, Wi-Fi off)",
    "ESP-IDF": "esp-idf v5.2.3 components/soc/esp32s3/include/soc/soc_caps.h: "
               "SOC_ADC_SAMPLE_FREQ_THRES_HIGH 83333, SOC_ADC_PATT_LEN_MAX 24",
    "D-11": "power-stage out-D11/README.md section 2: VADC = Vbias + 0.5 (VBUS_P - VBUS_N); "
            "divider 4 x 470k / 15.8k; over-range 1210 mV; invalid < 100 mV; 150 us stale",
    "Micro-Fit": "Molex 43030 terminal, 10 mOhm max contact resistance (distributor listing, "
                 "RS 2333021; Molex PS to confirm)",
    "AWG22": "52.96 mOhm/m copper at 20 C; x1.197 at 70 C (alpha 0.00393/K)",
    "Delta PFB0612EHE-F00": "DigiKey 603-1923-ND listing: 12 V rated, 7-13.2 V range, 0.63 A, 3-wire tach",
}


def rail_3v3() -> dict:
    """Regulator band vs the TPS3703 window vs the 3.135-3.465 V contract.

    Criteria: (1) both trip bands inside the contract; (2) the regulator's low
    corner clears the UV *release* threshold, or RESET never releases after
    start-up; (3) the margins from the steady band (+/- half ripple) to the UV
    and OV *trip* thresholds are what is left for load-step under/overshoot.
    The SENSE pin sees v3v3 through 1 k / 1 uF, so only events longer than
    about 1 ms use those margins; ISENSE (1.5 uA max) x 1 k shifts SENSE low.
    """
    r_top, r_bot, tol = 22.1e3, 7.06e3, 0.001
    drift = 25e-6 * TEMP_SPAN_K
    ratio = []
    for st, sb in product((-1, 1), repeat=2):
        rt = r_top * (1 + st * (tol + drift))
        rb = r_bot * (1 + sb * (tol + drift))
        ratio.append(1 + rt / rb)
    vfb = (0.788, 0.812)
    reg = (vfb[0] * min(ratio), vfb[1] * max(ratio))
    nominal = 0.800 * (1 + r_top / r_bot)
    uv_nom, ov_nom = 3.3 * 0.96, 3.3 * 1.04
    acc = 0.007
    uv = (uv_nom * (1 - acc), uv_nom * (1 + acc))
    ov = (ov_nom * (1 - acc), ov_nom * (1 + acc))
    sense_shift = 1.5e-6 * 1e3 * 1.01                 # ISENSE max x 1 k: SENSE reads low
    uv_release_max = uv[1] * (1 + 0.008) + sense_shift
    # Steady ripple (allocation inputs: L -20 %, Cout 3 x 22 uF at 50 % effective
    # after X5R DC bias and -20 % tolerance -> design assumption, bench to confirm).
    vin_max, f_min, l_min = 15.375, 450e3, 10e-6 * 0.8
    di = reg[1] * (1 - reg[1] / vin_max) / (l_min * f_min)
    c_eff = 3 * 22e-6 * 0.8 * 0.5
    v_ripple_pp = di / (8 * f_min * c_eff)
    low_margin = reg[0] - v_ripple_pp / 2 - sense_shift - uv[1]
    high_margin = ov[0] - (reg[1] + v_ripple_pp / 2 - sense_shift)
    release_margin = reg[0] - v_ripple_pp / 2 - uv_release_max
    checks = {
        "uv_trip_min_ge_contract_min": uv[0] >= CONTRACT[0],
        "ov_trip_max_le_contract_max": ov[1] <= CONTRACT[1],
        "reg_band_inside_contract": reg[0] > CONTRACT[0] and reg[1] < CONTRACT[1],
        "uv_release_cleared": release_margin > 0.010,
        # Allocation, not a vendor limit: >= 30 mV left for excursions slower
        # than the 1 ms SENSE filter (start-up overshoot, beyond-85 C drift).
        # Faster load steps are attenuated by the filter; bench item B-3 measures it.
        "slow_excursion_margins_ge_30mV": min(low_margin, high_margin) >= 0.030,
    }
    return {
        "source": ["TPS62933", "TPS3703A4330"],
        "feedback": {"r_top": r_top, "r_bot": r_bot, "tol": tol, "tcr_drift": drift},
        "vout_nominal_V": nominal,
        "vout_band_0_85C_V": reg,
        "window_uv_trip_V": uv, "window_ov_trip_V": ov,
        "uv_release_max_V": uv_release_max,
        "ripple_assumption": "L -20 %, f 450 kHz, Cout_eff = 3x22uF x0.8 x0.5 (DC bias) -- allocation",
        "inductor_ripple_A_pp": di, "vout_ripple_V_pp": v_ripple_pp,
        "uv_release_margin_V": release_margin,
        "low_transient_margin_V": low_margin,
        "high_transient_margin_V": high_margin,
        "sense_filter": "1 kOhm / 1 uF, tau 1 ms",
        "checks": checks,
    }


HARNESS_DEFAULT_M = 1.0            # DEFAULT (owner open item): J4 harness <= 1.0 m AWG22; R27 route is 74 mm


def harness(i_v3v3_native_a: float, i_v15_a: float, length_m: float = HARNESS_DEFAULT_M) -> dict:
    """v3v3 as seen by native-21 through the J4 harness (default allocation <= 1.0 m AWG22)."""
    r_contact = 0.010
    r_wire = 0.05296 * 1.197 * length_m
    r_path = 2 * r_contact + r_wire                  # one conductor, two mated contacts
    r_gnd = r_path / 3                               # three selv_gnd contacts
    # Ground current: v15 return flows controller -> native-21; v3v3 return flows back.
    i_gnd_net = i_v15_a - i_v3v3_native_a
    drop_v3v3 = i_v3v3_native_a * r_path
    gnd_shift = i_gnd_net * r_gnd                    # native-21 ground below controller ground
    return {"source": ["Micro-Fit", "AWG22"], "length_m": length_m,
            "allocation": f"J4 harness <= {length_m} m, AWG22, Micro-Fit 43030 terminals (DEFAULT; harness not yet specified)",
            "r_conductor_ohm": r_path, "r_ground_3pin_ohm": r_gnd,
            "v3v3_drop_V": drop_v3v3, "ground_shift_max_V": max(gnd_shift, 0.0),
            "ground_shift_min_V": min(-i_v3v3_native_a * r_gnd, 0.0)}


def fan_buck() -> dict:
    vfb = (0.788, 0.812)
    ratio = 1 + 140e3 / 10e3
    vout = (vfb[0] * ratio * (1 - 0.003), vfb[1] * ratio * (1 + 0.003))
    vin_min = 15 * 0.975 - 0.10                      # IRM tolerance, minus 0.10 V input-path allocation
    i_fan, r_l = 0.63, 0.089 * 1.3                   # SWPA6045S220MT DCR, +30 % hot (allocation)
    duty = (vout[1] + i_fan * r_l) / vin_min
    dmax_no_foldback = 1 - 140e-9 * 550e3
    return {"source": ["TPS62933", "IRM-20-15", "Delta PFB0612EHE-F00"],
            "vout_band_V": vout, "fan_range_V": (7.0, 13.2),
            "vin_min_V": vin_min, "duty_required": duty,
            "duty_max_without_foldback_typ": dmax_no_foldback, "duty_max_with_foldback": 0.98,
            "checks": {"vout_in_fan_range": 7.0 <= vout[0] and vout[1] <= 13.2,
                       "duty_ok_without_foldback": duty < dmax_no_foldback}}


def en_uvlo() -> dict:
    rt, rb = 100e3, 12.1e3
    out = {}
    for name, ven, ip in (("start_typ_V", 1.21, 0.7e-6), ("start_max_V", 1.28, 0.0),
                          ("stop_min_V", 1.10, 0.7e-6 + 1.4e-6)):
        hi = rt * (1.01 if "max" in name else 0.99)
        lo = rb * (0.99 if "max" in name else 1.01)
        out[name] = ven * (1 + hi / lo) - ip * hi
    out["checks"] = {"starts_below_irm_min": out["start_max_V"] < 15 * 0.975,
                     "stops_above_8V": out["stop_min_V"] > 8.0}
    out["source"] = ["TPS62933", "IRM-20-15"]
    return out


def pt100(t: float) -> float:
    return 100.0 * (1 + 3.9083e-3 * t - 5.775e-7 * t * t)


def pt100_inv(r: float) -> float:
    a, b = 3.9083e-3, -5.775e-7
    return (-a + math.sqrt(a * a - 4 * b * (1 - r / 100.0))) / (2 * b)


def runaway() -> dict:
    """Ratiometric comparator: trip when V(RTDIN+)/VBIAS > k = Rb/(Rt+Rb).

    V(RTDIN+) = VBIAS * (Rrtd + Rlead_fm) / (Rref + Rlead_fp + Rrtd + Rlead_fm)
    (sense leads carry no current; FORCE2 grounded; 4-wire per the RTD unit).
    Comparator offset is referred to VBIAS (1.95-2.06 V) at the trip voltage.
    """
    corners = []
    for st, sb, sr, so, lead in product((-1, 1), (-1, 1), (-1, 1), (-1, 1), (0.0, 1.0)):
        rt = 20e3 * (1 + st * (0.001 + 25e-6 * TEMP_SPAN_K))
        rb = 10e3 * (1 + sb * (0.001 + 25e-6 * TEMP_SPAN_K))
        rref = 430.0 * (1 + sr * (0.0005 + 10e-6 * TEMP_SPAN_K))
        k = rb / (rt + rb)
        vbias = 1.95 if so > 0 else 2.06
        k_eff = k + so * 0.005 / vbias       # VIO 5 mV referred to the ratiometric node
        # Solve (R + lead) / (rref + lead + R + lead) = k_eff for R
        r = (k_eff * (rref + 2 * lead) - lead) / (1 - k_eff)
        corners.append(pt100_inv(r))
    nominal_r = (1 / 3) * 430.0 / (1 - 1 / 3)
    band = (min(corners), max(corners))
    return {"source": ["MAX31865", "TLV3201", "Pt100"],
            "divider": "20.0k / 10.0k 0.1 % 25 ppm from MAX31865 BIAS", "k_nominal": 1 / 3,
            "trip_resistance_nominal_ohm": nominal_r, "trip_temp_nominal_C": pt100_inv(nominal_r),
            "trip_temp_band_C": band, "lead_allocation_ohm": "0-1 per conductor (RTD contract)",
            "firmware_runaway_C": 300.0, "max_cooking_C": 250.0,
            "checks": {"above_cooking_max": band[0] > 250.0, "below_350C": band[1] < 350.0}}


def d11_receiver() -> dict:
    vref = 2.5
    vbias = vref * 10.0 / (90.9 + 10.0)
    k = 15.8e3 / (4 * 470e3 + 15.8e3)
    pts = {f"{v} V": vbias + 0.5 * v * k for v in (0, 170, 198, 230)}
    diff_at_overrange = (1.210 - vbias) / 0.5
    return {"source": ["D-11", "ESP32-S3"],
            "bias_V": vbias, "bias_d11_V": 0.25, "bias_shift_mV": (vbias - 0.25) * 1e3,
            "adc_V_at_bus": pts, "bus_V_at_1210mV": diff_at_overrange / k,
            "atten": "ATTEN2 (0-1600 mV)",
            "checks": {"zero_above_invalid_100mV": vbias > 0.100,
                       "198V_below_overrange": pts["198 V"] < 1.210,
                       "full_scale_in_atten2": vbias + 0.5 * 2.0 < 1.6}}


def ct_mon() -> dict:
    r_src, r_load = 2e3, 10e6
    gain_err = r_src / (r_src + r_load)
    mv_per_a = 15.0          # 1.5 ohm burden / 100:1 CT (native-21 interface_numbers.py)
    out = {}
    for label, i_pk in (("22 A RMS tank", 22 * math.sqrt(2)), ("55 A pk trip", 55.0)):
        swing = i_pk * mv_per_a / 1e3
        out[label] = (1.65 - swing, 1.65 + swing)
    return {"source": ["ESP32-S3"], "settled": "CT_SENSE_MON via R47 1k, ~2 kOhm source",
            "load_ohm": r_load, "gain_error": gain_err,
            "range_V": out, "atten": "ATTEN3 (0-2900 mV)",
            "checks": {"load_ge_1Mohm": r_load >= 1e6,
                       "trip_range_in_atten3": out["55 A pk trip"][0] > 0.05
                       and out["55 A pk trip"][1] < 2.9}}


def adc_pattern() -> dict:
    total = 80_000.0
    pattern = ["VBUS", "CT_MON", "VBUS", "CT_MON", "VBUS", "HS", "COIL", "M12"]
    slot = 1 / total
    rates = {ch: pattern.count(ch) * total / len(pattern) for ch in dict.fromkeys(pattern)}
    idx = [i for i, ch in enumerate(pattern) if ch == "VBUS"]
    gaps = [((idx[(n + 1) % len(idx)] - i) % len(pattern) or len(pattern)) * slot for n, i in enumerate(idx)]
    return {"source": ["ESP32-S3", "ESP-IDF", "D-11"],
            "total_sps": total, "pattern": pattern, "rates_sps": rates,
            "vbus_max_gap_us": max(gaps) * 1e6,
            "checks": {"total_le_idf_83333": total <= 83333, "total_le_datasheet_100k": total <= 100e3,
                       "pattern_len_le_24": len(pattern) <= 24,
                       "vbus_ge_20k": rates["VBUS"] >= 20e3,
                       "vbus_gap_le_150us": max(gaps) <= 150e-6}}


def landings() -> dict:
    """R27 harness landings vs the six mounting holes' 8 mm screw-head keepouts.

    Board X-168..38, Y14..90 (world mm); R27 holes (-164,18) (-164,80) (-65,18)
    (-75,86) (34,18) (26,74) -- the rear three moved inboard in R27, the right-rear again in R28 (J9); keepout
    radius 4 mm (CONTROLLER-SPEC). A connector centred on its landing (X/Y
    projected onto the board) needs centre-to-hole >= 4 + half its body length,
    orientation unknown, so the longest body dimension is used (conservative).
    Body lengths: JLC listings of the chosen parts (XH 2/3/4/8-pin 7.4/9.9/12.4/22.4,
    Micro-Fit 2x8 27.65, Micro-MaTch 6-pin 9.7).
    """
    holes = [(-164.0, 18.0), (-164.0, 80.0), (-65.0, 18.0), (-75.0, 86.0), (34.0, 18.0), (26.0, 74.0)]
    rows = {
        "J4 SELV (right)": ((42.2, 42.0), 27.65),
        "J6 OLED (top)": ((-35.0, 70.0), 22.4),
        "J7 buttons A (top)": ((-90.0, 41.0), 9.9),
        "J8 button B (top)": ((5.0, 41.0), 7.4),
        "J5 encoder (right, R25)": ((42.2, 64.0), 9.7),
        "J9 M12 probe (right, R25)": ((39.2, 86.0), 9.9),
        "J10 fan (rear, R25)": ((-155.0, 91.3), 9.9),
        "J1 coil NTC (top)": ((-60.0, 88.0), 7.4),
        "J2 heatsink NTC (top)": ((20.0, 88.0), 7.4),
        "J3 pan RTD (rear)": ((-165.0, 92.0), 12.4),
    }
    out = {}
    for name, ((x, y), length) in rows.items():
        px, py = min(max(x, -168.0), 38.0), min(max(y, 14.0), 90.0)
        d, hole = min((math.hypot(px - hx, py - hy), (hx, hy)) for hx, hy in holes)
        need = 4.0 + length / 2
        out[name] = {"landing": (x, y), "on_board": (px, py), "nearest_hole": hole,
                     "distance_mm": round(d, 2), "needed_mm": round(need, 2),
                     "conflict": d < need}
    conflicts = [k for k, v in out.items() if v["conflict"]]
    return {"source": "CONTROLLER-SPEC R27 harness table and hole list; JLC body lengths",
            "rows": out, "conflicts_orientation_blind": conflicts,
            "note": "informational (enclosure-owned geometry): the circle bound assumes the worst "
                    "orientation; an XH body along the rear edge (5.75 mm deep) clears J3's keepout"}


def rms_channel() -> dict:
    """AD8436 tank-RMS channel into the MCP3202 (owner-approved follow-up)."""
    f_band = (31e3, 55e3)                       # tank frequency band (coordinator)
    bw_1pct = 65e3                              # AD8436 Rev. B Table 1, 300 mV rms
    mv_per_a = 15.0                             # 1.5 ohm burden / 100:1 CT
    gain = 1 + 30e3 / 10e3                      # output buffer, RT0603 0.1 %
    gain_tol = 2 * 0.001 * (30e3 / 10e3) / gain
    rms_22 = 22 * mv_per_a / 1e3
    rms_trip = 55 / math.sqrt(2) * mv_per_a / 1e3
    out_22, out_trip = rms_22 * gain, rms_trip * gain
    vdd_min, vdd_max = 3.242, 3.367             # v3v3 band (rail_3v3) = MCP3202 reference
    # coupling high-passes: 100 nF into the 10 MOhm bias and into the 8 kOhm core input
    hp_core = 1 / (2 * math.pi * 8e3 * 100e-9)
    hp_err = 1 - 1 / math.sqrt(1 + (hp_core / f_band[0]) ** 2)
    lpf = 1 / (2 * math.pi * 16e3 * 10e-9)      # OUT 16 kOhm internal + 10 nF C0G
    ripple_atten = 1 / math.sqrt(1 + (2 * f_band[0] / lpf) ** 2)
    # Settling: datasheet gives 0.1 % at CAVG 10 uF = 148 ms rising / 341 ms falling.
    # ASSUMPTION (bench item): settling scales with CAVG, as for a log-domain core.
    settle_fall_ms = 341 * (100e-9 / 10e-6)
    # Fault: output buffer on 15 V can reach VS - 1; 1 k into the BAT54S clamp to v3v3.
    i_fault = (15.375 - 1 - vdd_max) / 1e3
    v_clamp_over = 0.500                        # BAT54S VF max at 30 mA (DS11005); fault current < 30 mA
    leak_err = 2e-6 * 1e3 / out_22              # IR 2 uA (25 V) x 1 kOhm vs 22 A reading
    lsb = vdd_max / 4096
    return {"source": "AD8436 Rev. B; MCP3202 DS21034F; BAT54S DS11005; CT transfer 15 mV/A",
            "bandwidth_1pct_Hz": bw_1pct, "tank_band_Hz": f_band,
            "gain": gain, "gain_tolerance": gain_tol,
            "adc_V_at_22A_rms": out_22, "adc_V_at_55A_peak_trip": out_trip,
            "adc_lsb_V": lsb, "codes_at_22A": out_22 / lsb,
            "coupling_error_at_31kHz": hp_err, "post_filter_Hz": lpf, "ripple_attenuation_2f": ripple_atten,
            "settling_0p1pct_fall_ms_assumed": settle_fall_ms,
            "fault_clamp_current_A": i_fault, "clamp_node_max_over_vdd_V": v_clamp_over,
            "leakage_error_at_22A": leak_err,
            "reference": "MCP3202 VREF = v3v3 (3.242-3.367 V); CH1 reads the LM4040A25 (0.1 %) "
                         "so firmware divides it out",
            "checks": {"bandwidth_covers_tank_band": bw_1pct >= f_band[1],
                       "trip_level_inside_adc_range": out_trip < vdd_min,
                       "coupling_error_lt_0p1pct": hp_err < 1e-3,
                       "settles_within_half_line_cycle": settle_fall_ms < 8.33,
                       "clamp_keeps_adc_within_vdd_plus_0p6": v_clamp_over < 0.6 and i_fault <= 0.030,
                       "leakage_error_lt_0p5pct": leak_err < 0.005}}


def encoder_supply() -> dict:
    """5 V encoder option: v15 -> 2 x 100 ohm -> TLV76050 (DBZ 275.2 C/W)."""
    i_enc, i_gnd_max = 0.030, 0.005             # encoder allocation [UNVERIFIED]; TLV760 IGND 5 mA max
    r = 200.0
    out = {}
    for label, vin in (("vin_min", 15 * 0.975), ("vin_max", 15 * 1.025)):
        i = i_enc + i_gnd_max
        v_ldo_in = vin - i * r
        p_ldo = (v_ldo_in - 5.0) * i_enc + v_ldo_in * i_gnd_max
        out[label] = {"ldo_in_V": v_ldo_in, "ldo_W": p_ldo, "per_resistor_W": i * i * r / 2}
    rise = out["vin_max"]["ldo_W"] * 275.2
    return {"source": "TI TLV760 datasheet (IGND, dropout 1.2 V, RthJA 275.2 C/W); 1206 = 0.25 W",
            "rows": out, "ldo_rise_C": rise,
            "checks": {"ldo_headroom": out["vin_min"]["ldo_in_V"] >= 5.0 + 1.2,
                       "ldo_tj_le_125C_at_60C_ambient": 60 + rise <= 125,
                       "resistors_le_half_rating": out["vin_max"]["per_resistor_W"] <= 0.125}}


def harness_sensitivity() -> dict:
    """How far the DEFAULT harness length can grow before native-21's rail leaves 3.135 V.

    Uses the same model as the verifier with the verified native-21 load (49 mA) and the
    peak 15 V return (0.85 A); the controller's low corner is rail_3v3()'s band minimum.
    """
    reg_min = rail_3v3()["vout_band_0_85C_V"][0]
    lengths = [0.074, 0.5, 1.0, 2.0, 4.0, 8.0]
    rows = {}
    for length in lengths:
        h = harness(0.0493, 0.85, length)
        rows[f"{length} m"] = reg_min - h["v3v3_drop_V"] + h["ground_shift_min_V"]
    return {"default_m": HARNESS_DEFAULT_M, "native21_v3v3_min_V_by_length": rows,
            "checks": {"default_and_r27_route_inside_contract": rows["1.0 m"] >= 3.135 and rows["0.074 m"] >= 3.135}}


def main() -> int:
    quiet = "--quiet" in sys.argv
    result = {
        "schema": "temper.controller.calcs.v1",
        "sources": SOURCES,
        "rail_3v3": rail_3v3(),
        "fan_buck": fan_buck(),
        "en_uvlo": en_uvlo(),
        "runaway": runaway(),
        "d11_receiver": d11_receiver(),
        "ct_mon": ct_mon(),
        "adc_pattern": adc_pattern(),
        "landings": landings(),
        "rms_channel": rms_channel(),
        "encoder_supply": encoder_supply(),
        "harness_sensitivity": harness_sensitivity(),
    }
    failed = [f"{blk}.{name}" for blk, val in result.items() if isinstance(val, dict)
              for name, ok in val.get("checks", {}).items() if not ok]
    result["failed_checks"] = failed
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not quiet:
        print(json.dumps({k: v for k, v in result.items() if k != "sources"}, indent=2, sort_keys=True))
    print("calcs:", "PASS" if not failed else f"FAIL {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
