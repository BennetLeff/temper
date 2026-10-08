#!/usr/bin/env python3
"""Render a native-21 board by isolation domain.

    KICAD_PY render.py --dump BOARD.kicad_pcb OUT.json
    python3  render.py OUT.json PNG

Footprint fill: SELV green, HOT orange, SW_A red, SW_B purple, MAINS blue,
barrier parts (pins in SELV and HOT) hatched. Outline from Edge.Cuts.
"""
import json
import sys
from pathlib import Path

if sys.argv[1] == "--dump":
    import pcbnew
    b = pcbnew.LoadBoard(sys.argv[2])
    fps = []
    for f in b.GetFootprints():
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False, False)
        fps.append({"ref": f.GetReference(), "path": f.GetField("SourceInstance").GetText(),
                    "box": [bb.GetX() / 1e6, bb.GetY() / 1e6, (bb.GetX() + bb.GetWidth()) / 1e6, (bb.GetY() + bb.GetHeight()) / 1e6],
                    "nets": sorted({p.GetNetname() for p in f.Pads() if p.GetNetname()})})
    edges = [[d.GetStart().x / 1e6, d.GetStart().y / 1e6, d.GetEnd().x / 1e6, d.GetEnd().y / 1e6]
             for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    json.dump({"footprints": fps, "edges": edges}, open(sys.argv[3], "w"))
    sys.exit(0)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from domains import domain  # noqa: E402

COL = {"PE": "#795548", "SELV": "#4caf50", "HOT": "#ff9800", "SW_A": "#e53935", "SW_B": "#8e24aa", "MAINS": "#1e88e5"}
d = json.load(open(sys.argv[1]))
fig, ax = plt.subplots(figsize=(29 / 1.6, 19 / 1.6), dpi=110)
for e in d["edges"]:
    ax.plot([e[0], e[2]], [e[1], e[3]], "k-", lw=1.2)
for f in d["footprints"]:
    doms = {domain(n) for n in f["nets"]} or {"HOT"}
    x0, y0, x1, y1 = f["box"]
    if "SELV" in doms and len(doms - {"PE"}) > 1:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="white", ec="k", hatch="////", lw=0.6))
    else:
        dm = sorted(doms - {"HOT"})[0] if len(doms - {"HOT"}) == 1 else ("HOT" if doms == {"HOT"} else "HOT")
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=COL[dm], ec="k", lw=0.3, alpha=0.75))
    if (x1 - x0) * (y1 - y0) > 40:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, f["ref"], ha="center", va="center", fontsize=5)
ax.set_xlim(-2, 292); ax.set_ylim(192, -2); ax.set_aspect("equal")
ax.set_xticks(range(0, 291, 10)); ax.set_yticks(range(0, 191, 10)); ax.grid(lw=0.2)
ax.tick_params(labelsize=5)
for k, c in COL.items():
    ax.plot([], [], "s", color=c, label=k)
ax.legend(loc="lower right", fontsize=6)
fig.tight_layout()
fig.savefig(sys.argv[2])
