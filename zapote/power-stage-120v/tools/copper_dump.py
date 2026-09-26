#!/usr/bin/env python3
"""Dump every copper item (pads, tracks, vias, filled zones) with net and layer.

Run under KiCad's Python on a board whose zones are filled (for example the
board saved by `kicad-cli pcb drc --refill-zones --save-board`):

    KICAD_PY tools/copper_dump.py <board> <out.json>

Feeds tools/barrier_check.py, which KiCad's own DRC cannot replace: KiCad
checks clearance only within one copper layer.
"""

from __future__ import annotations

import json
import sys

import pcbnew  # type: ignore[import-not-found]


def main() -> None:
    board = pcbnew.LoadBoard(sys.argv[1])
    mm = pcbnew.ToMM
    copper = [lid for lid in board.GetEnabledLayers().CuStack()]
    names = {lid: board.GetLayerName(lid) for lid in copper}
    items = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not pad.GetNetname():
                continue
            bb = pad.GetBoundingBox()
            layers = [names[lid] for lid in copper if pad.IsOnLayer(lid)]
            items.append({"kind": "pad", "ref": f"{fp.GetReference()}.{pad.GetNumber()}",
                          "net": pad.GetNetname(), "layers": layers,
                          "box": [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]})
    for track in board.GetTracks():
        if track.Type() == pcbnew.PCB_VIA_T:
            via = pcbnew.Cast_to_PCB_VIA(track)
            pos = via.GetPosition()
            items.append({"kind": "via", "net": via.GetNetname(), "layers": list(names.values()),
                          "centre": [mm(pos.x), mm(pos.y)], "radius": mm(via.GetWidth(pcbnew.F_Cu)) / 2})
        else:
            items.append({"kind": "track", "net": track.GetNetname(), "layers": [names[track.GetLayer()]],
                          "start": [mm(track.GetStart().x), mm(track.GetStart().y)],
                          "end": [mm(track.GetEnd().x), mm(track.GetEnd().y)],
                          "width": mm(track.GetWidth())})
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.GetNetname():
            continue
        for lid in copper:
            if not zone.IsOnLayer(lid):
                continue
            polys = zone.GetFilledPolysList(lid)
            for i in range(polys.OutlineCount()):
                outline = polys.Outline(i)
                pts = [[mm(outline.CPoint(j).x), mm(outline.CPoint(j).y)] for j in range(outline.PointCount())]
                if len(pts) >= 3:
                    items.append({"kind": "zone", "net": zone.GetNetname(), "layers": [names[lid]],
                                  "polygon": pts})
    json.dump(items, open(sys.argv[2], "w"))


if __name__ == "__main__":
    main()
