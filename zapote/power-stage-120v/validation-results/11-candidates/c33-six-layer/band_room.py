#!/usr/bin/env python3
"""Routing room in the y 47-60 band (x 0-26), the corridor that blocked 30a / 30b (DECISIONS 33 / 34), per copper layer.

    [NATIVE21_STACKUP=...] python3 band_room.py ALL_COPPER.json.gz OUT.json

The same census as 13-coupling/scripts/physical.py section 4b, on any layer count (layers from layers21): a cell is
free for a probe net on a layer when a 0.2 mm track of that net there keeps rules21.clearance_on to every other net's
copper (pads, tracks, vias, zone fills) on that layer; "crossing" = a free path from y 47 to y 60 inside x 0-26;
via-legal cells = free on every layer at once (a through via needs room on all of them). Probes as physical.py:
LOW mon_good_ha, SELV hsb_good, SW_B (the HS-B island) bias_hb-fbm. On the stage-32 export it reproduces the
coupling audit's row (SELV nowhere; HS-B In2 only, 1 via-legal cell; LOW F and B) as its control.
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
import shapely.geometry as sg
import shapely.ops as so
from scipy import ndimage

UNIT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(UNIT / "native-21/layout"))
import layers21  # noqa: E402
import rules21  # noqa: E402

PITCH = 0.25
PROBES = {"LOW": "mon_good_ha", "SELV": "hsb_good", "SW_B": "bias_hb-fbm"}
BOX = (0.0, 47.0, 26.0, 60.0)


def main():
    d = json.load(gzip.open(sys.argv[1], "rt"))
    x0, y0, x1, y1 = BOX[0] - 9, BOX[1] - 9, BOX[2] + 9, BOX[3] + 9
    xs = np.arange(x0 + PITCH / 2, x1, PITCH)
    ys = np.arange(y0 + PITCH / 2, y1, PITCH)
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    win = sg.box(x0, y0, x1, y1)
    onb = (XX > 0.5) & (YY > 0.5)
    geoms = defaultdict(list)
    for x in d["primitives"]:
        n = x.get("net")
        if not n:
            continue
        if x["kind"] == "track":
            g = sg.LineString([x["start"], x["end"]]).buffer(x["width_mm"] / 2, cap_style=1)
        elif x["kind"] == "via":
            g = sg.Point(x["centre"]).buffer(x["diameter_mm"] / 2, 12)
        else:
            if not x.get("shell") or len(x["shell"]) < 3:
                g = sg.Point(x["centre"]).buffer(0.3)
            else:
                g = sg.Polygon(x["shell"], x.get("holes") or [])
                g = g if g.is_valid else g.buffer(0)
        if g.intersects(win):
            geoms[(n, x["layer"])].append(g.intersection(win))

    def raster(geom):
        return shapely.contains_xy(geom, XX, YY) if not geom.is_empty else np.zeros(XX.shape, bool)

    net_r = {k: raster(so.unary_union(v)) & onb for k, v in sorted(geoms.items())}

    def free_map(probe, L):
        cls = defaultdict(lambda: np.zeros(XX.shape, bool))
        for (n, LL), m in net_r.items():
            if LL != L or n == probe:
                continue
            cls[rules21.clearance_on(probe, n, L)] |= m
        blocked = ~onb.copy()
        for c, m in cls.items():
            if m.any():
                blocked |= ndimage.distance_transform_edt(~m) * PITCH <= c + 0.1
        return ~blocked

    ia, ib = int((BOX[0] - x0) / PITCH), int((BOX[2] - x0) / PITCH)
    jb0, jb1 = int((BOX[1] - y0) / PITCH), int((BOX[3] - y0) / PITCH)
    room = {"board_sha256": d.get("board_sha256"), "layers": list(layers21.CU), "stack": str(layers21.STACKUP_PATH),
            "box": BOX, "probes": PROBES, "rows": {}}
    for pn, pr in PROBES.items():
        free = {L: free_map(pr, L)[ia:ib, jb0:jb1] for L in layers21.CU}
        row = {}
        for L in layers21.CU:
            lab, nl = ndimage.label(free[L])
            cross = bool((set(np.unique(lab[:, 0])) - {0}) & (set(np.unique(lab[:, -1])) - {0})) if nl else False
            row[L] = {"free_frac": round(float(free[L].mean()), 4), "crossing_y47_to_y60": cross}
        row["via_legal_cells"] = int(np.logical_and.reduce([free[L] for L in layers21.CU]).sum())
        room["rows"][pn] = row
        print(pn, {L: (row[L]["free_frac"], row[L]["crossing_y47_to_y60"]) for L in layers21.CU}, "via-legal", row["via_legal_cells"])
    Path(sys.argv[2]).write_text(json.dumps(room, indent=1) + "\n")


if __name__ == "__main__":
    main()
