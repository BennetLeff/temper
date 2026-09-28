#!/usr/bin/env python3
"""Re-bracket any A1 ZVS threshold whose classification flips at 0.1 ns."""

from __future__ import annotations

import json
from pathlib import Path

from run_a1 import run_case

HERE = Path(__file__).resolve().parent


def fine_bracket(bus: int, direction: int, deadtime: int, scale: float,
                 coarse: list[float]) -> tuple[float, float]:
    low, high = coarse
    width = high-low
    for _ in range(10):
        if not run_case(bus, direction, deadtime, low, scale, 0.1)["zvs_20ns_5pct"]:
            break
        high, low = low, max(1.0, low-width)
        width *= 2
    else:
        raise RuntimeError("fine-step lower non-ZVS bracket not found")
    for _ in range(10):
        if run_case(bus, direction, deadtime, high, scale, 0.1)["zvs_20ns_5pct"]:
            break
        low, high = high, high+width
        width *= 2
    else:
        raise RuntimeError("fine-step upper ZVS bracket not found")
    for _ in range(16):
        if high-low <= 0.5:
            break
        mid = (low+high)/2
        if run_case(bus, direction, deadtime, mid, scale, 0.1)["zvs_20ns_5pct"]:
            high = mid
        else:
            low = mid
    if not (high-low <= 0.5 and
            not run_case(bus, direction, deadtime, low, scale, 0.1)["zvs_20ns_5pct"] and
            run_case(bus, direction, deadtime, high, scale, 0.1)["zvs_20ns_5pct"]):
        raise RuntimeError("fine-step bracket invalid")
    return low, high


def main() -> None:
    checks = json.loads((HERE / "timestep_checks.json").read_text())
    flipped = [row for row in checks if row["purpose"] == "threshold_bracket"
               and row["coarse_zvs"] != row["fine_zvs"]]
    payload = json.loads((HERE / "zvs_threshold.json").read_text())
    rows = payload["thresholds"]
    by_key = {(row["bus_v"], row["direction"], row["deadtime_ns"],
               row["board_l_scale"]): row for row in rows}
    refinements = []
    for key in sorted({(row["bus_v"], row["direction"], row["deadtime_ns"],
                       row["board_l_scale"]) for row in flipped}):
        row = by_key[key]
        if row["status"] != "bracketed":
            raise RuntimeError(f"cannot refine non-bracketed threshold {key}")
        if row.get("max_step_ns") == 0.1:
            refinements.append({"key": key,
                                "coarse_bracket_a": row["coarse_0p2ns_bracket_a"],
                                "fine_bracket_a": row["bracket_a"],
                                "fine_threshold_a": row["threshold_a"]})
            continue
        coarse_bracket = row["bracket_a"]
        low, high = fine_bracket(*key, coarse_bracket)
        row["coarse_0p2ns_threshold_a"] = row["threshold_a"]
        row["coarse_0p2ns_bracket_a"] = coarse_bracket
        row["threshold_a"] = (low+high)/2
        row["bracket_a"] = [low, high]
        row["half_width_a"] = (high-low)/2
        row["max_step_ns"] = 0.1
        row["timestep_refinement_cause"] = "0.2/0.1 ns ZVS classification flip at strict 5% diagnostic boundary"
        refinements.append({"key": key, "coarse_bracket_a": coarse_bracket,
                            "fine_bracket_a": [low, high],
                            "fine_threshold_a": row["threshold_a"]})
    payload["thresholds"] = rows
    payload["timestep_refined_tuple_count"] = len(refinements)
    (HERE / "zvs_threshold.json").write_text(json.dumps(payload, indent=2) + "\n")
    (HERE / "timestep_refined_thresholds.json").write_text(json.dumps(refinements, indent=2) + "\n")
    print(json.dumps(refinements, indent=2))


if __name__ == "__main__":
    main()
