"""Paths shared by the thermal-ratings audit scripts. The repo is read-only: nothing here writes under UNIT."""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True          # importing the repo's thermal.py / run_study.py must not drop .pyc files there
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

JOB = Path(__file__).resolve().parents[1]
UNIT = Path(os.environ.get("TEMPER_UNIT",
                           "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v"))
ROUND5 = UNIT / "validation-results/04-board-current-thermal/round5-native21"
B3 = ROUND5 / "b3"
CONV = ROUND5 / "b3-convergence"
FAB = UNIT / "validation-results/08-manufacturing-package/native-21/fab"
LEDGER = UNIT / "native-21/verification/datasheet-ledger/ledger.json"
MODEL = JOB / "model"
RESULTS = JOB / "results"
RUNS = JOB / "runs"                    # per-solve JSON (and thermal.py npz/png, deleted after parsing)
DL = JOB / "dl"
