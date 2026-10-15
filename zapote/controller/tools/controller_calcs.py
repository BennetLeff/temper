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
    out["source"] = ["TPS62933", "IRM-20-15 (3.3 V buck)", "IRM-60-15ST (blower buck, stage 16): same 15 V +/-2.5 %"]
    return out


def pt100(t: float) -> float:
    return 100.0 * (1 + 3.9083e-3 * t - 5.775e-7 * t * t)


def pt100_inv(r: float) -> float:
    a, b = 3.9083e-3, -5.775e-7
    return (-a + math.sqrt(a * a - 4 * b * (1 - r / 100.0))) / (2 * b)


R_LEAD_C1 = 1.80          # ohm per conductor, sensor-r3 checks.py R_LEAD (20 mm manganin + pigtail + harness)


def runaway() -> dict:
    """Ratiometric RTD runaway comparator (DECISIONS C38, sensor-r3 CR-3).

    The divider bottom sits on the connector-side S- node (J3.3) and the window branch on S+
    (J3.2), so the comparator trips when V(S+) - V(S-) > k (V(BIAS) - V(S-)), i.e.
        I R > k I (Rref + R_Fp + R)  ->  R > k (Rref + R_Fp) / (1 - k):
    the FORCE- lead and the MAX31865's internal FORCE- switch drop out. With a comparator offset
    Vos and I = VB / (A + R + B), A = Rref + R_Fp, B = R_Fn + R_sw:
        R = (VB k A + Vos (A + B)) / (VB (1 - k) - Vos).
    Corners: divider 0.1 % + 25 ppm/K x 60 K each, Rref 0.05 % + 5 ppm/K x 60 K (RG2012V-431-W-T1),
    VB 1.95 / 2.06 V, Vos +/-(5 mV VIO + 0.6 mV half the input hysteresis + 0.15 mV for the uA
    pull-up / divider currents in the sense leads), leads 0.9-1.1 x 1.80 ohm, FORCE- switch
    0.5-20 ohm (not specified by the vendor: swept). The sensor-r3 circuit solve
    (evidence/sensor-r3-checks/checks.py item 8) is the cross-check.
    """
    corners = []
    span = 0.001 + 25e-6 * TEMP_SPAN_K
    vos_max = 0.005 + 0.0006 + 0.00015
    for st, sb, sr, so, vb, lead, rsw in product((-1, 1), (-1, 1), (-1, 1), (-1, 1), (1.95, 2.06), (0.9, 1.1),
                                                 (0.5, 20.0)):
        rt = 20e3 * (1 + st * span)
        rb = 10e3 * (1 + sb * span)
        rref = 430.0 * (1 + sr * (0.0005 + 5e-6 * TEMP_SPAN_K))
        k = rb / (rt + rb)
        a = rref + lead * R_LEAD_C1
        b = lead * R_LEAD_C1 + rsw
        vos = so * vos_max
        r = (vb * k * a + vos * (a + b)) / (vb * (1 - k) - vos)
        corners.append(pt100_inv(r))
    nominal_r = (1 / 3) * (430.0 + R_LEAD_C1) / (1 - 1 / 3)
    band = (min(corners), max(corners))
    return {"source": ["MAX31865", "TLV3201", "Pt100", "sensor-r3 CHANGE-REQUEST CR-3"],
            "divider": "20.0k / 10.0k 0.1 % 25 ppm from MAX31865 BIAS, bottom on J3.3 (S-)", "k_nominal": 1 / 3,
            "trip_resistance_nominal_ohm": nominal_r, "trip_temp_nominal_C": pt100_inv(nominal_r),
            "trip_temp_band_C": band,
            "lead_allocation_ohm": "0.9-1.1 x 1.80 per conductor (sensor-r3 C1 leads); FORCE- switch 0.5-20 ohm",
            "firmware_runaway_C": 300.0, "max_cooking_C": 250.0,
            "checks": {"above_max_setpoint_plus_overshoot_plus_15K": band[0] > 250.0 + 5.0 + 15.0,
                       "below_bond_intermittent_325C": band[1] < 325.0}}


def _gt2_104(t: float, rs: float = 1.0, bs: float = 1.0) -> float:
    """Semitec 104GT-2 R(T) from the GT2_104 table (log-linear), with R25 and B corners
    (sensor-r3 checks.py ntc())."""
    ks = sorted(GT2_104)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            la, lb = math.log(GT2_104[a]), math.log(GT2_104[b])
            r = math.exp(la + (lb - la) * (t - a) / (b - a)) * 1e3
            break
    else:
        raise ValueError(t)
    return r * rs * math.exp(4267.0 * (bs - 1) * (1 / (t + 273.15) - 1 / 298.15))


def _gt2_104_t(r: float, rs: float = 1.0, bs: float = 1.0) -> float:
    lo, hi = 0.0, 290.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if _gt2_104(m, rs, bs) > r else (lo, m)
    return (lo + hi) / 2


def rim_trip() -> dict:
    """Rim NTC hardware trip (DECISIONS C38, sensor-r3 CR-5): TLV3201, INP = v3v3 x 10k/(86.6k+10k),
    INN = rim_filt (104GT-2 under a 1.00 k pull-up, 10 k / 100 nF filter). Output high (fault)
    when the node falls below INP: rim hotter than the trip point, or the NTC shorted. ORed with the
    RTD runaway into RUNAWAY_FAULT. Both sides are v3v3-ratiometric, so the offset is referred to
    the contract minimum 3.135 V. Corners: R25 +/-3 %, B +/-2 % (GT-2), pull-up and divider
    0.1 % + 25 ppm/K x 60 K, Vos +/-(5 mV + 0.6 mV hysteresis half); self-heating at the trip
    point reads hot (trips early) and widens the low side. The NTC's own leakage paths (ESD5Z5.0
    50 nA x 1 k = 50 uV) are below the offset term and ignored."""
    k_nom = 10e3 / (86.6e3 + 10e3)
    r_th = 1000.0 * k_nom / (1 - k_nom)
    t_nom = _gt2_104_t(r_th)
    span = 0.001 + 25e-6 * TEMP_SPAN_K
    temps = []
    for rs, bs, s1, s2, s3, so in product((0.97, 1.03), (0.98, 1.02), (-1, 1), (-1, 1), (-1, 1), (-1, 1)):
        rpu = 1000 * (1 + s1 * span)
        rt = 86.6e3 * (1 + s2 * span)
        rb = 10e3 * (1 + s3 * span)
        k = rb / (rt + rb) + so * (0.005 + 0.0006) / CONTRACT[0]
        temps.append(_gt2_104_t(rpu * k / (1 - k), rs, bs))
    sh = (3.3 / (r_th + 1000)) ** 2 * r_th / 0.6e-3                 # K, 0.6 mW/K dissipation constant
    band = (min(temps) - sh, max(temps))
    return {"source": ["TLV3201", "Semitec GT-2 series datasheet (2023-08-01) R-T table",
                       "sensor-r3 CHANGE-REQUEST CR-5 / checks.py item 8"],
            "k_nominal": k_nom, "r_trip_nominal_ohm": r_th, "trip_nominal_C": t_nom,
            "self_heating_at_trip_K": sh, "trip_band_C": band, "corners": len(temps),
            "enable_condition": "fit only after bench T3 logs the rim maximum under a 250 C hold <= band low - 10 K",
            "checks": {"band_above_250C": band[0] > 250.0, "band_below_300C": band[1] < 300.0,
                       "below_ntc_table_end_290C": band[1] < 290.0}}


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
    pattern = ["VBUS", "CT_MON", "VBUS", "CT_MON", "VBUS", "HS", "COIL", "M12", "RIM"]   # RIM: R36 rim NTC
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
    """R33 connector centres vs the six snap-in holes' 8 mm keep-outs.

    R31 (output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md, "R31" section) mirrors
    the assembly about X = 0: board X-38..168, Y14..90; Ø4.0 snap-in holes (164,18) (164,80)
    (65,18) (75,86) (-34,18) (-26,74); keep-out radius 4 mm. R33 (temper-manufacturing-r33
    design/r33/DECISIONS.md section 3, R35 HANDOFF "Controller layout") deletes J5/J6/J8 and adds
    the 12-way J7 at X29.8-62.2, Y57.1-62.9. A connector centred on its centre needs
    centre-to-hole >= 4 + half its body length, orientation unknown, so the longest body dimension
    is used (conservative). Body lengths: JLC listings / JST eXH.pdf (XH 2/3/4/12-pin
    7.4/9.9/12.4/32.4, Micro-Fit 2x8 27.65). layout/check_layout.py checks the real bodies.
    """
    holes = [(164.0, 18.0), (164.0, 80.0), (65.0, 18.0), (75.0, 86.0), (-34.0, 18.0), (-26.0, 74.0)]
    rows = {
        "J4 SELV (left edge, mating -X)": ((-31.15, 42.4), 27.65),
        "J7 UI bus (12-pin, R33)": ((46.0, 60.0), 32.4),
        "J9 M12 probe": ((-33.0, 86.0), 9.9),
        "J10 fan": ((139.0, 86.0), 9.9),
        "J1 coil NTC": ((55.0, 84.0), 7.4),
        "J2 heatsink NTC": ((-20.0, 84.0), 7.4),
        "J3 pan RTD": ((152.0, 86.0), 12.4),
        "J12 rim NTC (R36, proposed)": ((126.0, 86.0), 7.4),
    }
    out = {}
    for name, ((x, y), length) in rows.items():
        d, hole = min((math.hypot(x - hx, y - hy), (hx, hy)) for hx, hy in holes)
        need = 4.0 + length / 2
        out[name] = {"centre": (x, y), "nearest_hole": hole, "distance_mm": round(d, 2),
                     "needed_mm": round(need, 2), "conflict": d < need}
    conflicts = [k for k, v in out.items() if v["conflict"]]
    return {"source": "CONTROLLER-SPEC R31 connector table and hole list, R33 J7; JLC/JST body lengths",
            "rows": out, "conflicts_orientation_blind": conflicts,
            "note": "informational (enclosure-owned geometry): the circle bound assumes the worst "
                    "orientation; layout/check_layout.py checks the placed bodies"}


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


def ui_5v_supply() -> dict:
    """J7.1 +5 V for the UI board (R33; 5 V encoder option): v15 -> 2 x 100 ohm -> TLV76050
    (DBZ 275.2 C/W). The 30 mA allocation is the J7 +5 V budget the UI board must stay within."""
    i_enc, i_gnd_max = 0.030, 0.005             # UI +5 V allocation [UNVERIFIED]; TLV760 IGND 5 mA max
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


def blower_supply() -> dict:
    """Adjustable blower supply (L3, DECISIONS C28): TPS62933 with a filtered PWM injected into FB.

    Sources: Delta BFB1012VH-F00 spec (operating 5.5-13.2 V, input current 1.42 A typ / 2.70 A
    max, 17.04 W typ / 32.40 W max); TI SLUSEA4D (VFB 788-812 mV at 0-85 C, RDSON 76/32 mOhm at
    25 C, IHS_LIMIT 4.2-5.8 A, RthJA 112.2 C/W JEDEC and 60.2 C/W on TI's 2-layer EVM);
    Sunlord SWRB-S datasheet (SWRB1205S-100MT 10 uH +/-20 %, 4.0 A rated, 25 mOhm max, -40..105 C
    incl. self-heating); JST eXH.pdf (3 A per contact with AWG22). R32 CONTROLLER-SPEC: drive
    cap 0.8 (about 9 W) except in a fault.
    """
    rtop, rbot, rinj = 140e3, 11.5e3, 56.2e3 + 12.1e3      # injection 56.2 k + PWM filter 12.1 k
    tol = {"rtop": 0.001, "rbot": 0.001, "rinj": 0.01}
    vfb = (0.788, 0.812)
    vh = (3.242, 3.367)                         # GPIO high = v3v3 band (rail_3v3)

    def vout(vctl, f, rt, rb, ri):
        return f + rt * (f / rb - (vctl - f) / ri)
    corners = []
    for f in vfb:
        for st in (-1, 1):
            for sb in (-1, 1):
                for si in (-1, 1):
                    rt, rb, ri = rtop * (1 + st * tol["rtop"]), rbot * (1 + sb * tol["rbot"]), rinj * (1 + si * tol["rinj"])
                    corners.append((f, rt, rb, ri))
    vmax = [vout(0.0, *c) for c in corners]
    vmin = [vout(v, *c) for c in corners for v in vh]
    # inductor ripple and peak, worst case: L -20 %, fsw 500 kHz nominal (-10 % allowance), Vin 15.375
    L, fsw, vin = 10e-6 * 0.8, 500e3 * 0.9, 15 * 1.025
    ripple = {v: (vin - v) * v / (vin * L * fsw) for v in (max(vmax), 9.0, min(vmin))}
    i_typ, i_max = 1.42, 2.70
    peak_max = i_max + max(ripple.values()) / 2
    # converter loss at the blower's full current, hot RDSON (x1.4 at 125 C, typical MOSFET
    # tempco allowance), plus switching (10 ns edges) and the inductor DCR
    def loss(i, vo):
        d = vo / vin
        cond = d * i * i * 0.076 * 1.4 + (1 - d) * i * i * 0.032 * 1.4
        sw = 0.5 * vin * i * 20e-9 * 500e3
        return cond + sw + 0.03, i * i * 0.025
    p_ic_typ, p_l_typ = loss(i_typ, 12.0)
    p_ic_max, p_l_max = loss(i_max, 12.0)
    ta = 60.0
    tj = {"typ_jedec": ta + p_ic_typ * 112.2, "max_jedec": ta + p_ic_max * 112.2,
          "typ_evm": ta + p_ic_typ * 60.2, "max_evm": ta + p_ic_max * 60.2}
    # PS1 (IRM-20-15, 21 W) at the blower's normal cap and at full speed
    p_cap = 9.0 / 0.90
    p_full_typ = 17.04 / 0.90
    p_full_max = 32.40 / 0.90
    return {"source": "Delta BFB1012VH-F00 spec; TI SLUSEA4D; Sunlord SWRB-S; JST eXH.pdf; R32 CONTROLLER-SPEC",
            "vout_duty0_V": [min(vmax), max(vmax)], "vout_duty100_V": [min(vmin), max(vmin)],
            "inductor_ripple_pp_A": {f"{k:.1f}V": r for k, r in ripple.items()},
            "inductor_peak_at_2p70A": peak_max, "ic_loss_W": {"typ": p_ic_typ, "max": p_ic_max},
            "inductor_loss_W": {"typ": p_l_typ, "max": p_l_max}, "tj_C_at_60C": tj,
            "ps1_blower_input_W": {"r32_cap": p_cap, "full_typ": p_full_typ, "full_max": p_full_max},
            "checks": {"duty0_le_13p2V_fan_max": max(vmax) <= 13.2,
                       "duty0_ge_11p5V": min(vmax) >= 11.5,
                       # full duty spans the blower's 5.5 V floor; firmware closes the speed loop on FG
                       "duty100_le_6p0V": max(vmin) <= 6.0,
                       "duty100_ge_5p0V": min(vmin) >= 5.0,
                       "inductor_peak_within_4A_rating": peak_max <= 4.0,
                       # continuous: 1.42 A typ on the JEDEC figure; 2.70 A is the start-up / lock
                       # peak (the blower shuts down on a locked rotor), checked on TI's EVM figure
                       "tj_le_125C_continuous_jedec": tj["typ_jedec"] <= 125,
                       "tj_le_125C_peak_evm": tj["max_evm"] <= 125,
                       "j10_xh_3A_ge_2p70A": 3.0 >= i_max}}


def ps3_budget() -> dict:
    """Stage 16 (DECISIONS C33): PS3 = Mean Well IRM-60-15ST feeds the blower buck through J13.

    Sources: IRM-60-SPEC 2025-11-21 p.2 (15 V 4 A, 60 W, +/-2.5 %, OVP 15.75-20.25 V, overload
    115-160 % hiccup) and p.3 derating (100 % to 50 C, 75 % at 60 C, read from the graph);
    Delta BFB1012VH-F00 (32.4 W / 2.70 A max at 12.0 V); fan law P ~ V^3 to the buck's 12.40 V
    duty-0 corner (estimate, as PLAN-16 sec. 1.1); JST eVH.pdf p.1 (VH 10 A with AWG16, 7 A with
    AWG18 on the shrouded header: the lower figure is used; contact resistance 10 mOhm max initial);
    AWG18 20.95 mOhm/m at 20 C;
    TI SLUSEA4D IHS_LIMIT 4.2-5.8 A, VIN 3.8-30 V.
    """
    v_hi = blower_supply()["vout_duty0_V"][1]
    p_blower = 32.4 * (v_hi / 12.0) ** 3
    i_blower = p_blower / v_hi
    eta = 0.90                                     # buck allocation, as blower_supply()
    p_out = p_blower / eta
    v_lo = 15 * 0.975
    i_out = p_out / v_lo
    # 450 mm twisted pair out and back (enclosure R41 routes 292 mm; 450 kept as the envelope), AWG18
    # at 80 C (copper +0.393 %/K), plus 4 interfaces at 10 mOhm: the two VH contact pairs at J13 (JST
    # eVH p.1, initial maximum) and PS3's two screw terminals, assumed equal to the VH figure.
    loop_ohm = 2 * 0.450 * 20.95e-3 * (1 + 0.00393 * 60) + 4 * 10e-3
    drop = i_out * loop_ohm
    vin_u2 = v_lo - drop
    # start: U2 at its high-side limit, 12.40 V out -> 15 V draw
    i_start = [ilim * v_hi / eta / v_lo for ilim in (4.2, 5.8)]
    ocp_lo_a = 60 * 1.15 / 15
    derate = {"50C": 60.0, "60C": 45.0}
    # TPS62933 duty without foldback (fan_buck(): 1 - tOFF_MIN x f, typ) sets the VIN U2 needs
    dmax = 1 - 140e-9 * 550e3
    vin_need = (v_hi + i_blower * 0.025 * 1.3) / dmax
    return {"source": ["IRM-60-SPEC 2025-11-21 p.2/p.3", "Delta BFB1012VH-F00", "JST eVH.pdf p.1",
                       "TI SLUSEA4D", "PLAN-16 (power-stage stage16-blower-supply)"],
            "blower_W_at_duty0_corner": p_blower, "blower_A": i_blower,
            "ps3_out_W": p_out, "ps3_out_A_at_low_corner": i_out, "rating_W": 60.0,
            "derated_W": derate, "harness_loop_ohm": loop_ohm, "harness_drop_V": drop,
            "u2_vin_min_V": vin_u2, "u2_vin_needed_V": vin_need,
            "start_draw_A_at_u2_limit": i_start, "ps3_ocp_low_A": ocp_lo_a,
            "checks": {"ps3_within_60W": p_out <= 60.0,
                       "ps3_within_derated_60C": p_out <= derate["60C"],
                       "j13_vh_7A_ge_load": 7.0 >= i_out,
                       "j13_vh_7A_ge_start_bound": 7.0 >= max(i_start),
                       "u2_headroom_at_duty0": vin_u2 >= vin_need,
                       "c_blw_bulk_25V_above_ovp": 25.0 > 20.25,
                       # TPS62933 operating VIN 3.8-30 V (controller_parts.ato / SLUSEA4D)
                       "u2_vin_range_covers_ovp": 20.25 <= 30.0}}


def blw_pg() -> dict:
    """BLW_PG (DECISIONS C33): 20 k / 4.7 k (1 %) from V15_BLW into TCA9555 P16.

    TI SCPS200E: P-port VIH 0.7 x VCC, VIL 0.3 x VCC, 5 V tolerant I/O (abs max 6 V), internal
    pull-up 100 k typical (bounded here at 50 k as a conservative allowance). v3v3 3.135-3.465 V.
    PS3 absent is modelled with V15_BLW open (no path to ground other than the divider), which
    is the worst case: U2's EN divider only pulls it lower.
    """
    rt, rb, tol = 20e3, 4.7e3, 0.01
    vcc = (3.135, 3.465)
    rpu = (50e3, 100e3)

    def node(vin, rt_, rb_, rpu_, vcc_):
        # Thevenin of the divider, then the pull-up to VCC
        vth = vin * rb_ / (rt_ + rb_)
        rth = rt_ * rb_ / (rt_ + rb_)
        return vth + (vcc_ - vth) * rth / (rth + rpu_)
    hi_min = node(15 * 0.975, rt * (1 + tol), rb * (1 - tol), 1e12, vcc[1])
    hi_ovp = node(20.25, rt * (1 - tol), rb * (1 + tol), rpu[0], vcc[1])
    # absent: V15_BLW open -> only rb to ground; pull-up at its strongest
    lo_abs = vcc[1] * rb * (1 + tol) / (rb * (1 + tol) + rpu[0])
    return {"source": ["TI SCPS200E", "IRM-60-SPEC 2025-11-21 p.2"],
            "present_min_V": hi_min, "present_ovp_V": hi_ovp, "absent_max_V": lo_abs,
            "vih_V": 0.7 * vcc[1], "vil_V": 0.3 * vcc[0],
            "divider_mA_at_15V": 15 / (rt + rb) * 1e3,
            "checks": {"present_reads_high": hi_min >= 0.7 * vcc[1],
                       "absent_reads_low": lo_abs <= 0.3 * vcc[0],
                       "ovp_within_5V5_tolerant_input": hi_ovp <= 5.5}}


# Semitec GT-2 series datasheet (semitec.co.jp "GT-2シリーズ.pdf", 2023-08-01), R-T table in kOhm.
# 104GT-2: 100 k +/-3 % at 25 C, B25/85 4267 K +/-2 %, -50..+300 C; 103GT-2 (10 k) is rated
# -50..+200 C. Dissipation constant ~0.6 mW/C, time constant ~7 s (still air), 3.0 mW rated.
GT2_104 = {20: 126.8, 25: 100.0, 30: 79.36, 190: 0.5408, 200: 0.4393, 210: 0.3597, 240: 0.2065,
           250: 0.1740, 260: 0.1475, 270: 0.1258, 280: 0.1079, 290: 0.09305}
GT2_103 = {20: 12.64, 25: 10.00, 30: 7.968, 190: 0.07186, 200: 0.05960, 210: 0.04986, 240: 0.03059,
           250: 0.02640}


def rim_ntc() -> dict:
    """Rim NTC divider (L3, DECISIONS C31): node voltage and slope at 25/200/250/280 C for the
    chosen 104GT-2 with a 1.00 k pull-up, against the C27 10 k bead with a 10 k pull-up."""
    vdd = 3.3

    def node(rt_k, rpu_k):
        return vdd * rt_k / (rt_k + rpu_k)

    def table(rt, rpu_k, temps):
        out = {}
        for t in temps:
            if t - 10 not in rt and t - 5 not in rt or t not in rt:
                continue
            lo, hi = (t - 5, t + 5) if t == 25 else (t - 10, t + 10)
            if hi not in rt:              # end of the table: one-sided difference
                hi = t
            if lo not in rt:
                continue
            slope = (node(rt[lo], rpu_k) - node(rt[hi], rpu_k)) / (hi - lo) * 1e3
            out[t] = {"R_ohm": rt[t] * 1e3, "V": node(rt[t], rpu_k), "mV_per_K": slope}
        return out
    chosen = table(GT2_104, 1.0, (25, 200, 250, 280))
    old = table(GT2_103, 10.0, (25, 200, 250))
    # self-heating: power in the NTC peaks where R_ntc = R_pu (V^2 / 4R); dissipation 0.6 mW/C
    p_peak = vdd ** 2 / (4 * 1.0e3)
    p250 = (vdd / ((GT2_104[250] + 1.0) * 1e3)) ** 2 * GT2_104[250] * 1e3
    p280 = (vdd / ((GT2_104[280] + 1.0) * 1e3)) ** 2 * GT2_104[280] * 1e3
    i_max = vdd / 1.0e3
    return {"source": "Semitec GT-2 series datasheet (2023-08-01) R-T table; dissipation 0.6 mW/C",
            "chosen_104GT2_1k_pullup": chosen, "previous_10k_bead_10k_pullup": old,
            "self_heating_K": {"peak_at_R_eq_Rpu": p_peak * 1e3 / 0.6, "at_250C": p250 * 1e3 / 0.6,
                               "at_280C": p280 * 1e3 / 0.6},
            "ntc_power_peak_mW": p_peak * 1e3, "rail_current_max_mA": i_max * 1e3,
            "checks": {"node_250C_between_0p3_and_1p0V": 0.3 <= chosen[250]["V"] <= 1.0,
                       "slope_250C_ge_5mV_per_K": chosen[250]["mV_per_K"] >= 5.0,
                       "slope_280C_ge_3mV_per_K": chosen[280]["mV_per_K"] >= 3.0,
                       "ntc_power_le_3mW_rated": p_peak * 1e3 <= 3.0,
                       "self_heating_250C_le_3K": p250 * 1e3 / 0.6 <= 3.0}}


# ---- thermal-sense comparator trips (L3, DECISIONS C32): a Python port of the 64-corner method of
# zapote/packages/zapote-erc/src/thermal_sense.rs (corners: sensor B and R25 at their limits x each
# resistor at its tolerance), applied to the controller's values. Comparator: INP = reference with
# hysteresis to the output, INN = NTC node (10 k pull-up); hot when the node falls below INP.
GT2_104_HOT = {0: 353.7, 10: 208.6, 20: 126.8, 25: 100.0, 100: 5.556, 110: 4.082, 120: 3.043, 130: 2.298,
               140: 1.758, 150: 1.360, 160: 1.064, 170: 0.8414, 180: 0.6714, 190: 0.5408, 200: 0.4393,
               210: 0.3597}                      # kOhm, Semitec GT-2 table (104GT-2)
SENSORS = {
    # Vishay NTCALUG01A104GA as the thermal-sense validator models it (sensor-contract.json:
    # r25 100 k +/-2 %, beta 4190 K +/-1.5 %, -55..150 C)
    "vishay_ntcalug01a104ga": {"kind": "beta", "r25": 100e3, "r25_tol": 0.02, "beta": 4190.0, "beta_tol": 0.015,
                               "t_max": 150.0},
    # Semitec 104GT-2 (GT-2 datasheet: 100 k +/-3 %, B25/85 4267 K +/-2 %, -50..300 C)
    "semitec_104gt2": {"kind": "table", "table": GT2_104_HOT, "r25_tol": 0.03, "beta": 4267.0, "beta_tol": 0.02,
                       "t_max": 300.0},
}


def ntc_r(sensor, t, r25_scale=1.0, beta_scale=1.0):
    sp = SENSORS[sensor]
    tk = t + 273.15
    if sp["kind"] == "beta":
        return sp["r25"] * r25_scale * math.exp(sp["beta"] * beta_scale * (1 / tk - 1 / 298.15))
    tab = sp["table"]
    ks = sorted(tab)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            la, lb = math.log(tab[a]), math.log(tab[b])
            r = math.exp(la + (lb - la) * (t - a) / (b - a)) * 1e3
            break
    else:
        raise ValueError(f"{sensor}: {t} C outside the table")
    return r * r25_scale * math.exp(sp["beta"] * (beta_scale - 1) * (1 / tk - 1 / 298.15))


def _temp_at(sensor, r, rs, bs, lo, hi):
    for _ in range(70):
        mid = (lo + hi) / 2
        if ntc_r(sensor, mid, rs, bs) > r:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def comparator_trip(sensor, rfix, rtop, rbot, rhyst, rs=1.0, bs=1.0, lo=0.0, hi=210.0):
    par = lambda a, b: a * b / (a + b)  # noqa: E731
    k_trip = par(rbot, rhyst) / (rtop + par(rbot, rhyst))          # output low before the trip
    k_rel = rbot / (rbot + par(rtop, rhyst))                        # output high while hot
    return (_temp_at(sensor, rfix * k_trip / (1 - k_trip), rs, bs, lo, hi),
            _temp_at(sensor, rfix * k_rel / (1 - k_rel), rs, bs, lo, hi))


def trip_band(sensor, parts):
    """parts: {"fixed": (ohm, tol), "top": ..., "bottom": ..., "hyst": ...} -> nominal and 64 corners."""
    import itertools
    sp = SENSORS[sensor]
    nom = comparator_trip(sensor, *(parts[k][0] for k in ("fixed", "top", "bottom", "hyst")))
    trips, rels = [], []
    for sb, sr, s1, s2, s3, s4 in itertools.product((-1, 1), repeat=6):
        vals = [parts[k][0] * (1 + sgn * parts[k][1]) for k, sgn in zip(("fixed", "top", "bottom", "hyst"), (s1, s2, s3, s4))]
        t, r = comparator_trip(sensor, *vals, rs=1 + sr * sp["r25_tol"], bs=1 + sb * sp["beta_tol"])
        trips.append(t)
        rels.append(r)
    return {"trip_nominal_C": nom[0], "release_nominal_C": nom[1], "trip_band_C": [min(trips), max(trips)],
            "release_band_C": [min(rels), max(rels)]}


def open_margins(sensor, rfix=(10e3, 0.01), otop=(1.21e3, 0.01), obot=(100e3, 0.01), vcc=(3.135, 3.465),
                 t_valid_min=0.0, leak=1e-6, comp_err=0.014):
    """Open detection (contract: valid down to 0 C, comparator error 14 mV, sense leakage 1 uA):
    no false 'open' at 0 C, and a real open lifts the node above OPEN_REF."""
    sp = SENSORS[sensor]
    worst_cold, worst_open = 1e9, 1e9
    for v in vcc:
        for f in (-1, 1):
            for a in (-1, 1):
                for b in (-1, 1):
                    rf = rfix[0] * (1 + f * rfix[1])
                    ref = v * obot[0] * (1 + b * obot[1]) / (obot[0] * (1 + b * obot[1]) + otop[0] * (1 + a * otop[1]))
                    r0 = ntc_r(sensor, t_valid_min, 1 + sp["r25_tol"], 1 + sp["beta_tol"])
                    v0 = v * r0 / (r0 + rf)
                    worst_cold = min(worst_cold, ref - v0)
                    worst_open = min(worst_open, (v - leak * rf) - ref)
    return {"cold_0C_margin_V": worst_cold, "open_margin_V": worst_open, "comparator_error_V": comp_err}


def thermal_trips(values=None) -> dict:
    """Controller thermal-sense thresholds (L3, C32) and the trip ladder they must respect."""
    v = values or {"hs": {"fixed": (10e3, 0.01), "top": (11.5e3, 0.01), "bottom": (8.06e3, 0.01), "hyst": (34.8e3, 0.01)},
                   "coil": {"fixed": (10e3, 0.01), "top": (90.9e3, 0.001), "bottom": (7.06e3, 0.001),
                            "hyst": (140e3, 0.001)}}
    hs = trip_band("vishay_ntcalug01a104ga", v["hs"])
    coil = trip_band("semitec_104gt2", v["coil"])
    # Ladder (coordinator decision 2026-10-12; firmware thermal_mgmt / coil_guard on fw/controller-l2-pins):
    # sink: fan 88.6 < firmware trip 95 < hardware; coil: fan 140 < derate 150-160 < firmware trip 165 < hardware.
    # FET: IPW65R018CFD7, theta_jc 0.28 + theta_cs 0.634 C/W; Tj ~= T_sink + 27.8 K at 28 A, basis A
    # (power-stage task 05 round 6 board_side.py, commit 18318042c; requirement.py:37 Tj target 125 C,
    # datasheet Tj max 150 C).
    sensor_tol_95 = 2.0                       # K, Vishay r25 2 % / beta 1.5 % at 95 C (firmware reading)
    tj_hot = hs["trip_band_C"][1] + 27.8
    om_hs = open_margins("vishay_ntcalug01a104ga")
    om_coil = open_margins("semitec_104gt2")
    return {"source": "port of zapote-erc thermal_sense.rs 64-corner method; sensor-contract.json; Semitec GT-2; "
                      "power-stage board_side.py (18318042c) theta_jc 0.28 + theta_cs 0.634",
            "hs": hs, "coil": coil, "tj_at_hs_trip_high_corner_C": tj_hot,
            "open_hs": om_hs, "open_coil": om_coil,
            "checks": {"hs_trip_low_corner_above_fw_95_plus_sensor_tol": hs["trip_band_C"][0] >= 95.0 + sensor_tol_95,
                       "hs_trip_high_corner_tj_le_135C": tj_hot <= 135.0,
                       # the interlock latches a trip; release only re-arms the comparator after cooling
                       "hs_release_band_below_trip_band": hs["release_band_C"][1] < hs["trip_band_C"][0],
                       "coil_release_band_below_trip_band": coil["release_band_C"][1] < coil["trip_band_C"][0],
                       "coil_trip_low_corner_above_fw_165": coil["trip_band_C"][0] > 165.0,
                       "coil_trip_within_sensor_rating": coil["trip_band_C"][1] < SENSORS["semitec_104gt2"]["t_max"],
                       "hs_trip_within_sensor_rating": hs["trip_band_C"][1] < SENSORS["vishay_ntcalug01a104ga"]["t_max"],
                       "open_cold_margin_hs": om_hs["cold_0C_margin_V"] >= om_hs["comparator_error_V"],
                       "open_cold_margin_coil": om_coil["cold_0C_margin_V"] >= om_coil["comparator_error_V"],
                       "open_detect_margin_hs": om_hs["open_margin_V"] >= om_hs["comparator_error_V"],
                       "open_detect_margin_coil": om_coil["open_margin_V"] >= om_coil["comparator_error_V"]}}


# ---- capacitive-mode detector timing (DECISIONS C39; native-21 OPEN-ITEMS S14)
# Maximum propagation delays at VCC = 3.3 V +/- 0.3 V, -40..85 C, CL 30/50 pF unless noted.
CM_TPD_NS = {
    "u_cm_inv SN74LVC1G14 A->Y": (5.5, "SCES218AA 6.x, CL 30/50 pF"),
    "u_cm_ff SN74LVC74A CLK->Q": (5.2, "SCAS287U 6.11"),
    "u_cm_or SN74LVC1G32 A->Y": (4.5, "SCES219W, CL 30/50 pF"),
    "interlock.fault_inv SN74LVC14A A->Y": (6.4, "SCAS285AC 7.9"),
    "interlock.aggregate 74HC30 A->Y": (165.0, "Nexperia 74HC30 Rev. 6 tpd at VCC 2.0 V, -40..85 C (no 3.3 V row; "
                                                "tpd falls with VCC, so the 2.0 V figure bounds 3.135 V)"),
    "interlock.control_inv SN74LVC14A A->Y": (6.4, "SCAS285AC 7.9"),
    "interlock.latch SN74LVC1G74 CLR->Q": (5.9, "SCES794G 7.7"),
    "u_permit SN74LVC1G08 A->Y": (4.5, "SCES217AA 5.8, CL 30/50 pF"),
    "J4 harness <= 1 m (allocation 5 ns/m) + 100 ohm x 50 pF": (10.0, "allocation"),
    "native-21 U22/U23 SN74LVC1G00 A->Y (DIS)": (4.7, "SCES212AC, CL 30/50 pF"),
}
CM_DT_NS = (408.0, 569.0)       # native-21 DECISIONS (F6 entry): R9/R17 49.9 k, 2EDR8259X DT +/-15 %
CM_GATE = {"r_on_ohm": 68.0, "r_on_tol": 0.01, "cgs_F": 4.7e-9, "cgs_tol": 0.05, "v_on": 15.0, "v_off": -2.0,
           "vth_min_V": 1.9,
           "source": "native-21 candidate 39 (DECISIONS 54; gate-network-2026-10-15 README): R_on 25121WF680JT4E "
                     "68 ohm 1 %, Cgs GRM1885C1H472JA01D 4.7 nF C0G 5 %; F6 bipolar drive +15 / -2 V; 1.9 V = "
                     "the hot off-gate screen (DECISIONS 2026-10-03), used as the lowest Vth"}
CM_CT_TPD_NS = 55.0             # native-21 ct_zc TLV3201, SBOS561C tpd max -40..125 C, 20 mV overdrive
CM_F_MAX_HZ = 60e3              # top of the 33-60 kHz tank class (sensor-r3 checks.py item 7)
CM_SW_LATCH_EDGES = (370, 740)  # native-21 OPEN-ITEMS S14: S4 edges per leg before the software latch


def _gate_cross_ns(l_h: float, r: float, c: float, v_on: float, v_off: float, vth: float) -> float:
    """Series R-L-C gate loop stepped from v_off to v_on: time for the gate capacitor to reach vth
    (RK4; FET Ciss and the driver's output resistance left out, which only makes the edge faster)."""
    q = c * v_off
    i = 0.0
    t, h = 0.0, 0.05e-9
    while q / c < vth:
        def d(i_, q_):
            return (v_on - r * i_ - q_ / c) / l_h, i_
        k1 = d(i, q)
        k2 = d(i + h / 2 * k1[0], q + h / 2 * k1[1])
        k3 = d(i + h / 2 * k2[0], q + h / 2 * k2[1])
        k4 = d(i + h * k3[0], q + h * k3[1])
        i += h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        q += h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        t += h
        if t > 5e-6:
            raise RuntimeError("gate never reaches vth")
    return t * 1e9


def _burst_samples(fr: float, q: float, n_edges: int = 40, steps: int = 400) -> dict:
    """Normalised series RLC (L = C = 1, w0 = 1, R = 1/Q) driven from rest by a 50 % square wave at
    fr x f0, HS-on first. Sample the current at every turn-off command: HS turn-off expects i > 0,
    LS turn-off i < 0. Returns the wrong-sign edges and the smallest correct-sign |i| relative to
    the steady-state peak."""
    w = fr
    h = math.pi / w / steps
    r = 1.0 / q
    i = vc = 0.0
    bad, mags = [], []
    for e in range(n_edges):
        v = 1.0 if e % 2 == 0 else -1.0
        for _ in range(steps):
            def d(i_, vc_):
                return v - r * i_ - vc_, i_
            k1 = d(i, vc)
            k2 = d(i + h / 2 * k1[0], vc + h / 2 * k1[1])
            k3 = d(i + h / 2 * k2[0], vc + h / 2 * k2[1])
            k4 = d(i + h * k3[0], vc + h * k3[1])
            i += h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
            vc += h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        good = i > 0 if e % 2 == 0 else i < 0
        (mags if good else bad).append(abs(i) if good else e)
    # steady-state fundamental: |I1| = (4/pi) / |Z|, Z = R + j (w - 1/w)
    i_ss = (4 / math.pi) / math.hypot(r, w - 1 / w)
    return {"wrong_sign_edges": bad, "min_sample_over_ss_peak": (min(mags) / i_ss) if mags else None,
            "min_sample_V_over_Z0": min(mags) if mags else None}


def capmode() -> dict:
    """Timing of the hardware capacitive-mode detector against native-21's dead time and gate edge.

    A capacitive sample at an HS turn-off command (current already negative) makes the next LS
    turn-on hard (S4); the detector must drop the drivers' DIS before that LS gate reaches Vth.
    Deadline from the HS turn-off command: DT_min plus the time the LS gate takes from -2 V to Vth
    on R_on / Cgs and the extracted gate-loop inductance (LS 46.85 nH; the LA flip-flop guards the
    HS gate, 55.66 nH). The command-to-driver-input and driver propagation delays are left out
    (they only add margin). The 2EDR8259X DIS-to-output delay is not in its datasheet: the result is
    the slack left for it (open item for the power-stage bench).
    """
    import hashlib
    n21 = UNIT / "inputs/native-21"
    prov = json.loads((n21 / "legB21-h0-best.provenance.json").read_text())
    raw = (n21 / prov["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != prov["sha256"]:
        raise SystemExit("legB21-h0-best.matrix.txt does not match its provenance")
    mat = json.loads(raw.decode().split("RESULT", 1)[1])
    names = mat["names"]
    l_hs = mat["L0_nH"][names.index("P3_gate_high")][names.index("P3_gate_high")] * 1e-9
    l_ls = mat["L0_nH"][names.index("P4_gate_low")][names.index("P4_gate_low")] * 1e-9
    g = CM_GATE
    r_min = g["r_on_ohm"] * (1 - g["r_on_tol"])
    c_min = g["cgs_F"] * (1 - g["cgs_tol"])
    cross = {leg: _gate_cross_ns(l, r_min, c_min, g["v_on"], g["v_off"], g["vth_min_V"])
             for leg, l in (("LS (after a sampled HS turn-off)", l_ls), ("HS (after a sampled LS turn-off)", l_hs))}
    chain = sum(v for v, _ in CM_TPD_NS.values())
    deadline_start = CM_DT_NS[0]
    deadline_vth = CM_DT_NS[0] + min(cross.values())
    slack_start = deadline_start - chain
    slack_vth = deadline_vth - chain
    half_period = 0.5 / CM_F_MAX_HZ * 1e9
    # blind band: the sample sees the current CM_CT_TPD_NS before the command edge; ZVS needs the
    # sign to hold until the partner turns on, DT_max after the command
    blind_ns = CM_CT_TPD_NS + CM_DT_NS[1]
    blind_deg = blind_ns * 1e-9 * CM_F_MAX_HZ * 360.0
    # burst start from rest above resonance: no wrong-sign sample (no false trip); a start below
    # resonance is caught on the first edges (negative control)
    grid = {}
    for qf in (1.0, 2.0, 4.0, 8.0, 15.0):
        for fr in (1.02, 1.05, 1.1, 1.2, 1.3, 1.5, 1.8):
            grid[f"Q{qf:g}_f{fr:g}"] = _burst_samples(fr, qf)
    below = {f"Q{qf:g}_f0.9": _burst_samples(0.9, qf) for qf in (2.0, 8.0, 15.0)}
    worst_mag = min(v["min_sample_V_over_Z0"] for v in grid.values())
    return {"source": ["SCES218AA", "SCAS287U", "SCES219W", "SCAS285AC", "Nexperia 74HC30", "SCES794G",
                       "SCES217AA", "SCES212AC", "SBOS561C", "native-21 DECISIONS (DT band, candidate 39)",
                       "legB21-h0-best.matrix.txt (f4ed8b17a)"],
            "tpd_max_ns": {k: {"ns": v, "basis": b} for k, (v, b) in CM_TPD_NS.items()},
            "chain_to_dis_pin_max_ns": chain,
            "gate_loop_nH": {"HS": l_hs * 1e9, "LS": l_ls * 1e9}, "gate": g,
            "gate_reaches_vth_after_ns": cross,
            "dead_time_ns": CM_DT_NS,
            "slack_for_dis_to_output_before_partner_output_rises_ns": slack_start,
            "slack_for_dis_to_output_before_partner_gate_reaches_vth_ns": slack_vth,
            "half_period_at_f_max_ns": half_period,
            "edges_before_stop": {"hardware, DIS-to-output <= slack": 0,
                                  "hardware, DIS-to-output < half period": 1,
                                  "software latch (S14)": CM_SW_LATCH_EDGES},
            "blind_band": {"ns": blind_ns, "deg_at_f_max": blind_deg,
                           "meaning": "a current zero that falls between ct_zc's view of the command edge and "
                                      "the partner's turn-on (inside the dead time) is not sampled as "
                                      "capacitive: partial ZVS loss there stays a firmware matter (inductive "
                                      "margin, S14 software latch)"},
            "burst_start": {"grid_f_over_f0_1.02_to_1.8_Q_1_to_15": grid, "below_resonance_f0.9": below,
                            "min_sample_V_over_Z0": worst_mag,
                            "note": "smallest correct-sign current at any sampled edge, in units of the bridge "
                                    "drive voltage over the tank's characteristic impedance sqrt(L/C); CT_ZC "
                                    "must resolve at least this at the first edges (bench item, with the "
                                    "native-21 'zero-cross behaviour with no tank current' item)"},
            "firmware_requirements": [
                "start every burst at or above the tank resonance (the 2026-10-03 inductive-side rule); a start "
                "below it trips the detector on the first edges",
                "RUN_EN low -> high re-arms the detector; raise RUN_EN only with PWM idle",
                "read CM_HA_OK_RB / CM_LA_OK_RB on the expander after any interlock trip to name the cause"],
            "checks": {"chain_reaches_dis_before_dt_min": slack_start > 0,
                       "chain_reaches_dis_before_partner_vth": slack_vth > 0,
                       "chain_well_inside_half_period": chain < 0.1 * half_period,
                       "burst_start_above_resonance_never_samples_wrong_sign":
                           all(not v["wrong_sign_edges"] for v in grid.values()),
                       "burst_start_below_resonance_is_caught": all(v["wrong_sign_edges"] for v in below.values()),
                       "blind_band_le_15deg_at_60kHz": blind_deg <= 15.0}}


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
        "ui_5v_supply": ui_5v_supply(),
        "blower_supply": blower_supply(),
        "ps3_budget": ps3_budget(),
        "blw_pg": blw_pg(),
        "rim_ntc": rim_ntc(),
        "thermal_trips": thermal_trips(),
        "rim_trip": rim_trip(),
        "capmode": capmode(),
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
