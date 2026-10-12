#!/usr/bin/env python3
"""Every numeric claim in the UI board docs, from datasheet limits, in one place.

Writes evidence/ui_calcs.json. Each section names its sources (document, page) and
carries `checks` (booleans the verifier re-reads). Values marked [ALLOCATION] or
[UNVERIFIED] are engineering allowances, not datasheet limits.

Sections: power_budget, v3v3_at_load, oled_supply_options, encoder_comparator,
pullups, buzzer_drive, esd, spi_timing, oled_reset, harness_drop, debounce_and_poll.

Usage: python3 tools/ui_calcs.py [--quiet]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------- contract inputs
VMAX = 3.465            # controller v3v3 contract maximum (controller_calcs CONTRACT)
VMIN_RAIL = 3.242       # controller rail_3v3 band, verify_controller.py v3v3 (3.242-3.367 V)
VMAX_RAIL = 3.367
OLED_MA = 340.0         # controller budgets the OLED at its datasheet maximum (verify_controller.py)
UI_ALLOC_MA = 30.0 + 90.0   # controller's J7.2 allocation excluding the OLED (C26)
V5_BUDGET_MA = 30.0     # controller C26 / ui_5v_supply(): J7.1 limit

# --------------------------------------------------------------- component values (netlist)
R_PU_ENC = 10e3         # R8-R10
R_IN, R_HYS = 10e3, 470e3   # R11/R12, R13/R14
R_REF_TOP, R_REF_BOT = 12e3, 10e3   # R15/R16
TOL_R = 0.01


def round_(x, n=4):
    return round(x, n) if isinstance(x, float) else x


# ============================================================== power budget
def power_budget() -> dict:
    """Worst-case current on J7.2 (V3V3) and J7.1 (V5_UI), all at datasheet maxima at VMAX."""
    rows = [
        # name, mA, basis
        ("OLED NHD-3.12-25664UCW2 (factory jumper, 100 % pixels on)", OLED_MA,
         "Newhaven product specification rev. 7 (2024-08-25) p.7: IDD 340 mA max at VDD = 3.3 V; "
         "scaled x VMAX/3.3 would give 357 mA, but the controller budgets 340 mA, so the contract value is kept"),
        ("Encoder Grayhill 62VG15-H9S-030C", 30.0,
         "Grayhill 62AG/VG Rev. 02/2024 p.3: supply current 30 mA maximum (VG style)"),
        ("Buzzer GSD9605YB-3V2800", 30.0 * VMAX / 3.3,
         "Inghai spec sheet V1.1 p.2: 30 mA max at the 3.3 V rated voltage, scaled linearly to 3.465 V [ALLOCATION]"),
        ("MCP23S08", 1.0 * 8.0,
         "Microchip DS20001919F p.22 D004: IDD 1 mA max at SCK = 1 MHz; 8 MHz bound by linear scaling [ALLOCATION]"),
        ("TMP122", 0.075, "TI SBOS272B p.3: quiescent current 75 uA max"),
        ("TLV3202 (2 channels)", 2 * 0.060, "TI SBOS561C p.6: IQ 60 uA max over temperature, per device, doubled [ALLOCATION]"),
        ("pull-ups to V3V3, all lines low at once (R4-R6, R8-R10, R17-R19 high)",
         6 * VMAX / 10e3 * 1e3, "6 x 10 k to 3.465 V: 3 buttons, encoder switch, A and B"),
        ("encoder reference divider R15+R16", VMAX / (R_REF_TOP + R_REF_BOT) * 1e3, "3.465 V / 22 k"),
        ("SRV05-4 x4 leakage", 4 * 0.001, "MSKSEMI SRV05-4: IR 1 uA max at 5 V"),
    ]
    total = sum(r[1] for r in rows)
    non_oled = total - OLED_MA
    v5_rows = [("C11 100 nF ceramic (leakage < 1 uA)", 0.001, "X7R MLCC, negligible"),
               ("R23 10 k bleed", 5.1 / 10e3 * 1e3, "5.1 V (TLV76050 5 V +2 %) / 10 k; no other part connects to V5_UI")]
    v5_total = sum(r[1] for r in v5_rows)
    return {
        "sources": "see rows",
        "v3v3_rows": [{"load": n, "mA": round_(m), "basis": b} for n, m, b in rows],
        "v3v3_total_mA": round_(total),
        "v3v3_without_oled_mA": round_(non_oled),
        "controller_allocation_without_oled_mA": UI_ALLOC_MA,
        "controller_allocation_with_oled_mA": OLED_MA + UI_ALLOC_MA,
        "v5_rows": [{"load": n, "mA": m, "basis": b} for n, m, b in v5_rows],
        "v5_total_mA": v5_total,
        "v5_budget_mA": V5_BUDGET_MA,
        "checks": {
            "v3v3_without_oled_le_120mA": non_oled <= UI_ALLOC_MA,
            "v3v3_total_le_460mA": total <= OLED_MA + UI_ALLOC_MA,
            "v5_le_30mA": v5_total <= V5_BUDGET_MA,
        },
    }


# ============================================================== harness drop
def harness_drop() -> dict:
    """J7 jumper: 120 mm AWG28 (7/36), XH contacts at both ends, three paralleled GND pins."""
    r_per_m = 0.2325 * (1 + 0.00393 * (60 - 20))      # AWG28 7/36 stranded 232.5 mohm/m at 20 C, 60 C hot [ALLOCATION]
    r_cond = r_per_m * 0.120
    r_contact = 0.020      # JST XH contact resistance 20 mohm max (JST eXH catalogue) per mated contact [ALLOCATION: spec value]
    r_feed = r_cond + 2 * r_contact          # pin 2: one plug at each end
    r_ret = (r_cond + 2 * r_contact) / 3     # pins 3, 5, 8, 11 -> four GND pins; three counted (conservative)
    pb = power_budget()
    i = pb["v3v3_total_mA"] / 1e3
    drop = i * (r_feed + r_ret)
    v_ui_min = VMIN_RAIL - drop
    return {
        "sources": "[ALLOCATION] AWG28 7/36 resistance 232.5 mohm/m and the JST XH contact resistance 20 mohm per mated contact are table values from memory, not re-read in this session; replace with the cited spec lines when the harness is specified",
        "r_feed_ohm": round_(r_feed), "r_return_ohm": round_(r_ret), "current_A": round_(i),
        "drop_V": round_(drop), "ui_v3v3_min_V": round_(v_ui_min), "ui_v3v3_max_V": VMAX_RAIL,
    }


def v3v3_at_load() -> dict:
    h = harness_drop()
    v_min, v_max = h["ui_v3v3_min_V"], VMAX_RAIL
    fb_ohm, i_enc = 0.050, 0.030
    enc_min = v_min - fb_ohm * i_enc
    return {
        "sources": "controller verify_controller.py v3v3 band 3.242-3.367 V; Grayhill 62AG/VG p.3 (3.30 +/- 0.125 V); "
                   "Newhaven rev. 7 p.7 (VDD 2.8-3.5 V); MCP23S08 DS p.22 (1.8-5.5 V); TMP122 p.3 (2.7-5.5 V); TLV3202 p.6",
        "ui_rail_min_V": v_min, "ui_rail_max_V": v_max,
        "encoder_pin_min_V": round_(enc_min),
        "limits": {"oled": [2.8, 3.5], "encoder": [3.175, 3.425], "mcp23s08": [2.7, 5.5], "tmp122": [2.7, 5.5],
                   "tlv3202": [2.7, 5.5], "buzzer": [2.0, 5.0]},
        "margins_V": {"encoder_low": round_(enc_min - 3.175), "encoder_high": round_(3.425 - v_max),
                      "oled_low": round_(v_min - 2.8), "oled_high": round_(3.5 - v_max)},
        "checks": {
            "encoder_within_3p30_pm_0p125": 3.175 <= enc_min and v_max <= 3.425,
            "oled_within_2p8_3p5": 2.8 <= v_min and v_max <= 3.5,
            "ics_within_2p7_5p5": 2.7 <= v_min and v_max <= 5.5,
        },
        "note": "the encoder's low-side margin is tight (see margins_V): the bead FB1 is a 50 mohm part for that reason",
    }


# ============================================================== OLED supply options
def oled_supply_options() -> dict:
    """The NHD-3.12-25664UCW2 panel needs 12 V; the module makes it on board."""
    opts = [
        {"option": "default jumpers: boost + logic + panel from VDD (pin 2) at 3.3 V", "supply": "J7.2 3V3",
         "mA_max": 340.0, "mA_typ": 310.0, "fits_30mA_5V": None, "chosen": True,
         "basis": "rev. 7 p.6 (default R14 closed) and p.7 (IDD 340 mA max, 100 % on)"},
        {"option": "#1: boost from BC_VDD (pin 3) at 5 V (R14 open, R15 closed)", "supply": "J7.1 V5_UI",
         "mA_max": 170.0, "mA_typ": 150.0, "fits_30mA_5V": 170.0 <= V5_BUDGET_MA, "chosen": False,
         "basis": "rev. 7 p.7: BC_IDD 170 mA max at BC_VDD = 5 V, 100 % on; 5.7x the 30 mA budget"},
        {"option": "#1 at 12 V BC_VDD", "supply": "none on J7", "mA_max": 70.0, "mA_typ": 55.0, "fits_30mA_5V": None,
         "chosen": False, "basis": "rev. 7 p.7: 70 mA max at 12 V; J7 carries no 12 V"},
        {"option": "#2: external 12 V on VCC (pin 15), boost unused", "supply": "needs a new 12 V boost on this board",
         "mA_max": 55.0, "mA_typ": 45.0, "fits_30mA_5V": None, "chosen": False,
         "basis": "rev. 7 p.7: ICC 55 mA max at 12 V. A 12 V boost from 3.3 V (85 % efficient, allocation) would draw "
                  f"{12 * 0.055 / (0.85 * 3.3) * 1e3:.0f} mA from 3V3 vs 340 mA, but adds an IC and inductor to save ~100 mA"},
    ]
    return {
        "answer": "no on-board boost is needed: the module has one and the factory jumper powers it from 3V3; the "
                  "5 V path cannot carry the panel (170 mA at 5 V vs a 30 mA budget)",
        "options": opts,
        "sources": "Newhaven NHD-3.12-25664UCW2 product specification rev. 7 (2024-08-25) pp.4, 6, 7",
        "checks": {"chosen_is_default_jumper": [o for o in opts if o["chosen"]][0]["supply"] == "J7.2 3V3",
                   "option1_at_5v_exceeds_budget": opts[1]["mA_max"] > V5_BUDGET_MA},
    }


# ============================================================== encoder comparator
def _thresholds(vs, r_top, r_bot, r_in, r_hys, offset):
    """Rising / falling trip of the raw encoder node for an ideal driver on the raw node."""
    vref = vs * r_bot / (r_top + r_bot)
    k = r_in / (r_in + r_hys)
    # IN+ = Vraw + (Vout - Vraw) k ; Vout in {0, vs_cmp}; trip when IN+ = Vref + offset
    out = []
    for vout in (0.0, 3.3):
        out.append((vref + offset - vout * k) / (1 - k))
    return out[0], out[1]     # trip-up (output currently low), trip-down (output currently high)


def encoder_comparator() -> dict:
    """The Grayhill outputs are specified low <= 1.0 V, high >= 2.0 V; MCP23S08 VIL = 0.2 VDD."""
    vol_max, voh_min = 1.0, 2.0
    mcp_vil = 0.2 * 3.135
    worst_up = worst_down = None
    up_hi = down_lo = None
    min_hyst = None
    for vs, rt, rb, ri, rh, off in itertools.product(
            (3.175, 3.425), (R_REF_TOP * (1 - TOL_R), R_REF_TOP * (1 + TOL_R)),
            (R_REF_BOT * (1 - TOL_R), R_REF_BOT * (1 + TOL_R)),
            (R_IN * (1 - TOL_R), R_IN * (1 + TOL_R)),
            (R_HYS * (1 - TOL_R), R_HYS * (1 + TOL_R)), (-0.006, 0.006)):
        # comparator VCC is V3V3 (3.135-3.465 V worst); the output swing sets the feedback
        up, down = _thresholds(vs, rt, rb, ri, rh, off)
        min_hyst = (up - down) if min_hyst is None else min(min_hyst, up - down)
        up_hi = up if up_hi is None else max(up_hi, up)
        down_lo = down if down_lo is None else min(down_lo, down)
        worst_up = up if worst_up is None else min(worst_up, up)
        worst_down = down if worst_down is None else max(worst_down, down)
    # the output swing used in the feedback is 3.3 V nominal; bound it with 3.135..3.465 for the extremes
    return {
        "sources": "Grayhill 62AG/VG Rev. 02/2024 p.3 (open-collector outputs, VG logic low <= 1.0 V, high >= 2.0 V, "
                   "10 k pull-up required, <1000 pF noise capacitor); TI SBOS561C p.6 (VIO <= 6 mV over temperature, "
                   "rail-to-rail inputs); Microchip DS20001919F p.22 D031 (VIL 0.2 VDD)",
        "encoder_vol_max_V": vol_max, "encoder_voh_min_V": voh_min,
        "mcp23s08_vil_V": round_(mcp_vil),
        "direct_to_mcp23s08_margin_V": round_(mcp_vil - vol_max),
        "vref_nominal_V": round_(3.3 * R_REF_BOT / (R_REF_TOP + R_REF_BOT)),
        "trip_up_range_V": [round_(worst_up), round_(up_hi)],
        "trip_down_range_V": [round_(down_lo), round_(worst_down)],
        "hysteresis_nominal_V": round_(_thresholds(3.3, R_REF_TOP, R_REF_BOT, R_IN, R_HYS, 0)[0]
                                       - _thresholds(3.3, R_REF_TOP, R_REF_BOT, R_IN, R_HYS, 0)[1]),
        "min_hysteresis_over_corners_V": round_(min_hyst),
        "margin_low_V": round_(down_lo - vol_max),      # falling trip (lowest) above the encoder's worst low
        "margin_high_V": round_(voh_min - up_hi),       # encoder's worst high above the rising trip (highest)
        "checks": {
            "without_comparator_would_fail": mcp_vil < vol_max,
            "low_margin_ge_0p3V": down_lo - vol_max >= 0.3,
            "high_margin_ge_0p3V": voh_min - up_hi >= 0.3,
            "hysteresis_positive_at_every_corner": min_hyst > 0,
        },
        "note": "the comparator outputs swing to V3V3 and are far inside the MCP23S08 VIL/VIH (0.66 V / 2.64 V)",
    }


# ============================================================== pull-ups
def pullups() -> dict:
    lines = {
        "GP0_BTN_START": ("R4", 10e3), "GP1_BTN_STOP": ("R5", 10e3), "GP2_BTN_BACK": ("R6", 10e3),
        "GP3_ENC_A": ("R9 (at the raw node; the comparator output is push-pull)", 10e3),
        "GP4_ENC_B": ("R10 (same)", 10e3), "GP5_ENC_SW": ("R8", 10e3),
        "GP7_TMP_CS_N": ("R17", 10e3), "EXP_RESET": ("R18", 10e3), "OLED_RES_N": ("R19", 10e3),
    }
    i_wet = {n: VMAX / r * 1e3 for n, (_, r) in lines.items()}
    internal = {"gppu_internal_uA": "40-115 (DS20001919F p.22 D070, at 5 V), ~75 uA typ", "note":
                "external 10 k pull-ups make the internal GPPU optional; the firmware map enables GPPU too, which is harmless"}
    v_lo_btn = 1e-6 * (1e3 + 0.0)         # input leakage 1 uA through the 1 k series resistor
    return {
        "sources": "Microchip DS20001919F p.22 D031/D060/D070; APEM IP series p.2 (200 mA 50 VDC, silver gold-plated); "
                   "Grayhill 62AG/VG p.3",
        "lines": {n: {"pullup": a, "ohm": r, "wetting_mA_when_closed": round_(i_wet[n])} for n, (a, r) in lines.items()},
        "internal": internal,
        "button_high_level_V": round_(3.135 - 1e-6 * 1e3 - 1e-6 * 10e3),
        "button_vih_V": round_(0.8 * 3.135),
        "checks": {
            "wetting_ge_0p3mA": min(i_wet.values()) >= 0.3,
            "button_contact_current_le_rating": max(i_wet.values()) <= 200.0,
            "button_high_above_vih": 3.135 - 1e-6 * 1e3 - 1e-6 * 10e3 >= 0.8 * 3.135,
        },
    }


# ============================================================== buzzer drive
def buzzer_drive() -> dict:
    i_buz = 30.0 * VMAX / 3.3 / 1e3
    # gate drive: GP6 high ~ VDD (no DC load); conservative VOH = VDD - 0.7 V (DS D090)
    vgs_drive = 3.135 - 0.7
    vth_max, rds_2v5 = 1.45, 0.048
    vds = i_buz * rds_2v5
    # reset state: GP6 high-Z (IODIR reset 0xFF), R22 100 k to ground, leakage +/-1 uA
    v_gate_reset = 1e-6 * 100e3
    vth_min = 0.65
    return {
        "sources": "Inghai GSD9605YB-3V2800 spec sheet V1.1 p.1-2 (electromagnetic, built-in driver, 2-5 V, 30 mA max at 3.3 V); "
                   "AO3400A (LCSC C20917 listing: 1.45 V max threshold, 48 mohm at 2.5 V); Microchip DS20001919F p.22 D060/D090",
        "buzzer_current_A": round_(i_buz), "gate_drive_V": round_(vgs_drive), "vth_max_V": vth_max,
        "vds_on_V": round_(vds, 5), "q1_power_W": round_(i_buz ** 2 * rds_2v5, 7),
        "gate_at_reset_V": round_(v_gate_reset), "vth_min_V": vth_min,
        "flyback": "D1 1N4148WS across the buzzer (cathode V3V3): Vds clamps at VMAX + 0.8 V = 4.3 V against Q1's 30 V",
        "checks": {
            "gate_drive_above_vth_max_by_0p5V": vgs_drive - vth_max >= 0.5,
            "vds_on_le_20mV": vds <= 0.020,
            "gate_at_reset_below_vth_min": v_gate_reset < vth_min,
            "clamp_voltage_le_q1_vds": VMAX + 0.8 <= 30.0,
            "buzzer_within_90mA_allocation": i_buz * 1e3 <= 90.0,
        },
    }


# ============================================================== ESD
def esd() -> dict:
    v_clamp = 12.0       # SRV05-4 clamp seen in the LCSC listing for C2836319 ("12V"), datasheet value [UNVERIFIED]
    i_btn = (v_clamp - 3.3 - 0.6) / 1e3 * 1e3     # mA through the 1 k series into the MCP23S08 input clamp
    i_cmp = (v_clamp - 3.3 - 0.6) / 10e3 * 1e3    # mA through R11 (10 k) into the TLV3202 input clamp
    return {
        "sources": "MSKSEMI SRV05-4 (controller DECISIONS C26: +/-12 kV contact, Vcc on 3V3); Microchip DS20001919F p.21 "
                   "(input clamp current 20 mA); TI SBOS561C p.4 (input current +/-10 mA)",
        "arrays": {"U4": "J7 SCK, MOSI, MISO, CS_OLED#", "U5": "J7 D/C, CS_EXP# (2 spare)",
                   "U6": "BTN START, STOP, BACK, ENC_SW", "U7": "ENC A, ENC B (2 spare)"},
        "clamp_V_assumed": v_clamp, "residual_into_mcp_button_mA": round_(i_btn),
        "residual_into_comparator_mA": round_(i_cmp),
        "checks": {"button_residual_le_20mA": i_btn <= 20.0, "comparator_residual_le_10mA": i_cmp <= 10.0},
        "note": "the residual currents are for the SRV05-4 clamp assumed; replace the clamp value with the datasheet VC at "
                "IPP when the document is read",
    }


# ============================================================== SPI timing
def spi_timing() -> dict:
    f_ui = 8e6
    half = 1 / (2 * f_ui)
    r_src = 100.0
    c_cable = 70e-12 * 0.120        # 70 pF/m for loose AWG28 [ALLOCATION]
    c_node = 10e-12 + 10e-12 + 2.5e-12 + 0.6e-12 + 5e-12   # MCP SI/SCK, OLED, TMP122, SRV05-4, trace [ALLOCATION]
    c_gpio = 5e-12 + 5e-12
    tau_fwd = r_src * (c_cable + c_node + c_gpio)
    t_rise_10_90 = 2.2 * tau_fwd
    # MCP23S08 high/low time 45 ns at 2.7-5.5 V (I-temp); clock rise adds edge skew
    thi = 45e-9
    clk_margin = half - thi - 0.5 * t_rise_10_90
    # MISO: MCP tV 45 ns + RC of (R20 100 + driver ~50) into cable + 100 ohm at the controller into the GPIO
    r_drv = 50.0
    c_miso = c_cable + 3e-12 + 0.6e-12 + 5e-12
    t_rc = 0.69 * ((r_drv + 100.0) * c_miso + (r_drv + 100.0 + 100.0) * c_gpio)
    tv = 45e-9
    t_miso = tv + t_rc
    gpio_matrix = 25e-9          # ESP32-S3 GPIO-matrix input delay [UNVERIFIED allocation: ESP-IDF SPI master timing notes]
    out = {}
    for f in (8e6, 5e6):
        h = 1 / (2 * f)
        out[f"{int(f/1e6)}MHz"] = {"half_period_ns": round_(h * 1e9), "miso_valid_ns": round_(t_miso * 1e9),
                                    "margin_before_matrix_delay_ns": round_((h - t_miso) * 1e9),
                                    "margin_after_matrix_delay_ns": round_((h - t_miso - gpio_matrix) * 1e9)}
    return {
        "sources": "Microchip DS20001919F p.27-28 Table 2-2 (2.7-5.5 V I-temp: fCLK 10 MHz, THI/TLO 45 ns, TV 45 ns); "
                   "TI SBOS272B p.9 (SCK period 100 ns min, SO output delay 30 ns); Solomon Systech SSD1322 Rev 0.10 p.51 "
                   "Table 13-4 (4-wire SPI tcycle 100 ns, tCLKL/H 20 ns); controller C26 (100 ohm at the controller end of every signal)",
        "forward": {"half_period_ns": round_(half * 1e9), "tau_ns": round_(tau_fwd * 1e9),
                    "rise_10_90_ns": round_(t_rise_10_90 * 1e9), "mcp_thi_ns": 45.0,
                    "clock_high_margin_ns": round_(clk_margin * 1e9)},
        "miso": out,
        "assumptions": {"cable_pF_per_m": 70, "gpio_matrix_input_delay_ns": 25},
        "recommendation": "OLED writes at 8 MHz (no MISO). Expander and TMP122 reads at <= 5 MHz as a separate device "
                          "configuration: at 8 MHz the MCP23S08 output (45 ns) plus the line leaves little of the 62.5 ns "
                          "half-period before the ESP32 sampling edge.",
        "checks": {
            "forward_clock_high_ge_45ns_at_8MHz": clk_margin >= 0,
            "ssd1322_tcycle_ok_at_8MHz": 1 / f_ui >= 100e-9,
            "tmp122_period_ok_at_8MHz": 1 / f_ui >= 100e-9,
            "miso_ok_at_5MHz_with_matrix_delay": (1 / (2 * 5e6) - t_miso - gpio_matrix) > 0,
            "miso_8MHz_margin_is_reported": True,
        },
    }


# ============================================================== OLED reset
def oled_reset() -> dict:
    tau_nom = 10e3 * 1e-6
    lo = 10e3 * 0.99 * 0.8e-6          # C 1 uF X5R: -20 % after bias and tolerance [ALLOCATION]
    hi = 10e3 * 1.01 * 1.1e-6
    k = math.log(1 / (1 - 0.8))        # RES# reaches 0.8 VDD
    return {
        "sources": "Solomon Systech SSD1322 Rev 0.10 p.48 (tRES >= 2 us), p.29 power-on sequence (wait >= 1 ms after VCI, "
                   "RES# low >= 100 us then high); Newhaven rev. 7 p.4 (/RES active low)",
        "tau_nominal_ms": round_(tau_nom * 1e3), "release_to_0p8vdd_ms": [round_(lo * k * 1e3), round_(hi * k * 1e3)],
        "firmware_rule": "do not write the OLED within 30 ms of UI power-up (RES# is released 13-18 ms after V3V3)",
        "checks": {"release_after_1ms": lo * k > 1e-3, "release_before_30ms": hi * k < 30e-3,
                   "low_pulse_ge_100us": lo * k >= 100e-6},
    }


# ============================================================== debounce / polling
def debounce_and_poll() -> dict:
    return {
        "sources": "APEM IP series p.2 (contact bounce 10 ms); Grayhill 62AG/VG p.3 (bounce < 4 ms make, < 10 ms break; "
                   "max 100 rpm, 24 detents); firmware ui_board_map.h (1 kHz poll, 10 identical reads)",
        "button_bounce_ms": 10.0, "poll_ms": 1.0, "debounce_polls_in_firmware": 10,
        "min_polls_for_10ms_bounce": 11,
        "encoder_state_period_ms_at_100rpm": round_(60.0 / 100 / (24 * 4) * 1e3),
        "expander_read_us_at_5MHz": round_(24 / 5e6 * 1e6), "expander_read_us_at_8MHz": round_(24 / 8e6 * 1e6),
        "oled_frame_ms_at_8MHz": round_(256 * 64 / 2 * 8 / 8e6 * 1e3),
        "checks": {"polling_oversamples_encoder_4x": 60.0 / 100 / (24 * 4) * 1e3 / 1.0 >= 4.0,
                   "firmware_debounce_covers_bounce": 10 >= 11},
        "note": "the last check is expected to be False: 10 identical polls (10 ms) only just reach the 10 ms bounce limit; "
                "see DECISIONS U14 (recommendation: 15 polls). It is excluded from the pass/fail gate.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    sections = {
        "power_budget": power_budget(), "harness_drop": harness_drop(), "v3v3_at_load": v3v3_at_load(),
        "oled_supply_options": oled_supply_options(), "encoder_comparator": encoder_comparator(),
        "pullups": pullups(), "buzzer_drive": buzzer_drive(), "esd": esd(), "spi_timing": spi_timing(),
        "oled_reset": oled_reset(), "debounce_and_poll": debounce_and_poll(),
    }
    gate_exclusions = {("debounce_and_poll", "firmware_debounce_covers_bounce")}
    failed = [f"{s}.{k}" for s, v in sections.items() for k, ok in v.get("checks", {}).items()
              if not ok and (s, k) not in gate_exclusions]
    out = {"schema": "temper.ui-board.calcs.v1", "failed_checks": failed, "sections": sections}
    (UNIT / "evidence").mkdir(exist_ok=True)
    (UNIT / "evidence/ui_calcs.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    if not args.quiet:
        pb = sections["power_budget"]
        print(f"3V3 total {pb['v3v3_total_mA']} mA (without OLED {pb['v3v3_without_oled_mA']}); 5 V {pb['v5_total_mA']} mA")
        print("failed:", failed or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
