#!/usr/bin/env python3
"""Stage 50 integration: the input snapshot for the S21 temperature re-base on the s50 chain (temp_ratings.py --rebase).

    python3 -I scripts/temps_snap50.py SNAPDIR
    python3 -I .../temp-ratings-2026-10-15/scripts/temp_ratings.py --snap SNAPDIR --rebase --stage s50 --note ...

Stage 50 adds and removes no BOM line (R135 moves from 0603WAF1002T5E to the existing 0603WAF1003T5E line), so the
snapshot is the s49 one (c49-c34-bank/scripts/temps_snap49.py, run unchanged): this chain's six BASIS run files and
margins.json, the s50 frozen BOM, and the pre-S21 ledger 651640bb7 with the stage-48 / 49 line swaps. R135 is recounted
on the 100 k line; power_table.py carries its stage-50 power (3.47 V over 100 k).
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
    mod.main()
