#!/usr/bin/env python3
"""Re-run the candidate-39 / gate-network-2026-10-15 ngspice harness (gn.py, read-only import) on the adopted stage-42+
network (68 ohm 2512 turn-on, Cgs 4.7 nF C0G, PMEG + 1 ohm turn-off; cfg split68_1_cgs4p7_tt125, typical Qrr) with
the turn-off diode model swapped, to bound the D6-D9 alternates. Output goes to ../results/c39-sims/<cfg>/<grid>.

Diode models (subckt name kept 'PMEG6030EP' so the deck lines are untouched):
  pmeg      the repo's vendor model (validation-plan/sim-kit/models/vendor/PMEG6030EP.txt) = control. PMEG6030EP-Q
            publishes the identical VF / IR / Cd tables (datasheets 2017-11-07 and 2023-02-20), so it is covered here.
  vfhi      bounding high-VF model: IS / 4000 (RS unchanged), +0.218 V at every current: 25 C VF about 0.50 / 0.59 /
            0.68 V at 0.1 / 1 / 3 A (diode_bounds.py) >= the 25 C maximum of every candidate (PMEG6030ELP: 0.50 V at
            0.1 A and 0.67 V at 3 A are the highest).
  cjhi      bounding high-capacitance model: CJO x 1.6 (model Cd at 1 V 535 pF vs 335 pF control, 360 pF datasheet typ).
Usage: python3 -I c39_diode_rerun.py <grid> <model> [--workers N] [--limit N]
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
GN = PS / "validation-results/01-switching-parasitics/gate-network-2026-10-15/scripts/gn.py"
VENDOR = PS / "validation-plan/sim-kit/models/vendor/PMEG6030EP.txt"
MODELS = HERE.parent / "results/c39-models"
BASE_CFG = "split68_1_cgs4p7_tt125"

grid, model = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]

spec = importlib.util.spec_from_file_location("gn", GN)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
g.OUT = HERE.parent / "results/c39-sims"

MODELS.mkdir(parents=True, exist_ok=True)
txt = VENDOR.read_text()


def setp(t, k, f):
    m = re.search(rf"^\+ {k} = ([0-9.Ee+-]+)", t, re.M)
    return t.replace(m.group(0), f"+ {k} = {f(float(m.group(1))):.6g}")


variants = {"pmeg": txt,
            "vfhi": setp(txt, "IS", lambda v: v / 4000),
            "cjhi": setp(txt, "CJO", lambda v: v * 1.6)}
mp = MODELS / f"PMEG6030EP_{model}.txt"
mp.write_text(variants[model])

_build = g.build_deck


def build_deck(cfg, energy=False, long=False):
    d = _build(cfg, energy=energy, long=long)
    inc = f".include {VENDOR}"
    assert d.count(inc) == 1, "diode include not found exactly once"
    return d.replace(inc, f".include {mp}")


g.build_deck = build_deck
# gn.py hashes the CoolMOS-8 library into its identity block; this study runs CFD7 only and that library (dl/, not
# committed) is absent, so the identity entry points at the diode model in use instead
g.C8LIB = mp
_configs = g.configs


def configs():
    c = _configs()
    c[f"{BASE_CFG}_D{model}"] = dict(c[BASE_CFG], diode=model)
    return c


g.configs = configs
sys.argv = [str(GN), grid, "--cfg", f"{BASE_CFG}_D{model}"] + rest
g.main()
