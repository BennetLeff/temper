"""J2/J5 lug against the native-21 board parts around it: exact distances, replacing R43's 25 mm lug envelope.

Board solids: fit/inputs/board_c53int_near_J2J5.step (extract_board_near_lugs.py; the stage-53 integration board the
power stage's R43 real-pose gate measured, posed the same way). The tightest R43 pair was CT T1's provisional maximum
envelope body to the J2 lug envelope at 0.5 mm (r43-expected-hits.json), under the gate's 1.0 mm.
Measured here, for each lug model in lug.LUGS and for R43's own envelope (re-measured as the control):
  - lug solid (ring, neck, bend, barrel, PEEK sleeve if any, heat-shrink envelope) to every board solid;
  - washer, spring washer and screw head (exposed metal) to every board solid;
  - J2 lug to J5 lug and the exposed-metal gap J2-J5 (ring-to-ring rule: >= 5.0 mm at any rotation, ASSEMBLY.md).
Run: .venv/bin/python -B fit/lug_board.py  -> fit/results/lug_board.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build123d as bd  # noqa: E402

import lug as LUG  # noqa: E402

INP = HERE / "inputs"
OUT = HERE / "results" / "lug_board.json"
GATE = 1.0


def r43_envelope(name):
    """R43 electronics_r26.lug() re-built at its own seat (Z31.3), as the control for the method."""
    stud = {"J2": (-9.0, 150.5), "J5": (-9.0, 165.5)}[name]
    drop = {"J2": (-9.0, 142.5), "J5": (-9.0, 173.5)}[name]
    seat, t, ring_r, br, bh = 31.3, 0.79, 4.25, 3.5, 25.0
    ring = LUG.zcyl(*stud, seat, t, ring_r) - LUG.zcyl(*stud, seat - 1, 3, 2.15)
    y0, y1 = sorted((stud[1], drop[1]))
    tongue = bd.Pos(stud[0], (y0 + y1) / 2, seat) * bd.Box(5.0, y1 - y0, t, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return ring + tongue + LUG.zcyl(*drop, seat, t + bh, br)


def main():
    meta = json.loads((INP / "board_c53int_near_J2J5.json").read_text())
    board = list(bd.import_step(INP / "board_c53int_near_J2J5.step").solids())
    t1_box = meta["t1_box"]

    def is_t1(s):
        b = s.bounding_box()
        bb = [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z]
        return all(abs(bb[i] - t1_box[i]) < 0.02 for i in range(6))

    t1 = [s for s in board if is_t1(s)]
    if len(t1) != 1:
        raise SystemExit(f"T1 body not found once ({len(t1)})")

    def nearest(shape):
        rows = []
        for s in board:
            d = shape.distance_to(s)
            b = s.bounding_box()
            rows.append((d, [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)], is_t1(s)))
        rows.sort(key=lambda r: r[0])
        return [dict(distance_mm=round(d, 3), board_solid_world_bbox=bb, T1=t) for d, bb, t in rows[:3]]

    res = dict(about=__doc__.strip(), board=meta["source"], board_sha256=meta["source_sha256"], gate_mm=GATE,
               terminal=LUG.TERMINAL, seat_z=LUG.SEAT_Z, screw=LUG.SCREW, screw_stack=LUG.screw_stack(), cases={})
    cases = {"R43_envelope (control)": {n: r43_envelope(n) for n in ("J2", "J5")}}
    for which in LUG.LUGS:
        cases[which] = {n: LUG.lug_solid(n, which) for n in ("J2", "J5")}
    hw = {n: LUG.hardware_solid(n) for n in ("J2", "J5")}
    for case, lugs in cases.items():
        row = {}
        for n, s in lugs.items():
            row[n] = dict(to_T1_mm=round(s.distance_to(t1[0]), 3), nearest=nearest(s))
        row["J2_to_J5_lug_mm"] = round(lugs["J2"].distance_to(lugs["J5"]), 3)
        if case != "R43_envelope (control)":
            g = LUG.lug_geometry(case)
            row["axis_offset_mm"] = g["J2"]["axis_offset"]
            row["barrel_top_z"] = round(g["J2"]["barrel_top"], 2)
            row["drops_world"] = {n: [round(v, 2) for v in g[n]["drop"]] for n in g}
        res["cases"][case] = row
        print(case, {n: row[n]["to_T1_mm"] for n in ("J2", "J5")}, "J2-J5", row["J2_to_J5_lug_mm"], flush=True)
    res["hardware"] = {n: dict(to_T1_mm=round(hw[n].distance_to(t1[0]), 3), nearest=nearest(hw[n])) for n in hw}
    res["exposed_metal_J2_J5_mm"] = round(hw["J2"].distance_to(hw["J5"]), 3)
    ring_gap = 15.0 - LUG.LUGS[LUG.CHOICE]["ring_od"]
    res["ring_to_ring_any_rotation_mm"] = dict(
        rings=round(ring_gap, 2), washers=round(15.0 - LUG.SCREW["washer_d"], 2),
        rule="bare ring <= 10.0 mm and >= 5.0 mm between exposed metal at any rotation (ASSEMBLY.md, DECISIONS M6); the bend and barrel are insulated, so the exposed metal is ring + washer + head")
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k in ("hardware", "exposed_metal_J2_J5_mm", "ring_to_ring_any_rotation_mm", "screw_stack")}, indent=1))


if __name__ == "__main__":
    main()
