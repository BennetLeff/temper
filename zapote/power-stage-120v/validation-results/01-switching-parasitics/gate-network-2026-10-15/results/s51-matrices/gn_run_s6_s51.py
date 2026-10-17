#!/usr/bin/env python3
"""Run the as-built gate-network harness (11-candidates/s6-cmti-2026-10-16/scripts/gn_s6.py, imported read-only) on other
leg matrices, writing outside the repo. Same pattern as b15-proto-alternates/scripts/c39_diode_rerun.py.

    python3 -B gn_s51.py OUTDIR MATRIX_A MATRIX_B <grid> --cfg split68_1_cgs4p7_tt125 [--workers N]
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
GN = PS / "validation-results/11-candidates/s6-cmti-2026-10-16/scripts/gn_s6.py"
out, ma, mb = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
spec = importlib.util.spec_from_file_location("gn", GN)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
g.OUT = out
import os
if os.environ.get("C8LIB"):   # Infineon C8 library: hashed into identity only (the adopted cfg uses the CFD7 model)
    g.C8LIB = Path(os.environ["C8LIB"])
g.d2c.MATRICES["A"], g.d2c.MATRICES["B"] = ma, mb
sys.argv = [str(GN)] + sys.argv[4:]
g.main()
