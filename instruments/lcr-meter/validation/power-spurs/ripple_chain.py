#!/usr/bin/env python3
"""Task 3: switcher ripple -> LDO PSRR -> op-amp / FDA / ADC PSRR -> ADC input,
and the worst-case impedance error if a ripple harmonic aliases into the fit
main lobe. Also a USB-SOF / digital-current estimate through the supply rails.

Everything here is an ESTIMATE built from datasheet typical curves plus the
stated assumptions (A1-A9 in ASSUMPTIONS). The PSRR path only: direct magnetic
or capacitive pickup from the switch nodes and inductors, and ground-return
coupling, are not modelled (no extracted layout parasitics exist).
Writes ripple_chain.json.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np

import common as c
import regulator_check as rc
from dds_spurs import dut_coefficient, DUTS

HERE = pathlib.Path(__file__).resolve().parent
HARMONICS = np.arange(1, 41)

ASSUMPTIONS = {
    "A1_cap_retention_at_14V": [0.40, 0.70],     # worst / typical (no vendor curve)
    "A2_esr_per_10uF_ohm": [0.010, 0.004],       # at ~1 MHz, 1210 X7R
    "A3_output_loop_esl_h": [3e-9, 1.5e-9],      # cap ESL + vias + trace, parallel caps
    "A4_switch_edge_s": 10e-9,                   # current transition time
    "A5_ldo_psrr_margin_db": [6.0, 0.0],         # derate the typical curve
    "A6_load_scale": [2.0, 1.0],                 # x regulator_check load estimate
    "A7_adc_avdd_psrr_above_100k_db": 30.0,      # spec only < 100 kHz (70 dB)
    "A8_ferrite_fb1": "variant 'no_fb1': no attenuation credited; variant 'fb1_1ohm': FB1 >= 1 ohm "
                      "at >= 1 MHz into C103 22 uF (25 V, 75 % retention) || 3 x 1 uF || 2 x 100 nF",
    "A9_usb_digital_pulse": {"delta_i_a": 0.02, "width_s": 20e-6, "z_5v_ohm": 0.3},
}
SIGNALS = {  # ADC differential peaks (V): brief + docs/analog-validation-rev-c.md
    "15 ohm, 100 ohm range": {"A": c.SIGNAL_15R_A_V, "B": c.SIGNAL_15R_A_V * 100 / 15, "Vs": 1.398},
    "matched 100 ohm": {"A": c.SIGNAL_A_MATCHED_V, "B": c.SIGNAL_A_MATCHED_V, "Vs": 1.398},
}


def tri_harm(vpp, d, m):
    """One-sided harmonic amplitude of a piecewise-linear wave, rise fraction d."""
    return vpp * np.abs(np.sin(np.pi * m * d)) / (np.pi ** 2 * m ** 2 * d * (1 - d))


def rect_harm(vpp, d, m):
    return 2 * vpp * np.abs(np.sin(np.pi * m * d)) / (np.pi * m)


def esl_harm(l_esl, di, fsw, d, m, t_edge):
    a = 4 * l_esl * di * fsw * np.abs(np.sin(np.pi * m * d))
    m_c = 1 / (np.pi * t_edge * fsw)
    return a / np.sqrt(1 + (m / m_c) ** 2)


def output_ripple(rail, corner):
    """Harmonic amplitudes (V) at RAW_P / RAW_N for corner 'worst' or 'typ'."""
    w = 0 if corner == "worst" else 1
    s = c.TPS65131
    fsw = s["fsw_min_hz"] if corner == "worst" else s["fsw_typ_hz"]
    vin = rc.VIN[0] if corner == "worst" else rc.VIN[1]
    l = rc.L_NOM * (1 - rc.L_TOL) if corner == "worst" else rc.L_NOM
    iout = rc.LOAD[rail] * ASSUMPTIONS["A6_load_scale"][w]
    vo = rc.boost_vpos("max") if rail == "pos" else abs(rc.inverter_vneg("max"))
    if corner != "worst":
        vo = rc.boost_vpos("nom") if rail == "pos" else abs(rc.inverter_vneg("nom"))
    op = rc.converter_point(rail, vin, fsw, l, iout, vo)
    ceff = 3 * 10e-6 * ASSUMPTIONS["A1_cap_retention_at_14V"][w] * (1 - rc.TOL_C) * (1 - rc.TEMP_C)
    esr = ASSUMPTIONS["A2_esr_per_10uF_ohm"][w] / 3
    lesl = ASSUMPTIONS["A3_output_loop_esl_h"][w]
    if op["mode"] == "DCM":
        t_d = l * op["ipk_a"] / (vo + 0.45)     # diode conduction time
        d_dis = 1 - t_d * fsw                    # fraction the cap alone feeds the load
    else:
        d_dis = op["duty"]
    vpp_c = iout * d_dis / (fsw * ceff)
    m = HARMONICS
    cap = tri_harm(vpp_c, d_dis, m)
    esr_h = rect_harm(op["ipk_a"] * esr, d_dis, m)
    esl_h = esl_harm(lesl, op["ipk_a"], fsw, d_dis, m, ASSUMPTIONS["A4_switch_edge_s"])
    total = cap + esr_h + esl_h          # magnitudes added: pessimistic
    return {"fsw": fsw, "op": op, "ceff": ceff, "vpp_cap": vpp_c, "harm_v": total,
            "parts": {"cap": cap, "esr": esr_h, "esl": esl_h}}


def input_ripple(corner):
    """5 V node ripple (V per harmonic) from boost + inverter input currents."""
    w = 0 if corner == "worst" else 1
    s = c.TPS65131
    fsw = s["fsw_min_hz"] if corner == "worst" else s["fsw_typ_hz"]
    vin = rc.VIN[0] if corner == "worst" else rc.VIN[1]
    l = rc.L_NOM * (1 - rc.L_TOL) if corner == "worst" else rc.L_NOM
    scale = ASSUMPTIONS["A6_load_scale"][w]
    n = 4096
    t = np.arange(n) / n
    # boost input = inductor current (forced CCM triangle)
    opp = rc.converter_point("pos", vin, fsw, l, rc.LOAD["pos"] * scale, rc.boost_vpos("max"))
    ib = np.where(t < opp["duty"], -opp["ripple_a"] / 2 + opp["ripple_a"] * t / opp["duty"],
                  opp["ripple_a"] / 2 - opp["ripple_a"] * (t - opp["duty"]) / (1 - opp["duty"]))
    # inverter input = switch current: ramps 0 -> ipk during t_on (DCM) or trapezoid (CCM)
    opn = rc.converter_point("neg", vin, fsw, l, rc.LOAD["neg"] * scale, abs(rc.inverter_vneg("max")))
    if opn["mode"] == "DCM":
        iin = np.where(t < opn["duty"], opn["ipk_a"] * t / opn["duty"], 0.0)
    else:
        lo = opn["ipk_a"] - opn["ripple_a"]
        iin = np.where(t < opn["duty"], lo + opn["ripple_a"] * t / opn["duty"], 0.0)
    spec_b = 2 * np.abs(np.fft.rfft(ib)) / n
    spec_n = 2 * np.abs(np.fft.rfft(iin)) / n
    m = HARMONICS
    i_h = spec_b[m] + spec_n[m]
    f = m * fsw
    ret = 0.75 if corner == "worst" else 0.9
    zc = 1 / (2j * np.pi * f * 10e-6 * ret * (1 - rc.TOL_C)) + 0.005 + 2j * np.pi * f * 1e-9
    z1 = 1 / (2j * np.pi * f * 1e-6) + 0.01 + 2j * np.pi * f * 1e-9
    z01 = 1 / (2j * np.pi * f * 100e-9) + 0.02 + 2j * np.pi * f * 0.7e-9
    ztot = 1 / (2 / zc + 1 / z1 + 1 / z01)
    return {"fsw": fsw, "i_harm_a": i_h, "v_harm": i_h * np.abs(ztot)}


def propagate(corner, mode="undersample", divider=1):
    w = 0 if corner == "worst" else 1
    m = HARMONICS
    out = {}
    rp, rn = output_ripple("pos", corner), output_ripple("neg", corner)
    fsw = rp["fsw"]
    f = m * fsw
    margin = ASSUMPTIONS["A5_ldo_psrr_margin_db"][w]
    p49 = c.interp_loglog_db(c.PSRR_TPS7A49, f) - margin
    p30 = c.interp_loglog_db(c.PSRR_TPS7A30, f) - margin
    # optional post-filter: series ferrite (credited only >= 1 ohm at >= 1 MHz)
    # into the existing 10 uF LDO input cap (C94/C99, 40 % retention, 1 nH ESL)
    zci = 1 / (2j * np.pi * f * 10e-6 * 0.40 * 0.9 * 0.85) + 0.004 + 2j * np.pi * f * 1e-9
    lc = np.abs(zci / (zci + 1.0))
    vp = rp["harm_v"] * 10 ** (-p49 / 20)
    vn = rn["harm_v"] * 10 ** (-p30 / 20)
    pop = c.interp_loglog_db(c.PSRR_OPA2810, f)
    e_amp = (vp + vn) * 10 ** (-pop / 20)          # input-referred, both rails add
    common = np.abs(c.fda_filter(f)) * c.boxcar_gain(f, divider if mode == "boxcar" else 1)
    adc_a = 2 * e_amp * common                     # HIGH and LOW followers
    adc_b = (1 + 2) * e_amp * common               # LOW follower + TIA (noise gain <= 2)
    src = (6 + 1) * e_amp                          # OPA810 gain 6 + source buffer (source-borne)
    # 5 V input path into FDAs and ADC (no ferrite credit)
    ir = input_ripple(corner)
    pths = c.interp_loglog_db(c.PSRR_THS4551_POS, f)
    adc_psrr = np.where(f < 1e5, c.ADS9224R_PSRR_DB, ASSUMPTIONS["A7_adc_avdd_psrr_above_100k_db"])
    v5_adc = ir["v_harm"] * (10 ** (-pths / 20) * np.abs(1 / (1 + 2j * np.pi * f * 8.64 * 3.465e-9))
                             + 10 ** (-adc_psrr / 20)) * c.boxcar_gain(f, divider if mode == "boxcar" else 1)
    z5a = 1 / (1 / (1 / (2j * np.pi * f * 22e-6 * 0.75 * 0.9) + 0.003 + 2j * np.pi * f * 1e-9)
               + 3 / (1 / (2j * np.pi * f * 1e-6) + 0.01 + 2j * np.pi * f * 0.8e-9)
               + 2 / (1 / (2j * np.pi * f * 100e-9) + 0.02 + 2j * np.pi * f * 0.7e-9))
    fb1 = np.abs(z5a / (z5a + 1.0))
    v5_adc_fb1 = v5_adc * fb1
    out.update({"fsw": fsw, "harmonic": m.tolist(),
                "raw_p_v": rp["harm_v"].tolist(), "raw_n_v": rn["harm_v"].tolist(),
                "raw_p_parts_first3": {k: v[:3].tolist() for k, v in rp["parts"].items()},
                "raw_p_vpp_cap": rp["vpp_cap"], "raw_n_vpp_cap": rn["vpp_cap"],
                "ldo_psrr_db": {"tps7a49": p49.tolist(), "tps7a30": p30.tolist()},
                "rail_p12_v": vp.tolist(), "rail_n12_v": vn.tolist(),
                "opamp_psrr_db": pop.tolist(), "adc_a_v": adc_a.tolist(), "adc_b_v": adc_b.tolist(),
                "source_ripple_v": src.tolist(), "v5_node_v": ir["v_harm"].tolist(),
                "ferrite_postfilter_divider": lc.tolist(),
                "adc_from_5v_v": v5_adc.tolist(), "adc_from_5v_fb1_credit_v": v5_adc_fb1.tolist(),
                "fb1_divider": fb1.tolist(),
                "converter_points": {"pos": rp["op"], "neg": rn["op"]}})
    errs = {}
    for name, sig in SIGNALS.items():
        paths = {"rails_12v": adc_a / sig["A"] + adc_b / sig["B"],
                 "rails_12v_with_ferrite_postfilter": lc * (adc_a / sig["A"] + adc_b / sig["B"]),
                 "5v_no_fb1": v5_adc * (1 / sig["A"] + 1 / sig["B"]),
                 "5v_fb1_credit": v5_adc_fb1 * (1 / sig["A"] + 1 / sig["B"])}
        paths["total_no_fb1"] = paths["rails_12v"] + paths["5v_no_fb1"]
        paths["total_fb1_credit"] = paths["rails_12v"] + paths["5v_fb1_credit"]
        errs[name] = {k: {"max": float(v.max()), "argmax_harmonic": int(m[np.argmax(v)]),
                          "rss_all": float(np.sqrt(np.sum(v ** 2))), "per_harmonic": v.tolist()}
                      for k, v in paths.items()}
    out["z_error_if_collision"] = errs
    return out


def source_borne(prop, hz):
    """Source-borne switcher ripple at m*fsw, cancelled ratiometrically except
    for the DUT transfer difference (same formula as dds_spurs)."""
    a = c.acquisition(hz)
    worst = {}
    for name, z in DUTS.items():
        e = 0.0
        for m, v in zip(prop["harmonic"], prop["source_ripple_v"]):
            fk = m * prop["fsw"]
            e = max(e, v / 1.398 * dut_coefficient(z, a["f_dds_hz"], fk) * abs(c.fda_filter(fk)))
        worst[name] = e
    return worst


def collision_probability(hz, threshold=0.1):
    """Probability that one switcher harmonic's alias, uniformly distributed
    over [0, fs/2] (fsw unknown within its band), gives fit response > threshold."""
    a = c.acquisition(hz)
    fit = c.Fit(a["f_dds_hz"], a["fs_hz"])
    off = np.linspace(-20, 20, 4001) * a["bin_hz"]
    r = fit.response(a["f_dds_hz"] + off)
    width = np.sum(r > threshold) * (off[1] - off[0])
    return width / (a["fs_hz"] / 2)


def usb_digital(hz_list=c.TEMPER_GRID):
    """A9: RP2040 current pulse delta_i for width tau every 1 ms on 5 V of
    impedance z -> 5VA -> FDA/ADC PSRR; and -> TPS65131 (0 dB line rejection
    assumed) -> LDO PSRR -> op-amp PSRR. Board-coherent or SOF-locked harmonic h
    lands on f = h kHz."""
    p = ASSUMPTIONS["A9_usb_digital_pulse"]
    rows = {}
    for hz in hz_list:
        h = hz / 1000.0
        x = h * p["width_s"] * 1000.0          # sinc envelope, not its nulls
        amp_i = 2 * p["delta_i_a"] * p["width_s"] * 1000.0 * min(1.0, 1 / (np.pi * x))
        v5 = amp_i * p["z_5v_ohm"]
        adc_direct = v5 * (10 ** (-c.ADS9224R_PSRR_DB / 20) + 10 ** (-c.interp_loglog_db(c.PSRR_THS4551_POS, hz) / 20))
        rail = v5 * 10 ** (-min(c.interp_loglog_db(c.PSRR_TPS7A49, hz), c.interp_loglog_db(c.PSRR_TPS7A30, hz)) / 20)
        e_amp = 2 * rail * 10 ** (-c.interp_loglog_db(c.PSRR_OPA2810, hz) / 20)
        adc_rails = 3 * e_amp
        sig = SIGNALS["15 ohm, 100 ohm range"]
        err = (adc_direct + adc_rails) * (1 / sig["A"] + 1 / sig["B"])
        rows[str(int(hz))] = {"harmonic_current_a": amp_i, "v5_ripple_v": v5,
                              "adc_v": adc_direct + adc_rails, "z_error": err}
    return rows


def main():
    out = {"assumptions": ASSUMPTIONS, "signals": SIGNALS, "corners": {}}
    for corner in ("worst", "typ"):
        out["corners"][corner] = {"undersample": propagate(corner),
                                  "boxcar_N2": propagate(corner, "boxcar", 2)}
    out["source_borne_worst_corner"] = {str(int(hz)): source_borne(out["corners"]["worst"]["undersample"], hz)
                                        for hz in c.TEMPER_GRID}
    out["source_borne_typ_corner"] = {str(int(hz)): source_borne(out["corners"]["typ"]["undersample"], hz)
                                      for hz in c.TEMPER_GRID}
    out["collision_probability_per_harmonic"] = {str(int(hz)): collision_probability(hz) for hz in c.TEMPER_GRID}
    out["usb_digital_supply_path"] = usb_digital()
    (HERE / "ripple_chain.json").write_text(json.dumps(out, indent=1, default=float))
    for corner in ("worst", "typ"):
        p = out["corners"][corner]["undersample"]
        print(f"== {corner}: fsw {p['fsw']/1e6:.2f} MHz; boost {p['converter_points']['pos']['mode']} D={p['converter_points']['pos']['duty']:.3f}; "
              f"inverter {p['converter_points']['neg']['mode']} D={p['converter_points']['neg']['duty']:.3f}")
        print(f"   RAW_P cap-ripple pp {p['raw_p_vpp_cap']*1e3:.2f} mV, RAW_N {p['raw_n_vpp_cap']*1e3:.2f} mV")
        for i in (0, 1, 2, 4, 9, 19, 39):
            print(f"   m={p['harmonic'][i]:>2} {p['harmonic'][i]*p['fsw']/1e6:6.2f} MHz raw+ {p['raw_p_v'][i]*1e3:7.3f} mV raw- {p['raw_n_v'][i]*1e3:7.3f} mV "
                  f"| +12 {p['rail_p12_v'][i]*1e6:8.2f} uV -12 {p['rail_n12_v'][i]*1e6:8.2f} uV | ADC A {p['adc_a_v'][i]*1e6:7.3f} uV "
                  f"B {p['adc_b_v'][i]*1e6:7.3f} uV 5V-path {p['adc_from_5v_v'][i]*1e6:7.4f} uV (5V node {p['v5_node_v'][i]*1e3:.3f} mV)")
        for name, e in p["z_error_if_collision"].items():
            print(f"   worst |dZ/Z| if one harmonic hits the main lobe [{name}]: " + "; ".join(
                f"{k} {100*v['max']:.4f}% (m={v['argmax_harmonic']})" for k, v in e.items()))
        b = out["corners"][corner]["boxcar_N2"]["z_error_if_collision"]["15 ohm, 100 ohm range"]
        print("   boxcar N=2 variant [15 ohm]: " + "; ".join(f"{k} {100*v['max']:.4f}%" for k, v in b.items()))
    print("source-borne switcher ripple (worst corner, |dZ/Z| if in main lobe):",
          {k: {n: f"{100*v:.2e}%" for n, v in d.items()} for k, d in out["source_borne_worst_corner"].items()})
    print("source-borne switcher ripple (typ corner):",
          {k: {n: f"{100*v:.2e}%" for n, v in d.items()} for k, d in out["source_borne_typ_corner"].items()})
    print("collision probability per harmonic:", {k: f"{v:.2e}" for k, v in out["collision_probability_per_harmonic"].items()})
    print("USB/digital via supply rails:", {k: f"{100*v['z_error']:.2e}% (5V {v['v5_ripple_v']*1e3:.3f} mV)" for k, v in out["usb_digital_supply_path"].items()})


if __name__ == "__main__":
    main()
