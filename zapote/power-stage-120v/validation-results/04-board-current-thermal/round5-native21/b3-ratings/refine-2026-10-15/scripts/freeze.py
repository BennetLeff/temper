#!/usr/bin/env python3
"""Extract the repo files this study reads, at the board's pinned commit, into frozen/<board>/ (git archive; the live
worktree is never read: other sessions move it while solves run). Checks each extracted file against the commit's blob.
    THERMAL_REFINE_BOARD=s38|s35 python3 freeze.py  ->  frozen/<board>/..., results[-s38]/freeze.json
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD, BOARDS, FROZEN, PIN, REPO_WT, RESULTS  # noqa: E402

U = "zapote/power-stage-120v/"
PATHS = [U + "validation-results/04-board-current-thermal/round5-native21",
         U + BOARDS[BOARD]["geom"],
         U + "native-21/stackup.json",
         U + "native-21/bias_sizing.py",
         U + "elec/src/power_stage_120v.ato",
         U + "validation-results/08-manufacturing-package/native-21/fab/positions-kicad.csv",
         U + "validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv",
         U + "validation-results/08-manufacturing-package/native-21/owner-items/m11/RECOMMENDATION.md",
         U + "validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py",
         U + "validation-results/01-switching-parasitics/device-study-2026-10-15/results/bias.json",
         U + "validation-results/03-loss-thermal-budget/round3/outputs/board_heat_sources.json",   # make_heat_sources.py
         U + "native-21/layout/pads.json",                                                        # make_heat_sources.py
         "firmware/components/control/thermal_mgmt.h"]


def git(*a, **k):
    return subprocess.run(["git", "-C", str(REPO_WT), *a], check=True, capture_output=True, **k).stdout


def main():
    full = git("rev-parse", PIN, text=True).strip()
    assert full == PIN, (full, PIN)
    if (FROZEN / ".pin").exists():
        assert (FROZEN / ".pin").read_text().strip() == PIN
    FROZEN.mkdir(parents=True, exist_ok=True)
    if True:                              # (re-)extract: git archive output is fixed by the pin, so this is idempotent
        tar = git("archive", "--format=tar", PIN, "--", *PATHS)
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(FROZEN, filter="data")
        (FROZEN / ".pin").write_text(PIN + "\n")
    assert (FROZEN / ".pin").read_text().strip() == PIN
    # verify: every file at the pin under PATHS is present with the same blob hash
    listing = git("ls-tree", "-r", PIN, "--", *PATHS, text=True).splitlines()
    bad = []
    for line in listing:
        meta, path = line.split("\t", 1)
        blob = meta.split()[2]
        f = FROZEN / path
        if not f.exists():
            bad.append(f"missing {path}")
            continue
        h = subprocess.run(["git", "hash-object", str(f)], check=True, capture_output=True, text=True).stdout.strip()
        if h != blob:
            bad.append(f"differs {path}")
    out = {"board": BOARD, "pin": PIN, "frozen": str(FROZEN), "files": len(listing), "problems": bad, "pass": not bad}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "freeze.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out))
    raise SystemExit(0 if not bad else 1)


if __name__ == "__main__":
    main()
