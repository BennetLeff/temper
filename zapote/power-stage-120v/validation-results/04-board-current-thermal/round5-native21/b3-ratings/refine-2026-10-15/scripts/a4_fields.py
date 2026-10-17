#!/usr/bin/env python3
"""The A4 current-density heat fields (round5-native21/outputs/<case>-heat.npz) are gitignored build products of the
task-04 copper solve, so freeze.py's git archive cannot carry them. This copies them into frozen/<board>/ from the
worktree that built them for that board, after checking each one against the board's pinned outputs/<case>.json the
way b3/thermal.py remap_a4() does: sum of the four layers' joule_w + the JSON's barrel heat = the JSON's loss_w.
A JSON from another board (another copper solve) fails this check.

    THERMAL_REFINE_BOARD=s38|s35 python3 a4_fields.py [source round5-native21/outputs dir]  ->  results*/a4_fields.json

Default sources (2026-10-15):
  s35: ps-integrate (the s35 fields of 01:19, left in place when stage 38 committed only the s38 JSONs)
  s38: ps-selv (the stage-38 chain, SPINE_OWNER=selv, 03:41)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD, RESULTS, ROUND5  # noqa: E402

REL = "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/outputs"
SRC = {"s35": Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate") / REL,
       "s38": Path("/Users/bennet/Desktop/temper/worktrees/ps-selv") / REL}
LAYERS = ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC[BOARD]
    dst = ROUND5 / "outputs"
    rows, bad = {}, []
    for js in sorted(dst.glob("*.json")):
        meta = json.loads(js.read_text())
        if not isinstance(meta, dict) or "loss_w" not in meta or "barrel_heat_by_layer" not in meta:
            continue
        name = js.stem + "-heat.npz"
        f = dst / name if (dst / name).exists() else src / name
        if not f.exists():
            bad.append(f"{name}: not in {src}")
            continue
        a = np.load(f)
        found = sum(float(a[f"{lay}_joule_w"].sum()) for lay in LAYERS if f"{lay}_joule_w" in a.files)
        found += sum(w for item in meta["barrel_heat_by_layer"] for w in item["layer_joule_w"].values())
        ok = abs(found - meta["loss_w"]) <= 1e-8 * max(1.0, meta["loss_w"])
        if not ok:
            bad.append(f"{name}: energy {found} vs JSON loss_w {meta['loss_w']}")
        elif f.parent != dst:
            shutil.copyfile(f, dst / name)
        rows[name] = {"loss_w": meta["loss_w"], "found_w": found, "ok": ok, "sha256": sha(dst / name) if ok else None,
                      "source": str(f)}
    # negative control: the other board's fields (if frozen) checked against this board's JSONs
    other = {"s35": "s38", "s38": "s35"}[BOARD]
    odir = Path(str(dst).replace(f"/frozen/{BOARD}/", f"/frozen/{other}/"))
    neg = None
    if odir.exists() and any(odir.glob("*-heat.npz")):
        fails, same = 0, 0
        for name in rows:
            if not (odir / name).exists():
                continue
            if sha(odir / name) == rows[name]["sha256"]:
                same += 1
            meta = json.loads((dst / name.replace("-heat.npz", ".json")).read_text())
            a = np.load(odir / name)
            found = sum(float(a[f"{lay}_joule_w"].sum()) for lay in LAYERS if f"{lay}_joule_w" in a.files)
            found += sum(w for item in meta["barrel_heat_by_layer"] for w in item["layer_joule_w"].values())
            fails += abs(found - meta["loss_w"]) > 1e-8 * max(1.0, meta["loss_w"])
        neg = {"other_board": other, "other_fields_failing_this_boards_json": fails, "identical_files": same}
    out = {"board": BOARD, "source": str(src), "cases": len(rows), "problems": bad, "pass": bool(rows) and not bad,
           "negative_control": neg, "rows": rows}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "a4_fields.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
    raise SystemExit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
