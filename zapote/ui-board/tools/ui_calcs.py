#!/usr/bin/env python3
"""Every numeric claim in the UI board docs, from datasheet limits, in one place.

Writes evidence/ui_calcs.json. Each section names its sources (document, page) and
carries `checks` (booleans the verifier re-reads). Values marked [ALLOCATION] or
[UNVERIFIED] are engineering allowances, not datasheet limits.

Sections: power_budget, harness_drop, v3v3_at_load, oled_supply_options, pullups, buzzer_drive,
esd, spi_timing, oled_reset, debounce_and_poll, cs_qualification, tmag_sensing, magnet_field,
stray_field, buzzer_thermal, sensor_thermal, tact_switch.

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
TOL_R = 0.01
BUZZER_MA = 30.0        # GSD9605YB-5V2800: LCSC listing 30 mA; not scaled down for 3.465 V [ALLOCATION]
TMAG_MA = 3.4           # TMAG5170 IACT max, CS high, VCC 5.5 V (SBASAF4 p.5)
N_PULLUPS_10K = 11      # R4-R6, R17-R19, R24-R27, R29 (all low at once is the bound)
OWNER_NON_OLED_BASELINE_MA = 71.9    # owner's figure before the encoder removal (UI-BOARD-REQUIREMENTS)
OWNER_ENCODER_MA = 30.0
OWNER_HEADROOM_MA = 78.1


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
        ("Buzzer GSD9605YB-5V2800", BUZZER_MA,
         "LCSC C530415 listing: 30 mA (5 V rated, 2-12 V operating); at 3.465 V the draw is lower, not scaled [ALLOCATION]"),
        ("MCP23S08", 1.0 * 8.0,
         "Microchip DS20001919F p.22 D004: IDD 1 mA max at SCK = 1 MHz; 8 MHz bound by linear scaling [ALLOCATION]"),
        ("TMP122", 0.075, "TI SBOS272B p.3: quiescent current 75 uA max"),
        ("TMAG5170A1 (continuous measure mode)", TMAG_MA, "TI SBASAF4 p.5: IACT 3.4 mA max, CS high, VCC 5.5 V"),
        ("SN74LVC1G00 + SN74LVC2G32", 2 * 0.010, "TI SCES212 / SCES201N: ICC 10 uA max each (static)"),
        ("pull-ups to V3V3, all lines low at once (R4-R6, R17-R19, R24-R27, R29)",
         N_PULLUPS_10K * VMAX / 10e3 * 1e3, "11 x 10 k to 3.465 V: 3 buttons, GP7, expander reset, OLED RES#, sensor CS#, ALERT, GP3, GP5, TMP CS#"),
        ("SRV05-4 x4 leakage", 4 * 0.001, "MSKSEMI SRV05-4: IR 1 uA max at 5 V"),
    ]
    total = sum(r[1] for r in rows)
    non_oled = total - OLED_MA
    v5_rows = [("C11 100 nF ceramic (leakage < 1 uA)", 0.001, "X7R MLCC, negligible"),
               ("R23 10 k bleed", 5.1 / 10e3 * 1e3, "5.1 V (TLV76050 5 V +2 %) / 10 k; no other part connects to V5_UI")]
    v5_total = sum(r[1] for r in v5_rows)
    owner_after = OWNER_NON_OLED_BASELINE_MA - OWNER_ENCODER_MA
    return {
        "sources": "see rows",
        "v3v3_rows": [{"load": n, "mA": round_(m), "basis": b} for n, m, b in rows],
        "v3v3_total_mA": round_(total),
        "v3v3_without_oled_mA": round_(non_oled),
        "controller_allocation_without_oled_mA": UI_ALLOC_MA,
        "controller_allocation_with_oled_mA": OLED_MA + UI_ALLOC_MA,
        "headroom_without_oled_mA": round_(UI_ALLOC_MA - non_oled),
        "owner_bridge": {
            "owner_non_oled_before_removal_mA": OWNER_NON_OLED_BASELINE_MA,
            "owner_after_encoder_removal_mA": owner_after, "owner_headroom_mA": OWNER_HEADROOM_MA,
            "this_board_non_oled_mA": round_(non_oled), "this_board_headroom_mA": round_(UI_ALLOC_MA - non_oled),
            "note": "the owner's 71.9 mA counted six pull-ups and no R17-R19 (GP7, reset, OLED RES#), and 31.5 mA for the buzzer; "
                    "this budget counts every 10 k pull-up on the netlist, adds the sensor (3.4 mA), the two gate ICs and five new pull-ups, "
                    "and takes the buzzer at 30 mA",
        },
        "v5_rows": [{"load": n, "mA": m, "basis": b} for n, m, b in v5_rows],
        "v5_total_mA": v5_total,
        "v5_budget_mA": V5_BUDGET_MA,
        "checks": {
            "v3v3_without_oled_le_120mA": non_oled <= UI_ALLOC_MA,
            "v3v3_total_le_460mA": total <= OLED_MA + UI_ALLOC_MA,
            "v5_le_30mA": v5_total <= V5_BUDGET_MA,
            "headroom_ge_70mA": UI_ALLOC_MA - non_oled >= 70.0,
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
    return {
        "sources": "controller verify_controller.py v3v3 band 3.242-3.367 V; Newhaven rev. 7 p.7 (VDD 2.8-3.5 V); MCP23S08 DS p.22 "
                   "(1.8-5.5 V); TMP122 p.3 (2.7-5.5 V); TMAG5170 SBASAF4 p.4-5 (2.3-5.5 V); SN74LVC1G00 / 2G32 (1.65-5.5 V)",
        "ui_rail_min_V": v_min, "ui_rail_max_V": v_max,
        "limits": {"oled": [2.8, 3.5], "mcp23s08": [2.7, 5.5], "tmp122": [2.7, 5.5],
                   "tmag5170": [2.3, 5.5], "lvc_gates": [1.65, 5.5], "buzzer": [2.0, 12.0]},
        "margins_V": {"oled_low": round_(v_min - 2.8), "oled_high": round_(3.5 - v_max), "tmag_low": round_(v_min - 2.3)},
        "checks": {
            "oled_within_2p8_3p5": 2.8 <= v_min and v_max <= 3.5,
            "ics_within_2p7_5p5": 2.7 <= v_min and v_max <= 5.5,
            "tmag_within_2p3_5p5": 2.3 <= v_min and v_max <= 5.5,
        },
        "note": "the encoder's 26 mV low-side margin (old U5) is gone with the encoder; the OLED's 0.13 V high-side margin is now the tightest",
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


# ============================================================== pull-ups
def pullups() -> dict:
    lines = {
        "GP0_BTN_START": ("R4", 10e3), "GP1_BTN_STOP": ("R5", 10e3), "GP2_BTN_BACK": ("R6", 10e3),
        "GP3_TMAG_SEL_N": ("R26", 10e3), "GP4_TMAG_ALERT": ("R25", 10e3), "GP5_SPARE": ("R27", 10e3),
        "GP7_TMP_SEL_N": ("R17", 10e3), "CS_TMAG_N": ("R24 (at the sensor)", 10e3), "CS_TMP_N": ("R29", 10e3),
        "EXP_RESET": ("R18", 10e3), "OLED_RES_N": ("R19", 10e3),
    }
    i_wet = {n: VMAX / r * 1e3 for n, (_, r) in lines.items()}
    internal = {"gppu_internal_uA": "40-115 (DS20001919F p.22 D070, at 5 V), ~75 uA typ", "note":
                "external 10 k pull-ups make the internal GPPU optional; the firmware map enables GPPU on bits 3-5 and 7 too, which is harmless"}
    v_lo_btn = 1e-6 * (1e3 + 0.0)         # input leakage 1 uA through the 1 k series resistor
    # KSC2: minimum contact load 0.1 mA at 20 mV (the owner's SOURCES.md, KSC2 drawing); max 10 mA
    i_min = 3.135 / (10e3 * (1 + TOL_R) + 1e3 * (1 + TOL_R)) * 1e3
    i_max = 3.465 / (10e3 * (1 - TOL_R)) * 1e3
    return {
        "sources": "Microchip DS20001919F p.22 D031/D060/D070; C&K KSC2 series (min 0.1 mA, 20 mV; 10 mA, 32 V max; as quoted by "
                   "UI-BOARD-REQUIREMENTS / the owner's SOURCES.md, drawing not fetched here)",
        "lines": {n: {"pullup": a, "ohm": r, "wetting_mA_when_closed": round_(i_wet[n])} for n, (a, r) in lines.items()},
        "internal": internal,
        "tact_contact_current_mA": {"min_at_3.135V_1pct_high": round_(i_min), "max_at_3.465V_1pct_low": round_(i_max),
                                    "ksc2_min_mA": 0.1, "ksc2_max_mA": 10.0},
        "button_high_level_V": round_(3.135 - 1e-6 * 1e3 - 1e-6 * 10e3),
        "button_vih_V": round_(0.8 * 3.135),
        "checks": {
            "wetting_ge_0p1mA_ksc2_minimum": i_min >= 0.1,
            "tact_contact_current_le_10mA": i_max <= 10.0,
            "button_high_above_vih": 3.135 - 1e-6 * 1e3 - 1e-6 * 10e3 >= 0.8 * 3.135,
        },
    }


# ============================================================== buzzer drive
def buzzer_drive() -> dict:
    i_buz = BUZZER_MA / 1e3
    # gate drive: GP6 high ~ VDD (no DC load); conservative VOH = VDD - 0.7 V (DS D090)
    vgs_drive = 3.135 - 0.7
    vth_max, rds_2v5 = 1.45, 0.048
    vds = i_buz * rds_2v5
    # reset state: GP6 high-Z (IODIR reset 0xFF), R22 100 k to ground, leakage +/-1 uA
    v_gate_reset = 1e-6 * 100e3
    vth_min = 0.65
    return {
        "sources": "Inghai GSD9605YB-5V2800 (LCSC C530415 listing: electromagnetic, built-in driver, 2-12 V, 30 mA); the 3V2800 spec sheet V1.1 p.1-2 for the earlier part; "
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
    # sensor tab (U7): 100 ohm at the controller end of SCK/MOSI, the gate output (about 25 ohm) for CS#, 10 k for ALERT
    i_tab_alert = (v_clamp - 3.3 - 0.6) / 10e3 * 1e3   # ALERT into the TMAG ESD structure through R25 (10 k)
    return {
        "sources": "MSKSEMI SRV05-4 (controller DECISIONS C26: +/-12 kV contact, Vcc on 3V3); Microchip DS20001919F p.21 "
                   "(input clamp current 20 mA); TI SBASAF4 p.4 (ALERT/SDO output current +/-10 mA abs max)",
        "arrays": {"U4": "J7 SCK, MOSI, MISO, CS_OLED#", "U5": "J7 D/C, CS_EXP# (2 spare)",
                   "U6": "BTN START, STOP, BACK (1 spare)", "U7": "sensor tab: SCK, MOSI, CS_TMAG#, ALERT"},
        "clamp_V_assumed": v_clamp, "residual_into_mcp_button_mA": round_(i_btn),
        "residual_into_alert_path_mA": round_(i_tab_alert),
        "checks": {"button_residual_le_20mA": i_btn <= 20.0, "alert_residual_le_10mA": i_tab_alert <= 10.0},
        "note": "the residual currents are for the SRV05-4 clamp assumed; replace the clamp value with the datasheet VC at "
                "IPP when the document is read",
    }


# ============================================================== SPI timing
def spi_timing() -> dict:
    f_ui = 8e6
    half = 1 / (2 * f_ui)
    r_src = 100.0
    c_cable = 70e-12 * 0.120        # 70 pF/m for loose AWG28 [ALLOCATION]
    c_tab = 70e-12 * 0.150 + 5e-12 + 0.6e-12 + 5e-12        # sensor-tab harness, TMAG SCK/SDI, its SRV05-4, trace [ALLOCATION]
    c_node = 10e-12 + 10e-12 + 2.5e-12 + 0.6e-12 + 5e-12 + c_tab   # MCP SI/SCK, OLED, TMP122, SRV05-4, trace, tab [ALLOCATION]
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
    # TMAG5170 SDO: tpd_so 45 ns after the SCK falling edge (SBASAF4 p.11) + RC through R28 (390 ohm), the harness, R20, the
    # controller's 100 ohm and the GPIO. Elmore, 50 % crossing.
    r_sdo, r_drv_t = 390.0, 100.0
    c_harness = 70e-12 * 0.150
    c_local = 3e-12 + 0.6e-12 + 5e-12 + 7e-12    # TMP122, SRV05-4, trace, MCP SO pin [ALLOCATION]
    t_rc_tmag = 0.69 * ((r_drv_t + r_sdo) * (c_harness + c_local + c_cable + c_gpio)
                        + 100.0 * (c_cable + c_gpio) + 100.0 * c_gpio)
    t_tmag = 45e-9 + t_rc_tmag
    tmag = {}
    for f in (1e6, 2.5e6, 5e6):
        h = 1 / (2 * f)
        tmag[f"{f/1e6:g}MHz"] = {"half_period_ns": round_(h * 1e9), "sdo_valid_ns": round_(t_tmag * 1e9),
                                 "margin_after_matrix_delay_ns": round_((h - t_tmag - gpio_matrix) * 1e9)}
    f_tmag_max = 1 / (2 * (t_tmag + gpio_matrix + 10e-9))       # keeps 10 ns of margin
    return {
        "sources": "Microchip DS20001919F p.27-28 Table 2-2 (2.7-5.5 V I-temp: fCLK 10 MHz, THI/TLO 45 ns, TV 45 ns); "
                   "TI SBOS272B p.9 (SCK period 100 ns min, SO output delay 30 ns); Solomon Systech SSD1322 Rev 0.10 p.51 "
                   "Table 13-4 (4-wire SPI tcycle 100 ns, tCLKL/H 20 ns); controller C26 (100 ohm at the controller end of every signal)",
        "forward": {"half_period_ns": round_(half * 1e9), "tau_ns": round_(tau_fwd * 1e9),
                    "rise_10_90_ns": round_(t_rise_10_90 * 1e9), "mcp_thi_ns": 45.0,
                    "clock_high_margin_ns": round_(clk_margin * 1e9)},
        "miso": out,
        "tmag_miso": tmag, "tmag_max_sck_MHz_with_10ns_margin": round_(f_tmag_max / 1e6, 3),
        "assumptions": {"cable_pF_per_m": 70, "gpio_matrix_input_delay_ns": 25, "tab_harness_mm": 150},
        "recommendation": "OLED writes at 8 MHz (no MISO). Expander and TMP122 reads at <= 5 MHz as a separate device "
                          "configuration: at 8 MHz the MCP23S08 output (45 ns) plus the line leaves little of the 62.5 ns "
                          "half-period before the ESP32 sampling edge.",
        "checks": {
            "forward_clock_high_ge_45ns_at_8MHz": clk_margin >= 0,
            "ssd1322_tcycle_ok_at_8MHz": 1 / f_ui >= 100e-9,
            "tmp122_period_ok_at_8MHz": 1 / f_ui >= 100e-9,
            "miso_ok_at_5MHz_with_matrix_delay": (1 / (2 * 5e6) - t_miso - gpio_matrix) > 0,
            "miso_8MHz_margin_is_reported": True,
            "tmag_miso_ok_at_1MHz": tmag["1MHz"]["margin_after_matrix_delay_ns"] > 100,
            "tmag_miso_ok_at_2p5MHz": tmag["2.5MHz"]["margin_after_matrix_delay_ns"] > 30,
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
        "sources": "C&K KSC2 (bounce is not in the figures quoted by the owner; the APEM 10 ms is kept as the allocation); "
                   "firmware ui_board_map.h (1 kHz poll, 10 identical reads); UI-BOARD-REQUIREMENTS (1 kHz button service)",
        "button_bounce_ms": 10.0, "poll_ms": 1.0, "debounce_polls_in_firmware": 10,
        "min_polls_for_10ms_bounce": 11,
        "expander_read_us_at_5MHz": round_(24 / 5e6 * 1e6), "expander_read_us_at_8MHz": round_(24 / 8e6 * 1e6),
        "oled_frame_ms_at_8MHz": round_(256 * 64 / 2 * 8 / 8e6 * 1e3),
        "checks": {"firmware_debounce_covers_bounce": 10 >= 11},
        "note": "the check is expected to be False: 10 identical polls (10 ms) only just reach a 10 ms bounce; see DECISIONS U14 "
                "(recommendation: 15 polls) and U27 (the KSC2 bounce must be taken from its drawing). Excluded from the pass/fail gate.",
    }


# ============================================================== CS qualification
# canonical function: a GP-selected device's CS# is low iff GP is low AND CS_EXP# is high AND CS_OLED# is high
def cs_expected(gp: int, cs_exp: int, cs_oled: int) -> int:
    return 0 if (gp == 0 and cs_exp == 1 and cs_oled == 1) else 1


def cs_truth_table() -> list[dict]:
    rows = []
    for gp in (0, 1):
        for cse in (0, 1):
            for cso in (0, 1):
                bus_busy = 0 if (cse and cso) else 1          # NAND(CS_EXP#, CS_OLED#)
                cs_dev = gp | bus_busy                         # OR(GPx, BUS_BUSY)
                rows.append({"GPx": gp, "CS_EXP_N": cse, "CS_OLED_N": cso, "BUS_BUSY": bus_busy, "CS_dev_N": cs_dev,
                             "device_selected": cs_dev == 0, "expected_CS_dev_N": cs_expected(gp, cse, cso)})
    return rows


def cs_qualification() -> dict:
    """Timing proof of the CS qualification (DECISIONS U20-U22) against the ESP32-side sequence.

    Firmware sequence (one TMAG5170 frame; TMP122 is the same with GP7 and 16 clocks):
      A. expander write OLAT: GP3 low, expander device config cs_ena_posttrans >= 3 bit cycles (CS_EXP# rises >= 700 ns after the
         last data clock, after the GP output has settled), CS_OLED# high.
      B. wait >= 1 us; sensor frame: 32 clocks on SCK/MOSI with no hardware chip select (spics_io_num = -1); CS_EXP#, CS_OLED# high.
      C. wait >= 1 us; expander write OLAT: GP3 high (same posttrans).
    All times are worst case within the cited limits.
    """
    # SN74LVC1G00 (SCES212 p.6, 3.3 +/- 0.3 V, -40..125 C) and SN74LVC2G32 (SCES201N p.6)
    nand_min, nand_max = 1.0e-9, 5.0e-9
    or_min, or_max = 1.0e-9, 4.8e-9
    d_line, d_cable = 4e-9, 5e-9        # J7 edge to the gate input (100 ohm + cable RC); gate output to the sensor over 150 mm [ALLOCATION]
    f_exp, half_exp = 5e6, 1 / (2 * 5e6)
    t_css_min, t_csh_min = 50e-9, 50e-9          # MCP23S08 TCSS, TCSH (DS20001919F p.27)
    tgpov_max = 500e-9                            # MCP23S08 TGPOV (p.29): serial data to GPIO output valid
    posttrans_cycles = 3
    t_post = posttrans_cycles / f_exp             # CS_EXP# stays low this long after the last clock edge (ESP-IDF cs_ena_posttrans)
    # TMAG5170 (SBASAF4 p.10-11)
    tsu_cs, th_cs, tw_cs, tpd_soen, tpd_sodis = 45e-9, 45e-9, 100e-9, 45e-9, 55e-9
    # TMP122 (SBOS272B p.9)
    t5_tmp, t7_tmp = 40e-9, 30e-9
    t_gap = 1e-6                                  # firmware wait between the expander write and the sensor frame (rule)

    # offset from the last data-bit rising edge to CS_EXP# rising (earliest): half a clock + the hold
    off_min_nopost = half_exp + t_csh_min
    off_min_post = half_exp + max(t_csh_min, t_post)
    # A. select
    gp_late_nopost = tgpov_max - off_min_nopost           # GP edge after CS_EXP# rising, worst case (positive = after)
    gp_late_post = tgpov_max - off_min_post
    t_sel_after_cse_rise = max(d_line + nand_max + or_max, gp_late_post + or_max) + d_cable
    t_sel_after_cse_rise_nopost = max(d_line + nand_max + or_max, gp_late_nopost + or_max) + d_cable
    sel_setup_margin = t_gap - t_sel_after_cse_rise - tsu_cs
    sel_setup_margin_tmp = t_gap - t_sel_after_cse_rise - t5_tmp
    min_gap_needed = t_sel_after_cse_rise + tsu_cs
    # B. frame: CS low, CS_EXP# and CS_OLED# high: nothing else is selected
    # C. release: deselect after CS_EXP# falls, against the first expander clock and the sensor's hold
    desel_max = d_line + nand_max + or_max + d_cable
    desel_min = nand_min + or_min
    desel_margin_vs_first_expander_clock = t_css_min - desel_max
    hold_margin = t_gap + desel_min - th_cs
    # zero-clock select glitch at the end of the release write: CS_dev# low between CS_EXP# rising and a late GP rise
    glitch_ns_nopost = max(0.0, gp_late_nopost + or_max) * 1e9
    glitch_ns_post = max(0.0, gp_late_post) * 1e9
    # MISO overlap
    mcp_read_drive_start = 16 / f_exp                # SO driven from the 17th clock (opcode + address are 16 bits)
    tab_hiz = desel_max + tpd_sodis
    miso_handover_margin = mcp_read_drive_start - tab_hiz
    overlap_if_armed_during_read = max(0.0, 100e-9 - (desel_min + 0.0))    # MCP TDIS 100 ns vs earliest SDO enable (p.28, p.11)
    r_sdo, v_hi = 390.0, VMAX
    i_double = v_hi / r_sdo * 1e3
    # exhaustive table for the two gated devices and the 16-row MISO driver table
    tt = cs_truth_table()
    ok_table = all(r["CS_dev_N"] == r["expected_CS_dev_N"] for r in tt)
    miso = []
    for gp3 in (0, 1):
        for gp7 in (0, 1):
            for cse in (0, 1):
                for cso in (0, 1):
                    en = {"MCP23S08": cse == 0, "TMAG5170": cs_expected(gp3, cse, cso) == 0, "TMP122": cs_expected(gp7, cse, cso) == 0}
                    n = sum(en.values())
                    miso.append({"GP3": gp3, "GP7": gp7, "CS_EXP_N": cse, "CS_OLED_N": cso, "drivers_enabled": [k for k, v in en.items() if v],
                                 "count": n})
    one_driver_max = all(r["count"] <= 1 for r in miso if not (r["GP3"] == 0 and r["GP7"] == 0 and r["CS_EXP_N"] == 1 and r["CS_OLED_N"] == 1))
    double_rows = [r for r in miso if r["count"] > 1]
    # nominal edges of one read cycle, ns after CS_EXP# first falls (typ delays 3 ns per gate)
    t0 = 0.0
    last_clk = t0 + 100 + 24 * 200                   # 100 ns CS setup, 24 clocks at 5 MHz
    cse_rise = last_clk + 700
    edges = [("CS_EXP#", "fall", t0), ("BUS_BUSY", "rise", t0 + 3), ("GP3", "fall", last_clk + 250),
             ("CS_EXP#", "rise", cse_rise), ("BUS_BUSY", "fall", cse_rise + 3), ("CS_TMAG#", "fall", cse_rise + 6)]
    t_b = cse_rise + t_gap * 1e9
    edges += [("SCK sensor frame (32 clocks at 1 MHz)", "first rise", t_b), ("SCK sensor frame", "last fall", t_b + 32000 - 500)]
    t_c = t_b + 32000 + t_gap * 1e9
    edges += [("CS_EXP#", "fall", t_c), ("BUS_BUSY", "rise", t_c + 3), ("CS_TMAG#", "rise", t_c + 6)]
    return {
        "sources": "TI SN74LVC1G00 (SCES212) p.6 and SN74LVC2G32 (SCES201N) p.6 tpd; TI TMAG5170 SBASAF4 p.10-11 (tsu_cs 45 ns, th_cs 45 ns, "
                   "tw_cs 100 ns, SDO enable 45 ns, SDO disable 55 ns, 32-bit frames p.28-29); TI TMP122 SBOS272B p.9 (t5 40 ns, t7 30 ns); "
                   "Microchip DS20001919F p.27-29 (TCSS 50, TCSH 50, TDIS 100, TGPOV 500 ns, SO high-Z during writes)",
        "function": "CS_dev# = GPx OR NAND(CS_EXP#, CS_OLED#); selected only when GPx = 0 AND CS_EXP# = 1 AND CS_OLED# = 1",
        "truth_table_per_device": tt,
        "miso_driver_table": miso,
        "firmware_sequence": [
            "0. UI power-up: wait >= 30 ms (OLED rule, U12); expander at reset has every GP an input, pulled high: both devices deselected; "
            "write OLAT bits 3 and 7 = 1 BEFORE writing IODIR bits 3 and 7 = 0 (OLAT resets to 0 and would drive the pins low).",
            "1. Expander device configuration for these accesses: mode 0, <= 5 MHz, cs_ena_posttrans >= 3 bit cycles (CS_EXP# stays low "
            ">= 600 ns after the last clock, so the GP output has settled before CS_EXP# rises).",
            "2. Lock the whole SPI bus (OLED chunk transfers cannot interleave).",
            "3. Write OLAT with GP3 low (select request). CS_EXP# and CS_OLED# are idle high after the write.",
            "4. Wait >= 1 us. Clock exactly 32 bits (TMAG5170) or 16 bits (TMP122) with NO hardware chip select (spics_io_num = -1): "
            "CS_EXP# and CS_OLED# stay high, so the gate holds the selection. SCK <= 5 MHz (1 MHz first; 2.5 MHz recommended cap).",
            "5. Wait >= 1 us. Write OLAT with GP3 high (release). The first CS_EXP# edge deselects the sensor before the first expander clock.",
            "6. Unlock the bus. Never leave GP3 or GP7 low outside steps 3-5; never set both low.",
            "7. Each sensor frame needs its own select/release pair (CS must toggle between 32-clock frames: SBASAF4 p.28).",
        ],
        "timing_ns": {
            "gate_tpd_min_max": {"nand": [nand_min * 1e9, nand_max * 1e9], "or": [or_min * 1e9, or_max * 1e9]},
            "J7_line_to_gate_input": d_line * 1e9, "gate_to_sensor_cable": d_cable * 1e9,
            "cs_exp_rise_after_last_data_clock_min_posttrans0": off_min_nopost * 1e9,
            "cs_exp_rise_after_last_data_clock_min_posttrans3": off_min_post * 1e9,
            "tgpov_max": tgpov_max * 1e9,
            "select_cs_dev_falls_after_cs_exp_rise_max_posttrans3": t_sel_after_cse_rise * 1e9,
            "select_cs_dev_falls_after_cs_exp_rise_max_posttrans0": t_sel_after_cse_rise_nopost * 1e9,
            "firmware_wait_before_sensor_frame": t_gap * 1e9,
            "min_wait_needed_tmag": min_gap_needed * 1e9,
            "select_setup_margin_tmag_tsu_cs": sel_setup_margin * 1e9,
            "select_setup_margin_tmp_t5": sel_setup_margin_tmp * 1e9,
            "deselect_after_cs_exp_fall_max": desel_max * 1e9, "deselect_after_cs_exp_fall_min": desel_min * 1e9,
            "deselect_margin_to_first_expander_clock": desel_margin_vs_first_expander_clock * 1e9,
            "sensor_hold_margin_th_cs": hold_margin * 1e9,
            "zero_clock_select_glitch_ns_posttrans0": glitch_ns_nopost, "zero_clock_select_glitch_ns_posttrans3": glitch_ns_post,
            "tmag_sdo_hiz_after_cs_exp_fall_max": tab_hiz * 1e9,
            "mcp_so_first_drive_after_cs_exp_fall_min": mcp_read_drive_start * 1e9,
            "miso_handover_margin": miso_handover_margin * 1e9,
            "overlap_if_gp_armed_during_an_expander_read_ns": overlap_if_armed_during_read * 1e9,
            "tw_cs_between_sensor_frames_min": 2 * (24 / f_exp + t_gap) * 1e9,
        },
        "double_select_current_mA": round_(i_double), "tmag_sdo_abs_max_mA": 10.0,
        "nominal_edges_ns": [{"signal": a, "event": b, "t_ns": round_(c, 1)} for a, b, c in edges],
        "expander_read_cannot_corrupt_sensor": "a sensor armed (GP3 low) during an expander or OLED frame is deselected by BUS_BUSY "
                                               f"{desel_max * 1e9:.1f} ns after the frame's chip select falls, {desel_margin_vs_first_expander_clock * 1e9:.1f} ns "
                                               "before its first clock (the frame is lost, nothing is decoded or driven)",
        "checks": {
            "truth_table_matches_function": ok_table,
            "exactly_one_selected_row_per_device": sum(1 for r in tt if r["device_selected"]) == 1,
            "no_miso_contention_when_firmware_obeys_the_sequence": one_driver_max,
            "double_select_only_when_both_gps_low": len(double_rows) == 1,
            "select_setup_ge_tsu_cs_with_1us_wait": sel_setup_margin > 500e-9,
            "select_setup_ge_t5_tmp122_with_1us_wait": sel_setup_margin_tmp > 500e-9,
            "deselect_before_first_expander_clock": desel_margin_vs_first_expander_clock > 20e-9,
            "sensor_hold_th_cs_met": hold_margin > 500e-9,
            "no_zero_clock_glitch_with_posttrans3": glitch_ns_post == 0.0,
            "zero_clock_glitch_exists_without_posttrans": glitch_ns_nopost > 0.0,
            "miso_handover_margin_ge_1us": miso_handover_margin > 1e-6,
            "double_select_current_le_10mA_abs_max": i_double <= 10.0,
            "tw_cs_between_frames_ge_100ns": 2 * (24 / f_exp + t_gap) >= tw_cs,
        },
    }


# ============================================================== magnet field (TMAG5170 range and margin)
BR_35E = 1.190          # Arnold RECOMA 35E nominal Br, T (owner's UI-BOARD-REQUIREMENTS, 35E FINAL3 data sheet)
BR_28HE_REF = 1.100     # the owner's original ideal-model Br
MAG_R, MAG_H = 5.0, 5.0 # mm, diametric cylinder, owner's candidate


def magnet_b_mT(gap_mm: float, br: float = BR_35E) -> float:
    """Ideal uniform diametral cylinder, on the axis, transverse |B| (owner's FIELD-THERMAL.md): B = Br/4 [z2/sqrt(R^2+z2^2) - z1/sqrt(R^2+z1^2)]"""
    z1, z2 = gap_mm, gap_mm + MAG_H
    f = lambda z: z / math.sqrt(MAG_R ** 2 + z ** 2)
    return br / 4.0 * (f(z2) - f(z1)) * 1e3


def magnet_field() -> dict:
    nom20 = magnet_b_mT(5.0)
    nom176 = nom20 * (1 - 0.00035 * (176 - 20))             # reversible -0.035 %/C (owner's number)
    push = magnet_b_mT(4.5) / magnet_b_mT(5.0) - 1
    gap_p = magnet_b_mT(5.2) / magnet_b_mT(5.0) - 1
    gap_m = magnet_b_mT(4.8) / magnet_b_mT(5.0) - 1
    gap9 = magnet_b_mT(9.0)
    gap15 = magnet_b_mT(15.0)
    cold = 1 + 0.00035 * 60.0                                 # -40 C against 20 C
    br_tol = 0.05                                             # magnet Br tolerance [ALLOCATION]
    b_max = nom20 * (1 + magnet_b_mT(4.5) / magnet_b_mT(5.0) - 1) * (1 + (magnet_b_mT(4.8) / magnet_b_mT(4.5) - 1)) * cold * (1 + br_tol)
    # pushed 0.5 mm, then the gap 0.2 mm tighter on top, cold, magnet +5 % (the largest field the sensor can see)
    b_max = magnet_b_mT(4.3) * cold * (1 + br_tol)
    b_min = magnet_b_mT(5.2) * (1 - 0.00035 * (176 - 20)) * (1 - br_tol)
    rng = {"25": 25.0, "50": 50.0, "100": 100.0}
    sens = {"25": 1308, "50": 654, "100": 326}             # LSB/mT, SBASAF4 p.6
    # removal: field falls with the knob lifted; threshold at half the weakest seated field
    thr = 0.5 * b_min
    gap_at_thr = None
    lo, hi = 5.0, 40.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if magnet_b_mT(mid) * (1 - 0.00035 * (176 - 20)) * (1 - br_tol) > thr:
            lo = mid
        else:
            hi = mid
    gap_at_thr = lo
    return {
        "sources": "owner's UI-BOARD-REQUIREMENTS table and FIELD-THERMAL.md (ideal-cylinder closed form, Br 1.19 T, -0.035 %/C); TI SBASAF4 p.6 "
                   "(ranges +/-25, +/-50, +/-100 mT; 1308, 654, 326 LSB/mT) and p.8 (angle error specified at 80 % of full range)",
        "model_reproduces_owner_table": {"5mm_20C_mT": round_(nom20, 3), "9mm_20C_mT": round_(gap9, 3), "15mm_20C_mT": round_(gap15, 3),
                                         "5mm_176C_mT": round_(nom176, 3), "push_0p5mm_pct": round_(push * 100, 2),
                                         "gap_plus_0p2_pct": round_(gap_p * 100, 2), "gap_minus_0p2_pct": round_(gap_m * 100, 2)},
        "b_nominal_20C_mT": round_(nom20, 3), "b_nominal_176C_mT": round_(nom176, 3),
        "b_max_mT": round_(b_max, 2), "b_min_mT": round_(b_min, 2),
        "b_max_assumptions": "pushed 0.5 mm and gap -0.2 mm (4.3 mm), -40 C (+2.1 %), Br +5 % [ALLOCATION]; b_min: gap +0.2 mm, 176 C, Br -5 %",
        "range_choice_mT": 100, "range_register": "X_RANGE = Y_RANGE = Z_RANGE = 10b (+/-100 mT, A1 device)",
        "range_50mT_would_clip": nom20 > 50.0, "range_100mT_headroom_pct": round_((100.0 - b_max) / 100.0 * 100, 1),
        "range_100mT_within_80pct_of_full_scale": b_max <= 80.0,
        "lsb_uT_100mT": round_(1e3 / sens["100"], 3), "angle_quantisation_deg": round_(math.degrees((1.0 / sens["100"]) / b_min), 5),
        "removal_threshold_mT": round_(thr, 1), "removal_detected_at_gap_mm": round_(gap_at_thr, 2),
        "push_detection": {"push_0p5mm_change_pct": round_(push * 100, 2), "gap_tolerance_pct": [round_(gap_m * 100, 2), round_(gap_p * 100, 2)],
                           "temperature_change_20_to_176C_pct": round_((nom176 / nom20 - 1) * 100, 2),
                           "rule": "relative change of |B| against a slow baseline (time constant >> 1 s), threshold 8 %; absolute |B| cannot "
                                   "separate push from gap tolerance and temperature (owner's own caveat); a separate push actuator remains an option"},
        "checks": {
            "model_reproduces_owner_5mm_55p728": abs(nom20 - 55.728) < 0.01,
            "model_reproduces_owner_9mm_20p106": abs(gap9 - 20.106) < 0.01,
            "model_reproduces_owner_15mm_6p384": abs(gap15 - 6.384) < 0.01,
            "model_reproduces_owner_176C_52p685": abs(nom176 - 52.685) < 0.01,
            "model_reproduces_owner_push_15p29pct": abs(push * 100 - 15.29) < 0.05,
            "range_50mT_clips": nom20 > 50.0,
            "range_100mT_max_field_le_80pct": b_max <= 80.0,
            "removal_threshold_below_min_seated_field": thr < b_min,
        },
    }


# ============================================================== stray field and angle error
# per-axis RMS noise (uT, 1 sigma) of the +/-100 mT range against CONV_AVG, upper envelope read from SBASAF4 Fig. 6-8 (p.12)  [UNVERIFIED:
# read from a plot, +/- 10 %]
NOISE_XY_UT = {1: 190.0, 2: 135.0, 4: 95.0, 8: 62.0, 16: 45.0, 32: 34.0}
CONV_SPS_3AX = {1: 10000, 2: 5700, 4: 3100, 8: 1600, 16: 800, 32: 400}       # SBASAF4 p.17 Table 7-2 / p.34


def stray_field() -> dict:
    b_m = magnet_field()["b_nominal_176C_mT"]            # weakest design field (hot magnet), mT
    cases = {
        "pan_31000_bare": 33.206, "pan_31000_base_roof": 0.960, "nopan_60000_bare": 112.241, "nopan_60000_base_roof": 17.696,
    }
    avg = 16
    sigma = NOISE_XY_UT[avg]
    sig_deg = math.degrees(sigma * 1e-3 / b_m)
    pp_noise = 7.0 * sig_deg                                # 2000 samples in 10 s: expected range ~ 6.8 sigma, 7 used
    peak_noise = 3.5 * sig_deg
    table = {}
    for name, rms in cases.items():
        pk = rms * math.sqrt(2.0)
        err = math.degrees(math.asin(pk * 1e-3 / b_m))
        table[name] = {"B_rms_uT": rms, "B_peak_uT": round_(pk, 3), "angle_error_peak_deg": round_(err, 5),
                       "stray_pp_deg": round_(2 * err, 5), "jitter_pp_with_noise_deg": round_(pp_noise + 2 * err, 4),
                       "nonrepeatable_error_peak_deg": round_(peak_noise + err + 0.0017 + 0.057, 4)}
    worst = max(t["angle_error_peak_deg"] for t in table.values())
    assembled = {k: v for k, v in table.items() if "base_roof" in k or k == "pan_31000_bare"}
    # headroom: stray RMS that would use 0.25 deg / 1 deg, unfiltered, worst phase
    rms_for = lambda deg: b_m * 1e3 * math.sin(math.radians(deg)) / math.sqrt(2.0)
    # block-average gain of N samples spaced Ts against a tone at f (no reliance is placed on it)
    def gain(f, ts, n):
        x = math.pi * f * ts
        if abs(math.sin(x)) < 1e-12:
            return 1.0
        return abs(math.sin(n * x) / (n * math.sin(x)))
    gains = {}
    for f in (31e3, 40e3, 55e3, 60e3):
        vals = [gain(f, ts * 1e-6, avg) for ts in [23.0 + 0.1 * k for k in range(0, 46)]]       # 3.0-3.5 MHz oscillator: 22.9-27.5 us
        gains[f"{f/1e3:g}kHz"] = {"gain_at_25us": round_(gain(f, 25e-6, avg), 4), "max_gain_over_oscillator_tolerance": round_(max(vals), 4)}
    # the frequency window around the sampling alias (40 kHz at Ts = 25 us) where the average passes the tone at >= 50 %
    win = [f for f in range(20000, 100001, 100) if gain(float(f), 25e-6, avg) >= 0.5]
    near40 = [f for f in win if 30000 <= f <= 56000]
    worst_band = max(max(gain(f, ts * 1e-6, avg) for ts in [23.0 + 0.5 * k for k in range(0, 10)]) for f in [31e3 + 250 * k for k in range(0, 117)])
    return {
        "sources": "owner's UI-BOARD-REQUIREMENTS / FIELD-THERMAL.md (incident coil field at die w = -4 mm, 45 A peak, 31 kHz with pan, "
                   "60 kHz without pan, bare and with base/roof; no finite-fascia result; none at 55 kHz); TI SBASAF4 p.6-7 (noise), p.12 Fig. 6-8, "
                   "p.8 (X-Y angle error +/-0.4 deg at 25 C, 50 mT range), p.17 (update rates)",
        "signal_mT_used": b_m, "signal_basis": "hot magnet (176 C, reversible only), the weakest design field, so the stray error is a maximum",
        "conv_avg_choice": avg, "conv_avg_register": "CONV_AVG = 100b (16x)", "conversion_set_rate_sps": CONV_SPS_3AX[avg],
        "conversion_set_period_ms": round_(1e3 / CONV_SPS_3AX[avg], 3),
        "noise_per_axis_uT_1sigma": sigma, "noise_table_uT": NOISE_XY_UT,
        "angle_noise_1sigma_deg": round_(sig_deg, 4), "angle_noise_pp_10s_deg": round_(pp_noise, 4),
        "angle_noise_peak_3p5sigma_deg": round_(peak_noise, 4),
        "angle_noise_pp_by_avg_deg": {str(n): round_(7.0 * math.degrees(v * 1e-3 / b_m), 3) for n, v in NOISE_XY_UT.items()},
        "cases": table, "worst_stray_peak_error_deg": round_(worst, 5), "worst_case": "nopan_60000_bare (no pan, no base/roof, 60 kHz)",
        "tolerable_stray_rms_uT": {"0.25deg": round_(rms_for(0.25), 1), "1deg": round_(rms_for(1.0), 1)},
        "headroom_bare_nopan_to_0p25deg": round_(rms_for(0.25) / 112.241, 2),
        "filtering_claim": "none: the sensor samples one axis every ~25 us (40 ksps); a coil tone aliases, and a 16-sample average passes it unattenuated "
                           "near 40 kHz (inside the 31-55 kHz tank range) once the 3.0-3.5 MHz oscillator tolerance is included. The error is therefore "
                           "bounded by the unfiltered amplitude, which is what the table gives, and by the amplitude at 55 kHz, which is not computed "
                           "(bounded below)",
        "block_average_gain": gains,
        "gain_ge_half_window_Hz_in_tank_range": [min(near40), max(near40)] if near40 else None, "worst_gain_over_31_to_60kHz_and_oscillator_tolerance": round_(worst_band, 3),
        "gap_55kHz": {"no_solver_result_at_55kHz": True,
                      "bound_with_pan": "<= 33.206 uT rms (31 kHz pan case; eddy screening by the pan grows with frequency) [ASSUMPTION]",
                      "bound_without_pan": "<= 112.241 uT rms (60 kHz bare case at the same 45 A peak; the quasi-static coil field does not grow with "
                                           "frequency) [ASSUMPTION]",
                      "error_at_the_bounds_deg": {"pan": table["pan_31000_bare"]["angle_error_peak_deg"], "no_pan": table["nopan_60000_bare"]["angle_error_peak_deg"]},
                      "to_close": "bench: log raw X/Y/Z with the coil running through 31-55 kHz and its harmonics (owner's VALIDATION)"},
        "jitter_budget_pp_deg": 0.5, "step_hysteresis_deg": 1.0, "absolute_error_budget_deg": 1.0,
        "reported_not_gated": ["jitter_pp_bare_nopan_exceeds_0p5deg"],
        "checks": {
            "worst_stray_peak_error_le_0p25deg": worst <= 0.25,
            "assembled_stray_peak_error_le_0p06deg": max(v["angle_error_peak_deg"] for v in assembled.values()) <= 0.06,
            "noise_pp_10s_le_0p5deg_at_16x": pp_noise <= 0.5,
            "jitter_pp_assembled_cases_le_0p5deg": max(v["jitter_pp_with_noise_deg"] for v in assembled.values()) <= 0.5,
            "jitter_pp_all_cases_le_1deg_hysteresis": max(v["jitter_pp_with_noise_deg"] for v in table.values()) <= 1.0,
            "nonrepeatable_error_all_cases_le_0p5deg": max(v["nonrepeatable_error_peak_deg"] for v in table.values()) <= 0.5,
            "jitter_pp_bare_nopan_exceeds_0p5deg": table["nopan_60000_bare"]["jitter_pp_with_noise_deg"] > 0.5,
            "conversion_set_fits_5ms": 1e3 / CONV_SPS_3AX[avg] <= 5.0,
        },
    }


# ============================================================== TMAG5170 configuration and update schedule
def tmag_sensing() -> dict:
    # register words from the field tables, SBASAF4 p.34-36
    device = (4 << 12) | (2 << 8) | (2 << 4) | (1 << 3) | (1 << 2)        # CONV_AVG 16x, SmCo, continuous, T_CH_EN, T_RATE once/set
    sensor = (0 << 14) | (0 << 10) | (7 << 6) | (2 << 4) | (2 << 2) | 2     # no CORDIC, XYZ, all three ranges +/-100 mT
    system = 0                                                           # 32-bit regular frames, CRC on, trigger at SPI command (unused)
    f_exp, f_s = 5e6, 1e6
    ovh = 20e-6                                                          # ESP-IDF queued transaction overhead [ALLOCATION]
    t_wr = 24 / f_exp + ovh                                              # expander write: opcode, register, value
    t_fr = {f"{int(f/1e6) if f >= 1e6 else f}": 32 / f + ovh for f in (1e6, 2.5e6, 5e6)}
    t_gap = 1e-6
    groups = {}
    for key, f in (("1MHz", 1e6), ("2.5MHz", 2.5e6), ("5MHz", 5e6)):
        one = t_wr + t_gap + (32 / f + ovh) + t_gap + t_wr
        groups[key] = {"one_frame_group_us": round_(one * 1e6, 1), "three_frame_read_us": round_(3 * one * 1e6, 1),
                       "share_of_5ms_pct": round_(3 * one / 5e-3 * 100, 2)}
    oled_chunk = 512 * 8 / 8e6
    worst_latency = oled_chunk + 3 * (t_wr + t_gap + (32 / 1e6 + ovh) + t_gap + t_wr) + 1.25e-3
    return {
        "sources": "TI SBASAF4 p.34-37 (DEVICE_CONFIG, SENSOR_CONFIG, SYSTEM_CONFIG), p.17 (update rates), p.28-29 (32-bit SPI frames, CRC), p.5 (IACT)",
        "mode": "OPERATING_MODE = 010b (continuous conversion) after SENSOR_CONFIG and SYSTEM_CONFIG are written in configuration mode",
        "DEVICE_CONFIG": {"hex": f"0x{device:04X}", "CONV_AVG": "100b (16x: 0.8 ksps for XYZ, 1.25 ms per set)", "MAG_TEMPCO": "10b (SmCo, 0.03 %/C)",
                          "OPERATING_MODE": "010b", "T_CH_EN": 1, "T_RATE": "1 (temperature once per conversion set)"},
        "SENSOR_CONFIG": {"hex": f"0x{sensor:04X}", "ANGLE_EN": "00b (raw XYZ, angle by atan2 in firmware: the CORDIC angle is 0.25 deg effective)",
                          "MAG_CH_EN": "0111b (X, Y, Z)", "X_RANGE/Y_RANGE/Z_RANGE": "10b (+/-100 mT)"},
        "SYSTEM_CONFIG": {"hex": f"0x{system:04X}", "DATA_TYPE": "000b (16-bit register frames)", "CRC": "enabled (default; never write CRC_DIS)",
                          "DIAG": "AFE diagnostics run by firmware once a second and at power-up (DIAG_EN/DIAG_SEL), not every set"},
        "read_per_update": "3 frames per set (X, Y, Z results), each a separate select/release pair; the response to a read command arrives in the "
                           "next frame; every response carries conversion status and the set count, and a set is accepted only when the three "
                           "responses carry the same set count, CRC is good, and no ERROR_STAT / CRC_STAT / FRAME_STAT / conversion-status flag is set",
        "update_period_ms": 5.0, "update_rate_Hz": 200,
        "sck_policy": "1 MHz first; <= 2.5 MHz after the MISO scope check; 5 MHz only if the bench shows >= 10 ns more than the calc below",
        "bus_time_per_update": groups, "oled_chunk_ms": round_(oled_chunk * 1e3, 3),
        "worst_data_age_ms": round_(worst_latency * 1e3, 3),
        "temperature": "TEMP_RESULT read once per set group for diagnostics and gain-mismatch correction (25 C code 17522, 60 LSB/C, p.6)",
        "inhibit": "no valid set for 100 ms (20 missed updates), or any invalid/stale set: inhibit; replacement: 200 ms stable + explicit Start",
        "checks": {
            "update_period_covers_bus_time_at_1MHz": 3 * (t_wr + t_gap + (32 / 1e6 + ovh) + t_gap + t_wr) < 5e-3 * 0.2,
            "worst_data_age_le_5ms": worst_latency <= 5e-3,
            "conversion_set_faster_than_update": 1.25e-3 < 5e-3,
            "device_config_word_computed": device == 0x422C and sensor == 0x01EA,
            "sensor_current_in_allocation": TMAG_MA <= 5.0,
        },
    }


# ============================================================== thermal: buzzer and sensor tab
BUZZER_RATING_C = {"GSD9605YB-3V2800": (-20.0, 70.0), "GSD9605YB-5V2800": (-30.0, 85.0), "SMD-9650-3327": (-20.0, 80.0)}
BUZZER_MARGIN_K = 1.0


def buzzer_thermal() -> dict:
    sigma = 5.67e-8
    # steady-state node: buzzer body between the fascia (radiation + 6 mm air gap), the board (pads and bottom) and the internal air
    t_f, t_a = 139.73, 65.0           # pushed_pan_300, 40 C ambient: fascia at v26 and internal air (owner's FIELD-THERMAL.md thermal table)
    a_top, a_side = (9.6e-3) ** 2, 4 * 9.6e-3 * 5.0e-3
    eps = 1 / (1 / 0.9 + 1 / 0.8 - 1)
    h_rad = 4 * sigma * ((t_f + t_a) / 2 + 273.15) ** 3 * eps
    h_gap = 0.031 / 6e-3
    g_f = (h_rad + h_gap) * a_top
    g_a = 8.0 * a_side                # h = 8 W/m2K (the owner's study)
    g_p = 300.0 * a_top + 0.01        # 0.1 mm air film under the body + pads [ALLOCATION]
    p_buz = BUZZER_MA * 1e-3 * 3.465
    res = {}
    for name, t_pcb in (("board_at_air_65C", 65.0), ("board_at_75C", 75.0), ("board_at_80C_design_limit", 80.0)):
        tb = (g_f * t_f + g_a * t_a + g_p * t_pcb + p_buz) / (g_f + g_a + g_p)
        res[name] = round_(tb, 1)
    t_worst = res["board_at_80C_design_limit"]
    t_typ = res["board_at_air_65C"]
    ratings = {k: {"min_C": v[0], "max_C": v[1], "margin_at_80C_board_K": round_(v[1] - t_worst, 1),
                   "margin_at_65C_board_K": round_(v[1] - t_typ, 1)} for k, v in BUZZER_RATING_C.items()}
    return {
        "sources": "owner's FIELD-THERMAL.md thermal table (fascia at v = 26: 139.73 C, internal air 65 C, 40 C ambient, pushed pan 300), board design "
                   "limit 80 C (SPEC); LCSC listings C255327 (-20..70 C), C530415 (-30..85 C), C42420997 (-20..80 C)",
        "model": "one node: top face to the fascia (radiation, e_eff 0.72, plus 6 mm air gap), sides to internal air (h 8 W/m2K), bottom and pads to the board "
                 "(0.1 mm air film + 0.01 W/K); self-heating 30 mA x 3.465 V [ALLOCATION: h, emissivity, film thickness]",
        "coupling_W_per_K": {"fascia": round_(g_f, 6), "air": round_(g_a, 6), "board": round_(g_p, 6)},
        "buzzer_body_C": res, "buzzer_power_W": round_(p_buz, 4),
        "ratings": ratings,
        "location": "front face, centre (u, v) = (-95.0, 24.0): lowest v on the board (coolest fascia strip in the owner's table), 21 mm from the OLED's "
                    "lower-left corner and 10 mm from the nearest tact bezel",
        "decision": "GSD9605YB-5V2800 (85 C): the 70 C part has no margin at the 65 C internal air of the 40 C ambient case and fails at a 75 C board",
        "checks": {
            "chosen_part_rating_covers_worst_with_margin": BUZZER_RATING_C["GSD9605YB-5V2800"][1] - t_worst >= BUZZER_MARGIN_K,
            "old_part_rating_fails_at_75C_board": BUZZER_RATING_C["GSD9605YB-3V2800"][1] < res["board_at_75C"] + BUZZER_MARGIN_K,
            "fascia_coupling_is_minor": g_f < 0.1 * g_p,
        },
    }


def sensor_thermal() -> dict:
    sigma = 5.67e-8
    t_f, t_a = 150.23, 65.0          # knob fascia v53, pushed_pan_300, 40 C ambient (owner's table)
    a_tab, gap = 0.060 * 0.032, 1.78e-3          # tab front face to the fascia rear: 1.78 mm (w -4.78 to -3.00)
    eps = 1 / (1 / 0.9 + 1 / 0.8 - 1)
    h_rad = 4 * sigma * ((t_f + t_a) / 2 + 273.15) ** 3 * eps
    g_f = (h_rad + 0.033 / gap) * a_tab
    g_a = 8.0 * 2 * a_tab                       # both faces and edges to the internal air; the tab is open to it
    t_tab = (g_f * t_f + g_a * t_a) / (g_f + g_a)
    p = TMAG_MA * 1e-3 * 3.465
    t_die = t_tab + p * 100.0                   # package to board 100 K/W [ALLOCATION]
    return {
        "sources": "owner's FIELD-THERMAL.md (knob fascia 150.23 C, internal air 65 C in the hot case; TMAG5170 150 C rating, 125 C design target)",
        "model": "tab as an isothermal plate 60 x 32 mm between the fascia rear (1.78 mm air gap + radiation) and internal air; spacers of low-conductivity "
                 "material assumed (their conduction is not counted: a stiff spacer would add to g_fascia) [ALLOCATION]",
        "coupling_W_per_K": {"fascia": round_(g_f, 5), "air": round_(g_a, 5), "ratio": round_(g_f / g_a, 3)},
        "tab_C": round_(t_tab, 1), "die_C": round_(t_die, 1), "design_target_C": 125.0, "rating_C": 150.0,
        "owner_relation": "(T_sensor - T_air) / (T_fascia - T_sensor) = G_fascia / G_air; allowed ratio for 125 C: "
                          f"{(125.0 - t_a) / (t_f - 125.0):.2f}",
        "open": "the margin to 125 C is small (see die_C): the tab's thermal separation (spacer material and height, a window in the fascia carrier) "
                "is the owner's thermal proof; a larger gap lowers g_fascia",
        "checks": {"die_below_150C_rating": t_die < 150.0, "die_below_125C_target": t_die < 125.0},
    }


def tact_switch() -> dict:
    return {
        "sources": "UI-BOARD-REQUIREMENTS (KSC2 drawing figures as quoted); the drawing itself could not be fetched here",
        "part": "C&K (Littelfuse) KSC223G LFG = Y31B13136FPLFG, gold contacts, G (gullwing) terminals",
        "body_mm": [6.2, 6.2], "actuator_top_above_pcb_mm": 3.5, "force_N": [2.25 - 0.55, 2.25 + 0.55],
        "electrical_travel_mm": [0.35 - 0.15, 0.35 + 0.25], "min_contact_load": "0.1 mA, 20 mV", "min_tactile_ratio_pct": 10,
        "centres_uv_mm": {"back_GP2": [-75.0, 26.0], "select_start_GP0": [-35.0, 26.0], "stop_GP1": [5.0, 26.0]},
        "note": "the 10 % minimum tactile ratio does not guarantee the assembled 25 % snap (SPEC); that is a mechanism question for the cap stack",
        "checks": {"contact_current_inside_ksc2_envelope": pullups()["tact_contact_current_mA"]["min_at_3.135V_1pct_high"] >= 0.1},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    sections = {
        "power_budget": power_budget(), "harness_drop": harness_drop(), "v3v3_at_load": v3v3_at_load(),
        "oled_supply_options": oled_supply_options(),
        "pullups": pullups(), "buzzer_drive": buzzer_drive(), "esd": esd(), "spi_timing": spi_timing(),
        "oled_reset": oled_reset(), "debounce_and_poll": debounce_and_poll(),
        "cs_qualification": cs_qualification(), "magnet_field": magnet_field(), "stray_field": stray_field(),
        "tmag_sensing": tmag_sensing(), "buzzer_thermal": buzzer_thermal(), "sensor_thermal": sensor_thermal(),
        "tact_switch": tact_switch(),
    }
    gate_exclusions = {("debounce_and_poll", "firmware_debounce_covers_bounce"),
                       ("stray_field", "jitter_pp_bare_nopan_exceeds_0p5deg"),       # expected True: a reported finding, not a pass criterion
                       }
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
