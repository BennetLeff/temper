#!/usr/bin/env python3
"""Reproduce the CT sweep's numerical stalls without changing solver options."""

from __future__ import annotations

import json
from pathlib import Path

from sweep_frontends import CT, OUTPUT, checked_run


CASES = (
    {"FREQ": "33000", "I0": "37", "SLOPE": "1e6", "VOS": "-0.004", "TPD": "45e-9"},
    {"FREQ": "33000", "I0": "37", "SLOPE": "1e7", "VOS": "-0.004", "TPD": "45e-9"},
    {"FREQ": "33000", "I0": "10", "SLOPE": "1e6", "VOS": "0", "TPD": "55e-9"},
    {"FREQ": "39000", "I0": "37", "SLOPE": "1e6", "VOS": "-0.004", "TPD": "45e-9"},
)


def main() -> None:
    rows = []
    for params in CASES:
        try:
            meas, _, log_sha = checked_run(CT, params, timeout_s=5)
            rows.append({"params": params, "status": "complete", "meas": meas, "log_sha256": log_sha})
        except RuntimeError as error:
            rows.append({"params": params, "status": "blocked", "error": str(error)})
    (OUTPUT / "blocked_cases.json").write_text(json.dumps(rows, indent=2) + "\n")
    print([(row["params"]["FREQ"], row["params"]["I0"], row["params"]["SLOPE"], row["status"]) for row in rows])


if __name__ == "__main__":
    main()
