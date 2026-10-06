"""Aggregate preserved F6 results without treating solver failures as passes."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = ("leg", "temp_C", "case", "vbus", "il", "dir", "dt_ns", "esl_nH")


def case_key(row: dict) -> tuple:
    return tuple(row[k] for k in KEY)


def main() -> None:
    groups = {}
    sources = {}
    tables = []
    for name in ("screen-3p-0p125n", "klu-3p-0p125n"):
        path = HERE / name / "results.json"
        rows = json.loads(path.read_text())
        indexed = {case_key(r): r for r in rows}
        if len(rows) != 504 or len(indexed) != 504:
            raise ValueError(f"missing or duplicate cases in {name}")
        sources[name] = indexed
        complete = [r for r in rows if r["status"] == "complete"]
        groups[name] = {
            "cases": len(rows), "complete": len(complete),
            "indeterminate": len(rows)-len(complete),
            "candidate_pass": sum(r["pass_candidate"] for r in rows),
            "max_off_V": max(r["off_V"] for r in complete),
            "max_die_VDS_V": max(r["vds_pk"] for r in complete),
            "least_negative_partner_window_V": max(max(r["nl_partner_max"], r["nh_partner_max"]) for r in complete),
            "results_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        by_group = defaultdict(list)
        for row in rows:
            by_group[(row["leg"], row["temp_C"], row["case"])].append(row)
        tables += [f"\n## {name}\n", "| Leg | Tj °C | Case | Completed / attempted | Candidate passes |",
                   "| --- | ---: | --- | ---: | ---: |"]
        for (leg, temp, case), subset in sorted(by_group.items()):
            count = sum(r["status"] == "complete" for r in subset)
            passes = sum(r["pass_candidate"] for r in subset)
            tables.append(f"| {leg} | {temp} | {case} | {count}/{len(subset)} | {passes} |")
    first, second = sources.values()
    if set(first) != set(second):
        raise ValueError("solver grids differ")
    common = [k for k in first if first[k]["status"] == second[k]["status"] == "complete"]
    neither = [dict(zip(KEY, k)) for k in first if first[k]["status"] != "complete" and second[k]["status"] != "complete"]
    comparison = {
        "complete_in_both": len(common), "indeterminate_in_both": len(neither),
        "max_off_difference_V": max(abs(first[k]["off_V"]-second[k]["off_V"]) for k in common),
        "max_die_VDS_difference_V": max(abs(first[k]["vds_pk"]-second[k]["vds_pk"]) for k in common),
        "max_partner_rail_difference_V": max(abs(first[k][rail]-second[k][rail]) for k in common for rail in ("nl_partner_max", "nh_partner_max")),
        "candidate_verdict_disagreements": sum(first[k]["pass_candidate"] != second[k]["pass_candidate"] for k in common),
        "still_indeterminate_cases": neither,
    }
    result = {"campaigns": groups, "solver_comparison": comparison,
              "scope": "loaded local shunt rail and Thevenin upstream regulator; not full supply qualification"}
    (HERE / "campaign-comparison.json").write_text(json.dumps(result, indent=2)+"\n")
    (HERE / "campaign-table.md").write_text("# F6 loaded-rail screening\n\nA candidate pass is conditional on this model. Indeterminate is not a pass.\n"+"\n".join(tables)+"\n")
    print(json.dumps({"campaigns": groups, "solver_comparison": {k:v for k,v in comparison.items() if k != "still_indeterminate_cases"}}, indent=2))


if __name__ == "__main__":
    main()
