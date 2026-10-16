#!/usr/bin/env python3
"""Stage 51 integration: the input snapshot for the S21 temperature re-base on the s51 chain (temp_ratings.py --rebase).

    python3 -I scripts/temps_snap51.py SNAPDIR
    python3 -I .../temp-ratings-2026-10-15/scripts/temp_ratings.py --snap SNAPDIR --rebase --stage s51 --note ...

c49-c34-bank/scripts/temps_snap49.py (run through its main()) with stage 51's bank swap: the pre-S21 bank line
B32654A1104J000 is replaced by the fitted KNSCHA MMK104J3DF1KN208G2 entry that ledger51.py writes (rated: Top,max 105 C,
so the bank stays out of the unrated set, as at s49 / s50). TDK B32643B8104J000 is not on the s51 BOM (ledger
`alternates`), so it is not in the snapshot. The R33 / R34 (s49) and TPS70950 (s48) swaps are unchanged. No other line
changes at s51: 71 lines.
"""
import sys as _s; _s.dont_write_bytecode = True
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
S49 = HERE.parents[2] / "c49-c34-bank/scripts/temps_snap49.py"

if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("temps_snap49", S49)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SWAP = {**mod.SWAP, "B32654A1104J000": ("MMK104J3DF1KN208G2",)}
    mod.main()
