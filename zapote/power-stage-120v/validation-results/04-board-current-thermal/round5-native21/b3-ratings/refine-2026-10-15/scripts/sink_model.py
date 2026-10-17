#!/usr/bin/env python3
"""FET case (tab) temperature per operating case: the far end of the drain-lead path.

    python3 sink_model.py  ->  results/sink_model.json  (also imported: t_case(ceil, corner))

Chain (every constant is read from its source file and asserted, not retyped):
  * FET loss, basis B (ZVS conduction + covered turn-off; the m11 estimate), round 6 board_side.py fets():
      p_LS = 6.78 (I_t / 21.47)^2 + 0.33,  p_HS = p_LS - 0.07,  p_BR1 = 2 x 1.05 x 0.9 x I_line
    with I_t = 1.05 x ceiling (29.4 A at 28 A, as run_study OPS c28) and I_line = 11.1 A (the inlet hold the cases use).
  * Sink: the enclosure R33 sizing model (requirement.py, board_side.py): R_SA 0.29 C/W at 50 C inlet air + pedestal
    R_PED 0.0161 C/W x P_sink; case-to-sink R_cs 0.399-0.634 C/W per FET (m11 AlN stack; 0.634 is the R33 value).
  * Firmware fan law (thermal_mgmt.h): drive = max(PI on the sink NTC at FAN_SINK_SETPOINT_C 88.6, PI on the coil at
    140 C), cap 0.8. In steady state the sink loop slows the blower until the sink reads 88.6 C, unless the coil loop
    asks for more air (then the sink is cooler, down to the R_SA value). Firmware hard trip 95 C (OVER_TEMP_THRESHOLD,
    firmware/config.yaml, cited in thermal_mgmt.h); hardware comparator 98.3 / 101.4 / 104.6 C.
Corners (T_sink):
  cool     R_SA 0.29 x P_sink + 50 C inlet, R_cs 0.399   (coil loop holds the blower fast; most cooling of the board)
  central  88.6 C fan-law setpoint, R_cs 0.634          (sink loop governs: the steady state at these loads)
  hot      95.0 C firmware hard trip, R_cs 0.634        (the hottest sink that sustained operation can reach)
T_case = T_sink + R_PED x P_sink + p_FET x R_cs (the NTC is taken on the sink base; the pedestal drop is added).
Basis A (the D-18 switching proxy) is reported as a sensitivity: at 45-60 kHz it needs a sink above the 95 C trip at
28 A, so sustained operation is bounded by the trip, and its hotter FET raises T_case by p_A x R_cs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FETS, FIRMWARE, R33_THERMAL, RESULTS, UNIT  # noqa: E402

BOARD_SIDE = UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py"
REQ = R33_THERMAL / "requirement.py"
M11 = UNIT / "validation-results/08-manufacturing-package/native-21/owner-items/m11/RECOMMENDATION.md"


def _src_checks():
    bs = BOARD_SIDE.read_text()
    assert "p_fet = 6.78 * (i / 21.47) ** 2 + 0.33" in bs
    assert "p_sink_b = 2 * (p_fet - 0.07) + 2 * p_fet + p_br1" in bs
    assert "p_br1 = 2 * 1.05 * 0.9 * (P / (0.95 * V))" in bs
    assert "tj_b = 50.0 + (0.29 + RQ.R_PED) * p_sink_b + p_fet * (0.28 + 0.634)" in bs
    rq = REQ.read_text()
    r_ped = float(re.search(r"^R_PED = ([0-9.]+)", rq, re.M).group(1))
    fw = FIRMWARE.read_text()
    setpoint = float(re.search(r"#define FAN_SINK_SETPOINT_C\s+([0-9.]+)f", fw).group(1))
    hw = {k: float(re.search(rf"#define THERMAL_HW_SINK_TRIP_{k}_C\s+([0-9.]+)f", fw).group(1)) for k in ("LOW", "NOM", "HIGH")}
    assert "heatsink hard trip is OVER_TEMP_THRESHOLD (firmware/config.yaml, 95 C)" in fw
    m11 = M11.read_text()
    assert "0.40–0.63 °C/W per FET" in m11
    return r_ped, setpoint, hw


R_PED, FAN_SETPOINT_C, HW_TRIP_C = _src_checks()
FW_TRIP_C = 95.0
R_SA = 0.29
INLET_C = 50.0
RCS = {"cool": 0.399, "central": 0.634, "hot": 0.634}
RTH_JC = 0.28            # IPW65R018CFD7 Rev.2.0 p.4


def losses(ceil):
    i_t = 29.4 if ceil == 28.0 else 1.05 * ceil
    p_ls = 6.78 * (i_t / 21.47) ** 2 + 0.33
    p_hs = p_ls - 0.07
    p_br1 = 2 * 1.05 * 0.9 * 11.1
    return i_t, {"HS": p_hs, "LS": p_ls}, p_br1, 2 * p_hs + 2 * p_ls + p_br1


def t_case(ceil, corner="central"):
    """{FET ref: case temperature C} and the details."""
    i_t, p, p_br1, p_sink = losses(ceil)
    t_rsa = INLET_C + R_SA * p_sink
    t_sink = {"cool": t_rsa, "central": max(FAN_SETPOINT_C, t_rsa), "hot": max(FW_TRIP_C, t_rsa)}[corner]
    tc = {ref: t_sink + R_PED * p_sink + p[side] * RCS[corner] for ref, side in FETS.items()}
    return tc, {"I_t_A": i_t, "p_fet_W": p, "p_br1_W": p_br1, "p_sink_W": p_sink, "T_sink_rsa_C": t_rsa,
                "T_sink_C": t_sink, "R_cs": RCS[corner], "T_case_C": tc, "Tj_C": {r: tc[r] + p[s] * RTH_JC for r, s in FETS.items()}}


def basis_a(ceil, f_hz):
    """D-18 switching-proxy FET loss (R33 requirement.solve) and T_case with the sink held at the firmware trip."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(R33_THERMAL))
    import requirement as RQ  # noqa: E402
    i_t = 29.4 if ceil == 28.0 else 1.05 * ceil
    case = {"frequency_hz": f_hz, "i_rms_a": i_t, "target_w": 11.1 * 0.95 * 120.0, "vrms_v": 120.0}
    r = RQ.solve(case, INLET_C, R_SA + RQ.R_PED, 0.634, 13, ("Q5", "Q6", "Q3", "Q2", "BR1"), 0.378)
    if r is None:
        return {"f_kHz": f_hz / 1e3, "runaway": True}
    worst = max(r["powers"][q] for q in FETS)
    return {"f_kHz": f_hz / 1e3, "p_fet_max_W": worst, "sink_W": r["psink"],
            "T_sink_needed_at_RSA_0p29_C": INLET_C + (R_SA + RQ.R_PED) * r["psink"],
            "T_case_at_fw_trip_C": FW_TRIP_C + worst * 0.634}


def main():
    out = {"sink_basis": "S8 baseline sink: R_SA 0.29 C/W at 13 CFM, 50 C inlet (D-18 limit; R33 requirement.py, the device "
                         "study's S8). The K1 contingency sink (R_SA 0.214, DECISIONS 2026-10-12 item 15) is not used; its "
                         "123.8 / 128.7 C Tj figures were not reproduced by the device study (DECISIONS 49).",
           "sources": {"board_side": str(BOARD_SIDE), "requirement": str(REQ), "firmware": str(FIRMWARE), "m11": str(M11)},
           "constants": {"R_SA": R_SA, "R_PED": R_PED, "inlet_C": INLET_C, "fan_sink_setpoint_C": FAN_SETPOINT_C,
                         "fw_trip_C": FW_TRIP_C, "hw_trip_C": HW_TRIP_C, "R_cs": RCS, "RthJC": RTH_JC},
           "cases": {}}
    for ceil in (14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0, 28.0):
        out["cases"][f"c{ceil:g}"] = {c: t_case(ceil, c)[1] for c in ("cool", "central", "hot")}
        out["cases"][f"c{ceil:g}"]["basis_A"] = [basis_a(ceil, f) for f in (45e3, 60e3)]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "sink_model.json").write_text(json.dumps(out, indent=1) + "\n")
    for k in ("c22", "c28"):
        v = out["cases"][k]
        print(k, {c: (round(v[c]["T_sink_C"], 1), {r: round(t, 1) for r, t in v[c]["T_case_C"].items()}) for c in ("cool", "central", "hot")})
        print("   basis A:", [{kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in b.items()} for b in v["basis_A"]])


if __name__ == "__main__":
    main()
