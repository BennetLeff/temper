#!/usr/bin/env python3
"""Report the actual timestep check; an aborted fine run cannot validate coarse data."""

from pathlib import Path
import csv
import gzip
import json

HERE = Path(__file__).resolve().parent


def main():
    tags = ["v170-r2-e1.06-f60000-s2-c48", "v170-r2-e1.06-f60000-s0.5-c48"]
    rows = []
    for tag in tags:
        path = HERE / "periodic-runs" / (tag + ".json")
        if not path.exists():
            result = {"status": "PENDING", "missing": tag}
            break
        rows.append(json.loads(path.read_text()))
    else:
        if any(row["status"] != "complete" for row in rows):
            result = {
                "status": "INDETERMINATE",
                "cases": [{key: r[key] for key in ("tag", "status", "aborted")} for r in rows],
            }
        else:
            margins = json.loads((HERE / "margin-results.json").read_text())
            comparisons = []
            for old in (r for r in margins if r["case"] == tags[0]):
                new = next(
                    r for r in margins if r["case"] == tags[1] and r["scenario"] == old["scenario"]
                )
                waves = []
                for tag in tags:
                    with gzip.open(
                        HERE / "spectra" / (tag + "-" + old["scenario"] + ".csv.gz"), "rt"
                    ) as stream:
                        waves.append(
                            {
                                float(r["Hz"]): max(float(r["L_rms_dBuV"]), float(r["N_rms_dBuV"]))
                                for r in csv.DictReader(stream)
                            }
                        )
                comparisons.append(
                    {
                        "scenario": old["scenario"],
                        "coarse_min_AV_dB": old["AV_line_headroom_dB"],
                        "fine_min_AV_dB": new["AV_line_headroom_dB"],
                        "min_AV_change_dB": new["AV_line_headroom_dB"] - old["AV_line_headroom_dB"],
                        "fine_minus_coarse_at_240k_dB": waves[1][240e3] - waves[0][240e3],
                        "max_abs_line_change_150k_to_1M_dB": max(
                            abs(waves[1][f] - v) for f, v in waves[0].items() if f <= 1e6
                        ),
                        "max_abs_line_change_full_band_dB": max(
                            abs(waves[1][f] - v) for f, v in waves[0].items()
                        ),
                    }
                )
            result = {
                "status": "COMPARED_NOT_A_PHYSICAL_BOUND",
                "cases": tags,
                "power_W": [r["mean_input_power_estimate_W"] for r in rows],
                "comparisons": comparisons,
            }
    (HERE / "step-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
