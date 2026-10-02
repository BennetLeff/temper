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
        # D-9 (P2): a change in the simulator build, the runner or a deck include
        # must force a rerun, not reuse.
        n0 = len(calls)
        meas = dict(MEAS)
        with patch.object(grid, "ngspice_version", lambda: "other-build"):
            grid.one((case, (100 * np.eye(4)).tolist(), out, None))
        assert len(calls) == n0 + 1, "simulator change reused a cached case"
        real_sha = grid._sha
        with patch.object(grid, "_sha", lambda p: "changed" if p.name == "run_ngspice.py" else real_sha(p)):
            grid.one((case, (100 * np.eye(4)).tolist(), out, None))
        assert len(calls) == n0 + 2, "runner change reused a cached case"
        with patch.object(grid, "includes", lambda deck: {"../common/options.inc": "changed"}):
            grid.one((case, (100 * np.eye(4)).tolist(), out, None))
        assert len(calls) == n0 + 3, "include change reused a cached case"
    # D-9 (P2): --set may not override scenario parameters
    for bad in ("DIR=1", "DT=250n", "vbus=280", "LESL=5n"):
        with patch.object(sys, "argv", ["grid.py", "--matrix", "x", "--out", "y", "--set", bad]), \
                patch.object(run_d2, "read_L", lambda p: np.eye(4).tolist()):
            try:
                grid.main()
            except SystemExit as e:
                assert "scenario" in str(e), e
            else:
                raise AssertionError(f"--set {bad} was accepted")
    assert len(grid.cases(None)) == 510, len(grid.cases(None))
    print("PASS test_grid: identity-checked reuse (matrix, simulator, runner, includes), ZVS in task verdict, "
          "unknown cause label, scenario overrides refused, 510 cases")


if __name__ == "__main__":
    main()
