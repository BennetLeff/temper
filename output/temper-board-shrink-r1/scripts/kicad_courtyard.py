"""Read-only KiCad .kicad_pcb reader: footprints, courtyards, pads, outline, zones.

Standard library only. Parses the S-expression file, then for every footprint returns its
reference, atopile SourceInstance, library name, attribute (smd / through_hole), side, pose,
courtyard polygon(s) in the board frame and their area. A courtyard is built from the
footprint's F.CrtYd / B.CrtYd graphics (fp_rect, fp_poly, fp_circle, fp_line and fp_arc chained
into closed loops). If no closed loop can be built, the courtyard points' local bounding box is
used and the footprint is flagged `crtyd_fallback`.

KiCad stores footprint graphics in footprint-local coordinates. The board frame is y-down and a
footprint rotation is CCW on screen, so local (lx, ly) maps to
    X = x + lx*cos(t) + ly*sin(t),  Y = y - lx*sin(t) + ly*cos(t).
"""
from __future__ import annotations

import math
from pathlib import Path


# ---------------------------------------------------------------- S-expression parser
def parse_sexpr(text: str):
    """Iterative S-expression parser: returns nested lists of str tokens."""
    stack: list[list] = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif c in " \t\r\n":
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            stack[-1].append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            stack[-1].append(text[i:j])
            i = j
    return stack[0][0]


def kids(node, name):
    return [k for k in node[1:] if isinstance(k, list) and k and k[0] == name]


def kid(node, name):
    for k in node[1:]:
        if isinstance(k, list) and k and k[0] == name:
            return k
    return None


def xy(node):
    return float(node[1]), float(node[2])


# ---------------------------------------------------------------- geometry helpers
def shoelace(pts):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def arc_points(s, m, e, nseg=16):
    """Points along the circular arc start -> mid -> end (inclusive)."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [s, e]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1 = math.atan2(y1 - uy, x1 - ux)
    a2 = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)

    def ccw(a, b):
        return (b - a) % (2 * math.pi)
    sweep = ccw(a1, a3)
    if ccw(a1, a2) > sweep:          # mid not on the CCW path: go clockwise
        sweep -= 2 * math.pi
    return [(ux + r * math.cos(a1 + sweep * k / nseg), uy + r * math.sin(a1 + sweep * k / nseg))
            for k in range(nseg + 1)]


def chain_loops(segs, tol=1e-3):
    """Chain open polylines (each a list of points) into closed loops."""
    segs = [list(s) for s in segs]
    loops = []
    while segs:
        cur = segs.pop(0)
        changed = True
        while changed and math.dist(cur[0], cur[-1]) > tol:
            changed = False
            for k, s in enumerate(segs):
                if math.dist(cur[-1], s[0]) <= tol:
                    cur += s[1:]
                elif math.dist(cur[-1], s[-1]) <= tol:
                    cur += s[::-1][1:]
                elif math.dist(cur[0], s[-1]) <= tol:
                    cur = s[:-1] + cur
                elif math.dist(cur[0], s[0]) <= tol:
                    cur = s[::-1][:-1] + cur
                else:
                    continue
                segs.pop(k)
                changed = True
                break
        if math.dist(cur[0], cur[-1]) <= tol and len(cur) >= 4:
            loops.append(cur[:-1])
        else:
            return None                 # an open chain: caller falls back
    return loops


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


# ---------------------------------------------------------------- footprints
def _local_courtyard(fp, layers=("F.CrtYd", "B.CrtYd")):
    """Return (loops in local coords, all points, n_items) for the footprint's courtyard."""
    segs, loops, pts = [], [], []
    for g in fp[1:]:
        if not (isinstance(g, list) and g and g[0].startswith("fp_")):
            continue
        lay = kid(g, "layer")
        if not lay or lay[1] not in layers:
            continue
        t = g[0]
        if t == "fp_rect":
            (x1, y1), (x2, y2) = xy(kid(g, "start")), xy(kid(g, "end"))
            loop = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            loops.append(loop)
            pts += loop
        elif t == "fp_poly":
            p = [xy(q) for q in kid(g, "pts")[1:] if q[0] == "xy"]
            loops.append(p)
            pts += p
        elif t == "fp_circle":
            (cx, cy), (ex, ey) = xy(kid(g, "center")), xy(kid(g, "end"))
            r = math.hypot(ex - cx, ey - cy)
            loop = [(cx + r * math.cos(2 * math.pi * k / 48), cy + r * math.sin(2 * math.pi * k / 48)) for k in range(48)]
            loops.append(loop)
            pts += loop
        elif t == "fp_line":
            s = [xy(kid(g, "start")), xy(kid(g, "end"))]
            segs.append(s)
            pts += s
        elif t == "fp_arc":
            s = arc_points(xy(kid(g, "start")), xy(kid(g, "mid")), xy(kid(g, "end")))
            segs.append(s)
            pts += s
    fallback = False
    if segs:
        chained = chain_loops(segs)
        if chained is None:
            fallback = True
        else:
            loops += chained
    return loops, pts, fallback


def to_board(fx, fy, rot_deg, lx, ly):
    t = math.radians(rot_deg)
    return fx + lx * math.cos(t) + ly * math.sin(t), fy - lx * math.sin(t) + ly * math.cos(t)


def footprints(board):
    out = []
    for fp in kids(board, "footprint"):
        at = kid(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        props = {p[1]: p[2] for p in kids(fp, "property") if len(p) > 2}
        attr = kid(fp, "attr")
        layer = kid(fp, "layer")[1]
        loops, pts, fallback = _local_courtyard(fp)
        if loops and not fallback:
            # outer loops: drop a loop wholly inside another (a hole); courtyards rarely have one
            areas = sorted((shoelace(l), l) for l in loops)
            area = sum(a for a, _ in areas)
            board_loops = [[to_board(fx, fy, rot, *p) for p in l] for _, l in areas]
        elif pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            loop = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
            area = shoelace(loop)
            board_loops = [[to_board(fx, fy, rot, *p) for p in loop]]
            fallback = True
        else:
            area, board_loops, fallback = 0.0, [], True
        pads = []
        for pd in kids(fp, "pad"):
            net = kid(pd, "net")
            pads.append({"num": pd[1], "kind": pd[2], "net": (net[-1] if net else None)})
        bx = [p[0] for l in board_loops for p in l] or [fx]
        by = [p[1] for l in board_loops for p in l] or [fy]
        out.append({
            "ref": props.get("Reference"),
            "path": props.get("SourceInstance"),
            "value": props.get("Value"),
            "lib": fp[1],
            "attr": [a for a in attr[1:]] if attr else [],
            "side": "B" if layer == "B.Cu" else "F",
            "at": [fx, fy, rot],
            "crtyd_area_mm2": area,
            "crtyd_fallback": fallback,
            "crtyd_loops": board_loops,
            "crtyd_bbox": [min(bx), min(by), max(bx), max(by)],
            "pads": pads,
        })
    return out


# ---------------------------------------------------------------- board outline and zones
def edge_cuts(board):
    """Return (outline bbox, list of circular holes (cx, cy, r), outline polygon area estimate)."""
    segs, circles = [], []
    for g in board[1:]:
        if not (isinstance(g, list) and g and g[0].startswith("gr_")):
            continue
        lay = kid(g, "layer")
        if not lay or lay[1] != "Edge.Cuts":
            continue
        t = g[0]
        if t == "gr_line":
            segs.append([xy(kid(g, "start")), xy(kid(g, "end"))])
        elif t == "gr_arc":
            segs.append(arc_points(xy(kid(g, "start")), xy(kid(g, "mid")), xy(kid(g, "end"))))
        elif t == "gr_rect":
            (x1, y1), (x2, y2) = xy(kid(g, "start")), xy(kid(g, "end"))
            segs += [[(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)], [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)]]
        elif t == "gr_circle":
            (cx, cy), (ex, ey) = xy(kid(g, "center")), xy(kid(g, "end"))
            circles.append((cx, cy, math.hypot(ex - cx, ey - cy)))
        elif t == "gr_poly":
            p = [xy(q) for q in kid(g, "pts")[1:] if q[0] == "xy"]
            segs.append(p + [p[0]])
    loops = chain_loops(segs, tol=0.01) or []
    loops = sorted(loops, key=shoelace, reverse=True)
    outer = loops[0] if loops else []
    inner = loops[1:]
    xs = [p[0] for p in outer] or [0]
    ys = [p[1] for p in outer] or [0]
    holes = [(c[0], c[1], c[2]) for c in circles]
    for l in inner:                  # milled holes drawn as arcs/lines
        cx = sum(p[0] for p in l) / len(l)
        cy = sum(p[1] for p in l) / len(l)
        holes.append((cx, cy, math.sqrt(shoelace(l) / math.pi)))
    return {"bbox": [min(xs), min(ys), max(xs), max(ys)], "outer_area_mm2": shoelace(outer) if outer else 0.0,
            "outer": outer, "holes": holes}


def zones(board):
    out = []
    for z in kids(board, "zone"):
        net = kid(z, "net_name") or kid(z, "net")          # KiCad 10 writes (net "name")
        lays = kid(z, "layers") or kid(z, "layer")
        polys = []
        for poly in kids(z, "polygon"):
            p = [xy(q) for q in kid(poly, "pts")[1:] if q[0] == "xy"]
            polys.append(p)
        filled = []
        for fp in kids(z, "filled_polygon"):
            lay = kid(fp, "layer")
            p = [xy(q) for q in kid(fp, "pts")[1:] if q[0] == "xy"]
            filled.append((lay[1] if lay else None, p))
        out.append({"net": net[1] if net else None, "layers": lays[1:] if lays else [],
                    "outline_area_mm2": sum(shoelace(p) for p in polys), "outline": polys,
                    "filled": filled, "keepout": kid(z, "keepout") is not None})
    return out


def load(path):
    return parse_sexpr(Path(path).read_text())
