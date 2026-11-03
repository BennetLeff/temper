# /// script
# requires-python = ">=3.11"
# dependencies = ["gerbonara==1.6.3", "shapely==2.2.0", "numpy"]
# ///
"""Connectivity check of the fabrication files JLC builds from (Gerber copper + Excellon), not the .kicad_pcb.

Rerun from instruments/lcr-meter/:

    uv run --script validation/gerber-netlist/gerber_netlist_check.py              # check + write JSON
    uv run --script validation/gerber-netlist/gerber_netlist_check.py --self-test  # also prove it fails on a
                                                                                   # bridged pad pair and a cut track

What it does
  1. Reads the four copper Gerbers and both Excellon files out of manufacturing/temper-lcr-gerbers.zip (the
     file uploaded to JLC; gitignored, so on a fresh checkout the tracked manufacturing/gerbers/ is read). Every flash, draw and region is turned into exact polygons (shapely), applied in
     file order with its LPD/LPC polarity, and unioned per layer. Each resulting polygon is one piece of copper.
  2. Plated holes (PTH.drl, including routed slots) join every copper piece their barrel touches on any layer.
     Union-find over (layer, piece) gives the board's copper components.
  3. Labels come from the IPC-D-356 netlist (pad/via centre, side, drill): the IPC file inside the zip when
     present, else manufacturing/gerbers/temper-lcr.d356, else build/temper-lcr.d356. Each pad's net of record is taken from the *schematic* netlist by
     (reference, pin); the IPC net name is only cross-checked. SMD pads map to the piece under their centre;
     through pads and vias map through the drill hole at their centre.
  4. Asserts: no component holds pads of two nets (short); every schematic net with >= 2 placed pads lands in
     one component (open); reports copper with no pad (floating / via-only), NPTH holes that cut copper, drill
     holes missing from or extra to the IPC list, and the smallest gap between different-net copper per layer.

Geometry: exact polygons, no raster. Circles and arcs are polygonised with chord error <= 0.5 um (inscribed, so
copper is never grown and approximation cannot create a short). The reported minimum different-net gap per layer
shows how far every gap is from that 0.5 um tolerance.

Exit code 0 = pass, 1 = connectivity failure (or self-test failure).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import time
import warnings
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from gerbonara import ExcellonFile, GerberFile
from gerbonara import graphic_primitives as gp
from gerbonara.utils import MM, approximate_arc

warnings.filterwarnings("ignore", message=".*G90 header statement found after end of header")  # KiCad drill files

ROOT = Path(__file__).resolve().parents[2]
ZIP_DEFAULT = ROOT / "manufacturing" / "temper-lcr-gerbers.zip"
GERBER_DIR_FALLBACK = ROOT / "manufacturing" / "gerbers"  # tracked copy of the zip contents
IPC_FALLBACKS = [ROOT / "manufacturing" / "gerbers" / "temper-lcr.d356", ROOT / "build" / "temper-lcr.d356"]
SCH = ROOT / "cad" / "temper-lcr.kicad_sch"
PCB = ROOT / "cad" / "temper-lcr.kicad_pcb"
OUT_JSON = Path(__file__).resolve().parent / "gerber-netlist-check.json"
KICAD_CLI_CANDIDATES = ["/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli", "kicad-cli"]

LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]  # top to bottom; IPC access code k (1-based) = LAYERS[k-1]
LAYER_SUFFIX = {"F.Cu": "-F_Cu.gtl", "In1.Cu": "-In1_Cu.g1", "In2.Cu": "-In2_Cu.g2", "B.Cu": "-B_Cu.gbl"}
CHORD_ERR = 0.0005  # mm, max polygonisation error of circles/arcs
HOLE_MATCH_TOL = 0.005  # mm, IPC drill coordinate vs Excellon coordinate (IPC resolution is 0.00254 mm)
CONTACT_AREA_MIN = 1e-6  # mm^2, hole/copper overlap that counts as the barrel touching copper
GAP_SEARCH = 0.30  # mm, neighbour search radius for the minimum-gap report
GAP_WARN = 0.10  # mm, gaps below this between different nets are listed (JLC 4-layer min spacing 0.09-0.1 mm)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def quad_segs(r: float) -> int:
    """Segments per quarter circle so that the inscribed polygon deviates <= CHORD_ERR from radius r."""
    if r <= CHORD_ERR:
        return 4
    return max(4, math.ceil(math.pi / (4 * math.acos(1 - CHORD_ERR / r))))


def valid_polys(g) -> list[Polygon]:
    """Polygonal parts of a geometry (drops zero-width slivers that make_valid splits out of keyhole cuts)."""
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    if hasattr(g, "geoms"):
        return [p for sub in g.geoms for p in valid_polys(sub)]
    return []


def ring_area(pts) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2


class GeomStats:
    def __init__(self):
        self.region_area_mismatch_max = 0.0  # |shoelace| vs repaired polygon area, relative
        self.roundrect_nonconvex_max = 0.0  # hull area - area of RoundRect flashes (checks macro rotation sign)
        self.primitive_counts = defaultdict(int)


def prim_to_geom(p, stats: GeomStats):
    """One gerbonara graphic primitive (mm) -> shapely geometry. Own geometry code for every type except arc
    approximation inside polygons, so rotated-rectangle handling does not depend on gerbonara's ArcPoly path."""
    stats.primitive_counts[type(p).__name__] += 1
    if isinstance(p, gp.Circle):
        return Point(p.x, p.y).buffer(p.r, quad_segs=quad_segs(p.r))
    if isinstance(p, gp.Line):
        r = p.width / 2
        if math.isclose(p.x1, p.x2, abs_tol=1e-9) and math.isclose(p.y1, p.y2, abs_tol=1e-9):
            return Point(p.x1, p.y1).buffer(r, quad_segs=quad_segs(r))
        return LineString([(p.x1, p.y1), (p.x2, p.y2)]).buffer(r, quad_segs=quad_segs(r))
    if isinstance(p, gp.Arc):
        r = p.width / 2
        pts = list(approximate_arc(p.cx, p.cy, p.x1, p.y1, p.x2, p.y2, p.clockwise, max_error=CHORD_ERR))
        return LineString(pts).buffer(r, quad_segs=quad_segs(r)) if len(pts) > 1 else Point(p.x1, p.y1).buffer(r)
    if isinstance(p, gp.Rectangle):
        g = box(-p.w / 2, -p.h / 2, p.w / 2, p.h / 2)
        g = affinity.rotate(g, p.rotation, origin=(0, 0), use_radians=True)  # CCW, Gerber Y-up frame
        return affinity.translate(g, p.x, p.y)
    if isinstance(p, gp.ArcPoly):
        poly = p.approximate_arcs(max_error=CHORD_ERR) if p.arc_centers else p
        pts = [(float(x), float(y)) for x, y in poly.outline]
        if len(pts) < 3:
            return Polygon()
        raw = abs(ring_area(pts))
        g = shapely.make_valid(Polygon(pts))
        g = shapely.union_all(valid_polys(g)) if not isinstance(g, Polygon) else g
        if raw > 1e-6:
            stats.region_area_mismatch_max = max(stats.region_area_mismatch_max, abs(g.area - raw) / raw)
        return g
    raise ValueError(f"unhandled Gerber primitive {type(p).__name__}")


def gerber_layer_polys(text: str, stats: GeomStats) -> list[Polygon]:
    """Copper of one layer as disjoint polygons, polarity applied in file order."""
    gf = GerberFile.from_string(text)
    current = Polygon()
    batch, batch_dark = [], True

    def flush():
        nonlocal current, batch
        if batch:
            u = shapely.union_all(batch)
            current = shapely.union(current, u) if batch_dark else shapely.difference(current, u)
            batch = []

    for obj in gf.objects:
        dark = bool(obj.polarity_dark)
        if dark != batch_dark:
            flush()
            batch_dark = dark
        geoms = [prim_to_geom(p, stats) for p in obj.to_primitives(unit=MM)]
        if not geoms:
            continue
        g = shapely.union_all(geoms) if len(geoms) > 1 else geoms[0]
        ap = getattr(obj, "aperture", None)
        macro = getattr(ap, "macro", None)
        if macro is not None and getattr(macro, "name", "") == "RoundRect" and type(obj).__name__ == "Flash":
            stats.roundrect_nonconvex_max = max(stats.roundrect_nonconvex_max, g.convex_hull.area - g.area)
        # Each primitive inside one object carries its own polarity (macro exposure); objects in KiCad output
        # are uniform, so the object's polarity decides.
        batch.append(g)
    flush()
    polys = valid_polys(shapely.make_valid(current))
    return [p for p in polys if p.area > 1e-9]


def excellon_holes(text: str, plated: bool, stats: GeomStats) -> list[dict]:
    ef = ExcellonFile.from_string(text, plated=plated)
    holes = []
    for obj in ef.objects:
        prims = obj.to_primitives(unit=MM)
        for p in prims:
            g = prim_to_geom(p, stats)
            if isinstance(p, gp.Circle):
                holes.append({"x": p.x, "y": p.y, "dia": 2 * p.r, "slot": False, "geom": g})
            elif isinstance(p, gp.Line):
                holes.append({"x": (p.x1 + p.x2) / 2, "y": (p.y1 + p.y2) / 2, "dia": p.width, "slot": True,
                              "ends": [[p.x1, p.y1], [p.x2, p.y2]], "geom": g})
            else:
                raise ValueError(f"unhandled drill primitive {type(p).__name__}")
    return holes


# --------------------------------------------------------------------------------------------- IPC-D-356
IPC_RE = re.compile(r"A(\d\d)X([+-]\d+)Y([+-]\d+)X(\d+)Y(\d+)R(\d+)")


def parse_ipc356(text: str) -> list[dict]:
    """KiCad IPC-D-356 (UNITS CUST 0: inch, 0.0001 in). Fixed columns per IPC-D-356."""
    unit = None
    recs = []
    for line in text.splitlines():
        if line.startswith("P  UNITS"):
            unit = line.split()[-1]
            if line.split()[2] != "CUST" or unit != "0":
                raise ValueError(f"unsupported IPC-356 units line: {line!r}")
            continue
        code = line[:3]
        if code not in ("317", "327", "367"):
            continue
        m = IPC_RE.search(line, 38)
        if not m:
            raise ValueError(f"cannot parse IPC-356 record: {line!r}")
        drill = line[32:37].strip()
        recs.append({
            "code": code,
            "ipc_net": line[3:17].strip(),
            "ref": line[20:26].strip(),
            "pin": line[27:31].strip(),
            "drill_mm": int(drill[1:]) * 1e-4 * 25.4 if drill else None,
            "plated": line[37] == "P" if drill else None,
            "access": int(m.group(1)),
            "x": int(m.group(2)) * 1e-4 * 25.4,
            "y": int(m.group(3)) * 1e-4 * 25.4,
            "w": int(m.group(4)) * 1e-4 * 25.4,
            "h": int(m.group(5)) * 1e-4 * 25.4,
            "rot": int(m.group(6)),
        })
    if unit is None:
        raise ValueError("IPC-356 file has no UNITS record")
    return recs


def schematic_nets(netlist_xml: bytes) -> tuple[dict, dict]:
    root = ET.fromstring(netlist_xml)
    pin_net, net_nodes = {}, defaultdict(list)
    for n in root.find("nets"):
        name = n.get("name")
        for node in n.findall("node"):
            key = (node.get("ref"), node.get("pin"))
            pin_net[key] = name
            net_nodes[name].append(key)
        net_nodes.setdefault(name, [])
    return pin_net, dict(net_nodes)


def ipc_name_matches(ipc: str, sch: str) -> bool:
    """KiCad writes the last 14 characters of a long net name, upper-cased."""
    return ipc.upper() == sch[-14:].upper()


# --------------------------------------------------------------------------------------------- analysis
class DSU:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def r4(v):
    return round(float(v), 4)


def analyze(files: dict[str, bytes], ipc_text: str, netlist_xml: bytes) -> dict:
    t0 = time.time()
    stats = GeomStats()
    layer_polys = {}
    for layer in LAYERS:
        name = next(n for n in files if n.endswith(LAYER_SUFFIX[layer]))
        layer_polys[layer] = gerber_layer_polys(files[name].decode(), stats)
    pth_name = next(n for n in files if n.endswith("-PTH.drl"))
    npth_name = next(n for n in files if n.endswith("-NPTH.drl"))
    pth = excellon_holes(files[pth_name].decode(), True, stats)
    npth = excellon_holes(files[npth_name].decode(), False, stats)
    t_geom = time.time() - t0

    trees = {L: STRtree(layer_polys[L]) for L in LAYERS}
    dsu = DSU()
    for L in LAYERS:
        for i in range(len(layer_polys[L])):
            dsu.find((L, i))

    def touching(L, geom):
        hits = []
        for i in trees[L].query(geom, predicate="intersects"):
            if shapely.intersection(layer_polys[L][i], geom).area > CONTACT_AREA_MIN:
                hits.append(int(i))
        return hits

    # plated barrels join layers
    barrels_without_copper = []
    for h in pth:
        h["pieces"] = [(L, i) for L in LAYERS for i in touching(L, h["geom"])]
        for a in h["pieces"][1:]:
            dsu.union(h["pieces"][0], a)
        if not h["pieces"]:
            barrels_without_copper.append({"x": r4(h["x"]), "y": r4(h["y"]), "dia": r4(h["dia"])})

    comp_of = {}
    for L in LAYERS:
        for i in range(len(layer_polys[L])):
            comp_of[(L, i)] = dsu.find((L, i))
    comp_members = defaultdict(list)
    for k, c in comp_of.items():
        comp_members[c].append(k)
    hole_tree = STRtree([Point(h["x"], h["y"]) for h in pth])

    pin_net, net_nodes = schematic_nets(netlist_xml)
    recs = parse_ipc356(ipc_text)

    comp_pads = defaultdict(list)  # component -> pad labels
    comp_vias = defaultdict(list)
    pads_off_copper, ipc_net_mismatch, pads_not_in_schematic, board_only_pads = [], [], [], []
    # IPC net name -> schematic net(s) it can stand for (KiCad truncates long names to their last 14 chars)
    ipc_to_sch = defaultdict(set)
    for r in recs:
        if r["ipc_net"] not in ipc_to_sch:
            ipc_to_sch[r["ipc_net"]] = {n for n in net_nodes if ipc_name_matches(r["ipc_net"], n)}
    holes_matched = set()
    npth_ipc = []
    placed_nodes = set()

    def hole_at(x, y):
        idx = hole_tree.query(Point(x, y).buffer(HOLE_MATCH_TOL), predicate="intersects")
        best = min(idx, key=lambda i: math.hypot(pth[i]["x"] - x, pth[i]["y"] - y), default=None)
        return None if best is None else int(best)

    for r in recs:
        if r["code"] == "367" or r["plated"] is False:
            npth_ipc.append(r)
            continue
        is_via = r["ref"] == "VIA"
        loc = {"x": r4(r["x"]), "y": r4(r["y"])}
        if r["access"] == 0:  # through-hole: map via the drill hole
            hi = hole_at(r["x"], r["y"])
            if hi is None:
                pads_off_copper.append({**loc, "ref": r["ref"], "pin": r["pin"], "why": "no PTH drill at this pad/via"})
                continue
            holes_matched.add(hi)
            if abs(pth[hi]["dia"] - r["drill_mm"]) > 0.01 and not pth[hi]["slot"]:
                pads_off_copper.append({**loc, "ref": r["ref"], "pin": r["pin"],
                                        "why": f"drill {pth[hi]['dia']:.3f} mm vs IPC {r['drill_mm']:.3f} mm"})
            if not pth[hi]["pieces"]:
                pads_off_copper.append({**loc, "ref": r["ref"], "pin": r["pin"], "why": "drill touches no copper"})
                continue
            comp = comp_of[pth[hi]["pieces"][0]]
            layers_hit = sorted({L for L, _ in pth[hi]["pieces"]}, key=LAYERS.index)
        else:
            L = LAYERS[r["access"] - 1] if r["access"] < len(LAYERS) else "B.Cu"
            hits = [int(i) for i in trees[L].query(Point(r["x"], r["y"]), predicate="intersects")]
            if len(hits) != 1:
                pads_off_copper.append({**loc, "ref": r["ref"], "pin": r["pin"], "layer": L,
                                        "why": f"{len(hits)} copper pieces under pad centre"})
                continue
            comp = comp_of[(L, hits[0])]
            layers_hit = [L]
        if is_via:
            comp_vias[comp].append({**loc, "ipc_net": r["ipc_net"]})
            continue
        key = (r["ref"], r["pin"])
        if key in pin_net:
            net = pin_net[key]
            placed_nodes.add(key)
            if not ipc_name_matches(r["ipc_net"], net):
                ipc_net_mismatch.append({**loc, "ref": r["ref"], "pin": r["pin"], "ipc_net": r["ipc_net"],
                                         "schematic_net": net})
        elif r["ipc_net"] == "N/C":
            net = f"N/C:{r['ref']}-{r['pin']}"  # fiducials etc.: must stay alone
        elif len(ipc_to_sch[r["ipc_net"]]) == 1:
            # board-only footprint (e.g. a TestPoint pad added in layout): net of record is the schematic net the
            # IPC name resolves to, so a test pad on the wrong copper still shows up as a short
            net = next(iter(ipc_to_sch[r["ipc_net"]]))
            board_only_pads.append({**loc, "ref": r["ref"], "pin": r["pin"], "net": net})
        else:
            net = f"IPC-ONLY:{r['ipc_net']}"
            pads_not_in_schematic.append({**loc, "ref": r["ref"], "pin": r["pin"], "ipc_net": r["ipc_net"],
                                          "schematic_candidates": sorted(ipc_to_sch[r["ipc_net"]])})
        comp_pads[comp].append({**loc, "ref": r["ref"], "pin": r["pin"], "net": net, "layers": layers_hit})

    def comp_summary(c, with_pads=False):
        members = comp_members[c]
        geoms = [layer_polys[L][i] for L, i in members]
        u = shapely.union_all(geoms)
        cen = u.centroid
        d = {"layers": sorted({L for L, _ in members}, key=LAYERS.index),
             "area_mm2": r4(sum(g.area for g in geoms)),
             "centroid": [r4(cen.x), r4(cen.y)],
             "bbox": [r4(v) for v in u.bounds]}
        if with_pads:
            d["pads"] = [f"{p['ref']}-{p['pin']}" for p in comp_pads[c]]
        return d

    # shorts
    shorts = []
    for c, pads in comp_pads.items():
        nets = sorted({p["net"] for p in pads})
        if len(nets) > 1:
            by_net = defaultdict(list)
            for p in pads:
                by_net[p["net"]].append({"pad": f"{p['ref']}-{p['pin']}", "x": p["x"], "y": p["y"]})
            shorts.append({"nets": nets, **comp_summary(c), "pads_by_net": dict(by_net)})
    # vias whose IPC net disagrees with the pads they share copper with
    via_mismatch = []
    for c, vias in comp_vias.items():
        pad_nets = {p["net"] for p in comp_pads.get(c, [])}
        for v in vias:
            sch = ipc_to_sch.get(v["ipc_net"], set())
            if pad_nets and not (sch & pad_nets):
                via_mismatch.append({**v, "component_pad_nets": sorted(pad_nets)})

    # opens
    net_comps = defaultdict(set)
    for c, pads in comp_pads.items():
        for p in pads:
            net_comps[p["net"]].add(c)
    opens, single_pin, not_placed = [], [], []
    for net, nodes in sorted(net_nodes.items()):
        placed = [k for k in nodes if k in placed_nodes]
        missing = [f"{a}-{b}" for a, b in nodes if (a, b) not in placed_nodes]
        if missing:
            not_placed.append({"net": net, "pins_without_board_pad": missing})
        if len(placed) <= 1:
            single_pin.append(net)
            continue
        comps = net_comps.get(net, set())
        if len(comps) > 1:
            groups = []
            for c in comps:
                groups.append({**comp_summary(c),
                               "pads": [f"{p['ref']}-{p['pin']}" for p in comp_pads[c] if p["net"] == net]})
            opens.append({"net": net, "pieces": len(comps), "groups": groups})

    # floating copper
    floating, via_only = [], []
    for c in comp_members:
        if c in comp_pads:
            continue
        s = comp_summary(c)
        if c in comp_vias:
            via_only.append({**s, "vias": comp_vias[c]})
        else:
            floating.append(s)
    floating.sort(key=lambda d: -d["area_mm2"])

    # drills vs IPC
    extra_pth = [{"x": r4(h["x"]), "y": r4(h["y"]), "dia": r4(h["dia"]), "slot": h["slot"]}
                 for i, h in enumerate(pth) if i not in holes_matched]
    npth_unmatched_ipc = []
    for r in npth_ipc:
        if not any(math.hypot(h["x"] - r["x"], h["y"] - r["y"]) < HOLE_MATCH_TOL for h in npth):
            npth_unmatched_ipc.append({"ref": r["ref"], "x": r4(r["x"]), "y": r4(r["y"])})

    # NPTH vs copper
    npth_hits, npth_min_clear = [], {}
    for h in npth:
        for L in LAYERS:
            for i in trees[L].query(h["geom"].buffer(1.0)):
                d = h["geom"].distance(layer_polys[L][i])
                npth_min_clear[L] = min(npth_min_clear.get(L, 9e9), d)
                if d == 0:
                    c = comp_of[(L, int(i))]
                    npth_hits.append({"x": r4(h["x"]), "y": r4(h["y"]), "dia": r4(h["dia"]), "layer": L,
                                      "overlap_mm2": r4(shapely.intersection(h["geom"], layer_polys[L][i]).area),
                                      "nets": sorted({p["net"] for p in comp_pads.get(c, [])})})

    # smallest gap between copper pieces of different nets, per layer
    def label(c):
        nets = {p["net"] for p in comp_pads.get(c, [])}
        if not nets:
            nets = {f"via:{v['ipc_net']}" for v in comp_vias.get(c, [])} or {f"island:{c}"}
        return frozenset(nets)

    min_gap = {}
    close_pairs = []
    for L in LAYERS:
        P = layer_polys[L]
        best = (9e9, None)
        a_idx, b_idx = trees[L].query(P, predicate="dwithin", distance=GAP_SEARCH)
        for a, b in zip(a_idx, b_idx):
            if a >= b:
                continue
            ca, cb = comp_of[(L, int(a))], comp_of[(L, int(b))]
            la, lb = label(ca), label(cb)
            if la == lb:
                continue
            d = P[a].distance(P[b])
            if d < best[0]:
                pa, pb = nearest_points(P[a], P[b])
                best = (d, {"gap_mm": r4(d), "at": [r4((pa.x + pb.x) / 2), r4((pa.y + pb.y) / 2)],
                            "nets": [sorted(la), sorted(lb)]})
            if d < GAP_WARN:
                pa, pb = nearest_points(P[a], P[b])
                close_pairs.append({"layer": L, "gap_mm": r4(d), "at": [r4((pa.x + pb.x) / 2), r4((pa.y + pb.y) / 2)],
                                    "nets": [sorted(la), sorted(lb)]})
        min_gap[L] = best[1]

    nets_checked = [n for n in net_nodes if n not in single_pin]
    result = {
        "pass": not shorts and not opens and not pads_off_copper and not ipc_net_mismatch and not via_mismatch
                and not barrels_without_copper and not pads_not_in_schematic,
        "counts": {
            "copper_pieces_per_layer": {L: len(layer_polys[L]) for L in LAYERS},
            "copper_components": len(comp_members),
            "pth_holes": len(pth), "pth_slots": sum(h["slot"] for h in pth), "npth_holes": len(npth),
            "ipc_records": len(recs),
            "ipc_pads": sum(1 for r in recs if r["ref"] != "VIA" and r["code"] != "367"),
            "ipc_vias": sum(1 for r in recs if r["ref"] == "VIA"),
            "schematic_nets": len(net_nodes),
            "nets_checked_for_opens": len(nets_checked),
            "single_pin_nets": len(single_pin),
            "components_with_pads": len(comp_pads),
            "board_only_pads": len(board_only_pads),
        },
        "shorts": shorts,
        "opens": opens,
        "pads_off_copper": pads_off_copper,
        "ipc_net_name_mismatch": ipc_net_mismatch,
        "via_net_mismatch": via_mismatch,
        "pads_not_in_schematic": pads_not_in_schematic,
        "board_only_pads": board_only_pads,
        "schematic_pins_without_board_pad": not_placed,
        "plated_barrels_touching_no_copper": barrels_without_copper,
        "pth_holes_not_in_ipc": extra_pth,
        "npth_in_ipc_without_drill": npth_unmatched_ipc,
        "floating_copper": floating,
        "via_only_copper": via_only,
        "npth_cutting_copper": npth_hits,
        "npth_min_clearance_to_copper_mm": {L: r4(v) for L, v in npth_min_clear.items()},
        "min_gap_between_different_nets": min_gap,
        "gaps_below_warn": {"threshold_mm": GAP_WARN, "pairs": close_pairs},
        "single_pin_nets": single_pin,
        "geometry_sanity": {
            "chord_error_mm": CHORD_ERR,
            "region_area_vs_shoelace_max_rel": stats.region_area_mismatch_max,
            "roundrect_flash_hull_minus_area_max_mm2": stats.roundrect_nonconvex_max,
            "primitive_counts": dict(stats.primitive_counts),
        },
        "timing_s": {"geometry": round(t_geom, 1), "total": round(time.time() - t0, 1)},
    }
    # internal handles for the self-test (stripped before writing JSON)
    result["_internal"] = {"layer_polys": layer_polys, "comp_of": comp_of, "comp_pads": comp_pads,
                           "comp_vias": comp_vias, "recs": recs, "pin_net": pin_net}
    return result


# --------------------------------------------------------------------------------------------- self-test
def draws(text: str):
    """Yield (line_index, x0, y0, x1, y1) for every D01 draw outside regions (Gerber integer coords, 4.6 mm)."""
    x = y = 0
    in_region = False
    for i, line in enumerate(text.splitlines()):
        if line.startswith("G36"):
            in_region = True
        elif line.startswith("G37"):
            in_region = False
        m = re.match(r"^(?:G0?1)?(?:X(-?\d+))?(?:Y(-?\d+))?D0?([123])\*$", line)
        if not m:
            continue
        nx = int(m.group(1)) if m.group(1) is not None else x
        ny = int(m.group(2)) if m.group(2) is not None else y
        if m.group(3) == "1" and not in_region:
            yield i, x, y, nx, ny
        x, y = nx, ny


def self_test(files: dict[str, bytes], ipc_text: str, netlist_xml: bytes, base: dict) -> dict:
    internal = base["_internal"]
    fcu_name = next(n for n in files if n.endswith(LAYER_SUFFIX["F.Cu"]))
    fcu = files[fcu_name].decode()
    polys = internal["layer_polys"]["F.Cu"]
    tree = STRtree(polys)
    comp_of, comp_pads = internal["comp_of"], internal["comp_pads"]
    pin_net = internal["pin_net"]
    results = {}

    def mm(v):
        return v / 1e6

    def gi(v):
        return int(round(v * 1e6))

    # --- short: bridge the two closest top-side SMD pads of different nets with a 0.10 mm draw
    smd = [r for r in internal["recs"] if r["access"] == 1 and r["ref"] != "VIA" and (r["ref"], r["pin"]) in pin_net]
    best = None
    for i, a in enumerate(smd):
        for b in smd[i + 1:]:
            if pin_net[(a["ref"], a["pin"])] == pin_net[(b["ref"], b["pin"])]:
                continue
            d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if best is None or d < best[0]:
                best = (d, a, b)
    _, a, b = best
    bridge = (f"%ADD999C,0.100000*%\nD999*\nX{gi(a['x'])}Y{gi(a['y'])}D02*\nX{gi(b['x'])}Y{gi(b['y'])}D01*\n")
    mutated = fcu.replace("M02*", bridge + "M02*")
    assert mutated != fcu
    expect = sorted({pin_net[(a["ref"], a["pin"])], pin_net[(b["ref"], b["pin"])]})
    r = analyze({**files, fcu_name: mutated.encode()}, ipc_text, netlist_xml)
    caught = any(set(expect) <= set(s["nets"]) for s in r["shorts"])
    results["short"] = {
        "mutation": f"F.Cu: 0.10 mm draw from {a['ref']}-{a['pin']} ({a['x']:.3f},{a['y']:.3f}) "
                    f"to {b['ref']}-{b['pin']} ({b['x']:.3f},{b['y']:.3f})",
        "expected_short_between": expect,
        "checker_pass": r["pass"], "shorts_reported": [s["nets"] for s in r["shorts"]],
        "caught": bool(caught and not r["pass"]),
    }

    # --- open: delete one F.Cu track segment that is the only draw joining a two-pad net's pads
    seg_by_poly = defaultdict(list)
    for li, x0, y0, x1, y1 in draws(fcu):
        mid = Point(mm((x0 + x1) / 2), mm((y0 + y1) / 2))
        hits = tree.query(mid, predicate="intersects")
        if len(hits) == 1:
            seg_by_poly[int(hits[0])].append((li, x0, y0, x1, y1))
    # Of the two-pad nets joined by exactly one F.Cu segment, cut the longest one: on short ones the two pads'
    # teardrops can still touch after the track is gone (a real connection, which the checker rightly keeps).
    candidate = None
    for i, segs in sorted(seg_by_poly.items()):
        c = comp_of[("F.Cu", i)]
        pads = comp_pads.get(c, [])
        nets = {p["net"] for p in pads}
        if (len(segs) == 1 and len(pads) == 2 and len(nets) == 1 and not internal["comp_vias"].get(c)
                and all(p["layers"] == ["F.Cu"] for p in pads)
                and sum(1 for k, cc in comp_of.items() if cc == c) == 1):
            li, x0, y0, x1, y1 = segs[0]
            length = math.hypot(x1 - x0, y1 - y0)
            if candidate is None or length > candidate[3]:
                candidate = (segs[0], next(iter(nets)), pads, length)
    if candidate is None:
        results["open"] = {"caught": False, "error": "no single-segment two-pad net found to cut"}
    else:
        (li, x0, y0, x1, y1), net, pads, _ = candidate
        lines = fcu.splitlines()
        lines[li] = f"X{x1}Y{y1}D02*"  # move instead of draw: the segment disappears, the current point is kept
        mutated = "\n".join(lines) + "\n"
        r = analyze({**files, fcu_name: mutated.encode()}, ipc_text, netlist_xml)
        caught = any(o["net"] == net for o in r["opens"])
        results["open"] = {
            "mutation": f"F.Cu: Gerber line {li + 1} draw ({mm(x0):.3f},{mm(y0):.3f})->({mm(x1):.3f},{mm(y1):.3f}) "
                        f"turned into a move; it was the only track joining "
                        f"{' and '.join(p['ref'] + '-' + p['pin'] for p in pads)}",
            "expected_open_on": net,
            "checker_pass": r["pass"], "opens_reported": [o["net"] for o in r["opens"]],
            "caught": bool(caught and not r["pass"]),
        }

    # --- floating: a 0.5 mm copper dot on B.Cu where there is none within 1 mm
    bcu_name = next(n for n in files if n.endswith(LAYER_SUFFIX["B.Cu"]))
    bcu = files[bcu_name].decode()
    bpolys = STRtree(internal["layer_polys"]["B.Cu"])
    spot = None
    for yy in range(10, 90):
        for xx in range(10, 90):
            if not len(bpolys.query(Point(xx, yy).buffer(1.0), predicate="intersects")):
                spot = (float(xx), float(yy))
                break
        if spot:
            break
    if spot is None:
        results["floating"] = {"caught": False, "error": "no empty B.Cu spot found"}
    else:
        dot = f"%ADD998C,0.500000*%\nD998*\nX{gi(spot[0])}Y{gi(spot[1])}D03*\n"
        r = analyze({**files, bcu_name: bcu.replace("M02*", dot + "M02*").encode()}, ipc_text, netlist_xml)
        caught = any(f["layers"] == ["B.Cu"] and math.hypot(f["centroid"][0] - spot[0], f["centroid"][1] - spot[1]) < 0.01
                     for f in r["floating_copper"])
        results["floating"] = {"mutation": f"B.Cu: 0.5 mm flash at ({spot[0]}, {spot[1]})",
                               "floating_reported": len(r["floating_copper"]), "caught": bool(caught)}
    results["all_caught"] = all(v.get("caught") for v in results.values() if isinstance(v, dict))
    return results


# --------------------------------------------------------------------------------------------- main
def kicad_cli() -> str:
    for c in KICAD_CLI_CANDIDATES:
        if Path(c).exists() or c == "kicad-cli":
            return c
    raise FileNotFoundError("kicad-cli")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--zip", type=Path, default=ZIP_DEFAULT, help="Gerber/drill zip as uploaded to JLC")
    ap.add_argument("--ipc", type=Path, help="IPC-D-356 file (default: the .d356 inside the zip, else build/)")
    ap.add_argument("--netlist", type=Path, help="schematic netlist XML (default: exported now from the schematic)")
    ap.add_argument("--self-test", action="store_true", help="also run the short/open/floating mutation tests")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    args = ap.parse_args()

    if args.zip.exists():
        zbytes = args.zip.read_bytes()
        with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
            files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        fab_src = {"zip": str(args.zip.resolve().relative_to(ROOT)) if args.zip.resolve().is_relative_to(ROOT)
                   else str(args.zip), "sha256": sha256(zbytes)}
    else:  # the zip is gitignored; on a fresh checkout read the tracked files it is made from
        print(f"note: {args.zip} not found, reading {GERBER_DIR_FALLBACK.relative_to(ROOT)}/ instead")
        files = {p.name: p.read_bytes() for p in sorted(GERBER_DIR_FALLBACK.iterdir()) if p.is_file()}
        fab_src = {"dir": str(GERBER_DIR_FALLBACK.relative_to(ROOT)), "note": "zip absent; tracked Gerber dir used"}
    ipc_in_zip = [n for n in files if n.lower().endswith((".d356", ".ipc"))]
    if args.ipc:
        ipc_bytes, ipc_src = args.ipc.read_bytes(), str(args.ipc)
    elif ipc_in_zip:
        ipc_bytes, ipc_src = files[ipc_in_zip[0]], f"fab set:{ipc_in_zip[0]}"
    else:
        ipc_path = next((p for p in IPC_FALLBACKS if p.exists()), None)
        if ipc_path is None:
            sys.exit("no IPC-D-356 file: run cad/rebuild.sh, or kicad-cli pcb export ipcd356 "
                     "--output build/temper-lcr.d356 cad/temper-lcr.kicad_pcb")
        ipc_bytes, ipc_src = ipc_path.read_bytes(), str(ipc_path.relative_to(ROOT)) + " (not in the fab set)"
    if args.netlist:
        net_bytes, net_src = args.netlist.read_bytes(), str(args.netlist)
    else:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "netlist.xml"
            subprocess.run([kicad_cli(), "sch", "export", "netlist", "--format", "kicadxml", "--output", str(out),
                            str(SCH)], check=True, capture_output=True)
            net_bytes = out.read_bytes()
        net_src = f"kicad-cli sch export netlist {SCH.relative_to(ROOT)} (exported at run time)"

    used = {n: files[n] for n in files
            if n.endswith(tuple(LAYER_SUFFIX.values())) or n.endswith(("-PTH.drl", "-NPTH.drl"))}
    res = analyze(used, ipc_bytes.decode(), net_bytes)
    st = None
    if args.self_test:
        st = self_test(used, ipc_bytes.decode(), net_bytes, res)
    res.pop("_internal")

    def rel(p):
        try:
            return str(Path(p).resolve().relative_to(ROOT))
        except ValueError:
            return str(p)

    report = {
        "tool": "validation/gerber-netlist/gerber_netlist_check.py",
        "method": "exact polygons (shapely) from Gerber copper + Excellon; plated barrels join layers; "
                  "labels from IPC-D-356 positions, nets of record from the schematic netlist by (ref, pin)",
        "inputs": {
            "fab_files": fab_src,
            "zip_members_used": {n: sha256(b) for n, b in sorted(used.items())},
            "ipc_d356": {"source": ipc_src, "sha256": sha256(ipc_bytes)},
            "schematic": {"path": rel(SCH), "sha256": sha256(SCH.read_bytes())},
            "schematic_netlist": {"source": net_src, "sha256": sha256(net_bytes)},
            "board_for_reference_only": {"path": rel(PCB), "sha256": sha256(PCB.read_bytes()),
                                         "note": "not read by the checker; IPC-356 positions come from it"},
        },
        "versions": {"python": sys.version.split()[0], "shapely": shapely.__version__,
                     "gerbonara": __import__("importlib.metadata").metadata.version("gerbonara")},
        **res,
        "self_test": st,
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    ok = res["pass"] and (st is None or st["all_caught"])
    print(f"{'PASS' if res['pass'] else 'FAIL'}: {len(res['shorts'])} shorts, {len(res['opens'])} opens, "
          f"{len(res['pads_off_copper'])} pads off copper, {len(res['floating_copper'])} floating islands, "
          f"{len(res['via_only_copper'])} via-only pieces, {len(res['npth_cutting_copper'])} NPTH/copper hits; "
          f"{res['counts']['nets_checked_for_opens']} nets checked, {res['counts']['copper_components']} components")
    for L, g in res["min_gap_between_different_nets"].items():
        if g:
            print(f"  min different-net gap {L}: {g['gap_mm']} mm at {g['at']}")
    if st is not None:
        print("self-test:", {k: v.get("caught") for k, v in st.items() if isinstance(v, dict)},
              "ALL CAUGHT" if st["all_caught"] else "SELF-TEST FAILED")
    print(f"wrote {rel(args.out)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
