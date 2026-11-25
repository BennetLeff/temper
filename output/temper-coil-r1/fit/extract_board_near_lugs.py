"""Extract the native-21 board solids around J2/J5 into fit/inputs/ so the lug clearance check is reproducible here.

Source: the integration chain's stage-53 board STEP, the one the power stage's R43 real-pose fit gate measured
(validation-plan/enclosure-fit/native21-in-r43.json: step_sha256 1300b1b2...). Pose as board_in_r43.py: a pure translation
(-141, +236, +26) on the STEP's own axes. Every solid whose posed box reaches into the J2/J5 region is kept, with its
posed box; the T1 body is the solid whose box equals the T1 box in native21-in-r43.json.
Run once: .venv/bin/python -B fit/extract_board_near_lugs.py [BOARD_STEP]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import build123d as bd

HERE = Path(__file__).resolve().parent
BOARD = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/bennet/Desktop/temper/worktrees/runs-native21/s53/c53int/board.step")
FIT = HERE.parents[2] / "zapote/power-stage-120v/validation-plan/enclosure-fit/native21-in-r43.json"
REGION = (-30.0, 125.0, 26.0, 12.0, 190.0, 80.0)          # world box: >= 20 mm round J2 (-9, 150.5) and J5 (-9, 165.5)
T1_BOX = next(h["world"] for h in json.loads(FIT.read_text())["hits"] if h["ref"] == "T1")


def main():
    sha = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    want = json.loads(FIT.read_text())["step_sha256"]
    if sha != want:
        raise SystemExit(f"{BOARD}: sha256 {sha[:16]} is not the fit gate's board {want[:16]}")
    shape = bd.import_step(BOARD)
    keep, rows = [], []
    for s in shape.solids():
        w = bd.Pos(-141.0, 236.0, 26.0) * s
        b = w.bounding_box()
        bb = [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z]
        slab = (bb[3] - bb[0]) * (bb[4] - bb[1]) > 30000 and bb[5] - bb[2] < 2      # the board itself (top Z27.6): not kept
        if all(bb[i] < REGION[i + 3] and REGION[i] < bb[i + 3] for i in range(3)) and bb[5] - bb[2] < 60 and not slab:
            is_t1 = all(abs(bb[i] - T1_BOX[i]) < 0.02 for i in range(6))
            keep.append(w)
            rows.append(dict(index=len(rows), world_bbox=[round(v, 3) for v in bb], volume_mm3=round(w.volume, 2), T1=is_t1))
    out = HERE / "inputs"
    out.mkdir(exist_ok=True)
    bd.export_step(bd.Compound(keep), str(out / "board_c53int_near_J2J5.step"))
    t1 = [r for r in rows if r["T1"]]
    meta = dict(source=str(BOARD), source_sha256=sha, pose="translate (-141, +236, +26)", region_world=REGION,
                t1_box_from=str(FIT.relative_to(HERE.parents[2])), t1_box=T1_BOX, t1_found=len(t1), solids=rows)
    (out / "board_c53int_near_J2J5.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"kept {len(rows)} solids, T1 matches {len(t1)}: {t1}")


if __name__ == "__main__":
    main()
