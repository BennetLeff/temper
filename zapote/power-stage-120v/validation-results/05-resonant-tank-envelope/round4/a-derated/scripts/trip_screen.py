#!/usr/bin/env python3
"""Screen solved peak currents against the pinned round-3 static trip bands."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
OUT = TASK / "outputs"
THRESHOLD_SOURCE = UNIT / "validation-results/05-resonant-tank-envelope/round3/sources/a3-thresholds.json"


def band(peak: float, low: float, high: float) -> str:
    if peak <= low:
        return "below_lowest_static_trip"
    if peak <= high:
        return "inside_static_trip_band"
    return "above_highest_static_trip"


def main() -> None:
    with (OUT / "derated_cases.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    with (UNIT / "validation-results/05-resonant-tank-envelope/round3/outputs/grid-summary.json").open() as stream:
        prior = json.load(stream)["protection_screen"]
    ct_low, ct_high = prior["ct_static_threshold_range_a"]
    shunt_low, shunt_high = prior["ocp_static_threshold_range_a"]
    if len(cases) != 270:
        raise RuntimeError("expected 270 ceiling/case rows")
    rows = []
    summary = {}
    for r in cases:
        peak = float(r["i_pk_a"])
        row = {
            "ceiling_a": r["ceiling_a"], "run_id": r["run_id"], "status": r["status"],
            "peak_a": peak, "ct_band": band(peak, ct_low, ct_high),
            "shunt_band": band(peak, shunt_low, shunt_high),
            "ct_low_a": ct_low, "ct_high_a": ct_high,
            "shunt_low_a": shunt_low, "shunt_high_a": shunt_high,
            "accepted_frequency_only": r["status"] != "needs_burst_or_phase_shift",
        }
        rows.append(row)
    with (OUT / "trip-band-screen.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for ceiling in ("42.0", "40.45"):
        selected = [r for r in rows if r["ceiling_a"] == ceiling and r["accepted_frequency_only"]]
        if len(selected) == 0:
            raise RuntimeError(f"no accepted cases at {ceiling}")
        summary[ceiling] = {
            "accepted_case_count": len(selected),
            "ct_band_counts": dict(Counter(r["ct_band"] for r in selected)),
            "shunt_band_counts": dict(Counter(r["shunt_band"] for r in selected)),
            "retained_above_shunt_low": sum(r["shunt_band"] != "below_lowest_static_trip" and r["status"] == "retained" for r in selected),
            "derated_above_shunt_low": sum(r["shunt_band"] != "below_lowest_static_trip" and r["status"] == "derated" for r in selected),
        }
    (OUT / "trip-band-summary.json").write_text(json.dumps({
        "source": str(THRESHOLD_SOURCE.relative_to(UNIT)),
        "note": "Static thresholds only; no dynamic detection or gate-off latency is modelled.",
        "ceilings": summary,
    }, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
