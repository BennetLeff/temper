"""Read actual KiCad mask openings and candidate contact geometry.

A fixture-planning screen, not a qualified probe/voltage or assembly test.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "native-19"


def main():
    spec = json.loads((HERE / "probe-access.json").read_text())
    path = OUT / "section.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    rows = []
    for signal in spec["signals"]:
        contacts = []
        for role in ["pad", "reference"]:
            ref, pin = signal[role].split(".")
            fp = fps[ref]
            pad = next(p for p in fp.Pads() if p.GetNumber() == pin)
            side = signal["side"]
            mask = pcbnew.F_Mask if side == "F" else pcbnew.B_Mask
            center = pad.GetPosition()
            box = pad.GetBoundingBox()
            origin = fp.GetPosition()
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                # Choose an annulus point away from the plated drill. Package bodies are on F.Cu.
                pos = pcbnew.VECTOR2I(
                    center.x + pad.GetDrillSize().x // 2 + pcbnew.FromMM(0.2), center.y
                )
            elif abs(center.x - origin.x) > abs(center.y - origin.y):
                pos = pcbnew.VECTOR2I(
                    box.GetRight() - pcbnew.FromMM(0.2)
                    if center.x >= origin.x
                    else box.GetLeft() + pcbnew.FromMM(0.2),
                    center.y,
                )
            else:
                pos = pcbnew.VECTOR2I(
                    center.x,
                    box.GetBottom() - pcbnew.FromMM(0.2)
                    if center.y >= origin.y
                    else box.GetTop() + pcbnew.FromMM(0.2),
                )
            fab_layer = pcbnew.F_Fab if side == "F" else pcbnew.B_Fab
            fab_boxes = [
                g.GetBoundingBox() for g in fp.GraphicalItems() if g.GetLayer() == fab_layer
            ]
            outside_body = True
            if fab_boxes:
                x0 = min(b.GetLeft() for b in fab_boxes)
                x1 = max(b.GetRight() for b in fab_boxes)
                y0 = min(b.GetTop() for b in fab_boxes)
                y1 = max(b.GetBottom() for b in fab_boxes)
                margin = pcbnew.FromMM(0.1)
                outside_body = (
                    pos.x + margin < x0
                    or pos.x - margin > x1
                    or pos.y + margin < y0
                    or pos.y - margin > y1
                )
            contacts.append(
                {
                    "role": role,
                    "reference_pin": signal[role],
                    "net": pad.GetNetname(),
                    "mask_open": pad.IsOnLayer(mask),
                    "pad_center_mm": [pcbnew.ToMM(center.x), pcbnew.ToMM(center.y)],
                    "contact_center_mm": [pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)],
                    "contact_diameter_mm": spec["contact_diameter_mm"],
                    "outside_same_side_fab_body_bbox": outside_body,
                    "pad_bbox_mm": [
                        pcbnew.ToMM(box.GetLeft()),
                        pcbnew.ToMM(box.GetTop()),
                        pcbnew.ToMM(box.GetWidth()),
                        pcbnew.ToMM(box.GetHeight()),
                    ],
                }
            )
        a, b = [x["contact_center_mm"] for x in contacts]
        rows.append(
            {
                **signal,
                "contacts": contacts,
                "tip_separation_mm": math.hypot(a[0] - b[0], a[1] - b[1]),
            }
        )
    receipt = {
        "board_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "service_state": spec["state"],
        "status": "Candidate points only; copper/tip containment and actual mask-aperture containment NOT_CHECKED.",
        "screen": "Mask layer membership and selected toe/annulus geometry from pcbnew; same-side Fab bounding box excludes obvious body obstruction. Neighbor hardware, solder meniscus, touch safety and fixture tolerances still require physical fit review.",
        "signals": rows,
        "physical": "NOT_RUN",
    }
    (OUT / "verification/probe-access.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "signals": len(rows),
                "mask_closed": [
                    c["reference_pin"] for r in rows for c in r["contacts"] if not c["mask_open"]
                ],
                "body_bbox_conflicts": [
                    c["reference_pin"]
                    for r in rows
                    for c in r["contacts"]
                    if not c["outside_same_side_fab_body_bbox"]
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
