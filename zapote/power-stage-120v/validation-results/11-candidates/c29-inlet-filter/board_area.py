#!/usr/bin/env python3 -I
"""C29: where could the inlet-filter parts go on the stage-27 board?  Read-only text parse of the s27 KiCad board
(no KiCad run).  Footprint courtyards (F/B.CrtYd lines/rects/polys, rotated and translated) are rasterised on a 1 mm
grid inside the Edge.Cuts outline; the script reports occupancy, the mains-corner parts, and the largest free
axis-aligned rectangles (both sides; THT bodies occupy both).

Usage: python3 -I board_area.py [board.kicad_pcb]   -> board_area.json next to this file
Default board: runs-native21/s27/s27b/section.kicad_pcb (board sha256 44644390..., DECISIONS item 29).
Limitations: courtyards only (no copper keepouts, no 8 mm HOT/SELV barrier, no pours, no height or enclosure
envelope), so a 'free' rectangle is a necessary, not sufficient, condition for placement."""
import json, math, os, re, sys, hashlib

BOARD = sys.argv[1] if len(sys.argv) > 1 else "/Users/bennet/Desktop/temper/worktrees/runs-native21/s27/s27b/section.kicad_pcb"
HERE = os.path.dirname(os.path.abspath(__file__))


def tokenize(s):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', s)


def parse(tokens):
    stack, cur = [], []
    for t in tokens:
        if t == "(":
            stack.append(cur); cur = []
        elif t == ")":
            done = cur; cur = stack.pop(); cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first(node, key):
    r = find(node, key)
    return r[0] if r else None


raw = open(BOARD).read()
sha = hashlib.sha256(raw.encode()).hexdigest()
tree = parse(tokenize(raw))

# ---- outline
xs, ys = [], []
for g in tree:
    if isinstance(g, list) and g and g[0] in ("gr_line", "gr_rect", "gr_arc", "gr_poly"):
        lay = first(g, "layer")
        if lay and lay[1] == "Edge.Cuts":
            for k in ("start", "end", "mid"):
                p = first(g, k)
                if p: xs.append(float(p[1])); ys.append(float(p[2]))
            pts = first(g, "pts")
            if pts:
                for xy in find(pts, "xy"): xs.append(float(xy[1])); ys.append(float(xy[2]))
X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
# outline polygon from the Edge.Cuts gr_line segments (chained); the s27 outline is an L (290 x 140 plus 91 x 50)
segs = []
for g in tree:
    if isinstance(g, list) and g and g[0] == "gr_line":
        lay = first(g, "layer")
        if lay and lay[1] == "Edge.Cuts":
            a, b = first(g, "start"), first(g, "end")
            segs.append(((float(a[1]), float(a[2])), (float(b[1]), float(b[2]))))


def inside(px, py):
    c = False
    for (ax, ay), (bx, by) in segs:
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            c = not c
    return c

# ---- footprints
fps = []
for fp in find(tree, "footprint"):
    at = first(fp, "at"); x, y = float(at[1]), float(at[2]); rot = float(at[3]) if len(at) > 3 else 0.0
    ref = None
    for p in find(fp, "property"):
        if p[1] == "Reference": ref = p[2]
    if ref is None:
        for t in find(fp, "fp_text"):
            if t[1] == "reference": ref = t[2]
    side = first(fp, "layer")[1]
    pts = []
    for g in fp:
        if isinstance(g, list) and g and g[0] in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
            lay = first(g, "layer")
            if not lay or "CrtYd" not in lay[1]: continue
            if g[0] == "fp_circle":
                c, e = first(g, "center"), first(g, "end")
                cx, cy = float(c[1]), float(c[2]); r = math.hypot(float(e[1]) - cx, float(e[2]) - cy)
                pts += [(cx - r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx + r, cy - r)]
            for k in ("start", "end", "mid"):
                p = first(g, k)
                if p and g[0] != "fp_circle": pts.append((float(p[1]), float(p[2])))
            pp = first(g, "pts")
            if pp: pts += [(float(q[1]), float(q[2])) for q in find(pp, "xy")]
    if not pts: continue
    a = math.radians(-rot)   # KiCad: positive rotation is CCW on screen with y down
    w = [(x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a)) for px, py in pts]
    bx0, bx1 = min(p[0] for p in w), max(p[0] for p in w)
    by0, by1 = min(p[1] for p in w), max(p[1] for p in w)
    val = None
    for p in find(fp, "property"):
        if p[1] == "Value": val = p[2]
    fps.append(dict(ref=ref, lib=fp[1], value=val, side=side, x=x, y=y, rot=rot, bbox=[bx0, by0, bx1, by1],
                    tht=any(isinstance(c, list) and c and c[0] == "pad" and c[2] == "thru_hole" for c in fp)))

# ---- raster (1 mm); THT parts block both sides, SMD only their side
NX, NY = int(math.ceil(X1 - X0)), int(math.ceil(Y1 - Y0))
occ = {"F": [[0] * NX for _ in range(NY)], "B": [[0] * NX for _ in range(NY)]}
for f in fps:
    bx0, by0, bx1, by1 = f["bbox"]
    sides = ("F", "B") if f["tht"] else (f["side"][0],)
    for s in sides:
        for j in range(max(0, int(by0 - Y0)), min(NY, int(math.ceil(by1 - Y0)))):
            row = occ[s][j]
            for i in range(max(0, int(bx0 - X0)), min(NX, int(math.ceil(bx1 - X0)))):
                row[i] = 1
OUT = [[0 if inside(X0 + i + 0.5, Y0 + j + 0.5) else 1 for i in range(NX)] for j in range(NY)]
both = [[occ["F"][j][i] | occ["B"][j][i] | OUT[j][i] for i in range(NX)] for j in range(NY)]


def max_rects(grid, n=8, min_side=10):
    """Greedy: largest empty axis-aligned rectangle (histogram method), mark it, repeat."""
    g = [r[:] for r in grid]; out = []
    for _ in range(n):
        best = (0, None); h = [0] * NX
        for j in range(NY):
            for i in range(NX): h[i] = h[i] + 1 if not g[j][i] else 0
            st = []
            for i in range(NX + 1):
                cur = h[i] if i < NX else 0
                start = i
                while st and st[-1][1] >= cur:
                    s0, hh = st.pop()
                    wdt = i - s0
                    if min(wdt, hh) >= min_side and wdt * hh > best[0]:
                        best = (wdt * hh, (s0, j - hh + 1, wdt, hh))
                    start = s0
                st.append((start, cur))
        if not best[1]: break
        i0, j0, wdt, hh = best[1]
        out.append(dict(x0=X0 + i0, y0=Y0 + j0, w=wdt, h=hh, area_mm2=wdt * hh))
        for j in range(j0, j0 + hh):
            for i in range(i0, i0 + wdt): g[j][i] = 1
    return out


board_area = NX * NY - sum(map(sum, OUT))
used_both = sum(map(sum, both)) - sum(map(sum, OUT))
corner = [f for f in fps if f["x"] > X1 - 110 and f["y"] < Y0 + 80]
mains_refs = ("J1", "F1", "RV1", "C1", "C2", "R1", "R2", "L1", "C3", "C4", "BR1", "J6", "J3", "PS1", "PS2", "PS3", "J11", "F2")
res = dict(board=BOARD, board_sha256=sha, outline_mm=[X0, Y0, X1, Y1], outline_segments=segs, board_area_mm2=board_area,
           footprints=len(fps), occupied_both_sides_mm2=used_both, free_mm2=board_area - used_both,
           occupied_fraction=used_both / board_area,
           mains_parts={f["ref"]: dict(lib=f["lib"], value=f["value"], at=[f["x"], f["y"], f["rot"]],
                                       bbox=[round(v, 2) for v in f["bbox"]], tht=f["tht"])
                        for f in fps if f["ref"] in mains_refs},
           corner_parts_top_right_110x80=sorted(f["ref"] for f in corner),
           free_rects_both_sides=max_rects(both, 10, 10),
           free_rects_top_right_quadrant=None)
# free rectangles restricted to the right half / top half (mains corner region)
sub = [[both[j][i] if (X0 + i > X0 + NX / 2 and Y0 + j < Y0 + NY / 2) else 1 for i in range(NX)] for j in range(NY)]
res["free_rects_top_right_quadrant"] = max_rects(sub, 6, 8)
json.dump(res, open(os.path.join(HERE, "board_area.json"), "w"), indent=1)
print(f"board {sha[:12]}  outline {X0:.1f},{Y0:.1f} .. {X1:.1f},{Y1:.1f}  ({board_area} mm2, {len(fps)} footprints)")
print(f"courtyard-occupied (either side, THT both): {used_both} mm2 = {100*used_both/board_area:.1f} %; free {board_area-used_both} mm2 (fragmented)")
for r, d in sorted(res["mains_parts"].items()):
    print(f"  {r:5s} {d['lib'][:46]:46s} at {d['at'][0]:7.2f},{d['at'][1]:7.2f}  bbox {d['bbox']}")
print("largest free rectangles, whole board (>=10 mm side):")
for r in res["free_rects_both_sides"]: print(f"  x {r['x0']:.0f}..{r['x0']+r['w']:.0f}  y {r['y0']:.0f}..{r['y0']+r['h']:.0f}  {r['w']}x{r['h']} = {r['area_mm2']} mm2")
print("largest free rectangles, top-right quadrant (>=8 mm side):")
for r in res["free_rects_top_right_quadrant"]: print(f"  x {r['x0']:.0f}..{r['x0']+r['w']:.0f}  y {r['y0']:.0f}..{r['y0']+r['h']:.0f}  {r['w']}x{r['h']} = {r['area_mm2']} mm2")
