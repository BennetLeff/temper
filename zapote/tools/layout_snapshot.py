#!/usr/bin/env python3
"""Read-only KiCad facts for Rust layout checks. No engineering rules or scores.

Use KiCad's Python runtime. World geometry and connectivity come from pcbnew;
Rust owns net selection, path reconstruction, metric calculation and coverage.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pcbnew as p
import wx


def xy(point: Any) -> list[float]:
    return [p.ToMM(point.x), p.ToMM(point.y)]


def polygons(polyset: Any) -> list[dict[str, Any]]:
    shapes = p.SHAPE_POLY_SET(polyset)
    shapes.Unfracture()
    def ring(chain):
        return [xy(chain.CPoint(i)) for i in range(chain.PointCount())]
    return [{"shell": ring(shapes.Outline(i)),
             "holes": [ring(shapes.Hole(i, j)) for j in range(shapes.HoleCount(i))]}
            for i in range(shapes.OutlineCount())]


def pad_polygons(pad: Any, layer: int) -> list[dict[str, Any]]:
    copper = p.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(copper, layer, 0, 1000, p.ERROR_INSIDE)
    drill = p.SHAPE_POLY_SET()
    pad.TransformHoleToPolygon(drill, 0, 1000, p.ERROR_OUTSIDE)
    copper.BooleanSubtract(drill)
    return polygons(copper)


def extract(path: Path) -> dict[str, Any]:
    before = path.read_bytes()
    board = p.LoadBoard(str(path))
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    layers = list(board.GetEnabledLayers().CuStack())
    components, pads, tracks, vias, copper, gaps = [], [], [], [], [], []
    zone_count = 0
    for fp in board.GetFootprints():
        for item in fp.GraphicalItems():
            if any(item.IsOnLayer(layer) for layer in layers):
                gaps.append(item.m_Uuid.AsString() + ": unsupported footprint copper graphic")
        fp.BuildCourtyardCaches()
        ref = fp.GetReference()
        courtyards = []
        for layer in (p.F_CrtYd, p.B_CrtYd):
            shapes = polygons(fp.GetCourtyard(layer))
            if shapes:
                courtyards.append({"side": p.LayerName(layer), "polygons": shapes})
        components.append({"reference": ref, "uuid": fp.m_Uuid.AsString(),
                           "position_mm": xy(fp.GetPosition()),
                           "courtyards": courtyards})
        for pad in fp.Pads():
            uid = pad.m_Uuid.AsString()
            flashed = [layer for layer in layers if pad.IsOnLayer(layer) and pad.FlashLayer(layer)]
            if pad.GetAttribute() == p.PAD_ATTRIB_NPTH:
                continue
            pads.append({"uuid": uid, "reference": ref, "number": pad.GetNumber(),
                         "net": pad.GetNetname(), "position_mm": xy(pad.GetPosition()),
                         "layers": [board.GetLayerName(layer) for layer in flashed]})
            for layer in flashed:
                copper.append({"uuid": uid, "kind": "pad", "net": pad.GetNetname(),
                               "layer": board.GetLayerName(layer),
                               "polygons": pad_polygons(pad, layer)})

    for item in board.GetTracks():
        uid = item.m_Uuid.AsString()
        if item.Type() == p.PCB_VIA_T:
            vias.append({"uuid": uid, "net": item.GetNetname(),
                         "position_mm": xy(item.GetPosition()),
                         "layers": [board.GetLayerName(layer) for layer in layers if item.IsOnLayer(layer)]})
        elif item.GetClass() == "PCB_TRACK":
            tracks.append({"uuid": uid, "net": item.GetNetname(),
                           "layer": board.GetLayerName(item.GetLayer()),
                           "start_mm": xy(item.GetStart()), "end_mm": xy(item.GetEnd()),
                           "width_mm": p.ToMM(item.GetWidth()), "length_mm": p.ToMM(item.GetLength()),
                           "start_contacts": [v.m_Uuid.AsString() for v in connectivity.GetConnectedPads(item) if v.HitTest(item.GetStart())],
                           "end_contacts": [v.m_Uuid.AsString() for v in connectivity.GetConnectedPads(item) if v.HitTest(item.GetEnd())]})
        else:
            gaps.append(uid + ": unsupported routed item " + item.GetClass())
        for layer in layers:
            if not item.IsOnLayer(layer) or (item.Type() == p.PCB_VIA_T and not item.FlashLayer(layer)):
                continue
            shape = p.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(shape, layer, 0, 1000, p.ERROR_INSIDE)
            if item.Type() == p.PCB_VIA_T:
                hole = p.SHAPE_POLY_SET()
                item.GetEffectiveHoleShape().TransformToPolygon(hole, 1000, p.ERROR_OUTSIDE)
                shape.BooleanSubtract(hole)
            copper.append({"uuid": uid, "kind": "via" if item.Type() == p.PCB_VIA_T else "track",
                           "net": item.GetNetname(), "layer": board.GetLayerName(layer),
                           "polygons": polygons(shape)})
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        zone_count += 1
        for layer in layers:
            if not zone.IsOnLayer(layer):
                continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
                gaps.append(zone.m_Uuid.AsString() + ": missing saved zone fill")
                continue
            copper.append({"uuid": zone.m_Uuid.AsString(), "kind": "zone", "net": zone.GetNetname(),
                           "layer": board.GetLayerName(layer),
                           "polygons": polygons(zone.GetFilledPolysList(layer))})
    for item in board.GetDrawings():
        if any(item.IsOnLayer(layer) for layer in layers):
            gaps.append(item.m_Uuid.AsString() + ": unsupported board copper graphic")
    if path.read_bytes() != before:
        raise ValueError("board changed during extraction")
    return {"schema": "zapote.layout-native.v1", "board_sha256": hashlib.sha256(before).hexdigest(),
            "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "tool_version": p.Version(), "polygon_error_mm": 0.001,
            "layers": [board.GetLayerName(layer) for layer in layers],
            "components": components, "pads": pads, "tracks": tracks, "vias": vias,
            "copper": copper, "zone_count": zone_count, "gaps": gaps}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: layout_snapshot.py BOARD.kicad_pcb")
    app = wx.App(False)
    print(json.dumps(extract(Path(sys.argv[1]).resolve()), allow_nan=False))
    del app


if __name__ == "__main__":
    main()
