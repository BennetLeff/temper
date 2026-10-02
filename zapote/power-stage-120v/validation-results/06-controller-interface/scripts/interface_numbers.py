#!/usr/bin/env python3
"""Reproduce D10 arithmetic; assumptions and vendor tables are in README.

These are conditional resistor/DC calculations, not a whole-system bound.
"""
import json

rail_min, rail_max = 3.135, 3.465
r_top, r_bottom = 4 * 470_000, 15_800
ratio = r_bottom / (r_top + r_bottom)
ratio_min = r_bottom * .999 / (r_top * 1.01 + r_bottom * .999)
ratio_max = r_bottom * 1.001 / (r_top * .99 + r_bottom * 1.001)
subtotal = {
    "U1_U2_ICC_selected_DC_max_mA": 2 * 4.8,
    "U4_IDD2_max_mA": 7.2,
    "U9_ICC2_DC_max_mA": 1.2,
    "U10_U11_U12_IQ_max_mA": 3 * .060,
    "U13_ICC_max_mA": .010,
    "R8_R16_DIS_pullups_max_mA": 2 * rail_max / 990 * 1000,
    "R40_R41_bias_max_mA": rail_max / (2000 * .999) * 1000,
    "R43_R44_R45_R46_references_max_mA": 2 * rail_max / (13320 * .999) * 1000,
}
result = {
    "classification": "Conditional DC resistor corners and selected specification maxima; no ADC receiver, load, timing or whole-board-current bound",
    "divider": {"nominal_ratio": ratio, "ratio_min_resistor_only": ratio_min, "ratio_max_resistor_only": ratio_max,
        "bus_at_2V_nominal": 2 / ratio, "bus_at_2V_min_resistor_only": 2 / ratio_max,
        "bus_at_2V_max_resistor_only": 2 / ratio_min,
        "cases": [{"bus_V": bus, "VIN_nominal_V": bus * ratio, "VIN_resistor_range_V": [bus * ratio_min, bus * ratio_max],
                   "ideal_OUTP_V": 1.44 + bus * ratio / 2 if bus * ratio <= 2 else None,
                   "ideal_OUTN_V": 1.44 - bus * ratio / 2 if bus * ratio <= 2 else None,
                   "ADC_code": None, "reason": "no defined ADC receiver/calibration; outside linear range at 280 V"} for bus in [0,198,280]]},
    "fault": {"pullup_max_uA": rail_max / 9900 * 1e6, "pullup_min_for_high_level_V": rail_min - 10100 * 20e-6,
              "U13_high_min_100uA_V": rail_min - .1, "interlock_high_required_V": 2.7,
              "U13_low_guarantee_3V_16mA_V": .4, "interlock_low_required_V": .3},
    "PWM": {"ESP_high_high_impedance_min_V": .8 * rail_min, "ESP_low_high_impedance_max_V": .1 * rail_max,
            "UCC_high_threshold_max_V": 2.3, "UCC_low_threshold_min_V": .8,
            "UCC_input_pull_down_load_max_uA": rail_max/50000*1e6},
    "PERMIT": {"two_power_board_pulldowns_plus_100R_max_uA": 2 * rail_max / (99000 + 99) * 1e6,
               "includes_interlock_10k_pull_down_max_uA": (2/(99000+99) + 1/9900)*rail_max*1e6},
    "power_board_V3V3_selected_terms_mA": subtotal,
    "power_board_V3V3_selected_subtotal_mA": sum(subtotal.values()),
    "CT": {"burden_ohm": 1.5, "ratio_assumed_exact": 100,
           "nominal_transfer_mV_per_A": 15,
           "cases": [{"primary_peak_A": current, "ideal_monitor_V": [1.65-current*.015,1.65+current*.015],
                     "conditional_resistor_rail_range_V": [rail_min*.4995-current/100*1.515, rail_max*.5005+current/100*1.515]} for current in [37,71,88]],
           "burden_power_at_18_7A_rms_W": (18.7/100)**2*1.5},
    "ground_contacts": [2,4,15,16],
}
print(json.dumps(result, indent=2, sort_keys=True))
