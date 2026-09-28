#!/usr/bin/env python3
"""Export the power nets' copper as it is actually fabricated.

    KICAD_PY tools/export_power_copper.py <board.kicad_pcb> <output.json.gz>

For copper-current and thermal work (validation task 04 and the sheet
solver). Output format matches validation-results/04-board-current-thermal/
round2/scripts/extract_power_copper.py, with two corrections:

- Pads and vias are exported only on layers where KiCad flashes them
  (``FlashLayer``). ``IsOnLayer`` also reports rings that
  remove_unused_layers suppresses, which added copper that isn't fabricated.
- Zone fills are unfractured so their holes come out as explicit rings.

Drill bores stay in each item's ``drill_mm``/``centre``; the sheet solver
subtracts them from the final per-layer union. ``tools/copper_dump.py``
still over-counts suppressed rings; that is conservative for the barrier
check, which is its purpose.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import pcbnew as p  # type: ignore[import-not-found]

NETS = {"bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b", "res_a", "coil_feed",
        "ac_l_in", "ac_n_in", "l_f", "l_filt", "n_filt", "rect_p", "rect_n"}
LAYERS = (p.F_Cu, p.In1_Cu, p.In2_Cu, p.B_Cu)


def polygon_set(shape: p.SHAPE_POLY_SET) -> list[dict]:
    q = shape.CloneDropTriangulation()
    q.Unfracture()
    mm = p.ToMM
    result = []
    for i in range(q.OutlineCount()):
        o = q.Outline(i)
        shell = [[mm(o.CPoint(j).x), mm(o.CPoint(j).y)] for j in range(o.PointCount())]
        holes = [[[mm(h.CPoint(j).x), mm(h.CPoint(j).y)] for j in range(h.PointCount())]
                 for h in (q.Hole(i, k) for k in range(q.HoleCount(i)))]
        result.append({"shell": shell, "holes": holes})
    return result


def export(board_path: Path) -> dict:
    board = p.LoadBoard(str(board_path))
    mm = p.ToMM
    primitives, suppressed = [], 0
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
            ref = f"{fp.GetReference()}.{pad.GetNumber()}"
            if pad.GetAttribute() == p.PAD_ATTRIB_PTH and not (pad.FlashLayer(p.F_Cu) and pad.FlashLayer(p.B_Cu)):
                raise ValueError(f"{ref}: PTH pad without both outer lands")
            xy = [mm(pad.GetPosition().x), mm(pad.GetPosition().y)]
            drill = [mm(pad.GetDrillSize().x), mm(pad.GetDrillSize().y)]
            for lid in LAYERS:
                if not pad.IsOnLayer(lid):
                    continue
                if not pad.FlashLayer(lid):
                    suppressed += 1
                    continue
                for shape in polygon_set(pad.GetEffectivePolygon(lid)):
                    primitives.append({"kind": "pad", "ref": ref, "net": pad.GetNetname(),
                                       "layer": board.GetLayerName(lid), "centre": xy,
                                       "drill_mm": drill, **shape})
    for item in board.GetTracks():
        if item.GetNetname() not in NETS:
            continue
        if item.Type() == p.PCB_VIA_T:
            via = p.Cast_to_PCB_VIA(item)
            xy = [mm(via.GetPosition().x), mm(via.GetPosition().y)]
            for lid in LAYERS:
                if via.IsOnLayer(lid) and via.FlashLayer(lid):
                    primitives.append({"kind": "via", "net": via.GetNetname(),
                                       "layer": board.GetLayerName(lid), "centre": xy,
                                       "diameter_mm": mm(via.GetWidth(lid)),
                                       "drill_mm": mm(via.GetDrillValue())})
        else:
            primitives.append({"kind": "track", "net": item.GetNetname(),
                               "layer": board.GetLayerName(item.GetLayer()),
                               "start": [mm(item.GetStart().x), mm(item.GetStart().y)],
                               "end": [mm(item.GetEnd().x), mm(item.GetEnd().y)],
                               "width_mm": mm(item.GetWidth())})
    return {"board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
            "exporter": "tools/export_power_copper.py (FlashLayer-aware)",
            "suppressed_pad_layers": suppressed, "primitives": primitives}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_power_copper.py <board.kicad_pcb> <output.json.gz>")
    data = export(Path(sys.argv[1]).resolve())
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    with open(sys.argv[2], "wb") as out:
        with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw)
    print(json.dumps({"board_sha256": data["board_sha256"], "primitives": len(data["primitives"]),
                      "suppressed_pad_layers": data["suppressed_pad_layers"]}))


if __name__ == "__main__":
    main()
