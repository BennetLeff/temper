#!/usr/bin/env python3
"""Draw a world-mm region of a board to PNG: courtyards, pads (coloured by net class), tracks,
designators and short instance names. Review aid for floorplan edits.

    KICAD_PY evidence/c1-crs/draw_region.py dump BOARD OUT.json       (KiCad Python: geometry)
    python3  evidence/c1-crs/draw_region.py draw OUT.json X0 Y0 X1 Y1 OUT.png [px_per_mm]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "layout"))
import world  # noqa: E402


def dump(board, out):
    import pcbnew
    mm = pcbnew.ToMM
    b = pcbnew.LoadBoard(board)
    fps = []
    for fp in b.GetFootprints():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if not cy.IsEmpty() else fp.GetBoundingBox()
        x0, y1 = world.to_w(mm(bb.GetLeft()), mm(bb.GetTop()))
        x1, y0 = world.to_w(mm(bb.GetRight()), mm(bb.GetBottom()))
        pads = []
        for p in fp.Pads():
            pb = p.GetBoundingBox()
            a0, b1 = world.to_w(mm(pb.GetLeft()), mm(pb.GetTop()))
            a1, b0 = world.to_w(mm(pb.GetRight()), mm(pb.GetBottom()))
            pads.append([a0, b0, a1, b1, p.GetNetname(), p.GetNumber()])
        path = fp.GetFieldText("atopile_address") if fp.HasField("atopile_address") else ""
        fps.append({"ref": fp.GetReference(), "crtyd": [x0, y0, x1, y1], "pads": pads, "path": path})
    tracks = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            s, e = t.GetStart(), t.GetEnd()
            tracks.append([*world.to_w(mm(s.x), mm(s.y)), *world.to_w(mm(e.x), mm(e.y)), mm(t.GetWidth()),
                           t.GetLayerName(), t.GetNetname()])
    Path(out).write_text(json.dumps({"fps": fps, "tracks": tracks}))


def draw(src, x0, y0, x1, y1, out, ppm=40):
    from PIL import Image, ImageDraw
    d = json.loads(Path(src).read_text())
    W, H = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
    img = Image.new("RGB", (W, H), "white")
    g = ImageDraw.Draw(img)

    def P(x, y):
        return ((x - x0) * ppm, (y1 - y) * ppm)
    for t in d["tracks"]:
        col = {"F.Cu": (230, 120, 120), "B.Cu": (120, 120, 230), "In2.Cu": (120, 200, 120)}.get(t[5], (200, 200, 200))
        g.line([P(t[0], t[1]), P(t[2], t[3])], fill=col, width=max(1, int(t[4] * ppm)))
    for f in d["fps"]:
        c = f["crtyd"]
        if c[2] < x0 or c[0] > x1 or c[3] < y0 or c[1] > y1:
            continue
        a, b = P(c[0], c[3]), P(c[2], c[1])
        g.rectangle([a, b], outline=(0, 0, 0))
        for p in f["pads"]:
            col = (255, 170, 0) if p[4] == "selv_gnd" else (0, 160, 220) if "rtd" in p[4] else (150, 150, 150)
            g.rectangle([P(p[0], p[3]), P(p[2], p[1])], fill=col)
        label = f["ref"] + " " + f["path"].split(".")[-1][:12]
        g.text((a[0] + 2, a[1] + 2), label, fill=(0, 0, 0))
    for gx in range(int(x0), int(x1) + 1):
        g.line([P(gx, y0), P(gx, y0 + 0.3)], fill=(0, 0, 0))
        if gx % 5 == 0:
            g.text(P(gx, y0 + 1.0), str(gx), fill=(0, 0, 0))
    for gy in range(int(y0), int(y1) + 1):
        g.line([P(x0, gy), P(x0 + 0.3, gy)], fill=(0, 0, 0))
        if gy % 5 == 0:
            g.text(P(x0 + 0.5, gy), str(gy), fill=(0, 0, 0))
    img.save(out)
    print(out)


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2], sys.argv[3])
    else:
        draw(sys.argv[2], *map(float, sys.argv[3:7]), sys.argv[7], float(sys.argv[8]) if len(sys.argv) > 8 else 40)
