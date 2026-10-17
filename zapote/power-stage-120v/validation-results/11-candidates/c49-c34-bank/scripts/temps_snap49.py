#!/usr/bin/env python3
"""Stage 49 integration: the input snapshot for the S21 temperature re-base on the s49 chain (temp_ratings.py --rebase).

    python3 -I scripts/temps_snap49.py SNAPDIR
    python3 -I .../temp-ratings-2026-10-15/scripts/temp_ratings.py --snap SNAPDIR --rebase --stage s49 --note ...

c48-ldo-en-ref-watch/scripts/temps_snap48.py on stage 49 (same four inputs):
  * runs/: the chain's B3 BASIS run files (b3-ratings/runs, gitignored), all on the board margins.json was solved on;
  * margins-HEAD.json: b3-ratings/margins.json of that chain;
  * default-HEAD.csv: the s49 frozen BOM (native-21/frozen/default.csv): the bank is B32643B8104J000 and R33 / R34 / R35
    are the S23 B'-1.02 V parts, so the vendor gate keys the s49 rows;
  * ledger-HEAD.json: the pre-S21 ledger (651640bb7, so "unrated" means what it meant at S21) with the line changes of
    stages 48 and 49, each new entry taken from the current ledger at the old entry's position:
      - s48: TPS70950DBVR -> TPS70950QDBVRQ1 (rated, as at the s48 re-base);
      - s49: B32654A1104J000 -> B32643B8104J000 (both rated, the bank stays out of the unrated set);
      - s49: RT0603BRD0712K6L -> RT0603BRD077K5L (R33) and RT0603BRD0716KL (R34). ledger49.py writes both with the RT0603
        terminal-temperature rating and their local temperatures from results/bands-s49.json (the same B3 gate estimator
        on this chain's run files), so they are rated lines and leave the unrated set: 71 lines, not 72.
    The lines whose designators moved stay unrated and are recounted on their s49 refs: RT0603BRD0710KL without R33,
    RT0603BRD0711KL with R35, TNPW060311K7BEEA with R145 only.
The run files are checked to be on margins.json's board. Re-running gives the same snapshot.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
B3R = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
PRE_S21 = "651640bb7"
CASES = ("c17.5_h10", "c22_h10", "c28_h10")
SWAP = {"TPS70950DBVR": ("TPS70950QDBVRQ1",),
        "B32654A1104J000": ("B32643B8104J000",),
        "RT0603BRD0712K6L": ("RT0603BRD077K5L", "RT0603BRD0716KL")}


def main():
    out = Path(sys.argv[1]).resolve()
    (out / "runs").mkdir(parents=True, exist_ok=True)
    m = json.loads((B3R / "margins.json").read_text())
    board = set(m["board_sha256"].values())
    assert len(board) == 1, board
    for c in CASES:
        for mesh in ("0p25", "0p5"):
            f = B3R / "runs" / f"{c}_p{mesh}.json"
            assert json.loads(f.read_text())["board_sha256"] in board, (f, board)
            shutil.copy2(f, out / "runs" / f.name)
    shutil.copy2(B3R / "margins.json", out / "margins-HEAD.json")
    shutil.copy2(PS / "native-21/frozen/default.csv", out / "default-HEAD.csv")
    rel = str(LEDGER.relative_to(PS.parents[1]))
    pre = json.loads(subprocess.run(["git", "-C", str(PS), "show", f"{PRE_S21}:{rel}"], check=True, capture_output=True,
                                    text=True).stdout)
    cur = json.loads(LEDGER.read_text())["entries"]
    entries = {}
    for k, v in pre["entries"].items():
        if k in SWAP:
            for n in SWAP[k]:
                entries[n] = cur[n]
        else:
            entries[k] = v
    pre["entries"] = entries
    (out / "ledger-HEAD.json").write_text(json.dumps(pre, indent=1) + "\n")
    print("snapshot", out, "board", next(iter(board))[:8], "entries", len(entries))


if __name__ == "__main__":
    main()
