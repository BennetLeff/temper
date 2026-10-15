#!/usr/bin/env python3
"""Build model[-<board>]/ from the board's pinned commit + patches/*.diff and check its inputs (exit 1 on any failure).

  0. frozen/<board>/ (freeze.py) holds the pinned repo files; the geometry and A4 copper carry the board's sha
  1. model/b3 -> frozen round5-native21/b3 (symlink; thermal.py, run_study.py and the heat files are used read-only)
  2. for each patch: `git show <pin>:<file>` + `patch` -> model/... ; the result must equal the model file in place
     (patches are the source of truth; the model copies are what the solves import). All patches together must
     `git apply --cached --check` on a scratch index read from the pin, and from the repo's current HEAD (informational)
  3. b3-convergence/inputs/part-bodies.json (the pinned copy) against the board's pick-and-place (fab/positions-kicad.csv):
     same footprint and position for every part body
  4. model/b3-ratings/fet_case.py (proposed in-repo copy of the case-temperature chain) == sink_model.t_case()
    python3 prepare.py -> results/prepare.json
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD, BOARD_SHA, FAB, GEOM, JOB, MODEL, PIN, REPO_CONV, REPO_WT, RESULTS, ROUND5, RUNS, UNIT  # noqa: E402

PATCHES = {"lead-path.diff": ["b3-convergence/thermal_body.py", "b3-convergence/body_runs.py"],
           "heat-c28-60khz.diff": ["b3/make_heat_sources.py"],
           "gate-proposed-rows.diff": ["b3-ratings/b3_ratings_gate.py"],
           "run-basis-lead.diff": ["b3-ratings/run_basis.py", "b3-ratings/fet_case.py"]}
LOCAL = {"b3/make_heat_sources.py": "b3-heat/make_heat_sources.py"}
REL = "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/"
WT = REPO_WT


def apply_check(ref):
    idx = RUNS / "git-scratch-index"
    RUNS.mkdir(exist_ok=True)
    env = {**os.environ, "GIT_INDEX_FILE": str(idx)}
    subprocess.run(["git", "-C", str(WT), "read-tree", ref], check=True, env=env, capture_output=True)
    r = subprocess.run(["git", "-C", str(WT), "apply", "--cached", "--check"] + [str(JOB / "patches" / p) for p in PATCHES],
                       env=env, capture_output=True, text=True)
    idx.unlink()
    return r.returncode == 0


def main():
    import gzip
    out = {"board": BOARD, "pin": PIN, "pin_ok": (UNIT.parents[1] / ".pin").read_text().strip() == PIN}
    out["geometry_sha_ok"] = (json.loads(gzip.open(GEOM, "rt").read())["board_sha256"] == BOARD_SHA ==
                              json.loads(gzip.open(ROUND5 / "inputs/power_copper.json.gz", "rt").read())["board_sha256"])
    link = MODEL / "b3"
    if link.is_symlink() and link.resolve() != (ROUND5 / "b3").resolve():
        link.unlink()                      # re-point a link made before the inputs were frozen
    if not link.is_symlink():
        if link.exists():
            raise SystemExit("model/b3 exists and is not a symlink")
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(ROUND5 / "b3", link)
    out["symlink"] = str(link.resolve()) == str((ROUND5 / "b3").resolve())
    head = subprocess.run(["git", "-C", str(WT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    out["repo_head_now"] = head
    out["patches"] = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for patch, files in PATCHES.items():
            for f in files:
                (td / REL / f).parent.mkdir(parents=True, exist_ok=True)
                r = subprocess.run(["git", "-C", str(WT), "show", f"{PIN}:{REL}{f}"], capture_output=True, text=True)
                if r.returncode == 0:
                    (td / REL / f).write_text(r.stdout)
            r = subprocess.run(["patch", "-p1", "-s", "-d", str(td), "-i", str(JOB / "patches" / patch)], capture_output=True, text=True)
            ok = r.returncode == 0
            for f in files:
                built = (td / REL / f).read_text()
                dest = MODEL / LOCAL.get(f, f)
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(built)
                ok = ok and dest.read_text() == built
            out["patches"][patch] = ok
        out["git_apply_check_all"] = apply_check(PIN)
        out["git_apply_check_repo_head_now"] = apply_check(head)
    if not (MODEL / "b3-convergence/inputs/part-bodies.json").exists():
        (MODEL / "b3-convergence/inputs").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_CONV / "inputs/part-bodies.json", MODEL / "b3-convergence/inputs/part-bodies.json")
    out["part_bodies_equal_pinned"] = ((MODEL / "b3-convergence/inputs/part-bodies.json").read_bytes()
                                       == (REPO_CONV / "inputs/part-bodies.json").read_bytes())
    pb = json.loads((MODEL / "b3-convergence/inputs/part-bodies.json").read_text())["parts"]
    pos = {r["Ref"]: r for r in csv.DictReader(open(FAB / "positions-kicad.csv"))}
    bad = []
    for ref, b in pb.items():
        r = pos.get(ref)
        if r is None:
            bad.append(f"{ref}: not on the s35 pick-and-place")
        elif abs(float(r["PosX"]) - b["at"][0]) > 1e-3 or abs(-float(r["PosY"]) - b["at"][1]) > 1e-3 or not b["fp"].endswith(":" + r["Package"]):
            bad.append(f"{ref}: moved or footprint changed")
    out["part_bodies_vs_pick_and_place"] = {"parts": len(pb), "problems": bad}
    import sink_model
    src = (MODEL / "b3-ratings/fet_case.py").read_text().replace("UNIT = HERE.parents[3]", f"UNIT = Path({str(UNIT)!r})")
    ns = {"__name__": "fet_case", "__file__": str(MODEL / "b3-ratings/fet_case.py")}
    exec(compile(src, "fet_case", "exec"), ns)
    d = max(abs(ns["t_case"](c, k)[r] - sink_model.t_case(c, k)[0][r]) for c in (16.0, 22.0, 28.0)
            for k in ("cool", "central", "hot") for r in ("Q2", "Q3"))
    out["fet_case_vs_sink_model_max_K"] = d
    ok = (out["pin_ok"] and out["geometry_sha_ok"] and out["symlink"] and all(out["patches"].values())
          and out["git_apply_check_all"] and out["part_bodies_equal_pinned"] and not bad and d < 1e-12)
    out["pass"] = ok
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "prepare.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
