#!/usr/bin/env python3
"""Compare two prior round-two case families and the kit smoke reference."""
from __future__ import annotations

import json

from run_ct import HERE, analog


def main() -> None:
    sweep = json.loads((HERE / "outputs/ct_sweep.json").read_text())
    prior = sweep["reference_comparisons"]
    families = {(c["params"]["FREQ"], c["params"]["I0"], c["params"]["SLOPE"])
                for c in prior}
    if len(families) != 2 or len(prior) != 12:
        raise ValueError("expected two round-two case families / 12 rows")
    smoke = analog(35000, 37, 3e6)
    row = next(r for r in smoke["rows"] if float(r["params"]["VOS"]) == 0
               and float(r["params"]["TPD"]) == 55e-9)
    refs = {"t_ip_trip": 6.344e-6, "t_pos_trip": 6.589e-6}
    smoke_error = {name: abs(row[name] - ref) / ref * 100 for name, ref in refs.items()}
    max_prior = max(x for c in prior for x in c["relative_error_pct"].values())
    passed = max(max_prior, *smoke_error.values()) <= 1.0
    result = {"round_two_families": sorted(families), "round_two_rows": len(prior),
              "round_two_max_relative_error_pct": max_prior,
              "third_case": {"params": {"FREQ": 35000, "I0": 37, "SLOPE": 3e6,
                                         "VOS": 0, "TPD": 55e-9},
                             "smoke_reference_s": refs,
                             "computed_s": {name: row[name] for name in refs},
                             "relative_error_pct": smoke_error},
              "criterion_pct": 1.0, "pass": passed}
    (HERE / "outputs/reference_comparisons.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
