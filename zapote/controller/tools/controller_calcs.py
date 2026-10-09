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
    "TPS3703A4330": "TI SBVS249B 7.5: thresholds 3.3 V +/-4 %, accuracy +/-0.7 %, VHYS 0.3-0.8 %, "
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


def harness(i_v3v3_native_a: float, i_v15_a: float) -> dict:
    """v3v3 as seen by native-21 through the J4 harness (allocation: <= 1.0 m AWG22)."""
    r_contact = 0.010
    r_wire = 0.05296 * 1.197 * 1.0
    r_path = 2 * r_contact + r_wire                  # one conductor, two mated contacts
    r_gnd = r_path / 3                               # three selv_gnd contacts
    # Ground current: v15 return flows controller -> native-21; v3v3 return flows back.
    i_gnd_net = i_v15_a - i_v3v3_native_a
    drop_v3v3 = i_v3v3_native_a * r_path
    gnd_shift = i_gnd_net * r_gnd                    # native-21 ground below controller ground
    return {"source": ["Micro-Fit", "AWG22"],
            "allocation": "J4 harness <= 1.0 m, AWG22, Micro-Fit 43030 terminals (harness not yet specified)",
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
    """R25 harness landings vs the six mounting holes' 8 mm screw-head keepouts.

    Board X-168..38, Y14..90 (world mm); holes at X -164/-65/34, Y 18/86, keepout
    radius 4 mm (CONTROLLER-SPEC). A connector centred on its landing (X/Y
    projected onto the board) needs centre-to-hole >= 4 + half its body length,
    orientation unknown, so the longest body dimension is used (conservative).
    Body lengths: JLC listings of the chosen parts (XH 2/3/4/8-pin 7.4/9.9/12.4/22.4,
    Micro-Fit 2x8 27.65, Micro-MaTch 6-pin 9.7).
    """
    holes = [(x, y) for x in (-164.0, -65.0, 34.0) for y in (18.0, 86.0)]
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
    return {"source": "CONTROLLER-SPEC R25 harness table and hole list; JLC body lengths",
            "rows": out, "conflicts": [k for k, v in out.items() if v["conflict"]]}


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
