#!/usr/bin/env python3
"""Plot a routed native-21 board's copper per layer.

    KICAD_PY plot_copper.py --dump BOARD.kicad_pcb OUT.json
    python3  plot_copper.py OUT.json PNG [x0 x1 y0 y1]

Filled zone polygons, tracks, vias and pads on each of the four copper layers,
coloured by net (power nets fixed colours, everything else grey); the outline
from Edge.Cuts. Run after `kicad-cli pcb drc --refill-zones --save-board`.
"""
import json
import sys

LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

if sys.argv[1] == "--dump":
    import pcbnew
    b = pcbnew.LoadBoard(sys.argv[2])
    mm = pcbnew.ToMM
    out = {"zones": [], "tracks": [], "vias": [], "pads": [], "edges": []}
    for z in b.Zones():
        for lid in z.GetLayerSet().CuStack():
            ps = z.GetFilledPolysList(lid)
            for i in range(ps.OutlineCount()):
                ol = ps.Outline(i)
                pts = [[mm(ol.CPoint(k).x), mm(ol.CPoint(k).y)] for k in range(ol.PointCount())]
                holes = []
                for h in range(ps.HoleCount(i)):
                    hl = ps.Hole(i, h)
                    holes.append([[mm(hl.CPoint(k).x), mm(hl.CPoint(k).y)] for k in range(hl.PointCount())])
                out["zones"].append({"net": z.GetNetname(), "layer": b.GetLayerName(lid), "pts": pts, "holes": holes})
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            out["vias"].append({"net": t.GetNetname(), "at": [mm(t.GetPosition().x), mm(t.GetPosition().y)],
                                "d": mm(t.GetWidth(pcbnew.F_Cu))})
        else:
            out["tracks"].append({"net": t.GetNetname(), "layer": t.GetLayerName(), "w": mm(t.GetWidth()),
                                  "a": [mm(t.GetStart().x), mm(t.GetStart().y)], "b": [mm(t.GetEnd().x), mm(t.GetEnd().y)]})
    for f in b.GetFootprints():
        for p in f.Pads():
            poly = p.GetEffectivePolygon(pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
            ol = poly.Outline(0)
            # stage 18: the copper layers the pad is on (SMD side), for per-layer creepage checks
            out["pads"].append({"net": p.GetNetname(), "ref": f.GetReference(), "tht": p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                                "layers": [b.GetLayerName(lid) for lid in p.GetLayerSet().CuStack()],
                                "pts": [[mm(ol.CPoint(k).x), mm(ol.CPoint(k).y)] for k in range(ol.PointCount())]})
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            out["edges"].append([mm(d.GetStart().x), mm(d.GetStart().y), mm(d.GetEnd().x), mm(d.GetEnd().y)])
    json.dump(out, open(sys.argv[3], "w"))
    sys.exit(0)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402

COL = {"bus_p": "#d32f2f", "hv_ret": "#1565c0", "leg_ret": "#00897b", "sw_a": "#f57c00", "sw_b": "#7b1fa2",
       "rect_p": "#e91e63", "rect_n": "#3949ab", "l_filt": "#795548", "n_filt": "#607d8b", "res_a": "#c0ca33",
       "coil_feed": "#ffb300", "l_f": "#a1887f", "ac_n_in": "#90a4ae", "ac_l_in": "#8d6e63",
       "selv_gnd": "#2e7d32", "v3v3": "#66bb6a", "pe": "#4e342e", "ocp_kelvin_p": "#00e5ff", "n_ls": "#26a69a",
       "v15_ls": "#4db6ac", "p_ha": "#ff7043", "n_ha": "#ffab91", "p_hb": "#ab47bc", "n_hb": "#ce93d8"}
d = json.load(open(sys.argv[1]))
box = [float(v) for v in sys.argv[3:7]] if len(sys.argv) > 6 else [-2, 292, -2, 192]
w, h = box[1] - box[0], box[3] - box[2]
fig, axes = plt.subplots(2, 2, figsize=(2 * w / 12 + 1, 2 * h / 12 + 1), dpi=110)
for ax, layer in zip(axes.flat, LAYERS):
    for z in d["zones"]:
        if z["layer"] != layer:
            continue
        verts, codes = [], []
        for ring in [z["pts"]] + z["holes"]:
            verts += ring + [ring[0]]
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 1) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), fc=COL.get(z["net"], "#9e9e9e"), ec="none", alpha=0.75))
    for t in d["tracks"]:
        if t["layer"] == layer:
            ax.plot([t["a"][0], t["b"][0]], [t["a"][1], t["b"][1]], color=COL.get(t["net"], "#616161"),
                    lw=max(t["w"] * 72 / 25.4 * 110 / 110 * 0.9, 0.4), solid_capstyle="round")
    for p in d["pads"]:
        on = p["tht"] or layer == "F.Cu"
        if on:
            ax.add_patch(Polygon(p["pts"], closed=True, fc=COL.get(p["net"], "#bdbdbd"), ec="k", lw=0.2))
    for v in d["vias"]:
        ax.plot(*v["at"], "o", ms=1.5, color=COL.get(v["net"], "k"), mec="k", mew=0.2)
    for e in d["edges"]:
        ax.plot([e[0], e[2]], [e[1], e[3]], "k-", lw=0.8)
    ax.set_xlim(box[0], box[1]); ax.set_ylim(box[3], box[2]); ax.set_aspect("equal")
    ax.set_title(layer, fontsize=9); ax.tick_params(labelsize=5); ax.grid(lw=0.15)
for k, c in COL.items():
    axes.flat[0].plot([], [], "s", color=c, label=k)
axes.flat[0].legend(fontsize=4, loc="lower right", ncol=2)
fig.tight_layout()
fig.savefig(sys.argv[2])
