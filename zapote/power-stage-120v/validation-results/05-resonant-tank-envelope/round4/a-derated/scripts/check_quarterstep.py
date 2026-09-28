#!/usr/bin/env python3
"""Check near-ceiling and stress-extremum cases with a 12.5 ns max step."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
KIT = UNIT / "validation-plan/sim-kit"
OUT = TASK / "outputs"
sys.path.insert(0, str(KIT / "common"))
from check_numerics import verify_numerical_cache  # noqa: E402
from run_ngspice import run  # noqa: E402


def main() -> None:
    with (OUT / "derated_cases.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    prior = json.loads((OUT / "numerical-checks.json").read_text())
    half = {(r["ceiling_a"], r["run_id"]): r for r in prior["halfstep"]}
    if len(rows) != 270 or len(half) != 270 or prior["refined_above_ceiling"]:
        raise RuntimeError("the final 270-case 25 ns check must pass first")
    extrema = set()
    for ceiling in (42., 40.45):
        group = [r for r in rows if float(r["ceiling_a"]) == ceiling]
        for metric in ("i_pk_a", "vc_pk_v", "vc_rms_v", "i_rms_a"):
            r = max(group, key=lambda x: float(x[metric]))
            extrema.add((ceiling, r["run_id"]))
    selection = []
    for r in rows:
        key = (float(r["ceiling_a"]), r["run_id"])
        i25 = half[key]["metrics"]["i_pk"]["refined"]
        if key in extrema or key[0] - i25 < .18:
            selection.append(r)
    checks = []
    for index, r in enumerate(selection, 1):
        ceiling = float(r["ceiling_a"])
        run_id = r["run_id"]
        key = (ceiling, run_id)
        params = {"VRMS": r["vrms_v"], "FREQ": r["frequency_hz"],
                  "LLOAD": r["l_load_h"], "RPAN40": r["r_pan_40_ohm"],
                  "RCOIL": r["r_coil_ohm"]}
        folder = OUT / "runs/numerical/quarterstep" / f"{ceiling:g}a" / run_id / f"{float(r['frequency_hz']):.6f}hz"
        saved = folder / "result.json"
        if saved.is_file():
            result = json.loads(saved.read_text())
            verify_numerical_cache(folder, TASK / "scripts/tank-quarterstep.cir", params, result)
        else:
            result = run(TASK / "scripts/tank-quarterstep.cir", params, keep=folder)
            (folder / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
            saved.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        if result["aborted"] or result["failed"]:
            raise RuntimeError(f"invalid 12.5 ns result {folder}")
        i25 = half[key]["metrics"]["i_pk"]["refined"]
        i12 = result["meas"]["i_pk"]
        v25 = half[key]["metrics"]["vc_pk"]["refined"]
        v12 = result["meas"]["vc_pk"]
        row = {"ceiling_a": ceiling, "run_id": run_id,
               "is_extremum": key in extrema,
               "nominal_i_pk_a": float(r["i_pk_a"]),
               "i_pk_25ns_a": i25, "i_pk_12_5ns_a": i12,
               "i_pk_12_5ns_margin_a": ceiling - i12,
               "i_pk_relative_change_25_to_12_5": abs(i12-i25)/max(i25, 1e-12),
               "vc_pk_25ns_v": v25, "vc_pk_12_5ns_v": v12,
               "vc_pk_relative_change_25_to_12_5": abs(v12-v25)/max(v25, 1e-12)}
        checks.append(row)
        if i12 > ceiling or row["i_pk_relative_change_25_to_12_5"] >= .02 or row["vc_pk_relative_change_25_to_12_5"] >= .02:
            (OUT / "quarterstep-failure.json").write_text(json.dumps(row, indent=2) + "\n")
            raise RuntimeError(f"12.5 ns ceiling or peak convergence failure: {row}")
        if index % 25 == 0:
            print(json.dumps({"quarterstep_progress": index, "of": len(selection)}), flush=True)
    report = {"selected_case_count": len(selection),
              "selection": "all cases within 0.18 A of ceiling at 25 ns plus i_pk/vc_pk/vc_rms/i_rms extrema for both ceilings",
              "maximum_i_pk_relative_change": max(r["i_pk_relative_change_25_to_12_5"] for r in checks),
              "maximum_vc_pk_relative_change": max(r["vc_pk_relative_change_25_to_12_5"] for r in checks),
              "minimum_ceiling_margin_a": min(r["i_pk_12_5ns_margin_a"] for r in checks),
              "cases": checks}
    (OUT / "quarterstep-checks.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}), flush=True)


if __name__ == "__main__":
    main()
