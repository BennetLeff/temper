#!/usr/bin/env python3
"""FET case (tab) temperature for the B3 drain-lead path (thermal-refine 2026-10-15).

    t_case(ceil, corner="central", i_line=I_LINE_A) -> {ref: C}

Chain (constants asserted against their repo sources at import):
  * FET loss, basis B (ZVS), round 6 board_side.py: p_LS = 6.78 (I_t / 21.47)^2 + 0.33, p_HS = p_LS - 0.07,
    p_BR1 = 2 x 1.05 x 0.9 x I_line; I_t = 1.05 x ceiling (29.4 A at 28 A). I_line defaults to run_study.I_LINE_A, the
    13.5 A firmware inlet bound (was the 11.1 A hold of board_side.py; b3-ratings/line-hold-2026-10-15).
  * Sink: R_SA 0.29 C/W at 50 C inlet + pedestal 0.0161 C/W x P_sink (enclosure R33 requirement.py, as board_side.py);
    case-to-sink 0.634 C/W per FET (m11 AlN stack, conservative end of 0.40-0.63).
  * Firmware fan law (firmware/components/control/thermal_mgmt.h): drive = max(PI sink 88.6 C, PI coil 140 C) -> in steady
    state the sink sits at the 88.6 C setpoint unless the coil loop asks for more air.
Corners: cool = R_SA value with 0.399 C/W; central = max(88.6, R_SA value); hot = max(95 C firmware trip, R_SA value).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
_bs = (UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py").read_text()
assert "p_fet = 6.78 * (i / 21.47) ** 2 + 0.33" in _bs and "p_sink_b = 2 * (p_fet - 0.07) + 2 * p_fet + p_br1" in _bs
assert "tj_b = 50.0 + (0.29 + RQ.R_PED) * p_sink_b + p_fet * (0.28 + 0.634)" in _bs
_fw = (UNIT.parents[1] / "firmware/components/control/thermal_mgmt.h").read_text()
FAN_SINK_SETPOINT_C = float(re.search(r"#define FAN_SINK_SETPOINT_C\s+([0-9.]+)f", _fw).group(1))
assert "heatsink hard trip is OVER_TEMP_THRESHOLD (firmware/config.yaml, 95 C)" in _fw
FW_TRIP_C, R_SA, R_PED, INLET_C = 95.0, 0.29, 0.0161, 50.0
RCS = {"cool": 0.399, "central": 0.634, "hot": 0.634}
SIDE = {"Q2": "HS", "Q5": "HS", "Q3": "LS", "Q6": "LS"}
sys.path.insert(0, str(HERE.parent / "b3"))
from run_study import I_LINE_A  # noqa: E402  (one line-current basis for every B3 consumer)


def t_case(ceil: float, corner: str = "central", i_line: float = I_LINE_A) -> dict:
    i_t = 29.4 if ceil == 28.0 else 1.05 * ceil
    p_ls = 6.78 * (i_t / 21.47) ** 2 + 0.33
    p = {"HS": p_ls - 0.07, "LS": p_ls}
    p_sink = 2 * p["HS"] + 2 * p["LS"] + 2 * 1.05 * 0.9 * i_line
    t_rsa = INLET_C + R_SA * p_sink
    t_sink = {"cool": t_rsa, "central": max(FAN_SINK_SETPOINT_C, t_rsa), "hot": max(FW_TRIP_C, t_rsa)}[corner]
    return {ref: t_sink + R_PED * p_sink + p[s] * RCS[corner] for ref, s in SIDE.items()}
