#!/usr/bin/env python3
"""Export KiCad copper actually flashed on each layer for D1.

KiCad's IsOnLayer and GetEffectivePolygon can describe a nominal through-hole
pad on an internal layer even when remove-unconnected has suppressed the pad.
FlashLayer is the required conductive-presence gate. Filled zone contours are
unfractured in memory so the export has explicit valid hole rings.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pcbnew as pcb

EXPECTED_BOARD_SHA256 = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
LAYERS = (pcb.F_Cu, pcb.In1_Cu, pcb.In2_Cu, pcb.B_Cu)


def polygon_set(shape: pcb.SHAPE_POLY_SET) -> list[dict]:
    # Unfracture converts KiCad's bridge-connected contours to explicit hole
    # rings; raw Outline(i) can otherwise self-touch and confuse Shapely.
    q = shape.CloneDropTriangulation()
    q.Unfracture()
    result = []
    for i in range(q.OutlineCount()):
        outer = q.Outline(i)
        shell = [[pcb.ToMM(outer.CPoint(j).x), pcb.ToMM(outer.CPoint(j).y)]
                 for j in range(outer.PointCount())]
        holes = []
        for h in range(q.HoleCount(i)):
            ring = q.Hole(i,h)
            holes.append([[pcb.ToMM(ring.CPoint(j).x), pcb.ToMM(ring.CPoint(j).y)]
                          for j in range(ring.PointCount())])
        result.append({"shell":shell,"holes":holes})
    return result


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--board",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    board_path=args.board.resolve(strict=True)
    board_hash=hashlib.sha256(board_path.read_bytes()).hexdigest()
    if board_hash!=EXPECTED_BOARD_SHA256:
        raise ValueError(f"board hash changed: {board_hash}")
    board=pcb.LoadBoard(str(board_path))
    primitives=[]
    barrels=[]
    suppressed_pads=[]
    suppressed_vias=[]
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.GetNetname():
            continue
        for lid in LAYERS:
            if not zone.IsOnLayer(lid):
                continue
            for poly in polygon_set(zone.GetFilledPolysList(lid)):
                primitives.append({"kind":"zone","net":zone.GetNetname(),
                                   "layer":board.GetLayerName(lid),"zone_uuid":zone.m_Uuid.AsString(),**poly})
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if not pad.GetNetname():
                continue
            centre=[pcb.ToMM(pad.GetPosition().x),pcb.ToMM(pad.GetPosition().y)]
            drill=[pcb.ToMM(pad.GetDrillSize().x),pcb.ToMM(pad.GetDrillSize().y)]
            flashed_layers=[board.GetLayerName(lid) for lid in LAYERS if pad.IsOnLayer(lid) and pad.FlashLayer(lid)]
            if pad.GetAttribute()==pcb.PAD_ATTRIB_PTH and min(drill)>0:
                barrels.append({"kind":"pad","ref":f"{footprint.GetReference()}.{pad.GetNumber()}",
                                "net":pad.GetNetname(),"centre":centre,"drill_mm":drill,
                                "flashed_layers":flashed_layers,"physical_span_layers":["F.Cu","B.Cu"],
                                "component_side":board.GetLayerName(footprint.GetLayer())})
            for lid in LAYERS:
                if not pad.IsOnLayer(lid):
                    continue
                if not pad.FlashLayer(lid):
                    suppressed_pads.append({"ref":f"{footprint.GetReference()}.{pad.GetNumber()}",
                                            "net":pad.GetNetname(),"layer":board.GetLayerName(lid)})
                    continue
                for poly in polygon_set(pad.GetEffectivePolygon(lid)):
                    primitives.append({"kind":"pad","ref":f"{footprint.GetReference()}.{pad.GetNumber()}",
                                       "net":pad.GetNetname(),"layer":board.GetLayerName(lid),
                                       "centre":centre,"drill_mm":drill,**poly})
    for item in board.GetTracks():
        if not item.GetNetname():
            continue
        if item.Type()==pcb.PCB_VIA_T:
            via=pcb.Cast_to_PCB_VIA(item)
            centre=[pcb.ToMM(via.GetPosition().x),pcb.ToMM(via.GetPosition().y)]
            barrels.append({"kind":"via","net":via.GetNetname(),"centre":centre,
                            "drill_mm":pcb.ToMM(via.GetDrillValue()),
                            "flashed_layers":[board.GetLayerName(lid) for lid in LAYERS if via.IsOnLayer(lid) and via.FlashLayer(lid)],
                            "physical_span_layers":[board.GetLayerName(via.TopLayer()),board.GetLayerName(via.BottomLayer())]})
            for lid in LAYERS:
                if not via.IsOnLayer(lid):
                    continue
                if not via.FlashLayer(lid):
                    suppressed_vias.append({"net":via.GetNetname(),"layer":board.GetLayerName(lid),"centre":centre})
                    continue
                primitives.append({"kind":"via","net":via.GetNetname(),"layer":board.GetLayerName(lid),
                                   "centre":centre,"diameter_mm":pcb.ToMM(via.GetWidth(lid)),
                                   "drill_mm":pcb.ToMM(via.GetDrillValue())})
        else:
            lid=item.GetLayer()
            if lid not in LAYERS:
                continue
            primitives.append({"kind":"track","net":item.GetNetname(),"layer":board.GetLayerName(lid),
                               "start":[pcb.ToMM(item.GetStart().x),pcb.ToMM(item.GetStart().y)],
                               "end":[pcb.ToMM(item.GetEnd().x),pcb.ToMM(item.GetEnd().y)],
                               "width_mm":pcb.ToMM(item.GetWidth())})
    data={"board_sha256":board_hash,"kicad_version":pcb.Version(),
          "exporter_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "primitive_count":len(primitives),"suppressed_pad_layer_count":len(suppressed_pads),
          "suppressed_via_layer_count":len(suppressed_vias),"suppressed_pads":suppressed_pads,
          "suppressed_vias":suppressed_vias,"barrels":barrels,"primitives":primitives}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,separators=(",",":"),allow_nan=False).encode()
    with args.output.open("wb") as out:
        with gzip.GzipFile(fileobj=out,mode="wb",filename="",mtime=0) as stream:
            stream.write(raw)
    print(json.dumps({"board_sha256":board_hash,"primitive_count":len(primitives),
                      "suppressed_pad_layer_count":len(suppressed_pads),
                      "suppressed_via_layer_count":len(suppressed_vias),
                      "physical_barrel_count":len(barrels),
                      "output_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest()},indent=2))


if __name__=="__main__":
    main()
