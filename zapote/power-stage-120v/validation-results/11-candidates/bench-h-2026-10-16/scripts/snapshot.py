#!/usr/bin/env python3
"""Byte-copy snapshot of the B3 model at PS HEAD, for the bench-h fit (the airflow28 snapshot approach).

    python3 -I snapshot.py [--ps PS] [--out SNAP]

Copies, read-only on PS:
  * validation-results/04-board-current-thermal/round5-native21/  (code, inputs, the gitignored A4 fields in outputs/,
    and b3-ratings/runs/cache/ fine masks; not the chain's run files or __pycache__)
  * the files that tree reads outside itself (found by grep of thermal.py, run_study.py, fet_case.py,
    b3_ratings_gate.py at 05a3d9138): native-21/stackup.json, run_study.GEOM (native21s48-all-copper.json.gz),
    native-21/frozen/default.csv, sim-kit/04-current/sheet_solver.py, round6 board_side.py,
    firmware/components/control/thermal_mgmt.h, native-21/layout/gates/jet_strip_height.py
Writes SNAP/SNAPSHOT.txt: HEAD sha, time, `git status --short` of the copied tracked paths (must be empty), and the
sha256 of the geometry and of the A4 field set (a4_fields.set_hash, the value outputs/cache.json holds).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_DEFAULT = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate")
SNAP_DEFAULT = Path(__file__).resolve().parent.parent / "snap"
R5_REL = "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
EXTRA = ["zapote/power-stage-120v/native-21/stackup.json",
         "zapote/power-stage-120v/native-21/verification/native21s48-all-copper.json.gz",
         "zapote/power-stage-120v/native-21/frozen/default.csv",
         "zapote/power-stage-120v/native-21/layout/gates/jet_strip_height.py",
         "zapote/power-stage-120v/validation-plan/sim-kit/04-current/sheet_solver.py",
         "zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py",
         "firmware/components/control/thermal_mgmt.h"]


def ignore(dirpath, names):
    d = Path(dirpath)
    out = {n for n in names if n == "__pycache__"}
    if d.name == "runs" and d.parent.name == "b3-ratings":          # chain run files: keep only the mask cache
        out |= {n for n in names if n != "cache"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(REPO_DEFAULT))
    ap.add_argument("--out", default=str(SNAP_DEFAULT))
    a = ap.parse_args()
    repo, snap = Path(a.repo), Path(a.out)
    if snap.exists():
        raise SystemExit(f"{snap} exists: remove it first (a snapshot is never updated in place)")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(repo), "status", "--short", "--", R5_REL, *EXTRA],
                            capture_output=True, text=True, check=True).stdout
    shutil.copytree(repo / R5_REL, snap / R5_REL, ignore=ignore)
    for rel in EXTRA:
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, snap / rel)
    r5 = snap / R5_REL
    sys.path.insert(0, str(r5))
    import a4_fields
    a4 = a4_fields.set_hash(r5 / "outputs")
    cache = json.loads((r5 / "outputs/cache.json").read_text())
    geo = hashlib.sha256((snap / EXTRA[1]).read_bytes()).hexdigest()
    txt = (f"snapshot of {head} taken {time.strftime('%a %b %d %H:%M:%S %Z %Y')}\n"
           f"repo {repo}\n"
           f"git status of copied tracked paths: {'clean' if not status.strip() else chr(10) + status}\n"
           f"geometry {EXTRA[1]} sha256 {geo}\n"
           f"a4 field set sha256 {a4} (outputs/cache.json npz_sha256 {cache.get('npz_sha256')}: "
           f"{'match' if cache.get('npz_sha256') == a4 else 'MISMATCH'})\n")
    (snap / "SNAPSHOT.txt").write_text(txt)
    print(txt)
    if status.strip() or cache.get("npz_sha256") != a4:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
