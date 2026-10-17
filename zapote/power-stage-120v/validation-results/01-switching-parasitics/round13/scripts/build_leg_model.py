#!/usr/bin/env python3
"""Build the leg model (copper, barrels, closures, ports) and mesh the air.

KiCad's fused STEP copper (rounds 5-11) carries near-coincident faces from
zone fills, pad rings and clearances that gmsh's tetrahedral mesher can't
separate ("segment and facet intersect", "overlapping facets"). This builds
the copper instead from the FlashLayer-aware export (only fabricated
copper; tools/export_power_copper.py), per net and layer:

- union of zones, pads, tracks (buffered to width) and via rings, cropped,
  snapped to a 1 um grid, simplified at `--simplify` (10 um default), and
  slivers under `--min-area` dropped;
- extruded to the layer's z-range from stackup.json;
- plated barrels (vias and PTH pads in the crop) as solid 16-sided prisms of
  the drill diameter through the board: a lead or filled via, with no bore,
  which is equivalent for perfect-conductor copper;
- fused per net, then cut out of an air box.

Coordinates follow KiCad's STEP convention: X = board X, Y = -board Y, mm,
B.Cu underside at z = -0.07.

    PYTHONPATH=/opt/homebrew/lib python3 build_crop_geometry.py EXPORT.json.gz OUT.msh \
        --leg A --h-near 0.5 [--no-mesh]
"""
from __future__ import annotations

import argparse
import math
import gzip
import json
import time
from collections import defaultdict

import gmsh
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

LEGS = {"A": (125.865, 4.215, 164.6, 41.125), "B": (88.4, 4.215, 127.135, 41.125)}
Z = {"B.Cu": (-0.07, 0.0), "In2.Cu": (0.4355, 0.4965), "In1.Cu": (0.9965, 1.0575), "F.Cu": (1.493, 1.563)}
Z_BOTTOM, Z_TOP = -0.07, 1.563


def polys(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom] if isinstance(geom, Polygon) else \
        [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def surface(occ, poly: Polygon) -> int:
    loops = []
    for ring in [poly.exterior, *poly.interiors]:
        pts = list(ring.coords)[:-1]
        tags = [occ.addPoint(x, -y, 0.0) for x, y in pts]
        lines = [occ.addLine(tags[i], tags[(i + 1) % len(tags)]) for i in range(len(tags))]
        loops.append(occ.addCurveLoop(lines))
    return occ.addPlaneSurface(loops)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("out")
    ap.add_argument("--leg", choices=LEGS, default="A")
    ap.add_argument("--margin", type=float, default=10.0)
    ap.add_argument("--air", type=float, default=10.0)
    ap.add_argument("--simplify", type=float, default=0.01)
    ap.add_argument("--min-area", type=float, default=0.005)
    ap.add_argument("--h-near", type=float, required=True)
    ap.add_argument("--h-far", type=float, default=5.0)
    ap.add_argument("--h-edge", type=float, default=None,
                    help="size at copper edges and curved faces (feature-driven sizing; below the 0.2 mm clearances)")
    ap.add_argument("--algo3d", type=int, default=1, help="gmsh 3-D algorithm (1 Delaunay, 10 HXT: reports intersection points)")
    ap.add_argument("--surface-only", action="store_true", help="mesh surfaces only and report coincident triangles")
    ap.add_argument("--no-barrels", action="store_true",
                    help="omit via/PTH barrels (sizing runs only: barrels still produce local mesh conflicts)")
    ap.add_argument("--closures", default=None, help="JSON list of closures (ports and bridges)")
    ap.add_argument("--arch-h", type=float, default=1.0, help="arch height above the top copper (mm)")
    ap.add_argument("--no-mesh", action="store_true")
    a = ap.parse_args()
    x0, y0, x1, y1 = LEGS[a.leg]
    crop = box(x0 - a.margin, max(y0 - a.margin, -0.5), x1 + a.margin, y1 + a.margin)
    data = json.load(gzip.open(a.export, "rt"))
    shapes = defaultdict(list)
    barrels = defaultdict(dict)
    for it in data["primitives"]:
        k, net, lyr = it["kind"], it["net"], it.get("layer")
        if k in ("zone", "pad"):
            g = Polygon(it["shell"], it["holes"]).buffer(0)
        elif k == "track":
            g = LineString([it["start"], it["end"]]).buffer(it["width_mm"] / 2, 16)
        elif k == "via":
            g = Point(it["centre"]).buffer(it["diameter_mm"] / 2, 24)
        else:
            continue
        if not g.intersects(crop):
            continue
        shapes[(net, lyr)].append(g)
        drill = it.get("drill_mm") or 0.0
        if isinstance(drill, list):
            if drill[0] > 0 and abs(drill[0] - drill[1]) > 1e-6:
                raise SystemExit(f"slotted drill not supported: {it.get('ref')}")
            drill = drill[0]
        if k in ("pad", "via") and drill and drill > 0 and crop.contains(Point(it["centre"])):
            barrels[net][tuple(round(c, 4) for c in it["centre"])] = drill
    t0 = time.time()
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("General.NumThreads", 8)
    occ = gmsh.model.occ
    gmsh.option.setNumber("Geometry.ToleranceBoolean", 1e-4)   # glue sub-micron offsets
    per_net = defaultdict(list)
    stats = {"polygons": 0, "dropped_slivers": 0, "barrels": 0, "barrel_segments": 0}

    def extrude(poly, z0, z1):
        s_ = surface(occ, poly)
        occ.translate([(2, s_)], 0, 0, z0)
        return [(3, t) for d, t in occ.extrude([(2, s_)], 0, 0, z1 - z0) if d == 3]

    # Barrels: the footprint joins its net's copper on every layer in 2-D (so no
    # 3-D overlap with the layers), and solid prisms fill the dielectric gaps,
    # meeting the layers face to face. Barrels straddling the crop are dropped.
    order = sorted(Z.items(), key=lambda kv: kv[1][0])
    gap_prisms = defaultdict(list)
    for net, holes in ({} if a.no_barrels else barrels).items():
        for (cx, cy), drill in holes.items():
            fp = Point(cx, cy).buffer(drill / 2, 4)
            if not crop.buffer(-0.05).contains(fp):
                stats["barrels_dropped_at_crop_edge"] = stats.get("barrels_dropped_at_crop_edge", 0) + 1
                continue
            stats["barrels"] += 1
            gap_prisms[net].append(shapely.set_precision(fp, 0.001))
    # Barrel footprints join the layer copper *after* simplification, snapped to
    # the same 1 um grid, so the layer outline and the gap prism above it share
    # identical vertices (simplifying them together moved the layer's copy by
    # up to 10 um, and the mesher saw crossing segments).
    keys = set(shapes) | {(net, lyr) for net in gap_prisms for lyr, _ in order}
    for net, lyr in sorted(keys):
        g = unary_union(shapes.get((net, lyr), [])).intersection(crop)
        g = shapely.set_precision(g, 0.001).simplify(a.simplify, preserve_topology=True).buffer(0)
        if gap_prisms.get(net):
            g = shapely.set_precision(unary_union([g, *gap_prisms[net]]), 0.001).buffer(0)
        kept = [p for p in polys(g) if p.area >= a.min_area]
        stats["dropped_slivers"] += len(polys(g)) - len(kept)
        for p in kept:
            per_net[net] += extrude(p, *Z[lyr])
            stats["polygons"] += 1
    # Gap prisms reach 5 um into the layers above and below: their end faces
    # sit inside solid copper (the footprint is already part of each layer),
    # so the per-net fuse absorbs an overlap instead of matching coplanar
    # faces (imprinting failed at the 16-gon vertices; splitting left gaps).
    OVER = 0.005
    for net, fps in gap_prisms.items():
        for fp in fps:
            for i in range(len(order) - 1):
                per_net[net] += extrude(fp, order[i][1][1] - OVER, order[i + 1][1][0] + OVER)
                stats["barrel_segments"] += 1
    # Closures (D1-FEM section 2 and the round-6 amendment): each is an arch of two
    # PEC legs on the pads and a span at height h (+1 mm for level 1, so gate-loop
    # arches clear the power-loop arches over a TO-247). A "port" span is a flat
    # driven sheet (constant direction, pad a -> pad b); a "bridge" span is a PEC bar.
    port_sheets = {}
    closures = json.load(open(a.closures)) if a.closures else []
    W, LEG = 0.6, 0.6
    for cl in closures:
        (ax, ay), (bx, by) = cl["a"], cl["b"]
        zs = Z_TOP + a.arch_h + cl.get("level", 0) * 1.0
        legs = []
        for (px, py) in ((ax, ay), (bx, by)):
            legs.append((3, occ.addBox(px - LEG / 2, -py - LEG / 2, Z_TOP, LEG, LEG, zs - Z_TOP + 0.3)))
        L = math.hypot(bx - ax, by - ay)
        ang = math.atan2(-(by - ay), bx - ax)            # direction in STEP coordinates
        if cl["kind"] == "bridge":
            bar = occ.addBox(0, -W / 2, zs - 0.05, L, W, 0.1)
            occ.rotate([(3, bar)], 0, 0, 0, 0, 0, 1, ang)
            occ.translate([(3, bar)], ax, -ay, 0)
            per_net["closure:" + cl["name"]] += legs + [(3, bar)]
        else:
            sheet = occ.addRectangle(LEG / 2, -W / 2, zs, L - LEG, W)
            occ.rotate([(2, sheet)], 0, 0, 0, 0, 0, 1, ang)
            occ.translate([(2, sheet)], ax, -ay, 0)
            per_net["closure:" + cl["name"]] += legs
            port_sheets[cl["name"]] = {"tag": sheet, "dir": [math.cos(ang), math.sin(ang), 0.0],
                                       "k_A_per_m": 1.0 / (W * 1e-3), "a": cl["a"], "b": cl["b"], "z_mm": zs}
    copper = []
    for net, vols in sorted(per_net.items()):
        copper += occ.fuse(vols[:1], vols[1:])[0] if len(vols) > 1 else vols
    occ.synchronize()
    cx0, cy0, cx1, cy1 = crop.bounds
    air = occ.addBox(cx0 - a.air, -cy1 - a.air, Z_BOTTOM - a.air,
                     cx1 - cx0 + 2 * a.air, cy1 - cy0 + 2 * a.air, Z_TOP - Z_BOTTOM + 2 * a.air)
    # Fragment the air box with every copper piece: one conforming partition in
    # which touching faces exist once (fuse-then-cut left duplicate coincident
    # faces between same-net pieces). Then drop the copper volumes and mesh
    # only the air; their surfaces stay as the air's inner boundary.
    tools = copper + [(2, v["tag"]) for v in port_sheets.values()]
    out, omap = occ.fragment([(3, air)], tools)
    occ.synchronize()
    cu_set = {t for m in omap[1:1 + len(copper)] for d, t in m if d == 3}
    for i, (name, v) in enumerate(port_sheets.items()):
        v["surfaces"] = [t for d, t in omap[1 + len(copper) + i] if d == 2]
    vols = [t for d, t in out if d == 3 and t not in cu_set]
    gmsh.model.removeEntities([(3, t) for t in sorted(cu_set)], recursive=False)
    bnd = sorted({t for d, t in gmsh.model.getBoundary([(3, v) for v in vols], combined=True, oriented=False)})
    lim = (cx0 - a.air, -cy1 - a.air, Z_BOTTOM - a.air, cx1 + a.air, -cy0 + a.air, Z_TOP + a.air)
    far, cond = [], []
    for s in bnd:
        b = gmsh.model.getBoundingBox(2, s)
        on_box = any(abs(b[i] - lim[i]) < 1e-3 and abs(b[i + 3] - lim[i]) < 1e-3 for i in range(3)) or \
            any(abs(b[i] - lim[i + 3]) < 1e-3 and abs(b[i + 3] - lim[i + 3]) < 1e-3 for i in range(3))
        (far if on_box else cond).append(s)
    gmsh.model.addPhysicalGroup(3, vols, 1, "air")
    gmsh.model.addPhysicalGroup(2, cond, 2, "copper")
    gmsh.model.addPhysicalGroup(2, far, 3, "farfield")
    port_list = []
    for i, (name, v) in enumerate(port_sheets.items()):
        gmsh.model.addPhysicalGroup(2, v["surfaces"], 10 + i, "port_" + name)
        port_list.append({"name": name, "physical": 10 + i, "direction": v["dir"], "k_A_per_m": v["k_A_per_m"],
                          "a": v["a"], "b": v["b"], "z_mm": v["z_mm"], "surfaces": v["surfaces"]})
    info = {"leg": a.leg, "barrels_included": not a.no_barrels, "arch_h_mm": a.arch_h, "ports": port_list, "margin_mm": a.margin, "air_mm": a.air, "simplify_mm": a.simplify,
            "min_area_mm2": a.min_area, "h_near_mm": a.h_near, "h_far_mm": a.h_far,
            "nets": len(per_net), "copper_pieces": len(copper), "copper_volumes": len(cu_set), "air_volumes": len(vols),
            "copper_surfaces": len(cond), "farfield_surfaces": len(far), **stats,
            "geometry_s": round(time.time() - t0, 1)}
    if not a.no_mesh:
        f = gmsh.model.mesh.field
        dist = f.add("Distance")
        f.setNumbers(dist, "SurfacesList", cond)
        f.setNumber(dist, "Sampling", 20)
        th = f.add("Threshold")
        for k, v in (("InField", dist), ("SizeMin", a.h_near), ("SizeMax", a.h_far),
                     ("DistMin", 0.5), ("DistMax", 8.0)):
            f.setNumber(th, k, v)
        fields = [th]
        curvature = 0
        if a.h_edge:
            # Feature-driven: fine only at copper edges (outlines, antipads, barrels),
            # so neighbouring surfaces 0.2 mm apart don't produce crossing facets.
            edges = sorted({abs(c) for s_ in cond
                            for _, c in gmsh.model.getBoundary([(2, s_)], oriented=False)})
            de = f.add("Distance")
            f.setNumbers(de, "CurvesList", edges)
            f.setNumber(de, "Sampling", 40)
            te = f.add("Threshold")
            for k, v in (("InField", de), ("SizeMin", a.h_edge), ("SizeMax", a.h_near),
                         ("DistMin", a.h_edge), ("DistMax", 4 * a.h_near)):
                f.setNumber(te, k, v)
            fields.append(te)
            curvature = 16
            info["edge_curves"] = len(edges)
            info["h_edge_mm"] = a.h_edge
        mn = f.add("Min")
        f.setNumbers(mn, "FieldsList", fields)
        f.setAsBackgroundMesh(mn)
        for k, v in (("MeshSizeExtendFromBoundary", 0), ("MeshSizeFromPoints", 0),
                     ("MeshSizeFromCurvature", curvature), ("MeshSizeMin", (a.h_edge or a.h_near) / 4),
                     ("Algorithm", 6), ("Algorithm3D", a.algo3d), ("MshFileVersion", 2.2)):
            gmsh.option.setNumber(f"Mesh.{k}", v)
        t1 = time.time()
        if a.surface_only:
            import numpy as np
            gmsh.model.mesh.generate(2)
            tags, coords, _ = gmsh.model.mesh.getNodes()
            xyz = dict(zip(tags, np.round(coords.reshape(-1, 3), 5).tolist()))
            seen, dup = {}, []
            all_surf = sorted({abs(t) for v in vols for d, t in gmsh.model.getBoundary([(3, v)], oriented=False)})
            info["surfaces_checked"] = len(all_surf)
            for s_ in all_surf:
                for et, _tri, nodes in zip(*gmsh.model.mesh.getElements(2, s_)):
                    for tri in np.array(nodes).reshape(-1, 3):
                        key = tuple(sorted(tuple(xyz[n]) for n in tri))
                        if key in seen:
                            dup.append({"surfaces": [seen[key], s_], "at": list(key[0])})
                        seen.setdefault(key, s_)
            info["coincident_triangles"] = len(dup)
            info["coincident_examples"] = dup[:8]
            by_pair = {}
            for d_ in dup:
                by_pair.setdefault(tuple(sorted(d_["surfaces"])), d_["at"])
            info["coincident_surface_pairs"] = [{"surfaces": k, "at": v,
                                                 "bboxes": [gmsh.model.getBoundingBox(2, k[0]), gmsh.model.getBoundingBox(2, k[1])]}
                                                for k, v in list(by_pair.items())[:10]]
            gmsh.finalize()
            print("RESULT " + json.dumps(info))
            return
        try:
            gmsh.model.mesh.generate(3)
            info["tets"] = len(gmsh.model.mesh.getElementsByType(4)[0])
            info["triangles"] = len(gmsh.model.mesh.getElementsByType(2)[0])
            gmsh.write(a.out)
        except Exception as exc:
            info["error"] = str(exc)
        info["mesh_s"] = round(time.time() - t1, 1)
    gmsh.finalize()
    print("RESULT " + json.dumps(info))


if __name__ == "__main__":
    main()
