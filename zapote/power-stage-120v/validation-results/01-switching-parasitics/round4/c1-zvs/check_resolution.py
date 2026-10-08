#!/usr/bin/env python3
"""Halve ngspice max step on C1 bus/timing/L extremes and a known A1 boundary."""
from __future__ import annotations

import argparse
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_c1.py"


def load_c1():
    spec = importlib.util.spec_from_file_location("c1_resolution_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def choose_currents(row: dict) -> tuple[float, ...]:
    if row["minimum_bracket_a"]:
        return tuple(row["minimum_bracket_a"])
    if row["status"] == "no_pass_through_100a":
        return (40.0, 100.0)
    return (0.5, 40.0)


def check(a1, row: dict, current: float) -> dict:
    bus, direction = row["bus_v"], row["direction"]
    dt, scale = row["deadtime_ns"], row["reference_l_scale"]
    coarse = a1.run_case(bus, direction, dt, current, scale, 0.2)
    fine = a1.run_case(bus, direction, dt, current, scale, coarse["max_step_ns"] / 2)
    relative = {}
    for key in ("peak_die_vds_l_v", "peak_die_vds_h_v", "incoming_die_vds_pre20_max_abs_v"):
        x, y = coarse[key], fine[key]
        relative[key] = abs(x - y) / max(abs(y), 1e-12)
    return {"id": row["id"], "bus_v": bus, "direction": direction,
            "rdt_kohm": row["rdt_kohm"], "timing_corner": row["timing_corner"],
            "deadtime_ns": dt, "reference_l_scale": scale, "current_a": current,
            "coarse_step_ns": coarse["max_step_ns"], "fine_step_ns": fine["max_step_ns"],
            "coarse_zvs": coarse["zvs_20ns_5pct"], "fine_zvs": fine["zvs_20ns_5pct"],
            "zvs_flip": coarse["zvs_20ns_5pct"] != fine["zvs_20ns_5pct"],
            "relative_changes": relative, "peak_under_2pct": max(relative.values()) < 0.02,
            "coarse_waveform": coarse["waveform"], "fine_waveform": fine["waveform"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        raise ValueError("ngspice concurrency must be 1 to 4")
    c1 = load_c1()
    a1 = c1.load_a1()
    payload = json.loads((HERE / "zvs_thresholds_c1.json").read_text())
    selected = []
    for row in payload["thresholds"]:
        edge_bus = row["bus_v"] in (10, 198) and row["reference_l_scale"] == 1.0
        l_extreme = (row["timing_corner"] == "typ" and row["bus_v"] in (10, 198)
                     and row["reference_l_scale"] in (0.5, 3.0))
        known_boundary = (row["rdt_kohm"] == 51 and row["timing_corner"] == "typ"
                          and row["bus_v"] == 170 and row["direction"] == 1
                          and row["reference_l_scale"] == 1.0)
        if edge_bus or l_extreme or known_boundary:
            for current in choose_currents(row):
                selected.append((row, current))
    path = HERE / "timestep_checks.json"
    results = json.loads(path.read_text()) if path.exists() else []
    done = {(r["id"], r["current_a"]) for r in results}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(check, a1, row, current): (row, current)
                   for row, current in selected if (row["id"], current) not in done}
        for future in as_completed(futures):
            record = future.result()
            results.append(record)
            results.sort(key=lambda r: (r["id"], r["current_a"]))
            path.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
            print("CHECK", len(results), "/", len(selected), record["id"], record["current_a"],
                  "flip" if record["zvs_flip"] else "stable", "peak delta",
                  max(record["relative_changes"].values()), flush=True)
    print("CHECKS COMPLETE", len(results), "peak failures", sum(not r["peak_under_2pct"] for r in results),
          "classification flips", sum(r["zvs_flip"] for r in results), flush=True)


if __name__ == "__main__":
    main()
