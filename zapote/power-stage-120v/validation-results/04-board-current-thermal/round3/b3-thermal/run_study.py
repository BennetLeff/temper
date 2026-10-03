#!/usr/bin/env python3
"""Rerun the bounded B3 strip, BUS_P path and partial A6 experiments."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
GEOM = HERE / "inputs/native15-all-copper.json.gz"
A6 = HERE / "inputs/a6-board-heat-sources.json"


def execute(*args: str) -> dict:
    result = subprocess.run([sys.executable, str(HERE / "thermal.py"), *args],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    selftest = execute("--selftest")
    (OUT / "selftest.json").write_text(json.dumps(selftest, indent=2)+"\n")
    jobs = [
        ("bus_dc_q2_h10_p2", "bus_dc_q2-p0125-pl18", 2, 10, False),
        ("bus_dc_q2_h10_p1", "bus_dc_q2-p0125-pl18", 1, 10, False),
        ("bus_dc_q2_h10_p0p5", "bus_dc_q2-p0125-pl18", 0.5, 10, False),
        ("bus_dc_q2_h25_p2", "bus_dc_q2-p0125-pl18", 2, 25, False),
        ("bus_dc_q2_h25_p1", "bus_dc_q2-p0125-pl18", 1, 25, False),
        ("a6_partial_nominal_h10_p2", "none", 2, 10, True),
        ("a6_partial_nominal_h10_p1", "none", 1, 10, True),
        ("a6_partial_nominal_h25_p2", "none", 2, 25, True),
    ]
    results = {}
    for name, case, pitch, h, use_a6 in jobs:
        path = OUT / f"{name}.json"
        options = ["--geometry", str(GEOM), "--case", case, "--pitch-mm", str(pitch),
                   "--h", str(h), "--output", str(path)]
        if use_a6:
            options += ["--a6-heat", str(A6), "--a6-mode", "nominal"]
        execute(*options)
        result = json.loads(path.read_text())
        results[name] = {"peak": result["peak"], "balance": result["balance"],
                         "source_w": result["balance"]["source_w"],
                         "receipt": path.name, "image": path.with_suffix(".png").name}
        print(f"{name}: {result['peak']['temperature_c']:.3f} C, "
              f"balance {result['balance']['balance_w']:.3g} W", flush=True)
    (OUT / "summary.json").write_text(json.dumps({
        "status": "conditional_only_no_operating_temperature_verdict",
        "selftest": selftest, "runs": results,
        "bus_h10_peak_mesh_span_k": max(results[x]["peak"]["rise_k"] for x in
                                     ("bus_dc_q2_h10_p2", "bus_dc_q2_h10_p1", "bus_dc_q2_h10_p0p5"))
                                - min(results[x]["peak"]["rise_k"] for x in
                                      ("bus_dc_q2_h10_p2", "bus_dc_q2_h10_p1", "bus_dc_q2_h10_p0p5")),
        "a6_h10_peak_mesh_span_k": abs(results["a6_partial_nominal_h10_p2"]["peak"]["rise_k"]
                                      - results["a6_partial_nominal_h10_p1"]["peak"]["rise_k"])
    }, indent=2)+"\n")


if __name__ == "__main__":
    main()
