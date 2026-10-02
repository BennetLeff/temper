#!/usr/bin/env python3
"""Regression test for the D-4 review's grid findings (round17/delegation/out-D4).

D-4 showed, with the simulator stubbed out:
  1. a reused output directory returned an old case for a changed matrix;
  2. a non-ZVS nominal S1 case counted as an overall pass;
  3. a missing partner-command sample was labelled 'rebound'.
This replays the same three fixtures against the fixed grid.py and asserts
the corrected behaviour. Run: python3 test_grid.py  (prints PASS or raises).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import run_d2  # noqa: E402

MEAS = {"vds_ls_die_pk": 200.0, "vds_hs_die_pk": 200.0, "vgs_ls_die_max": 15.0, "vgs_hs_die_max": 15.0,
        "vgs_ls_die_min": -1.0, "vgs_hs_die_min": -1.0, "vgs_ls_off_max": 2.0, "vds_hs_at_on": 100.0,
        "vgs_ls_at_partner": 2.0}


def main() -> None:
    calls = []
    meas = dict(MEAS)

    def fake_run(*args, **kwargs):
        calls.append(True)
        return {"aborted": False, "meas": dict(meas)}

    case = ("S1", 170, 37, 0, 348, 10)
    with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(run_d2, "run", fake_run):
        out = Path(tmp)
        first = grid.one((case, np.eye(4).tolist(), out, None))
        # 2. non-ZVS nominal S1 (incoming VDS 100 V of 170 V): stress passes, task fails
        assert first["stress_pass"] and not first["zvs"] and not first["task_pass"] and not first["pass"], first
        # 1. same directory, changed matrix: must rerun, not reuse
        second = grid.one((case, (100 * np.eye(4)).tolist(), out, None))
        assert len(calls) == 2, "changed matrix reused a cached case"
        assert second["identity"]["matrix"] != first["identity"]["matrix"]
        # ... while an identical rerun is reused
        grid.one((case, (100 * np.eye(4)).tolist(), out, None))
        assert len(calls) == 2, "identical inputs were not reused"
        # 3. missing partner-command sample with a failing peak: 'unknown', not 'rebound'
        meas["vgs_ls_off_max"] = 4.0
        meas.pop("vgs_ls_at_partner")
        missing = grid.one((("S1", 170, 37, 0, 450, 10), np.eye(4).tolist(), out, None))
        assert missing["off_gate_cause"] == "unknown", missing["off_gate_cause"]
        # off-nominal S1 does not require ZVS
        assert missing["task_pass"] == missing["stress_pass"]
    assert len(grid.cases(None)) == 510, len(grid.cases(None))
    print("PASS test_grid: identity-checked reuse, ZVS in task verdict, unknown cause label, 510 cases")


if __name__ == "__main__":
    main()
