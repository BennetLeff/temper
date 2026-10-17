#!/usr/bin/env python3
"""Refine C1 half-step peak checks that initially changed by at least 2%."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_c1.py"
METRICS = ("peak_die_vds_l_v", "peak_die_vds_h_v", "incoming_die_vds_pre20_max_abs_v")


def load_c1():
    spec = importlib.util.spec_from_file_location("c1_refine_resolution", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    c1 = load_c1()
    a1 = c1.load_a1()
    path = HERE / "timestep_checks.json"
    rows = json.loads(path.read_text())
    for row in rows:
        if row["peak_under_2pct"]:
            row["peak_converged_under_2pct"] = True
            continue
        if row.get("peak_converged_under_2pct"):
            continue
        bus, direction, dt, current, scale = (row["bus_v"], row["direction"],
                                               row["deadtime_ns"], row["current_a"],
                                               row["reference_l_scale"])
        prior = a1.run_case(bus, direction, dt, current, scale, row["fine_step_ns"])
        extra = []
        for _ in range(3):
            finer = a1.run_case(bus, direction, dt, current, scale, prior["max_step_ns"] / 2)
            relative = {key: abs(prior[key] - finer[key]) / max(abs(finer[key]), 1e-12)
                        for key in METRICS}
            extra.append({"prior_step_ns": prior["max_step_ns"], "finer_step_ns": finer["max_step_ns"],
                          "relative_changes": relative, "zvs_flip": prior["zvs_20ns_5pct"] != finer["zvs_20ns_5pct"],
                          "finer_waveform": finer["waveform"]})
            prior = finer
            if max(relative.values()) < 0.02:
                break
        row["further_checks"] = extra
        row["peak_converged_under_2pct"] = max(extra[-1]["relative_changes"].values()) < 0.02
        path.write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
        print(row["id"], current, "first change", max(row["relative_changes"].values()),
              "final change", max(extra[-1]["relative_changes"].values()),
              "converged", row["peak_converged_under_2pct"], flush=True)
    if not all(row["peak_converged_under_2pct"] for row in rows):
        raise RuntimeError("a half-step peak check remains unconverged")
    print("REFINEMENT PASS")


if __name__ == "__main__":
    main()
