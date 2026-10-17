#!/usr/bin/env python3
"""Quantify the 20 mV condition without claiming ramp timing is guaranteed.

TLV3201 SBOS561C section 6.6 tests a step at 20 mV overdrive and CL=15 pF.
Its 55 ns maximum is *not* a general bound for an arbitrary moving input.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"


def shunt_crossing(slope: float, vos: float, overdrive: float) -> float:
    r32 = r33 = 10_000.0
    r34, r35 = 10_500.0, 10_000.0
    ref = 2.5
    tau = (r32 * r33 / (r32 + r33)) * 100e-12
    initial = ref * r33 / (r32 + r33)
    thresh = ref * r35 / (r34 + r35)
    gain = (r32 / (r32 + r33)) * .001  # 0.5 mV/A, from actual R32/R33/R5

    def differential(t: float) -> float:
        return initial - gain * slope * (t - tau * (1 - math.exp(-t / tau))) - thresh - vos

    lo, hi = 0.0, max(150 / slope, 1e-6)
    while differential(hi) > -overdrive:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        if differential(mid) > -overdrive:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> None:
    ct = json.loads((OUT / "ct_sweep.json").read_text())["rows"]
    fields = ("path", "freq_hz", "i0_a", "slope_a_per_s", "offset_v", "model_delay_s",
              "nominal_input_trip_s", "input_20mv_s", "time_to_20mv_after_nominal_s",
              "conditional_output_s", "conditional_primary_current_a", "conditional_current_abs_a",
              "model_output_s", "model_current_a", "classification")
    rows = []
    for item in ct:
        p = item["params"]
        t20 = item["t_20mv_overdrive"]
        conditional_output = t20 + 55e-9 + 4.5e-9  # U13 OR tpd retained separately
        current = min(float(p["I0"]) + float(p["SLOPE"]) * conditional_output, 150) * math.sin(
            6.283185307 * float(p["FREQ"]) * conditional_output)
        nominal_trip = min(item["t_ip_trip"], item["t_in_trip"])
        rows.append(dict(path="ct", freq_hz=p["FREQ"], i0_a=p["I0"],
                         slope_a_per_s=p["SLOPE"], offset_v=p["VOS"],
                         model_delay_s=p["TPD"], nominal_input_trip_s=nominal_trip,
                         input_20mv_s=t20,
                         time_to_20mv_after_nominal_s=t20 - nominal_trip,
                         conditional_output_s=conditional_output,
                         conditional_primary_current_a=current,
                         conditional_current_abs_a=abs(current),
                         model_output_s=item["t_or"],
                         model_current_a=item["primary_at_detection_a"],
                         classification="conditional_step_test_extrapolation_not_guaranteed_for_ramp"))
    for slope in (1e6, 3e6, 1e7, 1e8, 1e9):
        for vos in (-.005, -.004, 0.0, .004, .005):
            # Static nominal-R threshold from actual divider with comparator offset.
            nominal_trip_a = 60.97560975609761 - 2000 * vos
            nominal_trip_t = nominal_trip_a / slope
            t0 = shunt_crossing(slope, vos, 0)
            t20 = shunt_crossing(slope, vos, .020)
            output = t20 + 55e-9
            rows.append(dict(path="shunt", freq_hz="", i0_a=0,
                             slope_a_per_s=slope, offset_v=vos,
                             model_delay_s=55e-9, nominal_input_trip_s=nominal_trip_t,
                             input_20mv_s=t20,
                             time_to_20mv_after_nominal_s=t20 - nominal_trip_t,
                             conditional_output_s=output,
                             conditional_primary_current_a=slope * output,
                             conditional_current_abs_a=slope * output,
                             model_output_s=t0 + 55e-9,
                             model_current_a=slope * (t0 + 55e-9),
                             classification="conditional_step_test_extrapolation_not_guaranteed_for_ramp"))
    with (OUT / "overdrive_bound.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"ct_rows": len(ct), "shunt_rows": len(rows) - len(ct),
               "ct_conditional_max_abs_a": max(r["conditional_current_abs_a"] for r in rows if r["path"] == "ct"),
               "shunt_conditional_max_a": max(r["conditional_current_abs_a"] for r in rows if r["path"] == "shunt"),
               "status": "20 mV plus 55 ns is conditional only: datasheet uses 20 mV step and 15 pF load, not arbitrary ramp"}
    (OUT / "overdrive_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
