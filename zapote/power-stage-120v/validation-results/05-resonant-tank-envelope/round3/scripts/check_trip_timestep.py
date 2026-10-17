#!/usr/bin/env python3
"""Halve all-gates-off trip max step for the largest simulated bus peak."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope/round3"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import run  # noqa: E402


def main() -> None:
    out = TASK / "outputs/trip"
    summary = json.loads((out / "summary.json").read_text())
    worst = max(summary["cases"], key=lambda item: item["bus_peak_v"])
    original = (TASK / "scripts/trip_off.cir").read_text()
    old = ".tran 25n 500u 0 50n uic"
    if original.count(old) != 1:
        raise RuntimeError("trip deck timestep directive changed")
    deck = TASK / "scripts/trip_off_halfstep.cir"
    deck.write_text(original.replace(old, ".tran 12.5n 500u 0 25n uic"))
    result = run(deck, worst["params"], keep=out / "halfstep")
    if result["aborted"] or result["failed"] or "bus_peak" not in result["meas"]:
        raise RuntimeError(result)
    base = worst["bus_peak_v"]
    half = result["meas"]["bus_peak"]
    relative = abs(base-half)/base
    report = {"worst_tolerance_case": worst["tolerance_case"],
              "base_max_step_s": 50e-9, "half_max_step_s": 25e-9,
              "base_bus_peak_v": base, "halfstep_bus_peak_v": half,
              "relative_change": relative, "under_2_percent": relative < .02}
    (out / "timestep-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if relative >= .02:
        raise RuntimeError("trip bus peak has not converged to <2%")


if __name__ == "__main__":
    main()
