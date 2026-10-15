"""Paths and shared constants for the thermal-refine study (2026-10-15). The repo is read-only: nothing here writes under it.

Board under study: THERMAL_REFINE_BOARD = s38 (default; board of record since DECISIONS 50) or s35 (the board the task
was set on, DECISIONS 46 margins). Each board reads a frozen extract of the repo at a pinned commit (freeze.py: git
archive of the files this study reads -> frozen/<board>/), never the live worktree, which other sessions move.

Model sets:
  repo : the committed body model at the pin (round5-native21/b3-convergence/thermal_body.py + body_runs.py), as
         b3-ratings/run_basis.py runs it.
  mod  : model[-<board>]/b3-convergence/ = the pinned modules + patches/*.diff (FET drain-lead path). model[-<board>]/b3
         is a symlink to the frozen round5-native21/b3 (thermal.py, run_study.py, heat files).
"""
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

JOB = Path(__file__).resolve().parents[1]
REPO_WT = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate")      # git only (archive / show / apply --cached)
BOARDS = {
    "s35": {"pin": "c36251e4158e7c75af21ae9c3fdf74b7edd66404",            # last commit with s35 as the thermal board
            "geom": "native-21/verification/native21s35-all-copper.json.gz",
            "board_sha": "fba59ef3d8169ee71a81a08d29c72f4e76acf8f420c91fd2515227adaabc8be4", "dirs": ""},
    "s38": {"pin": "f8cca7d21ee1d65dd8c149b2cd053fa827959fd2",            # DECISIONS 50: board of record s38
            "geom": "native-21/verification/native21s38-all-copper.json.gz",
            "board_sha": "b5bf428d2ff59574027fae92f248996804fdabb4363d479d3ea7c30762b09983", "dirs": "-s38"},
}
BOARD = os.environ.get("THERMAL_REFINE_BOARD", "s38")
PIN = BOARDS[BOARD]["pin"]
FROZEN = JOB / "frozen" / BOARD
UNIT = FROZEN / "zapote/power-stage-120v"
ROUND5 = UNIT / "validation-results/04-board-current-thermal/round5-native21"
REPO_CONV = ROUND5 / "b3-convergence"
RATINGS = ROUND5 / "b3-ratings"
FAB = UNIT / "validation-results/08-manufacturing-package/native-21/fab"
_d = BOARDS[BOARD]["dirs"]
MODEL = JOB / f"model{_d}"
MOD_CONV = MODEL / "b3-convergence"
RUNS = JOB / f"runs{_d}"
RESULTS = JOB / f"results{_d}"
DL = JOB / "dl"
HEAT_DIR = RUNS / "heat"
CACHE = RUNS / "cache"
FIRMWARE = UNIT.parents[1] / "firmware/components/control/thermal_mgmt.h"
R33_THERMAL = Path("/Users/bennet/Desktop/temper/output/temper-r33-studies/09-coil-210-strayfield/thermal")   # outside git, static
GEOM = UNIT / BOARDS[BOARD]["geom"]
BOARD_SHA = BOARDS[BOARD]["board_sha"]

FETS = {"Q2": "HS", "Q5": "HS", "Q3": "LS", "Q6": "LS"}                            # m11 table: Q2/Q5 tab bus_p (HS)
PITCHES = (0.25, 0.5)
BAYS = (55.0, 61.0)          # enclosure R33 study 14: expected / worst (B3 heat only) bay air at a 40 C kitchen


def pinned(path):
    """A path recorded by a solve made before the inputs were frozen (s35 runs before 04:07 on 2026-10-15 read the live
    worktree, then at the s35 state) -> the same file in the frozen pinned tree."""
    p, live = str(path), str(REPO_WT) + "/"
    return FROZEN / p[len(live):] if p.startswith(live) else Path(p)
