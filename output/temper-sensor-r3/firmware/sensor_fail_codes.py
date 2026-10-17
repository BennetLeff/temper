"""DECISIONS.md D-OPEN: the C1 sensor-failure codes, and why a reading up there is not a temperature.

check_runaway_boundary() latches the unclearable RUNAWAY_FAULT on any reading
above 300 degC. An open Pt100 converts to full scale (code 32767, 988.7 degC),
so before D-OPEN an open element latched RUNAWAY even though register 07h had
flagged the conversion. rtd_convert_classify_failure() (components/sensors/
rtd_convert.c) now sends a conversion that is evidently a sensor failure to the
recoverable FAULT_PROBE_OPEN / FAULT_PROBE_SHORT path:

  OPEN   code >= RTD_C1_FAIL_HIGH_CODE = ceil(code(R(850 degC))), or 07h D5..D2
  SHORT  code <= RTD_C1_FAIL_LOW_CODE  = floor(code(R(-200 degC)))

This script recomputes both codes from IEC 60751 (RREF 430 ohm, 15-bit code)
and gates them against rtd_convert.h. It also writes the evidence that 850 degC
is out of physical reach as a first reading:

  - the C1 element's rating (IST P0K1.202, -200..+600 degC, cad/QUOTE-LIST.md)
    and the IEC 60751 range top (850 degC: the Callendar-Van Dusen equation
    the firmware inverts is not defined above it);
  - the hottest the r3 truth plant can drive the element uncontrolled: each
    frying pan at 1800 W x eta 0.92 (the top of es.ETA_SWEEP) from ambient
    to steady state, element temperature T_el;
  - the time a real pan needs to climb from the 300 degC latch to 850 degC at
    the fastest heating any modelled fault produces (runaway-checks.json
    margins.r1_fault_max_5block_rise_K_per_s), in 50 Hz conversions, every
    one of which latches RUNAWAY on the way;
  - the codes of full scale, the 360 degC high-threshold word (35544) and
    300 degC, so the bands are visible: plausible over-temperatures (300..850
    degC, flagged above 360 degC) still latch RUNAWAY.

Writes sensor-fail-codes.json. Exit 1 if rtd_convert.h disagrees or a margin
fails. Run: python3 sensor_fail_codes.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import ref  # noqa: E402
from ref import es, screen  # noqa: E402

A, B, C = 3.9083e-3, -5.775e-7, -4.183e-12
R0, RREF, CODES = 100.0, 430.0, 2 ** 15
SELF_HEATING_K = 0.061
T_CHIP_RATING = 600.0
T_IEC_TOP, T_IEC_BOTTOM = 850.0, -200.0
T_ABS = 300.0
HIGH_WORD = 35544
HEADER = REPO / "firmware" / "components" / "sensors" / "include" / "rtd_convert.h"


def cvd(t: float) -> float:
    return R0 * (1 + A * t + B * t * t + (C * (t - 100) * t ** 3 if t < 0 else 0.0))


def code_to_c(code: int) -> float:
    """rtd_convert_code_to_c (loading correction off), as the firmware computes it."""
    r = code / CODES * RREF
    disc = A * A - 4 * B * (1 - r / R0)
    return (-A + math.sqrt(disc)) / (2 * B) - SELF_HEATING_K


def header_codes() -> dict:
    text = HEADER.read_text()
    out = {}
    for name in ("RTD_C1_FAIL_HIGH_CODE", "RTD_C1_FAIL_LOW_CODE"):
        m = re.search(rf"#define\s+{name}\s+(\d+)u", text)
        out[name] = int(m.group(1)) if m else None
    return out


def plant_ceiling() -> dict:
    """Uncontrolled full power from ambient to steady state, per frying pan."""
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    eta = max(es.ETA_SWEEP)
    rows = {}
    for pan in ("cast_iron_26", "carbon_steel_28", "triply_clad_24"):
        lo, hi = spread[pan]
        h = (lo * hi) ** 0.5
        tr = screen.Truth(es.PANS[pan], h, eta, 0)
        prev = None
        for k in range(int(3000.0 / es.DT_SIM)):
            tr.step(es.P_MAX, h)
            if k % int(100.0 / es.DT_SIM) == 0:
                if prev is not None and abs(tr.Tel - prev) < 0.05:
                    break
                prev = tr.Tel
        rows[pan] = {"eta": eta, "T_el_C": round(float(tr.Tel), 1), "T_c_C": round(float(tr.T_c()), 1),
                     "hottest_ring_C": round(float(tr.T.max()), 1)}
    return rows


def main() -> int:
    r_hi, r_lo = cvd(T_IEC_TOP), cvd(T_IEC_BOTTOM)
    hi_code = math.ceil(r_hi / RREF * CODES)
    lo_code = math.floor(r_lo / RREF * CODES)
    hdr = header_codes()
    ceiling = plant_ceiling()
    hottest = max(v["T_el_C"] for v in ceiling.values())
    rc_path = HERE / "runaway-checks.json"
    fastest = json.loads(rc_path.read_text())["margins"]["r1_fault_max_5block_rise_K_per_s"]
    climb_s = (T_IEC_TOP - T_ABS) / fastest
    bands = {
        "full_scale": {"code": 32767, "degC": round(code_to_c(32767), 1)},
        "fail_high_code": {"code": hi_code, "ohm": round(hi_code * RREF / CODES, 3),
                           "degC": round(code_to_c(hi_code), 2), "below_degC": round(code_to_c(hi_code - 1), 2)},
        "high_threshold_word_35544": {"code": HIGH_WORD >> 1, "degC": round(code_to_c(HIGH_WORD >> 1), 2)},
        "absolute_300": {"code": math.ceil(cvd(T_ABS + SELF_HEATING_K) / RREF * CODES)},
        "fail_low_code": {"code": lo_code, "ohm": round(lo_code * RREF / CODES, 3)},
    }
    checks = {
        "header_high_code_matches": hdr["RTD_C1_FAIL_HIGH_CODE"] == hi_code,
        "header_low_code_matches": hdr["RTD_C1_FAIL_LOW_CODE"] == lo_code,
        "fail_high_above_chip_rating": code_to_c(hi_code) > T_CHIP_RATING,
        "fail_high_above_hottest_uncontrolled_plant": code_to_c(hi_code) > hottest,
        "fail_high_above_high_threshold_word": hi_code > HIGH_WORD >> 1,
        "full_scale_is_a_failure": 32767 >= hi_code,
    }
    out = {"scope": __doc__.strip(),
           "R_850C_ohm": round(r_hi, 4), "R_minus200C_ohm": round(r_lo, 4),
           "RTD_C1_FAIL_HIGH_CODE": hi_code, "RTD_C1_FAIL_LOW_CODE": lo_code, "header": hdr,
           "chip_rating_C": T_CHIP_RATING, "iec60751_top_C": T_IEC_TOP,
           "plant_uncontrolled_full_power": ceiling, "plant_hottest_T_el_C": hottest,
           "fastest_fault_heating_K_per_s": fastest,
           "climb_300_to_850C_s": round(climb_s, 1), "climb_300_to_850C_conversions": int(climb_s * 50),
           "bands": bands, "checks": checks, "all_pass": all(checks.values())}
    (HERE / "sensor-fail-codes.json").write_text(json.dumps(EC.stamp(out), indent=1) + "\n")
    print(f"fail codes: open >= {hi_code} ({bands['fail_high_code']['ohm']} ohm, "
          f"{bands['fail_high_code']['degC']} degC), short <= {lo_code}; header {hdr}")
    print(f"hottest uncontrolled element (eta {max(es.ETA_SWEEP)}): {hottest} degC; chip rating {T_CHIP_RATING}; "
          f"300 -> 850 degC at {fastest} K/s: {climb_s:.0f} s")
    print("CHECKS", checks)
    print("SENSOR FAIL CODES PASS" if out["all_pass"] else "SENSOR FAIL CODES FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
