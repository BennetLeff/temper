#!/usr/bin/env python3
"""Fit check of the board-jet change set against the frozen R43 assembly (temper-airflow-r1, step 3).

    ../.venv/bin/python fit_check.py      # build123d 0.11.1 (recipe: output/temper-sensor-r3/cad/DECISIONS.md) -> fit-check.json

Builds the three new parts as solids in the R43 world frame and measures, against every R43 catalog solid whose
bounding box comes within 20 mm: the overlap volume (must be 0 except at the intended hood joint) and the minimum
distance. native-21's frame: x_w = x_model - 141, y_w = 236 - y_model, board top Z27.5 (check_native21_pose.py).
  JETBOX  G11 jet manifold over the FET / film-cap channel: X-140..-53, Y213.5..225.5, Z33.5..42.5, 1.0 mm walls,
          8 x Ø3 jets in the floor at X-135.5 + 11k, Y222.0 (model x 5.5 + 11k, y 14.0: over the 2512 R_on row at y 12.4 and the copper peak at y 14.5-15.5), floor 6.0 mm above the board.
  F3      G11 feed duct from a 12 x 14 hole in the push hood's -Y wall (Y244.5) down to the jet box:
          leg A X-178..-164, Y213.5..244.5; leg B X-178..-140, Y213.5..225.5; both Z29.5..45.5.
  VENT    a 30 x 25 mm cut in the exhaust plenum's X-32 wall (Y330..360, Z25..50): the bay's exit to the plenum.
Also reports the distance from the new hood hole's metal rim (earthed) to the nearest native-21 solid.
"""
from __future__ import annotations

import json
from pathlib import Path

import build123d as bd

HERE = Path(__file__).resolve().parent
R43 = HERE.parents[2] / "output/temper-manufacturing-r43"
CAT = json.loads((R43 / "catalog.json").read_text())


def box(x0, x1, y0, y1, z0, z1):
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


def hollow(x0, x1, y0, y1, z0, z1, t=1.0, open_faces=()):
    s = box(x0, x1, y0, y1, z0, z1) - box(x0 + t, x1 - t, y0 + t, y1 - t, z0 + t, z1 - t)
    for f in open_faces:
        a = {"x0": box(x0 - 1, x0 + t + 0.01, y0 + t, y1 - t, z0 + t, z1 - t),
             "x1": box(x1 - t - 0.01, x1 + 1, y0 + t, y1 - t, z0 + t, z1 - t),
             "y0": box(x0 + t, x1 - t, y0 - 1, y0 + t + 0.01, z0 + t, z1 - t),
             "y1": box(x0 + t, x1 - t, y1 - t - 0.01, y1 + 1, z0 + t, z1 - t)}[f]
        s = s - a
    return s


def new_parts():
    jets = [bd.Pos(-135.5 + 11.0 * k, 222.0, 34.0) * bd.Cylinder(1.5, 3.0) for k in range(8)]
    jet = hollow(-140.0, -53.0, 213.5, 225.5, 33.5, 42.5, open_faces=("x0",))
    for j in jets:
        jet = jet - j
    f3 = (hollow(-178.0, -164.0, 213.5, 244.5, 29.5, 45.5, open_faces=("y1",))
          + hollow(-178.0, -140.0, 213.5, 225.5, 29.5, 45.5, open_faces=("x1",)))
    f3 = f3 - box(-177.0, -165.0, 214.5, 224.5, 30.5, 44.5)       # open the elbow between the legs
    vent = box(-33.0, -30.0, 330.0, 360.0, 25.0, 50.0)
    return {"JETBOX": jet, "F3": f3, "VENT_cutter": vent}


def near(bb, b, m=20.0):
    return all(bb.min.to_tuple()[i] - m < b[i + 3] and bb.max.to_tuple()[i] + m > b[i] for i in range(3))


def main():
    parts = new_parts()
    out = {"scope": __doc__.strip(), "new_parts": {}, "hood_hole_rim": None}
    cache = {}
    for name, s in parts.items():
        bb = s.bounding_box()
        rows = []
        for p in CAT:
            if not near(bb, p["bbox"]):
                continue
            if p["file"] not in cache:
                cache[p["file"]] = bd.import_step(R43 / p["file"])
            other = cache[p["file"]]
            best, vol = None, 0.0
            for so in other.solids():
                if not near(bb, [*so.bounding_box().min.to_tuple(), *so.bounding_box().max.to_tuple()], 20.0):
                    continue
                d = s.distance_to(so)
                best = d if best is None else min(best, d)
                if d < 1e-6:
                    inter = s.intersect(so)
                    vol += sum(x.volume for x in inter.solids()) if inter is not None else 0.0
            if best is not None:
                rows.append({"part": p["name"], "min_distance_mm": round(best, 2), "overlap_mm3": round(vol, 2)})
        rows.sort(key=lambda r: r["min_distance_mm"])
        out["new_parts"][name] = {"bbox": [round(v, 1) for v in (*bb.min.to_tuple(), *bb.max.to_tuple())], "neighbours": rows[:14]}
        print(name, json.dumps(rows[:10]))
    # earthed metal: the rim of the new hole in the push hood (wall Y244.5..245.5) to native-21's solids
    rim = box(-179.0, -163.0, 244.5, 245.5, 28.5, 46.5) - box(-177.0, -165.0, 244.0, 246.0, 30.5, 44.5)
    comp = cache.get("STEP/parts/electronics_native21_components_ENVELOPE.step") or bd.import_step(
        R43 / "STEP/parts/electronics_native21_components_ENVELOPE.step")
    brd = bd.import_step(R43 / "STEP/parts/electronics_native21_board.step")
    out["hood_hole_rim"] = {"to_native21_components_mm": round(min(rim.distance_to(x) for x in comp.solids()), 2),
                            "to_native21_board_mm": round(rim.distance_to(brd), 2)}
    print("hood hole rim:", out["hood_hole_rim"])
    (HERE / "fit-check.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
