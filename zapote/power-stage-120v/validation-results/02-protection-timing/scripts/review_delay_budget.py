#!/usr/bin/env python3
"""Compare task 02 SPICE front ends with the retained native-13 delay sums.

This is a review of model outputs, not an end-to-end maximum: the comparator
overdrive curve and task 01's MOSFET gate turn-off are still unresolved.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs"


def main() -> None:
    old = json.loads((OUTPUT / "detector_chain.json").read_text())["chain_improved_R14_100_R16_1k"]
    sweep = json.loads((OUTPUT / "frontend_sweep.json").read_text())
    rows = []
    summary = {}
    for path, prior_analog_count, analog_key in (
        ("tank_ct", 4, "detection_delay_ns"),
        ("shunt_ocp", 2, "corner_threshold_to_detection_ns"),
    ):
        links = old[path]["links"]
        old_analog = sum(link["ns"] for link in links[:prior_analog_count])
        digital = links[prior_analog_count:-1]
        gate = links[-1]
        assert "gate discharge" in gate["link"] and gate["ns"] == 150.0
        subtotal = sum(link["ns"] for link in digital)
        expected = (old_analog + subtotal + gate["ns"]) / 1000
        if abs(expected - old[path]["total_us"]) > 0.001:
            raise ValueError(f"old {path} sum does not reproduce: {expected} vs {old[path]['total_us']}")
        sample = sweep["ct" if path == "tank_ct" else "ocp"]
        # For the shunt, use the specified ±4 mV corners only. ±5 mV rows
        # remain in the raw sweep as runbook sensitivity cases.
        if path == "shunt_ocp":
            sample = [row for row in sample if abs(float(row["params"]["VOS"])) == 0.004]
        front = [row[analog_key] for row in sample]
        summary[path] = {"old_analog_ns": old_analog, "downstream_to_driver_output_ns": subtotal,
                         "old_gate_assumption_ns": gate["ns"], "old_total_us": old[path]["total_us"],
                         "spice_frontend_min_ns": min(front), "spice_frontend_max_ns": max(front),
                         "model_crossing_to_driver_output_min_ns": min(front) + subtotal,
                         "model_crossing_to_driver_output_max_ns": max(front) + subtotal,
                         "final_gate_off": "BLOCKED: task 01 gate waveform and small-overdrive comparator upper bound"}
        rows.append({"path": path, "link": "analog front end, SPICE model", "source": "frontend_sweep.json",
                     "min_ns": round(min(front), 3), "max_ns": round(max(front), 3)})
        for link in digital:
            rows.append({"path": path, "link": link["link"], "source": "detector_chain.json / datasheets.json",
                         "min_ns": "", "max_ns": link["ns"]})
        rows.append({"path": path, "link": "MOSFET gate discharge", "source": "task 01 required; old 150 ns is assumed",
                     "min_ns": "", "max_ns": "BLOCKED"})
    with (OUTPUT / "delay_budget.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=("path", "link", "source", "min_ns", "max_ns"),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (OUTPUT / "chain_review.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
