#!/usr/bin/env python3
"""Audit the completed C1 reference handback and its saved local raw cases."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    payload = json.loads((HERE / "zvs_thresholds_c1.json").read_text())
    rows = payload["thresholds"]
    keys = [(r["rdt_kohm"], r["timing_corner"], r["bus_v"], r["direction"], r["reference_l_scale"]) for r in rows]
    require(len(rows) == len(set(keys)) == 140, "threshold grid must contain 140 unique rows")
    require({r["bus_v"] for r in rows} == {10, 30, 60, 90, 120, 170, 198}, "missing bus")
    require({r["direction"] for r in rows} == {0, 1}, "missing direction")
    require(sum(r["reference_l_scale"] == 1 for r in rows) == 84, "missing six-timing base grid")
    require(sum(r["reference_l_scale"] != 1 for r in rows) == 56, "missing typical L sensitivity")
    statuses = Counter(r["status"] for r in rows)
    for row in rows:
        if row["minimum_bracket_a"] is not None:
            lo, hi = row["minimum_bracket_a"]
            require(0 < hi - lo <= 0.5 + 1e-9, f"wide bracket: {row['id']}")
            require(row["status"] == "bracketed", f"unqualified bracket: {row['id']}")
        require(row["bus_v"] >= 10, "below-domain bus")
    physical = json.loads((HERE / "physical_thresholds_10v.json").read_text())["rows"]
    require(len(physical) == 20, "missing 10 V supplemental rows")
    for row in physical:
        require(row["bus_v"] == 10, "supplemental row outside 10 V")
        if row["physical_commutation_bracket_a"]:
            lo, hi = row["physical_commutation_bracket_a"]
            require(0 < hi - lo <= 0.5 + 1e-9, f"wide physical bracket: {row['id']}")
    with (HERE / "outputs/waveform_metrics.csv").open(newline="") as handle:
        cases = list(csv.DictReader(handle))
    require(cases, "no waveform metrics")
    for case in cases:
        require((HERE / case["case_json"]).is_file(), f"missing case JSON {case['case_json']}")
        require((HERE / case["waveform"]).is_file(), f"missing waveform {case['waveform']}")
    checks = json.loads((HERE / "timestep_checks.json").read_text())
    require(checks, "no half-step checks")
    initial_peak_failures = [x for x in checks if not x["peak_under_2pct"]]
    peak_failures = [x for x in checks if not x.get("peak_converged_under_2pct", x["peak_under_2pct"])]
    source_manifest = json.loads((HERE / "source_hashes.json").read_text())
    for name, source in source_manifest.items():
        path = POWER / source["path"]
        require(path.is_file(), f"missing source {name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"], f"source drift: {name}")
    require((HERE / "smoke-test.txt").read_text().rstrip().endswith("SMOKE PASS"), "kit smoke did not pass")
    require("3327/3327 files verified" in (HERE / "raw-evidence-check.txt").read_text(), "raw evidence did not verify")
    print(json.dumps({"thresholds": len(rows), "status_counts": statuses,
                      "physical_10v_rows": len(physical), "waveform_cases": len(cases),
                      "half_step_checks": len(checks), "initial_half_step_peak_failures": len(initial_peak_failures),
                      "unresolved_half_step_peak_failures": len(peak_failures),
                      "half_step_classification_flips": sum(x["zvs_flip"] for x in checks),
                      "sources_verified": len(source_manifest)}, indent=2))
    require(not peak_failures, "half-step die-voltage peak changed >=2%")
    print("AUDIT PASS")


if __name__ == "__main__":
    main()
