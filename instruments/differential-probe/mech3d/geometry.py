"""Shared loader and helpers for the Rev C probe's printed parts.

Every dimension comes from validation/leads/geometry.json, written by tools/leads.rs
(`make leads`). The part scripts never restate a dimension that leads.rs owns; the
only numbers they add are print details (wall thickness, fillets, snap widths,
fastener clearances), named at the top of each script.

Frames (right-handed, mm):
  s53 : stage-53 board, X = KiCad x, Y = -KiCad y, Z = height above the board top.
  box : probe board, X along the board (tip edge 0), Y = -KiCad y, Z above the
        enclosure's inner floor.
"""
import json
import math
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
G = json.loads((ROOT / "validation/leads/geometry.json").read_text())
OUT = HERE / "out"

# Resins (Formlabs; no insulation credit, see README). Prices read 2026-10-20 from
# formlabs.com, before tax: Flame Retardant 0.84 L $249 (Form 4), Tough 2000 1 L $149.
RESIN = {
    "Flame Retardant": {"usd_per_l": 249.0 / 0.84, "note": "UL 94 V-0 at 3 mm; walls >= 3 mm where it matters"},
    "Tough 2000": {"usd_per_l": 149.0, "note": "clips, clamps and tool parts"},
}

# Common print details (not owned by leads.rs).
M3_CLEAR = 3.4  # nylon M3 screw clearance
M3_NUT_AF = 5.5 + 0.3  # nylon M3 hex nut across flats, with fit
M3_NUT_T = 2.4 + 0.3
FIT = 0.2  # sliding fit, each side
R_G = G["clearances"]["lead_groove_r"]  # lead groove radius (OD max / 2 + 0.15)
TIE_SLOT = G["box"]["bridge"]["tie_slot"]  # (along the lead, across) for a 2.5 mm tie
TIE_GAP = G["box"]["bridge"]["tie_gap"]


def box(lo, hi):
    """Axis-aligned box from two corners."""
    lo, hi = [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)]
    w, d, h = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    return cq.Workplane("XY").box(w, d, h, centered=False).translate(tuple(lo))


def gbox(b):
    return box(b["lo"], b["hi"])


def part_boxes(name):
    p = next(p for p in G["parts_s53"] if p["name"] == name)
    return {b["name"]: b["box"] for b in p["boxes"]}


def lead(probe, name):
    return next(l for l in G["leads"] if l["probe"] == probe and l["name"] == name)


def sweep_circle(pts, r):
    """Solid tube of radius r along a 3-D polyline (rounded joints)."""
    pts = dedupe(pts)
    v = [cq.Vector(*p) for p in pts]
    path = cq.Wire.makePolygon(v, close=False)
    d = (v[1] - v[0]).normalized()
    circ = cq.Wire.makeCircle(r, v[0], d)
    solid = cq.Solid.sweep(circ, [], path, transitionMode="round")
    return cq.Workplane("XY").add(solid)


def tube_union(pts, r, step=6):
    """Robust tube: union of short cylinders with spheres at the joints.

    Sweeping along long sampled polylines can fail in OCCT; this builds the same
    envelope from primitives. Used for cutting grooves and for display leads."""
    pts = dedupe(resample(pts, step))
    shape = None
    for a, b in zip(pts, pts[1:]):
        va, vb = cq.Vector(*a), cq.Vector(*b)
        d = vb - va
        L = d.Length
        if L < 1e-6:
            continue
        cyl = cq.Solid.makeCylinder(r, L, va, d.normalized())
        sph = cq.Solid.makeSphere(r, va)
        piece = cyl.fuse(sph)
        shape = piece if shape is None else shape.fuse(piece)
    shape = shape.fuse(cq.Solid.makeSphere(r, cq.Vector(*pts[-1])))
    return cq.Workplane("XY").add(shape.clean())


def tube(pts, r):
    """Tube of radius r along a lead: a circle swept along the polyline resampled
    every 1 mm, round transitions. (A spline sweep looked smoother but gave wrong
    booleans against the dock boxes.) Falls back to tube_union if OCCT rejects it."""
    pts = uniform(dedupe(pts, 0.05), 1.0)
    try:
        s = sweep_circle(pts, r).val()
        if s.isValid():
            return s
    except Exception:
        pass
    return tube_union(pts, r, step=2).val()


def open_groove(pts, r, d=None, depth=0.0, k=1.0):
    """Groove cutter: a tube of radius r along pts, swept `depth` along unit vector
    d (copies every k mm) so the lead can be laid in from that side."""
    shape = tube(pts, r)
    if d and depth > 0:
        n = int(math.ceil(depth / k))
        for i in range(1, n + 1):
            f = depth * i / n
            shape = shape.fuse(tube([[p[j] + d[j] * f for j in range(3)] for p in pts], r))
    return shape.clean()


def tagged(l, tags):
    """Points of lead l whose tag is in `tags`."""
    return [p for p, t in zip(l["pts"], l["tags"]) if t in tags]


def path_frame(pts, f):
    """Point and unit tangent at fraction f of the polyline's length."""
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    target = f * sum(seg)
    acc = 0.0
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if acc + L >= target and L > 0:
            u = (target - acc) / L
            return [a[i] + u * (b[i] - a[i]) for i in range(3)], [(b[i] - a[i]) / L for i in range(3)]
        acc += L
    a, b = pts[-2], pts[-1]
    L = math.dist(a, b)
    return list(b), [(b[i] - a[i]) / L for i in range(3)]


def uniform(pts, step):
    """Points every `step` mm of arc length along the polyline (ends kept), so a
    spline through them does not wiggle where the input spacing changes."""
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(seg)
    n = max(2, int(round(total / step)))
    out, i, acc = [], 0, 0.0
    for k in range(n + 1):
        t = total * k / n
        while i < len(seg) - 1 and acc + seg[i] < t:
            acc += seg[i]
            i += 1
        f = 0.0 if seg[i] == 0 else min(1.0, (t - acc) / seg[i])
        out.append([pts[i][j] + f * (pts[i + 1][j] - pts[i][j]) for j in range(3)])
    return out


def resample(pts, step):
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        acc += math.dist(a, b)
        if acc >= step:
            out.append(b)
            acc = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def dedupe(pts, eps=1e-4):
    out = [tuple(pts[0])]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > eps:
            out.append(tuple(p))
    return out


def export(wp, name, resin, orientation):
    """STEP + STL to mech3d/out/, and a one-line record for the BOM / README."""
    OUT.mkdir(exist_ok=True)
    shape = wp.val() if isinstance(wp, cq.Workplane) else wp
    if isinstance(wp, cq.Workplane) and len(wp.vals()) > 1:
        shape = cq.Compound.makeCompound([v for v in wp.vals()])
    cq.exporters.export(cq.Workplane("XY").add(shape), str(OUT / f"{name}.step"))
    cq.exporters.export(cq.Workplane("XY").add(shape), str(OUT / f"{name}.stl"), tolerance=0.05, angularTolerance=0.2)
    vol = shape.Volume() / 1000.0  # cm3
    bb = shape.BoundingBox()
    rec = {
        "part": name,
        "resin": resin,
        "volume_cm3": round(vol, 2),
        "bbox_mm": [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)],
        "orientation": orientation,
    }
    (OUT / f"{name}.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(f"{name}: {vol:.2f} cm3, bbox {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, {resin}")
    return shape


def hole_xy(name):
    h = next(h for h in G["stage53"]["holes"] if h["name"] == name)
    return h["at"][0], h["at"][1]
