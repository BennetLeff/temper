#!/usr/bin/env python3
"""Export a board-bound census of supported, filled KiCad copper geometry.

Run with KiCad Python after `kicad-cli pcb drc --refill-zones --save-board`:

    KICAD_PY tools/copper_dump.py <board> <out.json>

The adapter rejects geometry it cannot represent conservatively. The Rust
board/stackup and KiCad DRC gates remain separate acceptance checks.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

SCHEMA = "temper.power-stage-120v.copper-evidence.v1"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def dump(board_path: Path) -> dict:
    board_path = board_path.resolve()
    board_sha256 = hashlib.sha256(board_path.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(board_path))
    mm = pcbnew.ToMM
    copper = list(board.GetEnabledLayers().CuStack())
    names = {lid: board.GetLayerName(lid) for lid in copper}
    if not copper:
        raise ValueError("board has no enabled copper layers")
    items = []
    zone_count = 0
    footprints = list(board.GetFootprints())

    # Non-pad copper graphics have no net classification in this adapter.
    for graphic in board.GetDrawings():
        if any(graphic.IsOnLayer(lid) for lid in copper):
            raise ValueError(f"unsupported board copper graphic: {graphic.GetClass()}")
    for fp in footprints:
        for graphic in fp.GraphicalItems():
            if any(graphic.IsOnLayer(lid) for lid in copper):
                raise ValueError(f"unsupported footprint copper graphic: {fp.GetReference()} {graphic.GetClass()}")
        for pad in fp.Pads():
            layers = [names[lid] for lid in copper if pad.IsOnLayer(lid)]
            if not layers:
                continue
            # NPTH mounting holes are represented by their drilled absence, not copper.
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if not pad.GetNetname():
                raise ValueError(f"unclassified copper pad: {fp.GetReference()}.{pad.GetNumber()}")
            bb = pad.GetBoundingBox()
            items.append({"kind": "pad", "ref": f"{fp.GetReference()}.{pad.GetNumber()}",
                          "net": pad.GetNetname(), "layers": layers,
                          "box": [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]})

    for track in board.GetTracks():
        if track.Type() == pcbnew.PCB_VIA_T:
            via = pcbnew.Cast_to_PCB_VIA(track)
            if via.GetViaType() != pcbnew.VIATYPE_THROUGH:
                raise ValueError(f"unsupported non-through via on {via.GetNetname()}")
            if not via.GetNetname():
                raise ValueError("unclassified copper via")
            pos = via.GetPosition()
            items.append({"kind": "via", "net": via.GetNetname(), "layers": list(names.values()),
                          "centre": [mm(pos.x), mm(pos.y)],
                          "radius": max(mm(via.GetWidth(lid)) for lid in copper) / 2})
        elif track.GetClass() == "PCB_TRACK":
            if track.GetLayer() not in names:
                raise ValueError(f"track lies on disabled copper layer: {track.GetLayerName()}")
            if not track.GetNetname():
                raise ValueError("unclassified copper track")
            items.append({"kind": "track", "net": track.GetNetname(), "layers": [names[track.GetLayer()]],
                          "start": [mm(track.GetStart().x), mm(track.GetStart().y)],
                          "end": [mm(track.GetEnd().x), mm(track.GetEnd().y)],
                          "width": mm(track.GetWidth())})
        else:
            raise ValueError(f"unsupported copper track shape: {track.GetClass()}")

    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        zone_layers = [lid for lid in copper if zone.IsOnLayer(lid)]
        if not zone_layers:
            raise ValueError("zone lies on no enabled copper layer")
        if not zone.GetNetname():
            raise ValueError("unclassified copper zone")
        if not zone.IsFilled():
            raise ValueError(f"unfilled copper zone: {zone.GetNetname()}")
        zone_count += 1
        for lid in zone_layers:
            if not zone.HasFilledPolysForLayer(lid):
                raise ValueError(f"zone lacks fill on {names[lid]}: {zone.GetNetname()}")
            polys = zone.GetFilledPolysList(lid)
            if polys.OutlineCount() == 0:
                raise ValueError(f"zone has no filled polygons on {names[lid]}: {zone.GetNetname()}")
            for i in range(polys.OutlineCount()):
                outline = polys.Outline(i)
                pts = [[mm(outline.CPoint(j).x), mm(outline.CPoint(j).y)]
                       for j in range(outline.PointCount())]
                if len(pts) < 3:
                    raise ValueError(f"degenerate filled zone: {zone.GetNetname()}")
                # Holes are deliberately filled in this approximation, so it
                # overstates copper and cannot hide a barrier violation.
                items.append({"kind": "zone", "net": zone.GetNetname(), "layers": [names[lid]],
                              "polygon": pts})

    counts = Counter(item["kind"] for item in items)
    census = {"footprints": len(footprints), "pads": counts["pad"],
              "tracks": counts["track"], "vias": counts["via"], "zones": zone_count,
              "filled_zone_polygons": counts.get("zone", 0), "items": len(items)}
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != board_sha256:
        raise ValueError("board changed during copper extraction")
    return {"schema": SCHEMA, "board_path": str(board_path),
            "board_sha256": board_sha256,
            "copper_layers": list(names.values()), "census": census,
            "items_sha256": digest(items), "items": items}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: copper_dump.py <filled-board> <out.json>")
    evidence = dump(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(evidence, indent=1, allow_nan=False) + "\n")
    print(json.dumps({"board_sha256": evidence["board_sha256"], "census": evidence["census"]}))


if __name__ == "__main__":
    main()
