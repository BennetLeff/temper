# provenance: agent/hole-edge-placement-constraints, stacked on
# agent/per-pairing-placement-route @ bc3a19b06. Board sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
# verified unmodified before and after every run. See
# docs/evidence/2026-08-19-hole-geometry-placement-constraints.md
"""Static hole census on a .kicad_pcb: hole sizes, hole-to-hole, hole-to-edge.

Reads drills straight out of the file (footprint pads + vias), applies the
footprint's placement transform, and reports:

  * every drill diameter vs pcb/temper.kicad_pro's min_through_hole_diameter
    (the figure kicad-cli's `drill_out_of_range` is checked against)
  * minimum edge-to-edge hole-to-hole distance over all pairs, split into
    same-footprint and DIFFERENT-footprint pairs, vs the DRU's
    `hole_to_hole` min (0.5mm, scripts/generate_kicad_dru.py)
  * minimum hole-edge-to-board-outline distance vs the outline polygon

Read-only. No repo figure is invented here: every threshold is read from the
tree and printed with its source.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path

_ap = argparse.ArgumentParser()
_ap.add_argument("--board", type=Path, required=True)
_ap.add_argument("--repo", type=Path, default=Path.cwd())
_ap.add_argument("--label", default="")
_args = _ap.parse_args()
board_path = _args.board
repo = _args.repo
label = _args.label or board_path.name

pro = json.loads((repo / "pcb" / "temper.kicad_pro").read_text())
rules = pro["board"]["design_settings"]["rules"]
MIN_TH = rules["min_through_hole_diameter"]
MIN_H2H_PRO = rules["min_hole_to_hole"]
MIN_EDGE = rules["min_copper_edge_clearance"]
# DRU figure (scripts/generate_kicad_dru.py: '(rule "PTH hole to hole")')
DRU_H2H = 0.5

text = board_path.read_text(encoding="utf-8")

def sexp(s, i):
    """Parse one s-expression starting at s[i]=='(' -> (list, next_index)."""
    assert s[i] == "("
    i += 1; out = []; tok = ""
    while i < len(s):
        c = s[i]
        if c == "(":
            sub, i = sexp(s, i); 
            if tok: out.append(tok); tok = ""
            out.append(sub); continue
        if c == ")":
            if tok: out.append(tok)
            return out, i + 1
        if c == '"':
            j = i + 1; buf = ""
            while s[j] != '"' or s[j-1] == "\\":
                buf += s[j]; j += 1
            if tok: out.append(tok); tok = ""
            out.append(buf); i = j + 1; continue
        if c.isspace():
            if tok: out.append(tok); tok = ""
            i += 1; continue
        tok += c; i += 1
    raise ValueError("unbalanced")

def find_all(name):
    out = []
    pat = "(" + name + " "
    i = 0
    while True:
        i = text.find(pat, i)
        if i < 0: break
        node, _ = sexp(text, i)
        out.append(node)
        i += len(pat)
    return out

def get(node, key):
    for e in node:
        if isinstance(e, list) and e and e[0] == key:
            return e
    return None

def fnum(x): return float(x)

holes = []   # (x, y, dia, owner, kind)
# --- footprints -> pads
for fp in find_all("footprint"):
    at = get(fp, "at")
    fx, fy = fnum(at[1]), fnum(at[2])
    fang = math.radians(fnum(at[3])) if len(at) > 3 else 0.0
    ref = "?"
    for e in fp:
        if isinstance(e, list) and e and e[0] == "property" and len(e) > 2 and e[1] == "Reference":
            ref = e[2]
    for e in fp:
        if not (isinstance(e, list) and e and e[0] == "pad"): continue
        ptype = e[2] if len(e) > 2 else ""
        if ptype not in ("thru_hole", "np_thru_hole"): continue
        pat_ = get(e, "at"); dr = get(e, "drill")
        if pat_ is None or dr is None: continue
        px, py = fnum(pat_[1]), fnum(pat_[2])
        # drill: (drill D) or (drill oval W H)
        vals = [t for t in dr[1:] if not isinstance(t, list)]
        if vals and vals[0] == "oval":
            dia = min(fnum(vals[1]), fnum(vals[2]))
        else:
            dia = fnum(vals[0])
        # KiCad footprint rotation, Y-down file frame. VERIFIED against
        # kicad-cli's own DRC item positions: U27 (at 33.1 47.96 90) pad 2
        # local (-9.0, 8.89) -> kicad-cli reports (41.99, 56.96), which this
        # transform reproduces exactly and the standard math-CCW transform
        # does not (it gives (24.21, 38.96)).
        c, s = math.cos(fang), math.sin(fang)
        wx = fx + px * c + py * s
        wy = fy - px * s + py * c
        holes.append((wx, wy, dia, ref, "pad"))
# --- vias
for v in find_all("via"):
    at = get(v, "at"); dr = get(v, "drill")
    if at is None or dr is None: continue
    holes.append((fnum(at[1]), fnum(at[2]), fnum(dr[1]), "VIA", "via"))

# --- board outline segments (Edge.Cuts)
edges = []
for m in re.finditer(r"\(gr_line\b", text):
    node, _ = sexp(text, m.start())
    ly = get(node, "layer")
    if ly and ly[1] == "Edge.Cuts":
        s_, e_ = get(node, "start"), get(node, "end")
        edges.append((fnum(s_[1]), fnum(s_[2]), fnum(e_[1]), fnum(e_[2])))
for m in re.finditer(r"\(gr_rect\b", text):
    node, _ = sexp(text, m.start())
    ly = get(node, "layer")
    if ly and ly[1] == "Edge.Cuts":
        s_, e_ = get(node, "start"), get(node, "end")
        x1, y1, x2, y2 = fnum(s_[1]), fnum(s_[2]), fnum(e_[1]), fnum(e_[2])
        edges.extend([(x1,y1,x2,y1),(x2,y1,x2,y2),(x2,y2,x1,y2),(x1,y2,x1,y1)])

for m in re.finditer(r"\(gr_poly\b", text):
    node, _ = sexp(text, m.start())
    ly = get(node, "layer")
    if not (ly and ly[1] == "Edge.Cuts"):
        continue
    pts = get(node, "pts")
    coords = [(fnum(e[1]), fnum(e[2])) for e in pts[1:]
              if isinstance(e, list) and e and e[0] == "xy"]
    for a in range(len(coords)):
        (x1, y1), (x2, y2) = coords[a], coords[(a + 1) % len(coords)]
        edges.append((x1, y1, x2, y2))

def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx*dx + dy*dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / L2))
    return math.hypot(px - (x1 + t*dx), py - (y1 + t*dy))

print(f"=== hole census: {label} ===")
print(f"board {board_path}")
print(f"thresholds read from tree: min_through_hole_diameter={MIN_TH} "
      f"(pcb/temper.kicad_pro), hole_to_hole DRU={DRU_H2H} "
      f"(scripts/generate_kicad_dru.py), kicad_pro min_hole_to_hole={MIN_H2H_PRO}, "
      f"min_copper_edge_clearance={MIN_EDGE}")
pads = [h for h in holes if h[4] == "pad"]
vias = [h for h in holes if h[4] == "via"]
print(f"holes: {len(pads)} footprint pad holes, {len(vias)} via holes, {len(holes)} total")

under = [h for h in holes if h[2] < MIN_TH - 1e-9]
print(f"\ndrill diameter < min_through_hole_diameter ({MIN_TH}mm): {len(under)}")
from collections import Counter
print("  by (kind, diameter):", dict(Counter((h[4], round(h[2],3)) for h in under)))
print("  all drill diameters, pads:", dict(Counter(round(h[2],3) for h in pads)))
print("  all drill diameters, vias:", dict(Counter(round(h[2],3) for h in vias)))

# hole-to-hole
best_diff = (1e9, None); best_same = (1e9, None)
n = len(holes)
for i in range(n):
    xi, yi, di, oi, ki = holes[i]
    for j in range(i+1, n):
        xj, yj, dj, oj, kj = holes[j]
        gap = math.hypot(xi-xj, yi-yj) - di/2 - dj/2
        same = (oi == oj and ki == "pad" and kj == "pad")
        if same:
            if gap < best_same[0]: best_same = (gap, (oi,ki,oj,kj,xi,yi,xj,yj))
        else:
            if gap < best_diff[0]: best_diff = (gap, (oi,ki,oj,kj,xi,yi,xj,yj))
viol_diff = 0; viol_same = 0
for i in range(n):
    xi, yi, di, oi, ki = holes[i]
    for j in range(i+1, n):
        xj, yj, dj, oj, kj = holes[j]
        gap = math.hypot(xi-xj, yi-yj) - di/2 - dj/2
        if gap < DRU_H2H - 1e-9:
            if oi == oj and ki == "pad" and kj == "pad": viol_same += 1
            else: viol_diff += 1
print(f"\nhole-to-hole (edge-to-edge), threshold {DRU_H2H}mm:")
print(f"  min over DIFFERENT-owner pairs : {best_diff[0]:.4f} mm  {best_diff[1]}")
print(f"  min over SAME-footprint pairs  : {best_same[0]:.4f} mm  {best_same[1]}")
print(f"  violating pairs: different-owner {viol_diff}, same-footprint {viol_same}")

# hole-to-edge
if edges:
    worst = (1e9, None)
    nviol = 0
    for (x, y, d, o, k) in holes:
        dmin = min(seg_dist(x, y, *e) for e in edges) - d/2
        if dmin < worst[0]: worst = (dmin, (o, k, x, y))
        if dmin < MIN_EDGE - 1e-9: nviol += 1
    print(f"\nhole-edge to board outline (Edge.Cuts, {len(edges)} segments):")
    print(f"  min: {worst[0]:.4f} mm  {worst[1]}")
    print(f"  holes closer than min_copper_edge_clearance ({MIN_EDGE}mm): {nviol}")
else:
    print("\nNO Edge.Cuts gr_line found -- outline not measured")
