"""Shared loaders for the c55 device trade (read-only reuse of the committed harnesses).

* DS = device study 2026-10-15 (`01-switching-parasitics/device-study-2026-10-15/scripts/harness.py`), DECISIONS 49.
* GN = gate-network study 2026-10-15 (`01-switching-parasitics/gate-network-2026-10-15/scripts/gn.py`), DECISIONS 54.
Both are imported, never edited. Their output folders are redirected here (`../sims/`), so the committed `sims/`
and `results/` of those studies are only read.
Vendor models live outside git (C55_DL, default `worktrees/runs-native21/c55-dl`); see ../README.md for URL + sha256.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
C55 = HERE.parent
SIMS = C55 / "sims"
PS = HERE.parents[3]                                    # zapote/power-stage-120v
VR = PS / "validation-results"
DS_DIR = VR / "01-switching-parasitics/device-study-2026-10-15"
GN_DIR = VR / "01-switching-parasitics/gate-network-2026-10-15"
DL = Path(os.environ.get("C55_DL", "/Users/bennet/Desktop/temper/worktrees/runs-native21/c55-dl"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load("ds_harness", DS_DIR / "scripts/harness.py")
G = _load("gn", GN_DIR / "scripts/gn.py")
G.OUT = SIMS / "gn"                                     # redirect gn.py output (module global, read at call time)
C8_LIB = DL / "cm8/c8_600/IFX_C8_600V.lib"
G.C8LIB = C8_LIB                                        # gn reads C8LIB at call time
d2c, run_d2, Z = H.d2c, H.run_d2, H.Z


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
