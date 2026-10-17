#!/usr/bin/env python3
"""Summarize retained tank cases and a conditional isolated-capacitor bleed."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]


def main() -> None:
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError("No retained tank cases")
    for row in rows:
        if row["status"] != "frequency-control":
            raise RuntimeError(f"Partial summary assumes achieved target: {row}")
    peak_current = max(rows, key=lambda row: float(row["i_pk_a"]))
    peak_voltage = max(rows, key=lambda row: float(row["vc_pk_v"]))
    peak_cap_current = max(rows, key=lambda row: float(row["c21_i_rms_a"]))
    peak_resistor_power = max(rows, key=lambda row: float(row["bleed_each_p_avg_w"]))
    v0 = float(peak_voltage["vc_pk_v"])
    # This assumes the coil current and all bridge paths are already absent
    # when the bleed begins. It is not a trip ring-down simulation.
    tau_nom_s = 4 * 470_000 * 0.54e-6
    tau_high_s = tau_nom_s * 1.01 * 1.10
    bleed = {
        "initial_voltage_v": v0,
        "threshold_voltage_v": 60,
        "nominal_tau_s": tau_nom_s,
        "nominal_time_to_60v_s": tau_nom_s * math.log(v0 / 60),
        "high_r_high_c_tau_s": tau_high_s,
        "high_r_high_c_time_to_60v_s": tau_high_s * math.log(v0 / 60),
        "scope": "isolated capacitor through R22-R25 only; no coil/diode ring-down",
    }
    summary = {
        "retained_case_count": len(rows),
        "maximum_tank_peak_current": {
            "run_id": peak_current["run_id"],
            "ampere": float(peak_current["i_pk_a"]),
            "ct_88a_margin_a": 88 - float(peak_current["i_pk_a"]),
        },
        "maximum_capacitor_peak_voltage": {
            "run_id": peak_voltage["run_id"], "volt": v0,
            "energy_j": float(peak_voltage["c_energy_pk_j"]),
            "each_bleed_resistor_peak_v": float(peak_voltage["bleed_each_v_pk_v"]),
        },
        "maximum_c21_c22_rms_current": {
            "run_id": peak_cap_current["run_id"],
            "ampere": float(peak_cap_current["c21_i_rms_a"]),
            "manufacturer_reference_a_at_70c_100khz": 10.3,
            "actual_frequency_rating": None,
        },
        "maximum_bleed_resistor_power": {
            "run_id": peak_resistor_power["run_id"],
            "watt": float(peak_resistor_power["bleed_each_p_avg_w"]),
            "half_yageo_70c_rating_w": 0.125,
        },
        "bleed_only": bleed,
    }
    (TASK / "outputs/partial-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
