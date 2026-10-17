#!/usr/bin/env python3
"""Export actual KiCad power-net copper primitives for raster-topology audit.

Run with KiCad's Python. Pads and zones use KiCad's effective polygons; drills
are retained separately so a consumer can subtract the physical voids.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import pcbnew as p


NETS = {"bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b", "res_a", "coil_feed"}
LAYERS = (p.F_Cu, p.In1_Cu, p.In2_Cu, p.B_Cu)


def polygon_set(q: p.SHAPE_POLY_SET) -> list[dict]:
    mm = p.ToMM
    result = []
    for i in range(q.OutlineCount()):
        o = q.Outline(i)
        shell = [[mm(o.CPoint(j).x), mm(o.CPoint(j).y)] for j in range(o.PointCount())]
        holes = []
        for k in range(q.HoleCount(i)):
            h = q.Hole(i, k)
            holes.append([[mm(h.CPoint(j).x), mm(h.CPoint(j).y)] for j in range(h.PointCount())])
        result.append({"shell": shell, "holes": holes})
    return result


def export(board_path: Path) -> dict:
    board = p.LoadBoard(str(board_path))
    mm = p.ToMM
    primitives = []
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname() not in NETS:
            continue
        for lid in LAYERS:
            if zone.IsOnLayer(lid):
                for shape in polygon_set(zone.GetFilledPolysList(lid)):
                    primitives.append({"kind": "zone", "net": zone.GetNetname(),
                                       "layer": board.GetLayerName(lid), **shape})
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() not in NETS:
                continue
            xy = [mm(pad.GetPosition().x), mm(pad.GetPosition().y)]
            drill = [mm(pad.GetDrillSize().x), mm(pad.GetDrillSize().y)]
            for lid in LAYERS:
                if pad.IsOnLayer(lid):
                    for shape in polygon_set(pad.GetEffectivePolygon(lid)):
                        primitives.append({"kind": "pad", "ref": f"{fp.GetReference()}.{pad.GetNumber()}",
                                           "net": pad.GetNetname(), "layer": board.GetLayerName(lid),
                                           "centre": xy, "drill_mm": drill, **shape})
    for item in board.GetTracks():
        if item.GetNetname() not in NETS:
            continue
        if item.Type() == p.PCB_VIA_T:
            via = p.Cast_to_PCB_VIA(item)
            xy = [mm(via.GetPosition().x), mm(via.GetPosition().y)]
            for lid in LAYERS:
                if via.IsOnLayer(lid):
                    primitives.append({"kind": "via", "net": via.GetNetname(),
                                       "layer": board.GetLayerName(lid), "centre": xy,
                                       "diameter_mm": mm(via.GetWidth(lid)),
                                       "drill_mm": mm(via.GetDrillValue())})
        else:
            lid = item.GetLayer()
            primitives.append({"kind": "track", "net": item.GetNetname(),
                               "layer": board.GetLayerName(lid),
                               "start": [mm(item.GetStart().x), mm(item.GetStart().y)],
                               "end": [mm(item.GetEnd().x), mm(item.GetEnd().y)],
                               "width_mm": mm(item.GetWidth())})
    return {"board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
            "primitives": primitives}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_power_copper.py <board.kicad_pcb> <output.json.gz>")
    data = export(Path(sys.argv[1]).resolve())
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    with open(sys.argv[2], "wb") as out:
        with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw)
    print(json.dumps({"board_sha256": data["board_sha256"],
                      "primitives": len(data["primitives"]), "uncompressed_bytes": len(raw)}))


if __name__ == "__main__":
    main()
