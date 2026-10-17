#!/usr/bin/env python3
"""Model-side half of the chain's task-04 and B3 cache keys (stage 33, DECISIONS 38 "chain cache trap").

    python3 model_key.py                 ->  prints a SHA-256 over every model input that is not the board's copper
    python3 model_key.py --list          ->  prints each dependency and its SHA-256 (for cache.json / audits)

Both caches (regate.sh task04, chain.sh B3) take this one key, together with copper_key.py's board key. It covers
the union of the scripts both studies run (solver, case runner, summariser, topology check, exporters, layer module,
B3 thermal / study / sweep / heat-source scripts), B3's heat-source inputs, the resolved layer stack file(s) and the
environment switches that change a model's result. Before stage 33 the task-04 key hashed only its own four scripts
and B3's key only its own: a change to a B3 script (or the stackup) gave a task-04 hit and a B3 recompute, and B3
then failed its "geometry from the same board as the A4 cases" check, because a task-04 hit leaves the A4 cases on
the board they were computed on. With one shared model key, any model change misses both caches, so a task-04 hit
implies the B3 inputs are those of the run that computed it.
"""
import glob
import hashlib
import os
import re
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[3]          # zapote/power-stage-120v
R5 = "validation-results/04-board-current-thermal/round5-native21"
SCRIPTS = [
    # task 04
    f"{R5}/run_cases.py", f"{R5}/run_board.py", f"{R5}/summarize.py",
    "validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py",
    "validation-plan/sim-kit/04-current/sheet_solver.py",
    "tools/export_power_copper.py",
    "native-21/layout/gates/copper_key.py",
    "native-21/layout/layers21.py",
    # B3
    f"{R5}/b3/make_heat_sources.py", f"{R5}/b3/run_study.py", f"{R5}/b3/ceiling_sweep.py", f"{R5}/b3/thermal.py",
    f"{R5}/b3-convergence/thermal_multigrid.py",       # b3/thermal.py's preconditioner
    "validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py",
    "validation-results/03-loss-thermal-budget/round3/outputs/board_heat_sources.json",
]
# environment switches read by the models (a value change is a model change)
ENV = ("SHEET_BARREL",)          # the stack files are hashed by content above


def stackups():
    """The layer-stack files the models resolve: layers21 / run_board / kelvin ($NATIVE21_STACKUP or the default) and
    B3 ($B3_STACKUP, then $NATIVE21_STACKUP, then the default)."""
    default = UNIT / "native-21/stackup.json"
    n21 = Path(os.environ.get("NATIVE21_STACKUP") or default)
    b3 = Path(os.environ.get("B3_STACKUP") or n21)
    return [("stackup(native21)", n21), ("stackup(b3)", b3)]


def rows():
    out = []
    for rel in SCRIPTS:
        t = (UNIT / rel).read_bytes()
        if rel.endswith("b3/run_study.py"):       # the chain rewrites this TAG's geometry file name into it
            t = re.sub(rb'native21[0-9a-z]+-all-copper\.json\.gz', b'TAG-all-copper.json.gz', t)
        out.append((rel, hashlib.sha256(t).hexdigest()))
    for f in sorted(glob.glob(str(UNIT / R5 / "b3/inputs/*.json"))):
        out.append((str(Path(f).relative_to(UNIT)), hashlib.sha256(Path(f).read_bytes()).hexdigest()))
    for name, p in stackups():
        out.append((f"{name} {p}", hashlib.sha256(p.read_bytes()).hexdigest()))
    for k in ENV:
        out.append((f"env {k}", os.environ.get(k, "")))
    return out


def key():
    h = hashlib.sha256()
    for name, v in rows():
        # stack file rows hash by content only (the same file reached by another path is the same input)
        h.update((name.split(" ")[0] if name.startswith("stackup") else name).encode() + b"\0" + v.encode() + b"\n")
    return h.hexdigest()


if __name__ == "__main__":
    if "--list" in sys.argv:
        for name, v in rows():
            print(v, name)
    print(key())
