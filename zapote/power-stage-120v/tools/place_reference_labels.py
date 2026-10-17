#!/usr/bin/env python3
"""Choose collision-free designator positions at the fabricator legend minimum.

    KICAD_PY tools/place_reference_labels.py <board> reference-labels.json --output reference-labels.json

Every reference is set to 1.0 mm text with a 0.15 mm stroke (the JLCPCB
legend minimum). A position already in the label file is kept if the label
there clears every pad, silkscreen graphic, other label and the board edge.
Otherwise, and for any reference without a position, it searches rings around
the footprint courtyard and takes the first clear spot. The spot must be
within 4 mm of the courtyard, which is what tests/test_reference_labels.py
enforces. Only label positions are written; electrical geometry is untouched.
Labels with no clear spot are reported and keep their old position, so the
board's DRC shows them.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pcbnew

SIZE_MM = 1.0
THICKNESS_MM = 0.15
PAD_GAP_MM = 0.2        # JLCPCB pad-to-silkscreen >= 0.15 mm, plus margin
SILK_GAP_MM = 0.15
EDGE_GAP_MM = 0.6
MAX_COURTYARD_GAP_MM = 3.8


def mm(v: float) -> float:
    return pcbnew.ToMM(v)


# Plain geometry (KiCad's Python has no shapely): boxes are (x0, y0, x1, y1).
def rect(bb: pcbnew.BOX2I, grow: float = 0.0):
    return (mm(bb.GetX()) - grow, mm(bb.GetY()) - grow, mm(bb.GetRight()) + grow, mm(bb.GetBottom()) + grow)


def boxes_overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def box_gap(a, b) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def point_box_dist(px, py, b) -> float:
    return math.hypot(max(b[0] - px, 0.0, px - b[2]), max(b[1] - py, 0.0, py - b[3]))


def segment_hits_box(seg, b) -> bool:
    """True when a thick segment (x0, y0, x1, y1, r) comes within r of box b."""
    x0, y0, x1, y1, r = seg
    n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.1) + 1)
    return any(point_box_dist(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, b) < r
               for i in range(n + 1))


def silk_obstacles(board: pcbnew.BOARD):
    """Footprint F.Silkscreen graphics: thick segments and boxes."""
    segments, boxes = [], []
    for fp in board.GetFootprints():
        for item in fp.GraphicalItems():
            if item.GetLayer() != pcbnew.F_SilkS:
                continue
            if isinstance(item, pcbnew.PCB_SHAPE) and item.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                a, b = item.GetStart(), item.GetEnd()
                segments.append((mm(a.x), mm(a.y), mm(b.x), mm(b.y), mm(item.GetWidth()) / 2 + SILK_GAP_MM))
            elif isinstance(item, pcbnew.PCB_SHAPE):
                boxes.append(rect(item.GetBoundingBox(), SILK_GAP_MM))
            elif isinstance(item, pcbnew.PCB_TEXT) and item.IsVisible():   # e.g. polarity "K"
                boxes.append(rect(item.GetBoundingBox(), SILK_GAP_MM))
        if fp.Value().IsVisible() and fp.Value().GetLayer() == pcbnew.F_SilkS:
            boxes.append(rect(fp.Value().GetBoundingBox(), SILK_GAP_MM))
    return segments, boxes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(args.board), None)
    data = json.loads(args.labels.read_text())
    refs = data["references"]
    edge = rect(board.GetBoardEdgesBoundingBox(), -EDGE_GAP_MM)
    pads = [rect(p.GetBoundingBox(), PAD_GAP_MM)
            for fp in board.GetFootprints() for p in fp.Pads()
            if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask)]
    silk_segments, silk_boxes = silk_obstacles(board)
    placed: dict[str, tuple] = {}

    def label_box(fp, x: float, y: float):
        ref = fp.Reference()
        ref.SetLayer(pcbnew.F_SilkS)
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(SIZE_MM), pcbnew.FromMM(SIZE_MM)))
        ref.SetTextThickness(pcbnew.FromMM(THICKNESS_MM))
        ref.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        return rect(ref.GetBoundingBox())

    def clear(name: str, shape) -> bool:
        if not (edge[0] <= shape[0] and edge[1] <= shape[1] and shape[2] <= edge[2] and shape[3] <= edge[3]):
            return False
        if any(boxes_overlap(shape, p) for p in pads + silk_boxes):
            return False
        near = [s for s in silk_segments
                if min(s[0], s[2]) - s[4] < shape[2] and max(s[0], s[2]) + s[4] > shape[0]
                and min(s[1], s[3]) - s[4] < shape[3] and max(s[1], s[3]) + s[4] > shape[1]]
        if any(segment_hits_box(s, shape) for s in near):
            return False
        return not any(box_gap(shape, o) < SILK_GAP_MM for k, o in placed.items() if k != name)

    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    missing = sorted(set(fps) - set(refs))
    order = [r for r in sorted(fps) if r in refs] + missing   # keep authored ones first
    moved, unresolved = [], []
    for name in order:
        fp = fps[name]
        court = rect(fp.GetCourtyard(pcbnew.F_CrtYd).BBox())
        cx, cy = (court[0] + court[2]) / 2, (court[1] + court[3]) / 2
        candidates = []
        if name in refs:
            candidates.append(tuple(refs[name]["at"]))
        hw = (court[2] - court[0]) / 2
        hh = (court[3] - court[1]) / 2
        for off in (0.7, 0.9, 1.2, 1.4, 1.7, 2.0, 2.4, 2.7, 3.0, 3.4):
            for ang in range(0, 360, 15):
                t = math.radians(ang)
                candidates.append((cx + math.cos(t) * (hw + off), cy + math.sin(t) * (hh + off)))
        chosen = None
        for x, y in candidates:
            shape = label_box(fp, x, y)
            if box_gap(shape, court) > MAX_COURTYARD_GAP_MM:
                continue
            if clear(name, shape):
                chosen = (round(x, 3), round(y, 3), shape)
                break
        if chosen is None:
            unresolved.append(name)
            x, y = refs.get(name, {"at": [cx, cy]})["at"]
            chosen = (x, y, label_box(fp, x, y))
        if name in refs and tuple(refs[name]["at"]) != chosen[:2]:
            moved.append(name)
        placed[name] = chosen[2]
        refs[name] = {"at": [chosen[0], chosen[1]], "layer": "F.SilkS",
                      "size": SIZE_MM, "thickness": THICKNESS_MM}
    data["references"] = dict(sorted(refs.items()))
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"references": len(refs), "added": missing, "moved": moved,
                      "unresolved": unresolved}, indent=1))


if __name__ == "__main__":
    main()
