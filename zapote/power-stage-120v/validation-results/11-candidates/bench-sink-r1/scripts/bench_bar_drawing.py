#!/usr/bin/env python3
"""Bench clamp bar: one-page dimensioned fab drawing (PDF, A3) and the same sheet as a DXF, projected from the STEP.

    ~/.local/share/temper/cadenv/bin/python -I scripts/bench_bar_drawing.py   (from bench-sink-r1/; after bench_bar_step.py)
      -> fab/clamp-bar/bench-clamp-bar-r1.pdf, fab/clamp-bar/bench-clamp-bar-r1.dxf

The views are hidden-line projections (build123d / OCCT HLR) of the exported STEP, not redrawn from numbers: view on
face A, right view, section A-A through the pocket centres, and a small isometric. Every dimension value is measured
on the re-imported STEP (projected circle centres and radii, section depth), and the script exits 1 if a measured value
disagrees with bench_params.py. Notes and title-block values come from bench_params.py and the constants below.

The PDF is drawn at 2:1 on A3. The DXF holds the same sheet in model space at 1:1 (geometry true size, the sheet frame
and text scaled by 1/2), $INSUNITS = 4 (mm), with closed LWPOLYLINE outlines. matplotlib draws 2D only here.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_bar_step as B  # noqa: E402

PDF_PATH = B.OUT_DIR / "bench-clamp-bar-r1.pdf"
DXF_PATH = B.OUT_DIR / "bench-clamp-bar-r1.dxf"
S = 2.0                                  # drawing scale on the A3 sheet
SHEET = (420.0, 297.0)
QTY = 2
MATERIAL = "ALUMINIUM 6061-T6"
FINISH = "AS-MACHINED, DEBURRED. NO ANODIZE, NO COATING"
GENERAL_TOL = "ISO 2768-m"
DWG_NO = "BSR1-BAR-01"
REV = "A"
DATE = "2026-11-28"
FLOOR_R_MAX = round((P.SPRING["hole"] - P.SPRING["OD"]) / 2, 1)   # spring end coil must sit on the flat floor

PRIM = []          # (kind, layer, data) in paper mm


def L_(pts, layer="OUTLINE", closed=False):
    PRIM.append(("poly", layer, (list(pts), closed)))


def T_(x, y, s, h=3.0, layer="NOTES", ha="left", va="baseline", rot=0.0):
    PRIM.append(("text", layer, (x, y, s, h, ha, va, rot)))


def arrow(tip, frm, layer="DIM", size=2.5):
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size / 3.0
    PRIM.append(("solid", layer, [tip, (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)]))


def hatch(pts, layer="HATCH"):
    PRIM.append(("hatch", layer, list(pts)))


def edge_pts(e):
    import build123d as bd
    if e.geom_type == bd.GeomType.LINE:
        ts = (0.0, 1.0)
    else:
        ts = [i / 48 for i in range(49)]
    return [(e.position_at(t).X, e.position_at(t).Y) for t in ts]


class View:
    """Paper placement of a projected view: paper = origin + S_view * local, local in model mm."""

    def __init__(self, origin, scale=S):
        self.o, self.s = origin, scale

    def p(self, x, y):
        return (self.o[0] + self.s * x, self.o[1] + self.s * y)

    def draw(self, vis, hid, shift):
        """Full circles become CIRCLE primitives; other edges are chained end to end, so loops come out closed."""
        import build123d as bd
        seen = [(e.arc_center.X, e.arc_center.Y, e.radius) for e in vis if e.geom_type == bd.GeomType.CIRCLE]
        for layer, edges in (("HIDDEN", hid), ("OUTLINE", vis)):
            polys = []
            for e in edges:
                if e.geom_type == bd.GeomType.CIRCLE and e.is_closed:
                    c = e.arc_center
                    if layer == "HIDDEN" and any(math.dist((c.X, c.Y, e.radius), v) < 1e-6 for v in seen):
                        continue      # a hidden circle under a visible one (pocket floor, hole exit) is not drawn
                    PRIM.append(("circle", layer, (self.p(c.X + shift[0], c.Y + shift[1]), self.s * e.radius)))
                else:
                    polys.append([self.p(x + shift[0], y + shift[1]) for x, y in edge_pts(e)])
            for pts in _chain(_merge_collinear(polys)):
                closed = len(pts) > 3 and math.dist(pts[0], pts[-1]) < 1e-6
                L_(pts[:-1] if closed else pts, layer, closed=closed)


def _merge_collinear(polys, eps=1e-5):
    """Straight projected edges that overlap (the four pockets seen edge-on in the side views, a circle seen edge-on
    split into arcs) are merged per line into the union of their intervals, so each line is drawn once."""
    lines, curves = {}, []
    for pts in polys:
        a, b = pts[0], pts[-1]
        ln = math.dist(a, b)
        if ln < eps:
            curves.append(pts)
            continue
        ux, uy = (b[0] - a[0]) / ln, (b[1] - a[1]) / ln
        if ux < -eps or (abs(ux) < eps and uy < 0):
            ux, uy = -ux, -uy
        if any(abs((q[0] - a[0]) * uy - (q[1] - a[1]) * ux) > eps for q in pts):
            curves.append(pts)
            continue
        c = round(a[0] * uy - a[1] * ux, 4)          # signed distance of the line from the origin
        key = (round(ux, 5), round(uy, 5), c)
        ts = sorted(q[0] * ux + q[1] * uy for q in (a, b))
        lines.setdefault(key, []).append(ts)
    out = []
    for (ux, uy, c), ivs in lines.items():
        ivs.sort()
        merged = [list(ivs[0])]
        for t0, t1 in ivs[1:]:
            if t0 <= merged[-1][1] + eps:
                merged[-1][1] = max(merged[-1][1], t1)
            else:
                merged.append([t0, t1])
        for t0, t1 in merged:     # point = t * u + c * n, n = (uy, -ux)
            out.append([(t0 * ux + c * uy, t0 * uy - c * ux), (t1 * ux + c * uy, t1 * uy - c * ux)])
    return out + curves


def _chain(polys, eps=1e-6):
    polys = [list(p) for p in polys]
    out = []
    while polys:
        cur = polys.pop(0)
        grown = True
        while grown:
            grown = False
            for i, q in enumerate(polys):
                if math.dist(cur[-1], q[0]) < eps:
                    cur += q[1:]
                elif math.dist(cur[-1], q[-1]) < eps:
                    cur += q[-2::-1]
                elif math.dist(cur[0], q[-1]) < eps:
                    cur = q[:-1] + cur
                elif math.dist(cur[0], q[0]) < eps:
                    cur = q[:0:-1] + cur
                else:
                    continue
                polys.pop(i)
                grown = True
                break
        out.append(cur)
    return out


def dim_linear(a, b, off, text, orient, layer="DIM", h=3.0):
    """Dimension between paper points a and b; orient 'h' or 'v'; off = paper offset of the dimension line."""
    if orient == "h":
        y = max(a[1], b[1]) + off if off > 0 else min(a[1], b[1]) + off
        L_([a, (a[0], y + (1.5 if off > 0 else -1.5))], layer)
        L_([b, (b[0], y + (1.5 if off > 0 else -1.5))], layer)
        L_([(a[0], y), (b[0], y)], layer)
        arrow((a[0], y), (b[0], y)); arrow((b[0], y), (a[0], y))
        T_((a[0] + b[0]) / 2, y + 1.0, text, h, layer, ha="center")
    else:
        x = max(a[0], b[0]) + off if off > 0 else min(a[0], b[0]) + off
        L_([a, (x + (1.5 if off > 0 else -1.5), a[1])], layer)
        L_([b, (x + (1.5 if off > 0 else -1.5), b[1])], layer)
        L_([(x, a[1]), (x, b[1])], layer)
        arrow((x, a[1]), (x, b[1])); arrow((x, b[1]), (x, a[1]))
        T_(x - 1.0, (a[1] + b[1]) / 2, text, h, layer, ha="center", va="bottom", rot=90)


def leader(at, to, text, h=3.0, layer="DIM"):
    L_([at, to], layer)
    arrow(at, to)
    end = (to[0] + (4 if to[0] >= at[0] else -4), to[1])
    L_([to, end], layer)
    T_(end[0] + (1 if to[0] >= at[0] else -1), end[1] + 0.8, text, h, layer, ha="left" if to[0] >= at[0] else "right")


def centre_mark(c, r, layer="CENTER"):
    e = r + 1.5
    L_([(c[0] - e, c[1]), (c[0] + e, c[1])], layer)
    L_([(c[0], c[1] - e), (c[0], c[1] + e)], layer)


def build_sheet():
    import build123d as bd

    shape = bd.import_step(str(B.STEP_PATH))
    s = shape.solids()[0]
    Lb, Hb, Tb = B.L, B.H, B.T
    feats = B.features()
    errs = []

    # ------------------------------------------------ view on face A (looking -z), local = model (x, y)
    vis, hid = s.project_to_viewport((Lb / 2, Hb / 2, 500), (0, 1, 0), (Lb / 2, Hb / 2, Tb / 2))
    circles = [(e.arc_center.X + Lb / 2, e.arc_center.Y + Hb / 2, e.radius) for e in vis if e.geom_type == bd.GeomType.CIRCLE]
    measured = {}
    for name, kind, u, v, d, dep in feats:
        m = [c for c in circles if abs(c[0] - u) < 1e-3 and abs(c[1] - v) < 1e-3 and abs(2 * c[2] - d) < 1e-3]
        if not m:
            errs.append(f"{name}: no projected circle of dia {d} at ({u}, {v})")
        else:
            measured[name] = m[0]
    fv = View((50.0, 190.0))
    fv.draw(vis, hid, (Lb / 2, Hb / 2))
    T_(fv.p(0, 0)[0], fv.p(0, Hb)[1] + 34, "VIEW ON FACE A (spacer-seat face; pockets open here)", 3.5, ha="left")
    for name, (cx, cy, r) in measured.items():
        centre_mark(fv.p(cx, cy), S * r)

    # u ordinates along the top, datum = left end
    us = sorted({round(c[0], 3) for c in measured.values()})
    y_top = fv.p(0, Hb)[1]
    L_([fv.p(0, Hb), (fv.p(0, Hb)[0], y_top + 16)], "DIM")
    T_(fv.p(0, Hb)[0], y_top + 17, "0", 3.0, "DIM", ha="left", va="center", rot=90)
    for u in us + [Lb]:
        x = fv.p(u, 0)[0]
        cy = [c[1] for c in measured.values() if abs(c[0] - u) < 1e-3]
        y0 = fv.p(0, max(cy))[1] + S * 5.2 if cy else y_top
        L_([(x, y0 if u != Lb else y_top), (x, y_top + 16)], "DIM")
        T_(x, y_top + 17, f"{u:.2f}" if u != Lb else f"{Lb:.1f}", 3.0, "DIM", ha="left", va="center", rot=90)
    # v ordinates on the left, datum = lower edge
    vs = sorted({round(c[1], 3) for c in measured.values()})
    x_l = fv.p(0, 0)[0]
    for v, lab in [(0.0, "0")] + [(v, f"{v:.2f}") for v in vs] + [(Hb, f"{Hb:.1f}")]:
        y = fv.p(0, v)[1]
        L_([(x_l - 1.5, y), (x_l - 14, y)], "DIM")
        T_(x_l - 15, y, lab, 3.0, "DIM", ha="right", va="center")
    for v in vs:   # extension from the first feature on that row
        xs = [c[0] for c in measured.values() if abs(c[1] - v) < 1e-3]
        L_([fv.p(min(xs) - 5.5, v), (x_l - 1.5, fv.p(0, v)[1])], "CENTER")
    dim_linear(fv.p(0, 0), fv.p(Lb, 0), -10, f"{Lb:.1f}", "h")

    pq = [n for n in measured if n.startswith("pocket")]
    hq = [n for n in measured if n.startswith("end hole")]
    cx, cy, r = measured[pq[2]]
    depth = None
    leader(fv.p(cx + r * 0.707, cy - r * 0.707), (fv.p(cx, 0)[0] + 30, fv.p(0, 0)[1] - 24),
           f"{len(pq)}X Ø{2 * r:.2f} x {P.POCKET_DEPTH:.2f} ±{P.POCKET_DEPTH_TOL:.2f} DEEP, FLAT BOTTOM", 3.0)
    cx, cy, r = measured[hq[-1]]
    leader(fv.p(cx + r * 0.707, cy - r * 0.707), (fv.p(cx, 0)[0] + 24, fv.p(0, 0)[1] - 24), f"{len(hq)}X Ø{2 * r:.1f} THRU", 3.0)
    # cutting plane A-A at the pocket row
    v_cut = vs[0]
    ya = fv.p(0, v_cut)[1]
    for x in (fv.p(0, 0)[0] - 8, fv.p(Lb, 0)[0] + 8):
        L_([(x - 3, ya), (x + 3, ya)], "CUT")
        L_([(x, ya), (x, ya - 7)], "CUT")
        arrow((x, ya - 0.2), (x, ya - 7), "CUT", 3.0)
        T_(x, ya - 12, "A", 4.0, "CUT", ha="center")

    # ------------------------------------------------ right view (looking -x): local = (t - z, y), face A on the left
    vis, hid = s.project_to_viewport((Lb + 500, Hb / 2, Tb / 2), (0, 1, 0), (0, Hb / 2, Tb / 2))
    rv = View((345.0, 190.0))
    rv.draw(vis, hid, (Tb / 2, Hb / 2))
    T_(rv.p(0, 0)[0] - 4, rv.p(0, Hb)[1] + 34, "RIGHT VIEW", 3.5)
    dim_linear(rv.p(0, 0), rv.p(Tb, 0), -10, f"{Tb:.3f}", "h")
    dim_linear(rv.p(Tb, 0), rv.p(Tb, Hb), 8, f"{Hb:.1f}", "v")
    leader(rv.p(0, Hb * 0.85), (rv.p(0, 0)[0] - 10, rv.p(0, Hb)[1] + 10), "FACE A", 3.0)

    # ------------------------------------------------ section A-A at v_cut, looking +y, local = (x, z)
    box = bd.Pos(Lb / 2, v_cut + Hb, Tb / 2) * bd.Box(Lb + 10, 2 * Hb, Tb + 10)
    half = (s & box).solids()[0]
    vis, hid = half.project_to_viewport((Lb / 2, -500, Tb / 2), (0, 0, 1), (Lb / 2, v_cut, Tb / 2))
    sv = View((50.0, 120.0))
    sv.draw(vis, [], (Lb / 2, Tb / 2))
    cut = [f for f in half.faces() if abs(f.bounding_box().min.Y - v_cut) < 1e-6 and abs(f.bounding_box().max.Y - v_cut) < 1e-6]
    if len(cut) != 1:
        errs.append(f"section A-A: {len(cut)} cut faces")
    else:
        hatch([sv.p(x, z) for x, z in _wire_xz(cut[0].outer_wire())])
        zs = sorted({round(vv.Z, 4) for vv in cut[0].vertices()})
        depth = Tb - zs[1] if len(zs) == 3 else None   # z: back face, pocket floor, face A
        if depth is None or abs(depth - P.POCKET_DEPTH) > 1e-3:
            errs.append(f"section A-A: pocket depth measured {depth}, params {P.POCKET_DEPTH}")
    T_(sv.p(0, 0)[0], sv.p(0, 0)[1] - 20, f"SECTION A-A (through the pocket centres, v = {v_cut:.2f})", 3.5)
    T_(sv.p(0, Tb)[0], sv.p(0, Tb)[1] + 2.5, "FACE A", 3.0)
    dim_linear(sv.p(0, 0), sv.p(0, Tb), -8, f"{Tb:.3f}", "v")
    cxq, _, rq = measured[pq[-1]]
    if depth is not None:
        dim_linear(sv.p(cxq + rq, Tb - depth), sv.p(cxq + rq, Tb), 8,
                   f"{depth:.2f} ±{P.POCKET_DEPTH_TOL:.2f}", "v")
        dim_linear(sv.p(Lb, 0), sv.p(Lb, Tb - depth), 8, f"({Tb - depth:.3f})", "v")
    leader(sv.p(measured[pq[0]][0] - 4.0, Tb - P.POCKET_DEPTH), (sv.p(measured[pq[0]][0], 0)[0] + 10, sv.p(0, 0)[1] - 9),
           f"FLAT FLOOR, NO DRILL POINT; FLOOR CORNER R{FLOOR_R_MAX} MAX", 2.8)

    # ------------------------------------------------ isometric, not to scale
    vis, _ = s.project_to_viewport((Lb / 2 + 300, Hb / 2 - 300, Tb / 2 + 300), (0, 0, 1), (Lb / 2, Hb / 2, Tb / 2))
    iv = View((372.0, 126.0), scale=0.45)
    iv.draw(vis, [], (0, 0))
    T_(345, 100, "ISOMETRIC (not to scale)", 3.0)

    # ------------------------------------------------ frame, notes, title block
    W_, H_ = SHEET
    L_([(10, 10), (W_ - 10, 10), (W_ - 10, H_ - 10), (10, H_ - 10)], "FRAME", closed=True)
    notes = [
        f"1. MATERIAL: {MATERIAL}.",
        f"2. FINISH: {FINISH}. The bar is bonded to PE through its",
        "    screws and spacers; anodize would insulate it.",
        f"3. GENERAL TOLERANCES {GENERAL_TOL} UNLESS OTHERWISE SPECIFIED.",
        f"4. POCKET DEPTH {P.POCKET_DEPTH:.2f} ±{P.POCKET_DEPTH_TOL:.2f} FROM FACE A (spring preload). Floors flat,",
        f"    no drill point, floor corner radius R{FLOOR_R_MAX} max (Ø{P.SPRING['OD']} spring in Ø{P.SPRING['hole']}).",
        "5. DEBURR ALL EDGES AND HOLES; BREAK SHARP EDGES 0.1-0.3.",
        f"6. QUANTITY: {QTY}.   NO THREADS.   3/8 x 1 in 6061-T6 FLAT BAR STOCK ACCEPTABLE.",
        "7. All dimensions in mm. Model: bench-clamp-bar-r1.step (controls geometry).",
    ]
    y = 86.0
    T_(16, y + 6, "NOTES", 3.5)
    for n in notes:
        T_(16, y, n, 2.9)
        y -= 6.2
    tb_x, tb_y, tb_w, tb_h = 250.0, 10.0, 160.0, 56.0
    L_([(tb_x, tb_y), (tb_x + tb_w, tb_y), (tb_x + tb_w, tb_y + tb_h), (tb_x, tb_y + tb_h)], "FRAME", closed=True)
    cells = [("TITLE", "BENCH CLAMP BAR (bench-sink-r1)"), ("DWG NO / REV", f"{DWG_NO}   REV {REV}"),
             ("MATERIAL", MATERIAL), ("FINISH", "AS-MACHINED, DEBURRED, NO ANODIZE"),
             ("QTY / SCALE", f"{QTY}   /   {S:.0f}:1 on A3   /   THIRD ANGLE"),
             ("TOLERANCE", f"{GENERAL_TOL}; pocket depth ±{P.POCKET_DEPTH_TOL:.2f}"),
             ("DATE / UNITS", f"{DATE}   /   mm   /   mass {s.volume * 2.70e-3:.0f} g")]
    rh = tb_h / len(cells)
    for i, (k, v) in enumerate(cells):
        yy = tb_y + tb_h - (i + 1) * rh
        if i:
            L_([(tb_x, yy + rh), (tb_x + tb_w, yy + rh)], "FRAME")
        T_(tb_x + 2, yy + 2.4, k, 2.2)
        T_(tb_x + 34, yy + 2.2, v, 3.2 if i == 0 else 2.8)
    L_([(tb_x + 32, tb_y), (tb_x + 32, tb_y + tb_h)], "FRAME")
    return errs, measured, depth


def _wire_xz(w):
    pts = []
    for e in w.order_edges() if hasattr(w, "order_edges") else w.edges():
        p0 = e.position_at(0)
        pts.append((p0.X, p0.Z))
    return pts


# ------------------------------------------------------------------------------------------------ writers
def write_pdf(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["hatch.linewidth"] = 0.4
    W_, H_ = SHEET
    fig = plt.figure(figsize=(W_ / 25.4, H_ / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W_); ax.set_ylim(0, H_); ax.set_aspect("equal"); ax.axis("off")
    style = {"OUTLINE": dict(lw=1.1, color="k"), "HIDDEN": dict(lw=0.5, color="0.35", ls=(0, (4, 2))),
             "CENTER": dict(lw=0.35, color="0.3", ls=(0, (8, 2, 1.5, 2))), "DIM": dict(lw=0.35, color="k"),
             "CUT": dict(lw=0.9, color="k"), "FRAME": dict(lw=0.7, color="k"), "NOTES": dict(lw=0.35, color="k")}
    pt_per_mm = 72 / 25.4
    for kind, layer, d in PRIM:
        st = style.get(layer, dict(lw=0.35, color="k"))
        if kind == "poly":
            pts, closed = d
            xs, ys = zip(*(pts + ([pts[0]] if closed else [])))
            ax.plot(xs, ys, solid_capstyle="butt", **st)
        elif kind == "circle":
            from matplotlib.patches import Circle
            ax.add_patch(Circle(d[0], d[1], fill=False, ec=st["color"], lw=st["lw"], ls=st.get("ls", "-")))
        elif kind == "solid":
            ax.add_patch(Polygon(d, closed=True, fc="k", ec="none"))
        elif kind == "hatch":
            ax.add_patch(Polygon(d, closed=True, fill=False, hatch="////", ec="0.25", lw=0))
        else:
            x, y, s, h, ha, va, rot = d
            box = dict(fc="white", ec="none", pad=0.4) if layer == "DIM" else None
            ax.text(x, y, s, fontsize=h / 0.72 * pt_per_mm, ha=ha, va=va, rotation=rot, rotation_mode="anchor", color="k",
                    bbox=box)
    fig.savefig(path, format="pdf", metadata={"CreationDate": None, "Creator": None, "Producer": None})
    plt.close(fig)


def write_dxf(path):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 0.5
    for name, color, lt in (("OUTLINE", 7, "CONTINUOUS"), ("HIDDEN", 8, "DASHED"), ("CENTER", 8, "CENTER"),
                            ("DIM", 4, "CONTINUOUS"), ("CUT", 1, "CONTINUOUS"), ("HATCH", 8, "CONTINUOUS"),
                            ("FRAME", 7, "CONTINUOUS"), ("NOTES", 7, "CONTINUOUS")):
        doc.layers.add(name, color=color, linetype=lt)
    msp = doc.modelspace()
    k = 1.0 / S          # paper -> model space: geometry true size
    q = lambda p: (p[0] * k, p[1] * k)
    al = {("left", "baseline"): TextEntityAlignment.LEFT, ("center", "baseline"): TextEntityAlignment.CENTER,
          ("right", "baseline"): TextEntityAlignment.RIGHT, ("center", "bottom"): TextEntityAlignment.BOTTOM_CENTER,
          ("left", "bottom"): TextEntityAlignment.BOTTOM_LEFT, ("right", "bottom"): TextEntityAlignment.BOTTOM_RIGHT,
          ("left", "center"): TextEntityAlignment.MIDDLE_LEFT, ("right", "center"): TextEntityAlignment.MIDDLE_RIGHT}
    for kind, layer, d in PRIM:
        if kind == "poly":
            pts, closed = d
            pp = [q(p) for p in pts]
            if closed or (len(pp) > 2 and math.dist(pp[0], pp[-1]) < 1e-6):
                msp.add_lwpolyline(pp[:-1] if not closed else pp, close=True, dxfattribs={"layer": layer})
            elif len(pp) == 2:
                msp.add_line(pp[0], pp[1], dxfattribs={"layer": layer})
            else:
                msp.add_lwpolyline(pp, dxfattribs={"layer": layer})
        elif kind == "circle":
            msp.add_circle(q(d[0]), d[1] * k, dxfattribs={"layer": layer})
        elif kind == "solid":
            msp.add_solid([q(p) for p in d], dxfattribs={"layer": layer})
        elif kind == "hatch":
            h = msp.add_hatch(dxfattribs={"layer": layer})
            h.set_pattern_fill("ANSI31", scale=0.5)
            h.paths.add_polyline_path([q(p) for p in d], is_closed=True)
        else:
            x, y, s, hh, ha, va, rot = d
            t = msp.add_text(s, height=hh * 0.72 * k, rotation=rot, dxfattribs={"layer": layer})
            t.set_placement(q((x, y)), align=al.get((ha, va), TextEntityAlignment.LEFT))
    doc.saveas(path)
    # fixed timestamps and GUIDs, so an unchanged sheet re-exports to the same bytes (the README carries its sha256)
    import re
    t = path.read_text()
    t = re.sub(r"(\$TD(?:U?CREATE|U?UPDATE)\n 40\n)[0-9.]+", r"\g<1>2461373.0", t)
    t = re.sub(r"(\$(?:FINGERPRINT|VERSION)GUID\n  2\n)\{[0-9A-F-]+\}", r"\g<1>{00000000-0000-0000-0000-000000000000}", t)
    t = re.sub(r"(ezdxf )?([0-9.]+) @ [0-9T:.+-]+", r"\g<2> @ 2026-11-28T00:00:00+00:00", t)
    path.write_text(t)


def main():
    if B.cross_check():
        print("bench_params.py and drill-table.md disagree: run bench_bar_step.py first")
        return 1
    errs, measured, depth = build_sheet()
    if errs:
        print("drawing measurements disagree with bench_params.py:")
        print("\n".join(f"  - {e}" for e in errs))
        return 1
    write_pdf(PDF_PATH)
    write_dxf(DXF_PATH)
    for n, (x, y, r) in measured.items():
        print(f"{n:12s} measured on the STEP: u {x:8.3f}  v {y:7.3f}  dia {2 * r:6.3f}")
    print(f"section A-A pocket depth measured {depth:.3f}")
    print(f"wrote {PDF_PATH.relative_to(STUDY)}, {DXF_PATH.relative_to(STUDY)} ({len(PRIM)} primitives)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
