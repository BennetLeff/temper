#!/usr/bin/env python3
"""How many violations of each category NAME one of the six FinePitch vias?

Run kicad-cli DRC on two boards and split every category by whether the
violation names a via at one of the six positions the fix touched. Proves
the clearance delta is caused by those six pads and nothing else.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--scratch", type=Path, required=True)
ap.add_argument("--boards", nargs="+", required=True)
ap.add_argument(
    "--touched",
    default="",
    help="comma-separated x:y positions of the vias the fix rewrote; "
    "defaults to the six on the committed placement",
)
a = ap.parse_args()

sys.path.insert(0, str(a.repo / "scripts"))
from generate_kicad_dru import generate_dru  # noqa: E402
from temper_placer.validation._drc_api import _single_threaded_kicad_env  # noqa: E402

PCB_DIR = a.repo / "pcb"
DRU = generate_dru()

# The six vias the fix rewrote, from the routed-board diff.
TOUCHED = {
    (167.245, 46.22),
    (20.35, 46.96),
    (33.065, 31.02),
    (20.35, 49.96),
    (158.525, 33.1),
    (20.35, 43.96),
}
if a.touched:
    TOUCHED = {
        (float(p.split(":")[0]), float(p.split(":")[1]))
        for p in a.touched.split(",")
    }


def near(pos: dict) -> bool:
    x, y = pos.get("x"), pos.get("y")
    if x is None or y is None:
        return False
    return any(abs(x - tx) < 1e-6 and abs(y - ty) < 1e-6 for tx, ty in TOUCHED)


for board in a.boards:
    board = Path(board)
    dst = a.scratch / ("attr_" + board.stem)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy(board, dst / "temper.kicad_pcb")
    shutil.copy(PCB_DIR / "temper.kicad_pro", dst / "temper.kicad_pro")
    shutil.copy(PCB_DIR / "fp-lib-table", dst / "fp-lib-table")
    shutil.copytree(PCB_DIR / "libs", dst / "libs")
    (dst / "temper.kicad_dru").write_text(DRU, encoding="utf-8")
    out = dst / "_drc.json"
    with _single_threaded_kicad_env() as env:
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--all-track-errors", "--format", "json",
             "--output", str(out), str(dst / "temper.kicad_pcb")],
            capture_output=True, text=True, timeout=900, env=env, check=False)
    data = json.loads(out.read_text())
    tot: collections.Counter = collections.Counter()
    hit: collections.Counter = collections.Counter()
    for v in data.get("violations", []):
        tot[v["type"]] += 1
        if any(near(it.get("pos", {})) for it in v.get("items", [])):
            hit[v["type"]] += 1
    print(f"\n=== {board.name} ===")
    print(f"{'category':28s} {'total':>6s} {'names a touched via':>20s}")
    for c, n in tot.most_common():
        print(f"{c:28s} {n:6d} {hit[c]:20d}")
