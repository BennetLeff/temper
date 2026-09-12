#!/usr/bin/env python3
"""Read saved KiCad geometry for Rust manufacturing checks; never save or refill.

Native polygon conversion bounds curved-edge approximation to 1 micrometre.
No dimensions, fabrication limits, current ratings, or acceptance decisions
are invented by this transport.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pcbnew
import wx

ERROR_IU = 1000


def ring(chain: Any) -> dict[str, Any]:
    return {"vertices_mm": [[pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)] for p in chain.CPoints()]}


def polygons(poly_set: Any) -> list[dict[str, Any]]:
    # Native fracture retains holes with zero-area bridges instead of filling them.
    copy = pcbnew.SHAPE_POLY_SET(poly_set)
    copy.Fracture()
    return [ring(copy.Outline(i)) for i in range(copy.OutlineCount())]


def shape_polygons(item: Any, layer: int) -> list[dict[str, Any]]:
    poly_set = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(poly_set, layer, 0, ERROR_IU, pcbnew.ERROR_OUTSIDE)
    return polygons(poly_set)


def body_polygons(footprint: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Transport closed F.Fab primitives; order line endpoints without rotation."""
    result: list[dict[str, Any]] = []
    segments: list[tuple[tuple[int, int], tuple[int, int]]] = []
    gaps: list[str] = []
    for item in footprint.GraphicalItems():
        if item.GetLayer() not in (pcbnew.F_Fab, pcbnew.B_Fab) or not isinstance(item, pcbnew.PCB_SHAPE):
            continue
        kind = item.GetShapeStr()
        if kind == "Rect":
            result.append({"vertices_mm": [[pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)] for p in item.GetRectCorners()]})
        elif kind == "Polygon":
            result.extend(polygons(item.GetPolyShape()))
        elif kind == "Line":
            a, b = item.GetStart(), item.GetEnd()
            segments.append(((a.x, a.y), (b.x, b.y)))
        else:
            gaps.append(f"F.Fab {kind} body interpretation requires review")
    while segments:
        a, b = segments.pop()
        chain = [a, b]
        while chain[-1] != chain[0]:
            match = next(((i, q if p == chain[-1] else p) for i, (p, q) in enumerate(segments) if p == chain[-1] or q == chain[-1]), None)
            if match is None:
                break
            i, end = match
            segments.pop(i)
            chain.append(end)
        if chain[-1] == chain[0] and len(chain) >= 4:
            result.append({"vertices_mm": [[pcbnew.ToMM(x), pcbnew.ToMM(y)] for x, y in chain[:-1]]})
        else:
            gaps.append("open F.Fab detail lines are not a closed body polygon")
    if not result:
        gaps.append("no closed native F.Fab body polygon")
    return result, gaps


def extract(path: Path) -> dict[str, Any]:
    before = path.read_bytes()
    board = pcbnew.LoadBoard(str(path))
    enabled = list(board.GetEnabledLayers().CuStack())
    bodies, pads, holes, copper, unsupported = [], [], [], [], []
    census = {"footprints": 0, "pads": 0, "tracks": 0, "vias": 0, "zones": 0}
    for footprint in board.GetFootprints():
        census["footprints"] += 1
        ref = footprint.GetReference()
        fab, gaps = body_polygons(footprint)
        unsupported.extend(f"{ref}: {g}" for g in gaps)
        for polygon in fab:
            bodies.append({"component": ref, "local_polygon": polygon, "position_mm": [0., 0.], "rotation_deg": 0., "required": True})
        for pad in footprint.Pads():
            census["pads"] += 1
            uid = ref + "." + pad.GetNumber() + ":" + pad.m_Uuid.AsString()
            drill_set = pcbnew.SHAPE_POLY_SET()
            pad.TransformHoleToPolygon(drill_set, 0, ERROR_IU, pcbnew.ERROR_OUTSIDE)
            drills = polygons(drill_set)
            if len(drills) > 1:
                unsupported.append(uid + ": multiple drill polygons")
            drill = drills[0] if len(drills) == 1 else None
            pos = pad.GetPosition()
            if drill:
                holes.append({"id": uid, "center_mm": [pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)], "diameter_mm": pcbnew.ToMM(pad.GetDrillSize().x), "polygon": drill})
            for layer in enabled:
                if not pad.IsOnLayer(layer):
                    continue
                shapes = shape_polygons(pad, layer)
                if not shapes:
                    unsupported.append(uid + "@" + pcbnew.LayerName(layer) + ": missing copper polygon")
                for index, polygon in enumerate(shapes):
                    identity = uid + "@" + pcbnew.LayerName(layer) + f":{index}"
                    copper.append({"id": identity, "layer": pcbnew.LayerName(layer), "polygon": polygon})
                    pads.append({"id": identity, "copper": polygon, "drill_mm": None, "drill_center_mm": None, "drill_polygon": drill, "plated": pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH})
    for item in board.GetTracks():
        uid = item.m_Uuid.AsString()
        via = isinstance(item, pcbnew.PCB_VIA)
        census["vias" if via else "tracks"] += 1
        drill = None
        if via:
            # GetEffectiveHoleShape supplies the native hole, including its pose.
            hole = item.GetEffectiveHoleShape()
            poly_set = pcbnew.SHAPE_POLY_SET()
            hole.TransformToPolygon(poly_set, ERROR_IU, pcbnew.ERROR_OUTSIDE)
            drills = polygons(poly_set)
            if len(drills) == 1:
                drill = drills[0]
                p = item.GetPosition()
                holes.append({"id": uid, "center_mm": [pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)], "diameter_mm": pcbnew.ToMM(item.GetDrillValue()), "polygon": drill})
            else:
                unsupported.append(uid + ": missing native via drill polygon")
        for layer in enabled:
            if not item.IsOnLayer(layer):
                continue
            shapes = shape_polygons(item, layer)
            if not shapes:
                unsupported.append(uid + ": missing native track/via polygon")
            for index, polygon in enumerate(shapes):
                identity = uid + "@" + pcbnew.LayerName(layer) + f":{index}"
                copper.append({"id": identity, "layer": pcbnew.LayerName(layer), "polygon": polygon})
                if via:
                    pads.append({"id": identity, "copper": polygon, "drill_mm": None, "drill_center_mm": None, "drill_polygon": drill, "plated": True})
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        census["zones"] += 1
        for layer in enabled:
            if not zone.IsOnLayer(layer):
                continue
            if not zone.HasFilledPolysForLayer(layer):
                unsupported.append(zone.m_Uuid.AsString() + ": zone lacks saved filled copper")
                continue
            for index, polygon in enumerate(polygons(zone.GetFilledPolysList(layer))):
                copper.append({"id": zone.m_Uuid.AsString() + "@" + pcbnew.LayerName(layer) + f":{index}", "layer": pcbnew.LayerName(layer), "polygon": polygon})
    edges = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(edges, True) or edges.OutlineCount() != 1:
        raise ValueError("expected one closed native board outline")
    if path.read_bytes() != before:
        raise ValueError("saved PCB changed during extraction")
    return {"schema": "zapote.manufacturing-native.v1", "board_sha256": hashlib.sha256(before).hexdigest(), "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "tool_version": pcbnew.Version(), "polygon_max_error_mm": pcbnew.ToMM(ERROR_IU), "native_census": census,
            "input": {"board_id": str(path), "bodies": bodies, "pads": pads, "holes": holes, "copper": copper, "outline": ring(edges.Outline(0)), "cutouts": [ring(edges.Hole(0, i)) for i in range(edges.HoleCount(0))], "limits": {"name": "", "source": "", "qualified": False, "minimum_annular_ring_mm": 0., "minimum_hole_clearance_mm": 0., "assembly_process": ""}, "angle_policy": "Arbitrary", "unsupported": sorted(set(unsupported))}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    app = wx.App(False)
    result = extract(args.board.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream)
    del app


if __name__ == "__main__":
    main()
