#!/usr/bin/env python3
"""Stage 48 integration: the input snapshot for the S21 temperature re-base on the s48 chain (temp_ratings.py --rebase).

    python3 -I scripts/temps_snap48.py SNAPDIR
    python3 -I .../temp-ratings-2026-10-15/scripts/temp_ratings.py --snap SNAPDIR --rebase

Same four inputs as the S18 re-base (runs-native21/s18-ps2/c47int-s18-temps/snap, commit 8647aa05b), on stage 48:
  * runs/: the chain's B3 BASIS run files (b3-ratings/runs, gitignored), all on the board margins.json was solved on;
  * margins-HEAD.json: b3-ratings/margins.json of that chain;
  * default-HEAD.csv: the s48 frozen BOM (native-21/frozen/default.csv). The vendor gate keys its gated monitor rows to the
    MPN at each ref, and U3 is a gated TPS70950QDBVRQ1 row from stage 48, so the s47 BOM cannot reproduce the s48 rows;
  * ledger-HEAD.json: the pre-S21 ledger (651640bb7, the one S21 / S18 used, so "unrated" means what it meant there) with
    stage 48's one line change: the TPS70950DBVR entry is replaced, at the same position, by the TPS70950QDBVRQ1 entry
    ledger48.py writes (it carries TJ / EN / VIN ratings, so the line leaves the unrated set: 72 lines, not 73). The new
    stage-48 designators sit on existing lines of the BOM and are counted there.
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
    q1 = json.loads(LEDGER.read_text())["entries"]["TPS70950QDBVRQ1"]
    pre["entries"] = {("TPS70950QDBVRQ1" if k == "TPS70950DBVR" else k): (q1 if k == "TPS70950DBVR" else v)
                      for k, v in pre["entries"].items()}
    (out / "ledger-HEAD.json").write_text(json.dumps(pre, indent=1) + "\n")
    print("snapshot", out, "board", next(iter(board))[:8], "entries", len(pre["entries"]))


if __name__ == "__main__":
    main()
