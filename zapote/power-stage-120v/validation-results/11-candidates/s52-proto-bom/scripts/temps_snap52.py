#!/usr/bin/env python3
"""Stage 52 integration: the input snapshot for the S21 temperature re-base on the s52 chain (temp_ratings.py --rebase).

    python3 -I scripts/temps_snap52.py SNAPDIR
    python3 -I .../temp-ratings-2026-10-15/scripts/temp_ratings.py --snap SNAPDIR --rebase --stage s52 --note ...

c49-c34-bank/scripts/temps_snap49.py (run through its main()), as c51-bank-source/stage51/scripts/temps_snap51.py, with
stage 52's three line swaps, each new entry the one ledger52.py writes (all three carry a temperature rating, so they stay
out of the unrated set, as their predecessors did):
  * bank: the pre-S21 line B32654A1104J000 -> the fitted TDK B32643H8104J000 (Top,max 125 C). KNSCHA
    MMK104J3DF1KN208G2 and B32643B8104J000 are ledger `alternates` at s52 (not on the BOM), so neither is in the snapshot;
  * L1: B82726S2203A020 -> B82726S2243A020 (the 2203 is the production part, under `alternates`);
  * C3 / C4: DE1E3RA222MA4BP01F -> DE1E3RA222MJ4BH01F.
The R33 / R34 (s49) and TPS70950 (s48) swaps are unchanged. 71 lines.
"""
import sys as _s; _s.dont_write_bytecode = True
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
S49 = HERE.parents[1] / "c49-c34-bank/scripts/temps_snap49.py"

if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("temps_snap49", S49)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SWAP = {**mod.SWAP, "B32654A1104J000": ("B32643H8104J000",), "B82726S2203A020": ("B82726S2243A020",),
                "DE1E3RA222MA4BP01F": ("DE1E3RA222MJ4BH01F",)}
    mod.main()
