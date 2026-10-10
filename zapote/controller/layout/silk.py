"""Reference designators: on F.Silkscreen where they fit, otherwise F.Fab only.

Called by layout/route.py after routing. Each footprint's reference is tried at 1.0 mm height
(JLC minimum text height, read 2026-10-09), 0.15 mm stroke, beside its courtyard (above, below,
left, right; horizontal, then rotated 90 deg). A position is accepted only if the text box keeps
0.15 mm from every pad and every other part's courtyard, does not overlap an already placed
designator or the board's own silk text, and stays 0.5 mm inside the outline and outside the
screw-head circles. Parts with no legal spot keep their designator on F.Fab (the assembly drawing
carries every designator there) and have the silk designator hidden.
"""
from __future__ import annotations

import pcbnew

H, T = 1.0, 0.15


def _rect(bb, grow=0.0):
    m = pcbnew.ToMM
    return (m(bb.GetLeft()) - grow, m(bb.GetTop()) - grow, m(bb.GetRight()) + grow, m(bb.GetBottom()) + grow)


def _ov(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def run(board, holes_k, keepout_r):
    pads, crt = [], {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pads.append(_rect(p.GetBoundingBox(), 0.15))
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        crt[fp.GetReference()] = _rect(cy.BBox()) if cy.OutlineCount() else _rect(fp.GetBoundingBox(False))
    taken = [_rect(d.GetBoundingBox(), 0.2) for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.F_SilkS and d.Type() == pcbnew.PCB_TEXT_T]
    eb = _rect(board.GetBoardEdgesBoundingBox(), -0.55)
    on_silk, on_fab = [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(H), pcbnew.FromMM(H)))
        ref.SetTextThickness(pcbnew.FromMM(T))
        ref.SetKeepUpright(True)
        c = crt[fp.GetReference()]
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        placed = False
        for ang in (0, 90):
            ref.SetTextAngleDegrees(ang)
            ref.SetPosition(pcbnew.VECTOR2I(0, 0))
            w = _rect(ref.GetBoundingBox())
            tw, th = w[2] - w[0], w[3] - w[1]
            for px, py in ((cx, c[1] - th / 2 - 0.1), (cx, c[3] + th / 2 + 0.1),
                           (c[0] - tw / 2 - 0.1, cy), (c[2] + tw / 2 + 0.1, cy)):
                box = (px - tw / 2, py - th / 2, px + tw / 2, py + th / 2)
                if not (eb[0] <= box[0] and box[2] <= eb[2] and eb[1] <= box[1] and box[3] <= eb[3]):
                    continue
                if any(_ov(box, p) for p in pads) or any(_ov(box, t) for t in taken):
                    continue
                if any(_ov(box, r) for k, r in crt.items() if k != fp.GetReference()):
                    continue
                if any(max(abs(px - hx) - tw / 2, abs(py - hy) - th / 2) < keepout_r for hx, hy in holes_k):
                    continue
                ref.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py)))
                taken.append((box[0] - 0.2, box[1] - 0.2, box[2] + 0.2, box[3] + 0.2))
                placed = True
                break
            if placed:
                break
        ref.SetVisible(placed)
        if not placed:
            ref.SetTextAngleDegrees(0)
            ref.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx), pcbnew.FromMM(cy)))
        (on_silk if placed else on_fab).append(fp.GetReference())
    return on_silk, on_fab
