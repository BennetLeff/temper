#!/usr/bin/env python3
"""Derive pan and coil heat from the saved ideal-tank .meas RMS currents."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
OUT = TASK / "outputs"


def write_csv(name: str, fields: tuple[str, ...], rows: list[dict]) -> None:
    with (OUT / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with (OUT / "derated_cases.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    if len(cases) != 270:
        raise RuntimeError(f"expected 270 rows, got {len(cases)}")
    individual = []
    groups = defaultdict(list)
    for r in cases:
        current2 = float(r["i_rms_a"])**2
        frequency = float(r["frequency_hz"])
        pan_ohm = float(r["r_pan_40_ohm"]) * math.sqrt(frequency/40_000)
        coil_ohm = float(r["r_coil_ohm"])
        pan_w = current2 * pan_ohm
        coil_w = current2 * coil_ohm
        total = float(r["p_avg_w"])
        if abs((pan_w + coil_w) - total) > max(2., total*.01):
            raise RuntimeError(f"pan + coil split disagrees with ngspice .meas: {r['run_id']}")
        row = {
            "ceiling_a": r["ceiling_a"], "run_id": r["run_id"],
            "pan": r["pan"], "corner": r["corner"], "vrms_v": r["vrms_v"],
            "target_total_resistive_w": r["target_w"], "status": r["status"],
            "frequency_hz": frequency,
            "delivered_total_resistive_w": total if r["status"] != "needs_burst_or_phase_shift" else "",
            "delivered_pan_heating_w": pan_w if r["status"] != "needs_burst_or_phase_shift" else "",
            "delivered_coil_copper_w": coil_w if r["status"] != "needs_burst_or_phase_shift" else "",
            "total_shortfall_w": float(r["target_w"]) - total if r["status"] != "needs_burst_or_phase_shift" else "",
            "frequency_only_60khz_diagnostic_w": total if r["status"] == "needs_burst_or_phase_shift" else "",
        }
        individual.append(row)
        groups[(r["ceiling_a"], r["pan"], r["vrms_v"], r["target_w"])].append(row)
    write_csv("power-breakdown.csv", tuple(individual[0]), individual)
    table = []
    for (ceiling, pan, vrms, request), group in sorted(groups.items()):
        if len(group) != 3:
            raise RuntimeError("each pan/line/request requires three L/R corners")
        accepted = [r for r in group if r["status"] != "needs_burst_or_phase_shift"]
        table.append({
            "ceiling_a": ceiling, "pan": pan, "vrms_v": vrms,
            "target_total_resistive_w": request, "corner_count": 3,
            "retained": sum(r["status"] == "retained" for r in group),
            "derated": sum(r["status"] == "derated" for r in group),
            "needs_burst_or_phase_shift": sum(r["status"] == "needs_burst_or_phase_shift" for r in group),
            "min_total_resistive_w": min(r["delivered_total_resistive_w"] for r in accepted) if accepted else "",
            "mean_total_resistive_w": sum(r["delivered_total_resistive_w"] for r in accepted)/len(accepted) if accepted else "",
            "max_total_resistive_w": max(r["delivered_total_resistive_w"] for r in accepted) if accepted else "",
            "min_pan_heating_w": min(r["delivered_pan_heating_w"] for r in accepted) if accepted else "",
            "mean_pan_heating_w": sum(r["delivered_pan_heating_w"] for r in accepted)/len(accepted) if accepted else "",
            "max_pan_heating_w": max(r["delivered_pan_heating_w"] for r in accepted) if accepted else "",
            "mean_coil_copper_w": sum(r["delivered_coil_copper_w"] for r in accepted)/len(accepted) if accepted else "",
        })
    write_csv("delivered-power.csv", tuple(table[0]), table)
    print(json.dumps({"case_count": len(individual), "table_rows": len(table)}))


if __name__ == "__main__":
    main()
