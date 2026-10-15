"""sensor-r3 open item 7: recompute the MAX31865 C1 fault-threshold words from the CR-7 inputs.

CR-7 inputs (pcb/REQUIREMENTS.md R3.2, CHANGE-REQUEST.md section 5):
  low  = R(-40 C), high = R(360 C), Pt100 IEC 60751 Callendar-Van Dusen,
  RREF 430 ohm (CR-2), 15-bit ratiometric code, word = code << 1.
MAX31865 semantics (datasheets/max31865.pdf, "Fault Threshold Registers"):
  RTD High bit set if the RTD register >= the High Fault Threshold;
  RTD Low  bit set if the RTD register <= the Low  Fault Threshold.
The firmware rule (firmware/tools/board_derivation_lib.py, used here unchanged):
  high word = floor(code(R_high)) << 1, low word = ceil(code(R_low)) << 1, so a
  resistance at or beyond the boundary trips whether the converter truncates
  or rounds its code.

It prints and writes cr7-thresholds.json:
  - the words from the exact CVD resistances (the CR-7 inputs are temperatures);
  - the words from the 2-decimal resistances printed in CR-7 (84.27 / 233.21 ohm);
  - CR-7's listed words (pcb/checks.json firmware_constants) and the firmware's
    (firmware/config.yaml);
  - the boundary temperature each candidate word actually trips at.
Gate (exit 1 otherwise): config.yaml carries the words of the exact inputs, and
its boundary resistances reproduce them.

Run: python3 cr7_thresholds.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "firmware" / "tools"))
from board_derivation_lib import max31865_high_threshold_word, max31865_low_threshold_word  # noqa: E402

A, B, C = 3.9083e-3, -5.775e-7, -4.183e-12
R0, RREF, CODES = 100.0, 430.0, 2 ** 15
T_LOW, T_HIGH = -40.0, 360.0


def cvd(t: float) -> float:
    return R0 * (1 + A * t + B * t * t + (C * (t - 100) * t ** 3 if t < 0 else 0.0))


def cvd_inv(r: float) -> float:
    lo, hi = -200.0, 850.0
    for _ in range(100):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if cvd(m) < r else (lo, m)
    return (lo + hi) / 2


def word_info(word: int) -> dict:
    code = word >> 1
    r = code * RREF / CODES
    return {"word": word, "code": code, "ohm": round(r, 5), "degC": round(cvd_inv(r), 4)}


def main() -> int:
    r_lo, r_hi = cvd(T_LOW), cvd(T_HIGH)
    exact = {"low": max31865_low_threshold_word(r_lo, RREF), "high": max31865_high_threshold_word(r_hi, RREF)}
    printed = {"low": max31865_low_threshold_word(84.27, RREF), "high": max31865_high_threshold_word(233.21, RREF)}
    pcb = json.loads((HERE.parent / "pcb" / "checks.json").read_text())
    fc = pcb["info"]["firmware_constants"]
    cr7 = {"low": fc["LOW_THRESHOLD_WORD"], "high": fc["HIGH_THRESHOLD_WORD"]}
    cfg = yaml.safe_load((REPO / "firmware" / "config.yaml").read_text())
    consts = {}

    def walk(x):
        if isinstance(x, dict):
            if "c_symbol" in x and "value" in x:
                consts[x["c_symbol"]] = x["value"]
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(cfg)
    fw = {"low": consts["MAX31865_C1_LOW_THRESHOLD_WORD"], "high": consts["MAX31865_C1_HIGH_THRESHOLD_WORD"]}
    fw_ohm = {"low": consts["RTD_C1_SHORT_FAULT_OHM"], "high": consts["RTD_C1_OPEN_FAULT_OHM"]}
    fw_rederived = {"low": max31865_low_threshold_word(fw_ohm["low"], RREF),
                    "high": max31865_high_threshold_word(fw_ohm["high"], RREF)}
    checks = {
        "config_words_equal_exact_cr7_inputs": fw == exact,
        "config_ohms_rederive_config_words": fw_rederived == fw,
        "high_word_trips_at_or_below_360C": word_info(exact["high"])["degC"] <= T_HIGH,
        "low_word_trips_at_or_above_minus40C": word_info(exact["low"])["degC"] >= T_LOW,
    }
    out = {
        "scope": __doc__.strip(),
        "R_low_ohm": r_lo, "R_high_ohm": r_hi,
        "code_low_exact": r_lo / RREF * CODES, "code_high_exact": r_hi / RREF * CODES,
        "words_from_exact_inputs": exact, "words_from_printed_2dp_ohms": printed,
        "cr7_listed_words": cr7, "firmware_config_words": fw, "firmware_config_ohms": fw_ohm,
        "trip_points": {name: word_info(w) for name, w in
                        (("high_35542", 35542), ("high_35544", 35544), ("low_12844", 12844))},
        "checks": checks, "all_pass": all(checks.values()),
    }
    (HERE / "cr7-thresholds.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"R(-40) = {r_lo:.5f} ohm, code {r_lo / RREF * CODES:.3f}; R(360) = {r_hi:.5f} ohm, code "
          f"{r_hi / RREF * CODES:.3f}")
    print(f"exact inputs -> {exact}; printed 2-dp ohms -> {printed}; CR-7 lists {cr7}; firmware {fw}")
    for k, v in out["trip_points"].items():
        print(f"  {k}: code {v['code']} = {v['ohm']} ohm = {v['degC']} C")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print("CR-7 THRESHOLDS PASS" if out["all_pass"] else "CR-7 THRESHOLD FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
