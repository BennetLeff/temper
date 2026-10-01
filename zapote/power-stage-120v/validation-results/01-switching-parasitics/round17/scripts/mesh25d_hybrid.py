#!/usr/bin/env python3
"""Hybrid air mesh of one board leg, on SIMPLIFIED copper (round 16).

Round 16 change: only a band from --band-pad below the board to --band-pad
above the highest arch is extruded (steps 2-3 below). The air above and below
the band is two boxes meshed with free tetrahedra by gmsh, whose faces on
the band are the band's own 2-D triangulation. Round 15 extruded the whole
air box, which stretched sliver 2-D triangles through 2-3 mm slabs into
thousands of elements with aspect ratio above 100.

Round-15 description (unchanged otherwise):

Defeaturing (D1-FEM round 15): only the loop nets are kept (other nets' copper
is dropped; their clearance holes in the planes remain); each net and layer
is opened at --open-r (removing features narrower than 2r), closed at the same
radius (filling same-net gaps narrower than 2r), stripped of holes and islands
below --min-area, simplified at --simplify and snapped to GRID. Results are
checked by solving at two simplification levels.


Rounds 11 and 13 built exact 3-D copper solids with OpenCASCADE booleans and
meshed the air around them; every attempt with barrels failed at some local
spot where surfaces met. This mesher uses no 3-D booleans:

1. Every outline (all nets' copper on every layer, barrel footprints,
   closure legs, bridge bars, port strips, the crop and the air box) is
   noded into non-crossing segments and embedded in one 2-D domain, which
   gmsh meshes once. Each triangle is then wholly inside or outside every
   outline.
2. The 2-D mesh is extruded through a list of z-levels (board layers,
   dielectric sub-layers, arch levels, graded air above and below). Every
   level uses the same 2-D nodes, so the mesh conforms by construction.
3. Each triangle-by-slab prism is copper or air according to the outline it
   lies in on that slab. Only air prisms are written, each split into three
   tetrahedra by the sorted-vertex rule, so neighbouring prisms share
   diagonals.
4. Air/copper faces become the PEC boundary (physical 2), the outer box the
   far field (3), and each port the horizontal faces at its span level
   within its strip (10, 11, ...).

Coordinates: X = board X, Y = -board Y (KiCad STEP convention), mm; B.Cu
underside at z = -0.07. Output: gmsh MSH 2.2 ASCII.

    PYTHONPATH=/opt/homebrew/lib python3 mesh25d.py EXPORT.json.gz OUT.msh \
        --leg A --closures closures-legA.json --arch-h 1 --h-edge 0.25 --h-far 2
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from collections import defaultdict

import gmsh
import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

LOOP_NETS = {"A": {"bus_p", "hv_ret", "leg_ret", "sw_a", "leg_a-out_h", "leg_a-gate_h", "leg_a-out_l", "leg_a-gate_l"}}
LEGS = {"A": (125.865, 4.215, 164.6, 41.125), "B": (88.4, 4.215, 127.135, 41.125)}
LAYERS = {"B.Cu": (-0.07, 0.0), "In2.Cu": (0.4355, 0.4965), "In1.Cu": (0.9965, 1.0575), "F.Cu": (1.493, 1.563)}
Z_BOTTOM, Z_TOP = -0.07, 1.563
LEG_W, SPAN_W, BAR_T, LEG_EXTRA = 0.6, 0.6, 0.1, 0.3
# Driven port strips are narrower than the legs and are not snapped: their
# sides must stay exactly parallel to the current. Snapped 0.6 mm strips took
# their corners onto nearby pad edges and leaked 0.13 A of 1 A into the air
# (round 15), which stalls an ungauged iterative solve.
PORT_W = 0.4
LEAK_TOL_A = 1e-9
# One snapping grid for every outline (mm): near-duplicate edges from different
# layers become identical, so polygonize doesn't make zero-area sliver faces.
GRID = 0.01
SNAP_TOL = 0.03


def polys(g):
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]


def rect(ax, ay, bx, by, width, inset=0.0):
    """Rectangle of `width` along the segment (ax,ay)->(bx,by), shortened by
    `inset` at both ends, in board coordinates."""
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx, ny = -uy * width / 2, ux * width / 2
    p0 = (ax + ux * inset, ay + uy * inset)
    p1 = (bx - ux * inset, by - uy * inset)
    return Polygon([(p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny),
                    (p1[0] - nx, p1[1] - ny), (p0[0] - nx, p0[1] - ny)])


def clean(g, open_r, min_area, simplify):
    """Morphological opening then closing, drop small holes/islands, simplify, snap."""
    if g.is_empty:
        return g
    g = g.buffer(-open_r, join_style="mitre").buffer(open_r, join_style="mitre")
    g = g.buffer(open_r, join_style="mitre").buffer(-open_r, join_style="mitre")
    out = []
    for p in polys(g):
        if p.area < min_area:
            continue
        holes = [h for h in p.interiors if Polygon(h).area >= min_area]
        out.append(Polygon(p.exterior, holes))
    g = unary_union(out).simplify(simplify, preserve_topology=True)
    return shapely.set_precision(g, GRID).buffer(0)


def load_copper(path, crop, simplify, min_area, no_barrels, nets, open_r):
    data = json.load(gzip.open(path, "rt"))
    shapes = defaultdict(lambda: defaultdict(list))
    barrels = defaultdict(list)
    for it in data["primitives"]:
        if it["net"] not in nets:
            continue
        k, lyr = it["kind"], it.get("layer")
        if k in ("zone", "pad"):
            g = Polygon(it["shell"], it["holes"]).buffer(0)
        elif k == "track":
            g = LineString([it["start"], it["end"]]).buffer(it["width_mm"] / 2, 16)
        elif k == "via":
            g = Point(it["centre"]).buffer(it["diameter_mm"] / 2, 24)
        else:
            continue
        if g.intersects(crop):
            shapes[it["net"]][lyr].append(g)
        drill = it.get("drill_mm") or 0.0
        if isinstance(drill, list):
            drill = drill[0]
        if k in ("pad", "via") and drill > 0:
            fp = Point(it["centre"]).buffer(drill / 2, 4)
            if crop.buffer(-0.05).contains(fp):
                barrels[it["net"]].append(fp)
    barrel_union = Polygon()
    if not no_barrels:
        barrel_union = shapely.set_precision(unary_union([b_ for v in barrels.values() for b_ in v]), GRID)
    layer = {}
    for lyr in LAYERS:
        per_net = []
        for net in nets:
            g = unary_union(shapes[net].get(lyr, [])).intersection(crop)
            g = clean(g, open_r, min_area, simplify)
            if not no_barrels and barrels.get(net):
                g = shapely.set_precision(unary_union([g, *barrels[net]]), GRID).buffer(0)
            per_net.append(g)
        layer[lyr] = shapely.set_precision(unary_union(per_net), GRID).buffer(0)
    # Snap each layer to the layers before it (GEOS snap, SNAP_TOL): the same
    # feature on several layers came out 3-15 um apart after per-layer
    # simplification, and those near-parallel edges crossed at shallow angles
    # (round 15: duplicate nodes at (119.888, 20.784)).
    ref = None
    for lyr in LAYERS:
        g = layer[lyr]
        if ref is not None and not g.is_empty:
            g = shapely.set_precision(shapely.snap(g, ref, SNAP_TOL).buffer(0), GRID).buffer(0)
            layer[lyr] = g
        ref = g.boundary if ref is None else unary_union([ref, g.boundary])
    if not barrel_union.is_empty:
        barrel_union = shapely.set_precision(shapely.snap(barrel_union, ref, SNAP_TOL).buffer(0), GRID)
    n_barrels = 0 if no_barrels else len({(round(b_.centroid.x, 4), round(b_.centroid.y, 4)) for v in barrels.values() for b_ in v})
    return layer, barrel_union, n_barrels, ref


def rings(e_bnd):
    """Split the 2-D mesh's boundary edges (u, v, tri) into closed rings.

    One ring is the air box outline; any other would be a hole in the 2-D
    mesh, which main() forbids."""
    nb = defaultdict(list)
    for u, v, _ in e_bnd:
        nb[int(u)].append(int(v))
        nb[int(v)].append(int(u))
    assert all(len(v) == 2 for v in nb.values()), "2-D boundary is not a set of simple rings"
    left, out = set(nb), []
    while left:
        start = min(left)
        ring, prev, cur = [start], None, start
        while True:
            nxt = nb[cur][0] if nb[cur][0] != prev else nb[cur][1]
            if nxt == start:
                break
            ring.append(nxt)
            prev, cur = cur, nxt
        left -= set(ring)
        out.append(np.array(ring))
    return out


def outer_boxes(xyz_all, tri, n2, nz, e_bnd, z_far_lo, z_far_hi, a):
    """Mesh the air above and below the extruded band with free tetrahedra.

    Each box is bounded by the band's end triangulation (shared nodes), walls
    over the 2-D boundary ring (structured, spaced about h_far) and a far face
    (gmsh 2-D). gmsh fills the closed surface; interior nodes are appended.
    Returns (xyz_all, [tets], [far-field triangles]).
    """
    rs = rings(e_bnd)
    lo = xyz_all[:n2, :2].min(0)
    outer = [r for r in rs if np.isclose(xyz_all[r, :2], lo).all(1).any()]
    assert len(outer) == 1, "no unique outer ring"
    ring = outer[0]
    # holes would be PEC columns (spurious vias); main() refuses to make them
    assert len(rs) == 1, f"2-D mesh has {len(rs) - 1} holes"
    xyz = [xyz_all]
    n_tot = len(xyz_all)
    all_tets, all_far = [], []
    for k_face, z_far in ((nz - 1, z_far_hi), (0, z_far_lo)):
        z_face = xyz_all[k_face * n2, 2]
        nlev = max(1, math.ceil(abs(z_far - z_face) / a.h_far))
        zw = [z_face + (z_far - z_face) * (l / nlev) for l in range(nlev + 1)]
        ring_ids = [ring + k_face * n2]
        ring_xy = xyz_all[ring + k_face * n2, :2]
        for l in range(1, nlev + 1):
            ids = np.arange(n_tot, n_tot + len(ring))
            n_tot += len(ring)
            xyz.append(np.column_stack([ring_xy, np.full(len(ring), zw[l])]))
            ring_ids.append(ids)
        walls = []
        for l in range(nlev):
            u, v = ring_ids[l], np.roll(ring_ids[l], -1)
            U, V = ring_ids[l + 1], np.roll(ring_ids[l + 1], -1)
            walls += [np.stack([u, v, V], 1), np.stack([u, V, U], 1)]
        # far face: gmsh 2-D inside the top ring, boundary nodes fixed
        top = ring_ids[-1]
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        g = gmsh.model.geo
        pts = [g.addPoint(x_, y_, z_far, a.h_far) for x_, y_ in ring_xy]
        lns = [g.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        sf = g.addPlaneSurface([g.addCurveLoop(lns)])
        g.synchronize()
        for ln in lns:
            gmsh.model.mesh.setTransfiniteCurve(ln, 2)
        gmsh.model.mesh.generate(2)
        pt_node = {}
        for i, pt_ in enumerate(pts):
            nt, _, _ = gmsh.model.mesh.getNodes(0, pt_)
            pt_node[int(nt[0])] = int(top[i])
        nt, nc, _ = gmsh.model.mesh.getNodes(2, sf, includeBoundary=False)
        for t_, c_ in zip(nt, nc.reshape(-1, 3)):
            pt_node[int(t_)] = n_tot
            xyz.append(c_[None, :])
            n_tot += 1
        _, en = gmsh.model.mesh.getElementsByType(2, sf)
        far = np.array([pt_node[int(t_)] for t_ in en], dtype=np.int64).reshape(-1, 3)
        gmsh.finalize()
        face = tri + k_face * n2
        closed = np.concatenate([face] + walls + [far])
        far_all = np.concatenate(walls + [far])
        # volume: gmsh fills the closed discrete surface
        X = np.concatenate(xyz)
        used = np.unique(closed)
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 8)
        gmsh.option.setNumber("Mesh.Algorithm3D", a.algo3d)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.option.setNumber("Mesh.Renumber", 0)                 # keep our node tags
        gmsh.model.addDiscreteEntity(2, 1)
        gmsh.model.mesh.addNodes(2, 1, (used + 1).tolist(), X[used].ravel().tolist())
        gmsh.model.mesh.addElementsByType(1, 2, [], (closed + 1).ravel().tolist())
        sl = gmsh.model.geo.addSurfaceLoop([1])
        gmsh.model.geo.addVolume([sl], 1)
        gmsh.model.geo.synchronize()
        gmsh.model.mesh.generate(3)
        _, en = gmsh.model.mesh.getElementsByType(4)
        # The shared surface must come back unchanged: a Steiner point inserted
        # on it during boundary recovery would break conformity with the band.
        ns, _, _ = gmsh.model.mesh.getNodes(2, 1)
        extra = sorted(set(int(t_) for t_ in ns) - set((used + 1).tolist()))
        if extra:
            raise SystemExit(f"gmsh inserted {len(extra)} nodes on the outer-box surface")
        nt, nc, _ = gmsh.model.mesh.getNodes(3, 1, includeBoundary=False)
        known = set((used + 1).tolist()) | set(nt.tolist())
        stray = set(en.tolist()) - known
        if stray:
            raise SystemExit(f"{len(stray)} tet nodes are neither input nor volume nodes")
        remap = {}
        for t_, c_ in zip(nt, nc.reshape(-1, 3)):
            remap[int(t_)] = n_tot
            xyz.append(c_[None, :])
            n_tot += 1
        gmsh.finalize()
        tt = np.array([remap.get(int(t_), int(t_) - 1) for t_ in en], dtype=np.int64).reshape(-1, 4)
        all_tets.append(tt)
        all_far.append(far_all)
    return np.concatenate(xyz), all_tets, all_far


def merge_thin(faces, thin):
    """Merge each arrangement face narrower than `thin` (mean width 2A/P) into
    the neighbour it shares the longest boundary with (round 16).

    Near-coincident outlines from different layers leave faces a few microns
    wide; any triangle in them is a sliver, and extruded it becomes a
    tetrahedron with aspect ratio above 1000. Triangles are classified by
    centroid against the original outlines, so the model moves by less than
    the sliver width."""
    from shapely.strtree import STRtree
    faces = list(faces)
    merged = 0
    for _ in range(20):
        width = [2 * f_.area / f_.length for f_ in faces]
        thin_ix = sorted((i for i, w in enumerate(width) if w < thin), key=lambda i: width[i])
        if not thin_ix:
            break
        tree = STRtree(faces)
        gone, out = set(), {}
        for i in thin_ix:
            if i in gone or i in out:
                continue
            best, best_len = None, 0.0
            for j in tree.query(faces[i]):
                j = int(j)
                if j == i or j in gone or j in out or width[j] < thin:
                    continue
                shared = faces[i].boundary.intersection(faces[j].boundary).length
                if shared > best_len:
                    best, best_len = j, shared
            if best is None:
                continue
            out[best] = unary_union([faces[best], faces[i]])
            gone.add(i)
            merged += 1
        if not gone:
            break
        faces = [out.get(i, f_) for i, f_ in enumerate(faces) if i not in gone]
        faces = [g_ for f_ in faces for g_ in polys(f_)]
    return faces, merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("out")
    ap.add_argument("--leg", choices=LEGS, default="A")
    ap.add_argument("--margin", type=float, default=10.0)
    ap.add_argument("--air", type=float, default=10.0)
    ap.add_argument("--closures", required=True)
    ap.add_argument("--arch-h", type=float, default=1.0)
    ap.add_argument("--h-edge", type=float, default=0.25)
    ap.add_argument("--h-far", type=float, default=2.0)
    ap.add_argument("--dz-max", type=float, default=0.25, help="max sub-layer thickness in the board and arch region")
    ap.add_argument("--simplify", type=float, default=0.05)
    ap.add_argument("--min-area", type=float, default=0.05)
    ap.add_argument("--open-r", type=float, default=0.1)
    ap.add_argument("--no-barrels", action="store_true")
    ap.add_argument("--algo2d", type=int, default=6, help="gmsh 2-D algorithm")
    ap.add_argument("--extend-boundary", type=int, default=1, help="gmsh Mesh.MeshSizeExtendFromBoundary for the 2-D mesh")
    ap.add_argument("--thin", type=float, default=0.02, help="merge arrangement faces narrower than this (mm)")
    ap.add_argument("--cov-simplify", type=float, default=0.0, help="coverage simplify tolerance for the arrangement (mm; 0 = off)")
    ap.add_argument("--band-pad", type=float, default=0.5, help="air extruded above and below the copper (mm)")
    ap.add_argument("--algo3d", type=int, default=1, help="gmsh 3-D algorithm for the outer air boxes")
    a = ap.parse_args()
    t0 = time.time()
    x0, y0, x1, y1 = LEGS[a.leg]
    crop = box(x0 - a.margin, max(y0 - a.margin, -0.5), x1 + a.margin, y1 + a.margin)
    layer, barrel_union, n_barrels, snap_ref = load_copper(a.export, crop, a.simplify, a.min_area, a.no_barrels,
                                                 LOOP_NETS[a.leg], a.open_r)

    # Closures: legs (copper columns), bridge bars (thin copper slabs), port strips (driven faces).
    closures = json.load(open(a.closures))
    # Level-1 closures (gate-source bridges crossing over the drain-source
    # bridges) sit at 2h, not h + 1 mm, so they also vanish in the h -> 0
    # extrapolation (round 17: at h + 1 mm they left ~2-3 nH in the gate loops).
    # They must clear the level-0 bars and leg tops: 2h - BAR_T/2 > h + LEG_EXTRA.
    z_span = {0: Z_TOP + a.arch_h, 1: Z_TOP + 2 * a.arch_h}
    if a.arch_h - BAR_T / 2 <= LEG_EXTRA:
        raise SystemExit(f"arch height {a.arch_h} mm too low: level-1 bridges would touch level-0 legs/bars")
    legs = defaultdict(list)          # level -> leg squares (columns from Z_TOP to span + LEG_EXTRA)
    bars = defaultdict(list)          # level -> bar rectangles
    ports = []
    for cl in closures:
        lvl = cl.get("level", 0)
        (ax, ay), (bx, by) = cl["a"], cl["b"]
        for (px, py) in ((ax, ay), (bx, by)):
            legs[lvl].append(box(px - LEG_W / 2, py - LEG_W / 2, px + LEG_W / 2, py + LEG_W / 2))
        if cl["kind"] == "bridge":
            bars[lvl].append(rect(ax, ay, bx, by, SPAN_W))
        else:
            L = math.hypot(bx - ax, by - ay)
            strip = rect(ax, ay, bx, by, PORT_W, inset=LEG_W / 2)
            ports.append({"name": cl["name"], "strip": strip, "z": z_span[lvl],
                          "direction": [(bx - ax) / L, -(by - ay) / L, 0.0],
                          "k_A_per_m": 1.0 / (PORT_W * 1e-3), "a": cl["a"], "b": cl["b"], "level": lvl})
    leg_union = {lvl: shapely.set_precision(unary_union(v), GRID) for lvl, v in legs.items()}
    bar_union = {lvl: shapely.set_precision(unary_union(v), GRID) for lvl, v in bars.items()}
    leg_union = {k: shapely.set_precision(shapely.snap(v, snap_ref, SNAP_TOL).buffer(0), GRID) for k, v in leg_union.items()}
    bar_union = {k: shapely.set_precision(shapely.snap(v, snap_ref, SNAP_TOL).buffer(0), GRID) for k, v in bar_union.items()}
    for p in ports:
        p["strip"] = shapely.set_precision(p["strip"], GRID)

    # ---- 1. planar arrangement and 2-D mesh
    cx0, cy0, cx1, cy1 = crop.bounds
    bx0, by0, bx1, by1 = cx0 - a.air, cy0 - a.air, cx1 + a.air, cy1 + a.air
    outlines = [crop] + list(layer.values()) + [barrel_union] + list(leg_union.values()) \
        + list(bar_union.values()) + [p["strip"] for p in ports]
    # 2-D arrangement: node all outlines, snap, node again, polygonize; one gmsh
    # plane surface per face with shared curves (round 14's fast route; on the
    # defeatured copper it should no longer produce slivers).
    segs = [LineString([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1), (bx0, by0)])]
    for g in outlines:
        for p in polys(g):
            for ring in [p.exterior, *p.interiors]:
                segs.append(LineString(ring.coords))
    noded = unary_union(shapely.set_precision(unary_union(MultiLineString([list(s_.coords) for s_ in segs])), GRID))
    faces_all = list(shapely.polygonize(list(noded.geoms) if hasattr(noded, "geoms") else [noded]).geoms)
    faces2d = [f_ for f_ in faces_all if f_.area > 0]
    degenerate_faces = len(faces_all) - len(faces2d)       # zero-area only: leaves no hole
    faces2d, n_merged = merge_thin(faces2d, a.thin)
    if a.cov_simplify > 0:
        faces2d = [f_ for f_ in shapely.coverage_simplify(np.array(faces2d, dtype=object), a.cov_simplify)
                   if not f_.is_empty]
        faces2d = [shapely.set_precision(f_, GRID) for f_ in faces2d]
        faces2d = [g_ for f_ in faces2d for g_ in polys(f_)]

    def touching(poly):
        for ring in [poly.exterior, *poly.interiors]:
            c = [(round(x / GRID), round(y / GRID)) for x, y in ring.coords[:-1]]
            if len(c) != len(set(c)):
                return True
        return False
    bad = [f_ for f_ in faces2d if touching(f_)]
    print("DIAG " + json.dumps({"faces": len(faces_all), "tiny_below_1e-4": sum(f_.area < 1e-4 for f_ in faces_all),
                               "self_touching": len(bad),
                               "self_touching_examples": [[round(v, 3) for v in f_.representative_point().coords[0]] + [round(f_.area, 4)] for f_ in bad[:6]]}), flush=True)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 8)
    geo = gmsh.model.geo
    pt, ln_tags = {}, {}

    def P(x, y):
        key = (round(round(x / GRID) * GRID, 6), round(round(y / GRID) * GRID, 6))
        if key not in pt:
            pt[key] = geo.addPoint(key[0], -key[1], 0.0)
        return pt[key]

    def L(pa, pb):
        if (pa, pb) in ln_tags:
            return ln_tags[(pa, pb)]
        if (pb, pa) in ln_tags:
            return -ln_tags[(pb, pa)]
        ln_tags[(pa, pb)] = geo.addLine(pa, pb)
        return ln_tags[(pa, pb)]

    def loop(ring):
        c = [P(x, y) for x, y in ring.coords]
        return geo.addCurveLoop([L(u, v) for u, v in zip(c, c[1:]) if u != v])

    # Tiny and self-touching faces (zero-area slivers where outlines nearly meet)
    # are skipped; their area is below 1e-4 mm^2 in total per face.
    # No face may be dropped. A dropped face is a hole in the 2-D mesh, which
    # extrudes into a PEC column through every layer: round 16 found two such
    # columns acting as spurious vias that shorted all four copper layers and
    # cut P1's loop inductance from 29.8 to 18.2 nH. Thin faces are merged
    # into neighbours above (merge_thin); anything left over is an error.
    skipped = [f_ for f_ in faces2d if f_.area < 1e-4 or touching(f_)]
    if skipped:
        raise SystemExit(f"{len(skipped)} degenerate 2-D faces would become PEC columns: "
                         f"{[[round(v, 3) for v in f_.representative_point().coords[0]] for f_ in skipped[:6]]}"
                         " (raise --thin)")
    skipped_area = 0.0
    surfs = []
    for fc in faces2d:
        surfs.append(geo.addPlaneSurface([loop(fc.exterior)] + [loop(r) for r in fc.interiors]))
    emb = [abs(t) for t in ln_tags.values()]
    n_in = sum(len(polys(g)) for g in outlines)
    geo.synchronize()
    f = gmsh.model.mesh.field
    d = f.add("Distance")
    f.setNumbers(d, "CurvesList", emb)
    f.setNumber(d, "Sampling", 4)
    th = f.add("Threshold")
    for k, v in (("InField", d), ("SizeMin", a.h_edge), ("SizeMax", a.h_far),
                 ("DistMin", a.h_edge), ("DistMax", 8 * a.h_far)):
        f.setNumber(th, k, v)
    f.setAsBackgroundMesh(th)
    # Size follows short boundary segments (round 16): with a fixed h_edge at
    # every outline, 0.05 mm segments next to 1.2 mm triangles made slivers.
    for k, v in (("MeshSizeExtendFromBoundary", a.extend_boundary), ("MeshSizeFromPoints", 0),
                 ("MeshSizeFromCurvature", 0), ("Algorithm", a.algo2d)):
        gmsh.option.setNumber(f"Mesh.{k}", v)
    try:
        gmsh.model.mesh.generate(2)
    except Exception as exc:
        import re as _re
        tags_ = [int(t) for t in _re.findall(r"\d+", str(exc))[:2]]
        where = []
        for t_ in tags_:
            try:
                c_, _, _, _ = gmsh.model.mesh.getNode(t_)
                where.append([round(c_[0], 4), round(-c_[1], 4)])
            except Exception:
                where.append(None)
        print("MESH2D_FAIL " + json.dumps({"error": str(exc), "nodes_board_xy": where}), flush=True)
        raise
    ntags, ncoords, _ = gmsh.model.mesh.getNodes()
    idx = {int(t): i for i, t in enumerate(ntags)}
    xy = ncoords.reshape(-1, 3)[:, :2].copy()
    xy[:, 1] = -xy[:, 1]                                      # back to board coordinates
    tri_l = []
    for sf in surfs:
        etypes, _, enodes = gmsh.model.mesh.getElements(2, sf)
        if 2 in list(etypes):
            tri_l.append(np.array([idx[int(n)] for n in enodes[list(etypes).index(2)]], dtype=np.int64).reshape(-1, 3))
    tri = np.concatenate(tri_l)
    gmsh.finalize()
    n2 = len(xy)
    cent = xy[tri].mean(axis=1)
    e1, e2 = xy[tri[:, 1]] - xy[tri[:, 0]], xy[tri[:, 2]] - xy[tri[:, 0]]
    area2d = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    t_mesh2d = time.time() - t0

    # ---- 2. z-levels and per-slab copper masks
    def inside(g):
        if g is None or g.is_empty:
            return np.zeros(len(tri), bool)
        return shapely.contains_xy(g, cent[:, 0], cent[:, 1])

    in_layer = {lyr: inside(g) for lyr, g in layer.items()}
    in_barrel = inside(barrel_union)
    in_leg = {lvl: inside(g) for lvl, g in leg_union.items()}
    in_bar = {lvl: inside(g) for lvl, g in bar_union.items()}
    in_port = [inside(p["strip"]) for p in ports]

    arch_top = max(z_span.values()) + LEG_EXTRA
    z_far_lo, z_far_hi = Z_BOTTOM - a.air, Z_TOP + a.air + 3.0
    band_lo, band_hi = Z_BOTTOM - a.band_pad, arch_top + a.band_pad
    assert z_far_lo < band_lo and band_hi < z_far_hi
    breaks = {band_lo, band_hi}
    for z0, z1 in LAYERS.values():
        breaks |= {z0, z1}
    for lvl, zs in z_span.items():
        if lvl in leg_union:
            breaks |= {zs, zs + LEG_EXTRA}
        if lvl in bar_union:
            breaks |= {zs - BAR_T / 2, zs + BAR_T / 2}
    levels = sorted(breaks)
    z = [levels[0]]
    for za, zb in zip(levels, levels[1:]):
        n = max(1, math.ceil((zb - za) / a.dz_max - 1e-9))
        z += [za + (zb - za) * (k + 1) / n for k in range(n)]
    z = np.array(sorted(set(round(v, 9) for v in z)))
    nz = len(z)

    def copper_mask(za, zb):
        zm = 0.5 * (za + zb)
        for lyr, (l0, l1) in LAYERS.items():
            if l0 - 1e-9 <= za and zb <= l1 + 1e-9:
                return in_layer[lyr]
        if Z_BOTTOM < zm < Z_TOP:
            return in_barrel                                  # dielectric: barrels only
        m = np.zeros(len(tri), bool)
        if zm > Z_TOP:
            for lvl, zs in z_span.items():
                if lvl in in_leg and zm < zs + LEG_EXTRA:
                    m |= in_leg[lvl]
                if lvl in in_bar and zs - BAR_T / 2 < zm < zs + BAR_T / 2:
                    m |= in_bar[lvl]
        return m

    cu = np.array([copper_mask(z[k], z[k + 1]) for k in range(nz - 1)])   # (nz-1, ntri)
    air = ~cu

    # ---- 3. tetrahedra from air prisms (sorted-vertex split)
    order = np.sort(tri, axis=1)                                # v0 < v1 < v2 by 2-D index
    tets = []
    for k in range(nz - 1):
        sel = order[air[k]]
        if not len(sel):
            continue
        b = sel + k * n2
        t_ = sel + (k + 1) * n2
        v0, v1, v2 = b[:, 0], b[:, 1], b[:, 2]
        V0, V1, V2 = t_[:, 0], t_[:, 1], t_[:, 2]
        tets += [np.stack([v0, v1, v2, V2], 1), np.stack([v0, v1, V1, V2], 1), np.stack([v0, V0, V1, V2], 1)]
    tets = np.concatenate(tets)

    # ---- 4. boundary triangles
    faces = {2: [], 3: []}
    port_faces = [[] for _ in ports]
    # horizontal faces at level k between slab k-1 (below) and k (above)
    for k in range(nz):
        below = air[k - 1] if k > 0 else np.zeros(len(tri), bool)
        above = air[k] if k < nz - 1 else np.zeros(len(tri), bool)
        pec = below ^ above
        if k in (0, nz - 1):                                   # band ends: interface to the outer boxes
            assert (below | above).all(), "band end level must be all air"
            pec = np.zeros(len(tri), bool)
        faces[2].append(order[pec & ((below & ~above) | (above & ~below))] + k * n2)
        for i, p in enumerate(ports):
            if abs(z[k] - p["z"]) < 1e-9:
                port_faces[i].append(order[in_port[i] & below & above] + k * n2)
    # vertical faces: 2-D edges between triangles with different air status, and box edges
    edges = defaultdict(list)
    for ti, (p0, p1, p2) in enumerate(tri):
        for u, v in ((p0, p1), (p1, p2), (p2, p0)):
            edges[(min(u, v), max(u, v))].append(ti)
    e_int = np.array([(u, v, ts[0], ts[1]) for (u, v), ts in edges.items() if len(ts) == 2], dtype=np.int64)
    e_bnd = np.array([(u, v, ts[0]) for (u, v), ts in edges.items() if len(ts) == 1], dtype=np.int64)

    def quads(uv, k):
        u, v = uv[:, 0] + k * n2, uv[:, 1] + k * n2
        U, V = u + n2, v + n2
        # Same diagonal as the tetrahedra: from the lower-index bottom vertex (u < v)
        # to the higher-index top vertex.
        return np.concatenate([np.stack([u, v, V], 1), np.stack([u, V, U], 1)])

    for k in range(nz - 1):
        m = air[k][e_int[:, 2]] != air[k][e_int[:, 3]]
        if m.any():
            faces[2].append(quads(e_int[m][:, :2], k))
        m = air[k][e_bnd[:, 2]]
        if m.any():
            faces[3].append(quads(e_bnd[m][:, :2], k))
    faces = {k: np.concatenate([f_.reshape(-1, 3) for f_ in v]) if v else np.zeros((0, 3), int)
             for k, v in faces.items()}
    port_arr = [np.concatenate([f_.reshape(-1, 3) for f_ in v]) if v else np.zeros((0, 3), int)
                for v in port_faces]

    # ---- 5. compact nodes, orient tetrahedra, write MSH 2.2
    xyz_all = np.column_stack([np.tile(xy[:, 0], nz), -np.tile(xy[:, 1], nz), np.repeat(z, n2)])

    # ---- 4b. outer air boxes: free tetrahedra on the band's end triangulation
    xyz_all, box_tets, box_far = outer_boxes(xyz_all, tri, n2, nz, e_bnd, z_far_lo, z_far_hi, a)
    tets = np.concatenate([tets] + box_tets)
    faces[3] = np.concatenate([faces[3]] + box_far)

    # Source consistency gate: a constant sheet current K on the port triangles
    # puts s_i = sum_T K . grad(phi_i) A_T on node i. Off PEC it must vanish, or
    # current leaks into the air and the ungauged curl-curl system has no
    # solution (see scripts/port_divergence.py for the same check on a mesh).
    pec_nodes = np.zeros(len(xyz_all), bool)
    pec_nodes[faces[2].ravel()] = True
    leaks = []
    for p, arr in zip(ports, port_arr):
        K = np.array(p["direction"]) * p["k_A_per_m"] * 1e-3
        Pt = xyz_all[arr]
        nrm = np.cross(Pt[:, 1] - Pt[:, 0], Pt[:, 2] - Pt[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1)[:, None]
        s_ = np.zeros(len(xyz_all))
        for k in range(3):
            e = Pt[:, (k + 2) % 3] - Pt[:, (k + 1) % 3]
            np.add.at(s_, arr[:, k], np.cross(nrm, e) @ K / 2)
        leak = float(np.abs(s_[~pec_nodes]).sum())
        leaks.append({"port": p["name"], "leak_A": leak})
        if leak > LEAK_TOL_A:
            bad = np.argsort(-np.abs(s_ * ~pec_nodes))[:3]
            raise SystemExit(f"port {p['name']} leaks {leak:.3g} A into the air at "
                             f"{[[round(c, 3) for c in xyz_all[i]] for i in bad]}")
    used = np.unique(np.concatenate([tets.ravel()] + [f_.ravel() for f_ in faces.values()]
                                    + [p.ravel() for p in port_arr]))
    new = -np.ones(len(xyz_all), np.int64)
    new[used] = np.arange(1, len(used) + 1)
    P_ = xyz_all
    vol = np.einsum("ij,ij->i", np.cross(P_[tets[:, 1]] - P_[tets[:, 0]], P_[tets[:, 2]] - P_[tets[:, 0]]),
                    P_[tets[:, 3]] - P_[tets[:, 0]])
    flip = vol < 0
    tets[flip] = tets[flip][:, [0, 2, 1, 3]]
    zero_vol = int((np.abs(vol) < 1e-15).sum())
    with open(a.out, "w") as fh:
        names = [(3, 1, "air"), (2, 2, "pec"), (2, 3, "farfield")] + \
                [(2, 10 + i, "port_" + p["name"]) for i, p in enumerate(ports)]
        fh.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n%d\n" % len(names))
        for dim, tag, nm in names:
            fh.write(f'{dim} {tag} "{nm}"\n')
        fh.write("$EndPhysicalNames\n$Nodes\n%d\n" % len(used))
        for i, u in enumerate(used):
            x_, y_, z_ = P_[u]
            fh.write(f"{i + 1} {x_:.9g} {y_:.9g} {z_:.9g}\n")
        fh.write("$EndNodes\n$Elements\n")
        blocks = [(2, 2, faces[2]), (2, 3, faces[3])] + [(2, 10 + i, p) for i, p in enumerate(port_arr)] + [(4, 1, tets)]
        total = sum(len(b[2]) for b in blocks)
        fh.write(f"{total}\n")
        eid = 1
        for etype, tag, arr in blocks:
            for row in new[arr]:
                fh.write(f"{eid} {etype} 2 {tag} {tag} " + " ".join(map(str, row)) + "\n")
                eid += 1
        fh.write("$EndElements\n")
    info = {"thin_faces_merged": n_merged, "thin_mm": a.thin, "cov_simplify_mm": a.cov_simplify,
            "port_leak_A": leaks, "port_w_mm": PORT_W, "leg": a.leg, "barrels_included": not a.no_barrels, "barrels": n_barrels,
            "arch_h_mm": a.arch_h, "h_edge_mm": a.h_edge, "h_far_mm": a.h_far, "dz_max_mm": a.dz_max,
            "margin_mm": a.margin, "air_mm": a.air, "segments": len(emb), "faces_2d": len(faces2d), "degenerate_faces_skipped": degenerate_faces, "skipped_area_mm2": skipped_area, "outline_polygons": n_in,
            "open_r_mm": a.open_r, "simplify_mm": a.simplify, "min_area_mm2": a.min_area, "grid_mm": GRID,
            "tri_area_min_mm2": float(area2d.min()), "tri_area_below_1e-6": int((area2d < 1e-6).sum()), "triangles_2d": len(tri),
            "z_levels": nz, "tets": int(len(tets)), "nodes": int(len(used)),
            "pec_faces": int(len(faces[2])), "farfield_faces": int(len(faces[3])), "zero_volume_tets": zero_vol,
            "ports": [{"name": p["name"], "physical": 10 + i, "faces": int(len(port_arr[i])),
                       "direction": p["direction"], "k_A_per_m": p["k_A_per_m"], "z_mm": p["z"],
                       "a": p["a"], "b": p["b"]} for i, p in enumerate(ports)],
            "mesh2d_s": round(t_mesh2d, 1), "total_s": round(time.time() - t0, 1)}
    print("RESULT " + json.dumps(info))


if __name__ == "__main__":
    main()
