"""Read saved KiCad geometry for retention and existing-pad probe planning.

Uses KiCad's effective shapes and filled polygons; no independent transforms.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/orientation-cooling"


def main():
    path = ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    windows = [
        ("L20", 0, 17, 3, 6),
        ("L140", 0, 137, 3, 6),
        ("R20", 237, 17, 3, 6),
        ("R80", 237, 77, 3, 6),
        ("front_stop", 0, 0, 3, 1),
        ("rear_stop", 0, 159, 3, 1),
    ]
    results = []
    for name, x, y, w, h in windows:
        box = pcbnew.BOX2I(
            pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)),
            pcbnew.VECTOR2I(pcbnew.FromMM(w), pcbnew.FromMM(h)),
        )
        shape = pcbnew.SHAPE_RECT(box)
        hits = []
        for layer in [pcbnew.F_Cu, pcbnew.B_Cu]:
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.IsOnLayer(layer) and pad.GetEffectiveShape(layer).Collide(shape):
                        hits.append(
                            f"{fp.GetReference()}.{pad.GetNumber()} {board.GetLayerName(layer)}"
                        )
            for track in board.GetTracks():
                if track.IsOnLayer(layer) and track.GetBoundingBox().Intersects(box):
                    hits.append(
                        f"{track.GetNetname()} {board.GetLayerName(layer)} {track.m_Uuid.AsString()}"
                    )
            for zone in board.Zones():
                if zone.IsOnLayer(layer) and zone.GetFilledPolysList(layer).Collide(shape):
                    hits.append(f"zone {zone.GetNetname()} {board.GetLayerName(layer)}")
        results.append(
            {
                "name": name,
                "rectangle_mm": [x, y, w, h],
                "rigid_world_xy_bounds": [129.5 - x - w, 162 + y, 129.5 - x, 162 + y + h],
                "copper_hits": hits,
                "nominal_outer_copper_clear": not hits,
            }
        )
    receipt = {
        "board_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "method": "KiCad effective pad shape; conservative track bounding box; whole saved filled copper polygon vs rectangle; both outer layers. Zero added clearance.",
        "windows": results,
        "limitation": "Contact geometry only. Does not qualify insulation, creepage, tolerances, loading or energized operation.",
    }
    (OUT / "native-contact-screen.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
