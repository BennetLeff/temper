#!/usr/bin/env python3
"""Correct cases whose 25 ns peak crossed the provisional current ceiling."""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
ROUND3 = UNIT / "validation-results/05-resonant-tank-envelope/round3"
OUT = TASK / "outputs"
sys.path.insert(0, str(TASK / "scripts"))
from find_freq import create_case  # noqa: E402


def main() -> None:
    checks = json.loads((OUT / "numerical-checks.json").read_text())
    failures = [
        {"ceiling_a": item["ceiling_a"], "run_id": item["run_id"],
         "refined_i_pk_a": item["metrics"]["i_pk"]["refined"]}
        for item in checks["halfstep"]
        if item["ceiling_a"] - item["metrics"]["i_pk"]["refined"] < .05
    ]
    with (ROUND3 / "outputs/cases.csv").open(newline="") as stream:
        baseline = {row["run_id"]: row for row in csv.DictReader(stream)}
    prior_file = OUT / "numerical-corrections.json"
    corrected = json.loads(prior_file.read_text())["cases"] if prior_file.is_file() else []
    new_count = 0
    for failure in failures:
        ceiling = float(failure["ceiling_a"])
        run_id = failure["run_id"]
        original = OUT / "runs" / f"{ceiling:g}a" / run_id
        archive = OUT / "runs/superseded-numerical" / f"{ceiling:g}a" / run_id
        if archive.exists():
            current = json.loads((original / "case.json").read_text())["row"]
            if current["ceiling_margin_a"] >= .10:
                continue
            raise RuntimeError(f"earlier numerical archive exists but current case is not safely corrected: {archive}")
        archive.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads((original / "case.json").read_text())["row"]
        shutil.move(str(original), str(archive))
        create_case(baseline[run_id], ceiling, target_margin_a=.12)
        new = json.loads((original / "case.json").read_text())["row"]
        if new["status"] != "derated" or not .10 <= new["ceiling_margin_a"] <= .17:
            raise RuntimeError(f"corrected case did not preserve a safe ceiling margin: {run_id}: {new}")
        corrected.append({"ceiling_a": ceiling, "run_id": run_id,
                          "reason": "25 ns peak within 0.05 A of ceiling; numerical guard",
                          "prior_status": old["status"],
                          "old_frequency_hz": old["frequency_hz"],
                          "old_i_pk_50ns_a": old["i_pk_a"],
                          "old_i_pk_25ns_a": failure["refined_i_pk_a"],
                          "new_frequency_hz": new["frequency_hz"],
                          "new_i_pk_50ns_a": new["i_pk_a"],
                          "raw_archive": str(archive.relative_to(TASK))})
        new_count += 1
        prior_file.write_text(json.dumps({"corrected_count": len(corrected),
            "new_corrected_count": new_count, "cases": corrected}, indent=2, allow_nan=False) + "\n")
        print(json.dumps(corrected[-1]), flush=True)
    (OUT / "numerical-corrections.json").write_text(json.dumps({
        "corrected_count": len(corrected), "new_corrected_count": new_count, "cases": corrected,
    }, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
