"""1:1 winding template and the no-printer roof sheet (build route C, README D6).

out/template_R1_1to1.pdf   A3 portrait, print at 100 % ("actual size"); check the 100 mm bar with a ruler before use.
                           Bar outlines (glue the bars here, under the roof sheet), spoke centre lines with a tick at every
                           turn crossing (the notch radii of the CNC/printed comb), the R1 spirals, the spare outer turn
                           (dashed), start/crossover/end marks, the J2/J5 lead drops, the lug holes and the NTC pad.
out/template_R1_1to1.dxf   the same, in mm, layered (for a laser cutter, a plotter, or a CNC shop).
out/roof_sheet_R1.dxf      cut profile for the 1.0 mm FR4 (G10) roof sheet: Ø247 disc + four lug ears with Ø3.4 holes at r127,
                           Ø44 centre hole, J2 lead hole. A drill/knife/laser profile only.
Run: .venv/bin/python cad/template.py
"""
from __future__ import annotations

import math
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import geom as K  # noqa: E402
from geom import G  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"


def bar_corners(phi):
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    pts = [(G.BAR_R[0], -G.BAR_W / 2), (G.BAR_R[1], -G.BAR_W / 2), (G.BAR_R[1], G.BAR_W / 2), (G.BAR_R[0], G.BAR_W / 2)]
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def geometry():
    sps = K.spirals(G.R1, G.R1_SPARE_OUTER_TURNS)
    nominal_outer_end = G.OUTER_START_DEG + 360.0 * G.R1.sections[1].turns
    out = dict(bars=[bar_corners(p) for p in G.bar_angles()], spokes=[], ticks=[], spirals=[], spare=[], marks=[])
    for phi in G.bar_angles():
        out["spokes"].append((K.P(K.HUB_R[0], phi)[:2], K.P(K.RIM_R[1], phi)[:2]))
        for si, sp in enumerate(sps):
            for r in K.crossings(sp, phi):
                spare = si == 1 and r > G.R1.sections[1].r1 + 1e-6
                a = math.radians(phi)
                t = (-math.sin(a), math.cos(a))
                c = K.P(r, phi)[:2]
                hl = 4.0
                out["ticks"].append(((c[0] - hl * t[0], c[1] - hl * t[1]), (c[0] + hl * t[0], c[1] + hl * t[1]), spare))
    inner, outer = sps
    out["spirals"].append([p[:2] for p in K.spiral_pts(inner, 0, 3)])
    nom = (outer[0], G.R1.sections[1].r1, outer[2], nominal_outer_end)
    out["spirals"].append([p[:2] for p in K.spiral_pts(nom, 0, 3)])
    out["spare"] = [p[:2] for p in K.spiral_pts((G.R1.sections[1].r1, outer[1], nominal_outer_end, outer[3]), 0, 3)]
    out["crossover"] = [K.P(inner[1], inner[3])[:2], K.P(outer[0], outer[2])[:2]]
    out["marks"] = [("START r27.4 @ -95 deg (centre lead)", K.P(inner[0], inner[2])[:2]),
                    ("inner end r82.6 @ 75 deg", K.P(inner[1], inner[3])[:2]),
                    ("outer start r93.4 @ 90 deg", K.P(outer[0], outer[2])[:2]),
                    ("R1 END r114.8 (6.46 outer turns)", K.P(G.R1.sections[1].r1, nominal_outer_end)[:2]),
                    ("spare end r118.1", K.P(outer[1], outer[3])[:2]),
                    ("J2 drop", K.J2), ("J5 drop", K.J5)]
    return out


def write_dxf(g):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, col in (("BARS", 5), ("SPOKES", 8), ("TICKS", 1), ("SPARE", 6), ("SPIRAL", 3), ("OUTLINE", 7), ("TEXT", 7), ("HOLES", 2)):
        doc.layers.add(name, color=col)
    for b in g["bars"]:
        msp.add_lwpolyline(b, close=True, dxfattribs={"layer": "BARS"})
    for a, b in g["spokes"]:
        msp.add_line(a, b, dxfattribs={"layer": "SPOKES"})
    for a, b, sp in g["ticks"]:
        msp.add_line(a, b, dxfattribs={"layer": "SPARE" if sp else "TICKS"})
    for s in g["spirals"]:
        msp.add_lwpolyline(s, dxfattribs={"layer": "SPIRAL"})
    msp.add_lwpolyline(g["spare"], dxfattribs={"layer": "SPARE", "linetype": "DASHED"})
    msp.add_line(*g["crossover"], dxfattribs={"layer": "SPIRAL"})
    for r in (K.HUB_R[0], K.HUB_R[1], K.RIM_R[0], K.RIM_R[1], K.GAP_R[0], K.GAP_R[1]):
        msp.add_circle((0, 0), r, dxfattribs={"layer": "OUTLINE"})
    for a in K.LUG_ANGLES:
        msp.add_circle(K.P(K.LUG_R, a)[:2], K.LUG_HOLE / 2, dxfattribs={"layer": "HOLES"})
    for txt, p in g["marks"]:
        msp.add_circle(p, 1.2, dxfattribs={"layer": "TEXT"})
        msp.add_text(txt, height=2.5, dxfattribs={"layer": "TEXT"}).set_placement((p[0] + 2, p[1] + 2))
    msp.add_line((-50, -140), (50, -140), dxfattribs={"layer": "OUTLINE"})
    msp.add_text("100 mm", height=3, dxfattribs={"layer": "TEXT"}).set_placement((-8, -146))
    doc.saveas(OUT / "template_R1_1to1.dxf")
    # roof sheet profile
    doc2 = ezdxf.new("R2010")
    doc2.units = ezdxf.units.MM
    m2 = doc2.modelspace()
    m2.add_lwpolyline(roof_profile(), close=True)
    m2.add_circle((0, 0), K.HUB_R[0])
    for a in K.LUG_ANGLES:
        m2.add_circle(K.P(K.LUG_R, a)[:2], K.LUG_HOLE / 2)
    m2.add_circle(K.J2, K.D_LEAD / 2 + 1.0)
    doc2.saveas(OUT / "roof_sheet_R1.dxf")


def roof_profile():
    """Outline: circle r123.5 with rectangular lug ears (12 wide, to r134) at the four lug angles."""
    half = math.degrees(math.asin((K.LUG_W / 2) / K.RIM_R[1]))
    ears = sorted(((a % 360) - half, (a % 360) + half, a % 360) for a in K.LUG_ANGLES)
    pts, done = [], set()
    for i in range(720):
        th = i * 0.5
        e = next((e for e in ears if e[0] <= th <= e[1]), None)
        if e is None:
            pts.append(K.P(K.RIM_R[1], th)[:2])
        elif e[2] not in done:
            done.add(e[2])
            a = math.radians(e[2])
            er, et = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
            pts.append(K.P(K.RIM_R[1], e[0])[:2])
            for (x, y) in ((K.LUG_R1, -K.LUG_W / 2), (K.LUG_R1, K.LUG_W / 2)):
                pts.append((x * er[0] + y * et[0], x * er[1] + y * et[1]))
            pts.append(K.P(K.RIM_R[1], e[1])[:2])
    return pts


def write_pdf(g):
    W, H = 297.0, 420.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-W / 2, W / 2)
    ax.set_ylim(-H / 2 - 40, H / 2 - 40)
    ax.set_aspect("equal")
    ax.axis("off")
    for b in g["bars"]:
        xs, ys = zip(*(b + [b[0]]))
        ax.fill(xs, ys, color="#c9d6e8", lw=0.6, ec="#2b4c7e")
    for a, b in g["spokes"]:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="0.5", lw=0.3)
    for a, b, sp in g["ticks"]:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#b00" if not sp else "#a0a", lw=0.5)
    for s in g["spirals"]:
        xs, ys = zip(*s)
        ax.plot(xs, ys, color="#1a7f37", lw=0.4)
    xs, ys = zip(*g["spare"])
    ax.plot(xs, ys, color="#a0a", lw=0.4, ls="--")
    (x0, y0), (x1, y1) = g["crossover"]
    ax.plot([x0, x1], [y0, y1], color="#1a7f37", lw=0.6)
    th = [i * 2 * math.pi / 720 for i in range(721)]
    for r, ls in ((K.HUB_R[0], "-"), (K.RIM_R[1], "-"), (K.GAP_R[0], ":"), (K.GAP_R[1], ":")):
        ax.plot([r * math.cos(t) for t in th], [r * math.sin(t) for t in th], color="k", lw=0.4, ls=ls)
    xs, ys = zip(*(roof_profile() + [roof_profile()[0]]))
    ax.plot(xs, ys, color="k", lw=0.6)
    for a in K.LUG_ANGLES:
        c = K.P(K.LUG_R, a)
        ax.add_patch(plt.Circle(c[:2], K.LUG_HOLE / 2, fill=False, lw=0.5))
    for txt, p in g["marks"]:
        ax.plot(*p, "ko", ms=2)
        ax.text(p[0] + 2, p[1] + 2, txt, fontsize=5)
    ax.plot([-50, 50], [-150, -150], "k", lw=1.2)
    for x in (-50, 50):
        ax.plot([x, x], [-152, -148], "k", lw=1.2)
    ax.text(0, -157, "100 mm - print at 100 % (actual size) and check this bar", ha="center", fontsize=7)
    ax.text(-W / 2 + 10, H / 2 - 50, "temper-coil-r1  winding template R1 (14.47 + 6.46 turns, +1 spare outer)  1:1, viewed from ABOVE (glass side)\n"
            "blue = ferrite bars (under the roof sheet); red ticks = turn crossings on each bar centre line; magenta = spare turn;\n"
            "green = bundle-centre path. Start at the -95 deg mark, wind CCW as seen here. Source: cad/template.py", fontsize=6, va="top")
    fig.savefig(OUT / "template_R1_1to1.pdf")
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    g = geometry()
    write_dxf(g)
    write_pdf(g)
    print("ticks", len(g["ticks"]), "of which spare", sum(1 for t in g["ticks"] if t[2]))


if __name__ == "__main__":
    main()
