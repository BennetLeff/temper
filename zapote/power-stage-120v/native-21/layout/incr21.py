#!/usr/bin/env python3
"""Incremental native-21 routing on top of frozen copper.

    python3 native-21/layout/incr21.py BASE_COPPER.json DRC.json[,DRC2.json...] [OUT=copper.json] [FILLS=copper-dump.json]

route21.py regenerates all copper from scratch; with ~800 connections the order of the
remaining-connection passes reshuffles which leftovers fail. Once a build is good, its copper
is frozen as a base (`copper_base.json`): this script loads it, applies the hand fixes in
`patches21.py` (REMOVE: base items to drop; add(g): new explicit copper), then joins only the
pairs KiCad still reports open in DRC.json, with route21's helpers and rules (same corridors,
same plan-view barrier). The output replaces layout/copper.json; the base only ever grows.
"""
import json
import math
import re
import sys
from pathlib import Path

from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
src = (HERE / "route21.py").read_text()
helpers = src.split("# ---------------------------------------------------------------- bus trunk")[0]
tail = src[src.index("OPEN_IN1 = ["):src.index("# ---------------------------------------------------------------- island-local signals")]
g = {"__file__": str(HERE / "route21.py"), "__name__": "route21_lib"}
exec(compile(helpers, "route21.py", "exec"), g)
exec(compile(tail, "route21.py", "exec"), g)
GEO = g["GEO"]
import patches21  # noqa: E402
import rules21  # noqa: E402

WIDE = ("leg_ret", "v15_ls", "n_ls", "v24_raw", "bias_sw1", "bias_sw2", "hot5", "v15_selv", "pe", "l_filt",
        "n_filt", "l_f", "ac_n_in", "ac_l_in", "tco_l")
LANES = ("rect_p BR1.1", "rect_n BR1.4", "n_filt BR1.3", "l_filt BR1.2", "sw_a Q2.3", "sw_a leg-A link",
         "sw_b leg B", "res_a J5", "coil_feed J2")


def removed(item, kind):
    for rm in patches21.REMOVE:
        if rm["net"] != item["net"] or rm.get("kind", kind) != kind:
            continue
        if "layer" in rm and (kind == "via" or rm["layer"] != item["layer"]):
            continue          # a layer-scoped removal names tracks only
        x0, y0, x1, y1 = rm.get("box", (-1e9, -1e9, 1e9, 1e9))
        pts = [item["at"]] if kind == "via" else \
            [p for p in item["points"] if not isinstance(p, str)] + \
            ([g["_xy"](p) for p in item["points"] if isinstance(p, str)] if rm.get("pads") else [])
        inside = [x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts]
        if pts and (any(inside) if rm.get("touch") else all(inside)):
            return True
    return False


PATCHED = set()


def moved_refs(base_path):
    """Parts whose pads moved since the base was frozen (<base>_pads.json beside it)."""
    prev_path = Path(base_path).with_name(Path(base_path).stem + "_pads.json")
    if not prev_path.exists():
        return set(), []
    prev_list = json.loads(prev_path.read_text())
    prev = {(p["ref"], p["pad"], round(p["x"], 3), round(p["y"], 3)) for p in prev_list}
    return {p["ref"] for p in GEO.pads if (p["ref"], p["pad"], round(p["x"], 3), round(p["y"], 3)) not in prev}, prev_list


def zgeom(z):
    """A pour as geometry: a filled polygon from the previous build's dump, or an authored outline."""
    if "pts" in z:
        return Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0) if len(z["pts"]) > 2 else Polygon()
    return Polygon(z["outline"], z["holes"]).buffer(0)


def prune_dangling(base, nets):
    """Drop base tracks / vias of `nets` left hanging by removals: a track end touching no pad,
    via, other track or pour of its net, and vias touching only one such track. Repeats until
    stable; returns the number dropped."""
    from shapely.geometry import LineString as _LS, Point as _Pt, Polygon as _Poly, box as _box
    dropped = 0
    while True:
        gone = []
        for t in base["tracks"]:
            if t["net"] not in nets:
                continue
            for end in (t["points"][0], t["points"][-1]):
                if isinstance(end, str):
                    continue
                pt = _Pt(*end).buffer(t["width"] / 2)
                touch = any(_box(*p["box"]).intersects(pt) for p in GEO.pads if p["net"] == t["net"]
                            and (p["tht"] or t["layer"] == "F.Cu"))
                touch = touch or any(math.dist(v["at"], end) < v["size"] / 2 + 0.01 for v in base["vias"] if v["net"] == t["net"])
                touch = touch or any(o is not t and o["net"] == t["net"] and o["layer"] == t["layer"] and
                                     _LS([g["_xy"](q) for q in o["points"]]).buffer(o["width"] / 2).intersects(pt)
                                     for o in base["tracks"])
                touch = touch or any(z["net"] == t["net"] and z["layer"] == t["layer"] and zgeom(z).intersects(pt)
                                     for z in (FILLS or base["zones"]))
                if not touch:
                    gone.append(t)
                    break
        vgone = []
        for v in base["vias"]:
            if v["net"] not in nets:
                continue
            pt = _Pt(*v["at"]).buffer(v["size"] / 2)
            # a via earns its drill only by joining copper on two or more layers
            lays = {t["layer"] for t in base["tracks"] if t["net"] == v["net"] and t not in gone and
                    _LS([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2).intersects(pt)}
            lays |= {z["layer"] for z in (FILLS or base["zones"]) if z["net"] == v["net"] and zgeom(z).intersects(pt)}
            for p in GEO.pads:
                if p["net"] == v["net"] and _box(*p["box"]).intersects(pt):
                    lays |= set(CU4) if p["tht"] else {"F.Cu"}
            if len(lays) <= 1:
                vgone.append(v)
        if not gone and not vgone:
            return dropped
        dropped += len(gone) + len(vgone)
        base["tracks"] = [t for t in base["tracks"] if t not in gone]
        base["vias"] = [v for v in base["vias"] if v not in vgone]


def reclip_for_moved(base_path, zones):
    """Pours were clipped to the plan-view barrier around the pads of their day: clip them again
    against moved parts' pads of the other side (SELV/PE pours vs HOT pads and back)."""
    from shapely.geometry import box as _box
    from shapely.ops import unary_union as _union
    moved, _ = moved_refs(base_path)
    pads = [p for p in GEO.pads if p["ref"] in moved and p["net"]]
    if not pads:
        return zones
    out = []
    for z in zones:
        cut = [_box(*p["box"]) for p in pads if rules21.barrier(z["net"], p["net"])]
        poly = Polygon(z["outline"], z["holes"])
        if cut:
            poly = poly.difference(_union(cut).buffer(rules21.BARRIER + 0.2, resolution=16))
        for q in getattr(poly, "geoms", [poly]):
            if q.is_empty or q.area < 1.0:
                continue
            q = q.simplify(0.001)
            out.append({**z, "outline": [[round(x, 3), round(y, 3)] for x, y in list(q.exterior.coords)[:-1]],
                        "holes": [[[round(x, 3), round(y, 3)] for x, y in list(i.coords)[:-1]] for i in q.interiors]})
    return out
FILLS = []          # filled pour polygons from the previous build's copper dump (optional argv[4])


def isolated(net, ref_pad):
    """True when no authored track or via of `net` touches the pad (KiCad's ratsnest end is bare)."""
    p = GEO.pad(ref_pad)
    x0, y0, x1, y1 = (p["box"][0] - 0.05, p["box"][1] - 0.05, p["box"][2] + 0.05, p["box"][3] + 0.05)
    for t in g["TRACKS"]:
        if t["net"] == net and any(q == ref_pad or (not isinstance(q, str) and x0 <= q[0] <= x1 and y0 <= q[1] <= y1)
                                   for q in t["points"]):
            return False
    return not any(v["net"] == net and x0 <= v["at"][0] <= x1 and y0 <= v["at"][1] <= y1 for v in g["VIAS"])


def clusters(net):
    """Same-net copper grouped by contact (authored tracks, vias, pads, pour outlines), a stand-in
    for KiCad's connectivity. Returns [(kind, layer or None, geometry, payload)], cluster ids."""
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.strtree import STRtree
    items = []
    for t in g["TRACKS"]:
        if t["net"] == net:
            pts = [g["_xy"](q) for q in t["points"]]
            items.append(("track", t["layer"], LineString(pts).buffer(t["width"] / 2), (t, pts)))
    for v in g["VIAS"]:
        if v["net"] == net:
            items.append(("via", None, Point(*v["at"]).buffer(v["size"] / 2), v))
    for p in GEO.pads:
        if p["net"] == net:
            items.append(("pad", None if p["tht"] else "F.Cu", box(*p["box"]), p))
    if FILLS:      # KiCad's fill of the previous build: what the pours really reach
        for z in FILLS:
            if z["net"] == net and len(z["pts"]) > 2:
                items.append(("zone", z["layer"], Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0), z))
    else:
        for z in g["ZONES"]:
            if z["net"] == net:
                items.append(("zone", z["layer"], Polygon(z["outline"], z["holes"]), z))
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tree = STRtree([it[2] for it in items])
    for i, (_, la, geo_, _) in enumerate(items):
        for j in tree.query(geo_):
            if j <= i:
                continue
            lb = items[j][1]
            if (la is None or lb is None or la == lb) and geo_.intersects(items[j][2]):
                parent[find(i)] = find(j)
    return items, [find(i) for i in range(len(items))]


def cluster_of(items, cid, where):
    """Cluster id of the item at a pad name or an "@x,y,layer" point."""
    from shapely.geometry import Point
    if where.startswith("@"):
        x, y, lay = where[1:].split(",")
        pt = Point(float(x), float(y))
        hits = [i for i, it in enumerate(items) if (lay == "*" or it[1] in (None, lay)) and it[2].distance(pt) < 0.05]
    else:
        ref, pad = where.split(".")
        hits = [i for i, it in enumerate(items) if it[0] == "pad" and it[3]["ref"] == ref and it[3]["pad"] == pad]
    return cid[hits[0]] if hits else None


def _samples(items, cid, c, layers):
    """Points of cluster c on `layers`: track vertices every 0.4 mm, vias and THT pads on any
    layer, SMD pads on F."""
    out = []
    for (kind, lay, _, payload), k in zip(items, cid):
        if k != c:
            continue
        if kind == "track" and lay in layers:
            pts = payload[1]
            for (ax, ay), (bx_, by) in zip(pts, pts[1:]):
                n = max(1, int(math.hypot(bx_ - ax, by - ay) / 0.4))
                out += [(ax + (bx_ - ax) * i / n, ay + (by - ay) * i / n, layers.index(lay)) for i in range(n + 1)]
        elif kind == "via":
            out.append((payload["at"][0], payload["at"][1], None))
        elif kind == "pad" and (payload["tht"] or "F.Cu" in layers):
            out.append((payload["x"], payload["y"], None if payload["tht"] else layers.index("F.Cu")))
    return out


def join_clusters(net, a, b, layers, width):
    """Join the cluster holding end `a` to the one holding `b` anywhere along them (multi-start,
    multi-goal maze), growing the search box around the two named ends."""
    import maze21
    items, cid = clusters(net)
    ca, cb = cluster_of(items, cid, a), cluster_of(items, cid, b)
    if ca is None or cb is None or ca == cb:
        return ca is not None and ca == cb
    A, B = _samples(items, cid, ca, layers), _samples(items, cid, cb, layers)
    xy = [incr21_point(a), incr21_point(b)]
    for m in (8.0, 20.0, 45.0, 95.0):     # the last for detours round pockets / through the band
        bx = (max(0.6, min(x for x, _ in xy) - m), max(0.6, min(y for _, y in xy) - m),
              min(289.4, max(x for x, _ in xy) + m), min(189.4, max(y for _, y in xy) + m))
        sa = [q for q in A if bx[0] < q[0] < bx[2] and bx[1] < q[1] < bx[3]]
        sb = [q for q in B if bx[0] < q[0] < bx[2] and bx[1] < q[1] < bx[3]]
        if not sa or not sb:
            continue
        for w in (width, 0.2):
            res = maze21.connect2(GEO, net, bx, w, sa, sb, layers=layers, via=0.6)
            if res is not None and g["_legal"](net, res[0], w, res[1]):
                for lay, path in res[0]:
                    g["track"](net, lay, w, *path)
                for x, y, la, lb in res[1]:
                    g["add_signal_via"](net, x, y, la, lb, w)
                return True
    return False


def drop_reported_tails(drc_path, longest=0.5):
    """Short track segments KiCad's previous DRC called dangling (one end on nothing): drop the
    matching authored segment (same net and layer, an end at the reported spot, under `longest`)."""
    if not Path(drc_path).exists():
        return 0
    d = json.loads(Path(drc_path).read_text())
    n = 0
    for v in d.get("violations", []):
        if v["type"] != "track_dangling":
            continue
        it = v["items"][0]
        m = re.search(r"Track \[([^\]]*)\] on (\S+), length ([0-9.]+) mm", it["description"])
        if not m or float(m.group(3)) > longest:
            continue
        net, lay, pos = m.group(1), m.group(2).rstrip(","), (it["pos"]["x"], it["pos"]["y"])
        for t in list(g["TRACKS"]):
            pts = [g["_xy"](q) for q in t["points"]]
            if t["net"] == net and t["layer"] == lay and len(pts) == 2 and \
                    min(math.dist(pts[0], pos), math.dist(pts[1], pos)) < 0.02 and math.dist(*pts) <= longest:
                g["TRACKS"].remove(t)
                n += 1
                break
    return n


def dogbone():
    """Move every via that sits in an SMD pad of its net to the nearest legal spot just off the
    pad: an F stub from the pad, and on each other layer a short join from the old via centre
    to the new one. All new copper is checked; if any piece fails, the via stays."""
    from shapely.geometry import LineString as _LS, Point as _Pt, box as _box
    keep_in = set(getattr(patches21, "IN_PAD", ()))       # pads whose vias are intended (filled / capped)
    smd = [p for p in GEO.pads if not p["tht"] and p["net"] and p["ref"] not in keep_in]
    moved = kept = 0
    for v in list(g["VIAS"]):
        c = _Pt(*v["at"])
        r = v["size"] / 2
        pad = next((p for p in smd if p["net"] == v["net"] and _box(*p["box"]).intersection(c.buffer(r)).area
                    > 0.5 * c.buffer(r).area), None)
        if pad is None:
            continue
        net = v["net"]
        # layers on which other copper meets the via centre (those need a join to the new spot)
        # tracks meeting the via anywhere (not only at its centre): their layers need a join, and
        # a track that touches the via other than by an endpoint is left alone (keep the via)
        meet = [t for t in g["TRACKS"] if t["net"] == net and t["layer"] != "F.Cu" and
                _LS([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2).intersects(c.buffer(r))]
        if any(not any(not isinstance(q, str) and math.dist(q, v["at"]) < r for q in (t["points"][0], t["points"][-1]))
               for t in meet):
            kept += 1
            continue
        joins = sorted({t["layer"] for t in meet})
        ends = [(t["layer"], next(q for q in (t["points"][0], t["points"][-1])
                                  if not isinstance(q, str) and math.dist(q, v["at"]) < r)) for t in meet]
        # pours the via fed: the new spot must sit well inside each of them
        pours = [Polygon(z["outline"], z["holes"]) for z in g["ZONES"] if z["net"] == net and z["layer"] != "F.Cu"
                 and Polygon(z["outline"], z["holes"]).contains(c)]
        best = None
        hw, hh = (pad["box"][2] - pad["box"][0]) / 2, (pad["box"][3] - pad["box"][1]) / 2
        for step in (0.25, 0.4, 0.6, 0.8, 1.0, 1.3):
            for k in range(16):
                a = k * math.pi / 8
                ex = abs(math.cos(a)) * hw + abs(math.sin(a)) * hh
                d = ex + r + step
                x, y = round(pad["x"] + d * math.cos(a), 3), round(pad["y"] + d * math.sin(a), 3)
                nv = _Pt(x, y).buffer(r)
                if GEO.conflicts(net, CU4, nv, limit=1, via=True):
                    continue
                stub = _LS([(pad["x"], pad["y"]), (x, y)]).buffer(0.125)
                if GEO.conflicts(net, ("F.Cu",), stub, limit=1):
                    continue
                if any(not q.buffer(-(r + 0.4)).contains(_Pt(x, y)) for q in pours):
                    continue
                if any(GEO.conflicts(net, (lay,), _LS([e, (x, y)]).buffer(0.125), limit=1) for lay, e in ends):
                    continue
                best = (x, y)
                break
            if best:
                break
        if best is None:
            kept += 1
            continue
        g["VIAS"].remove(v)
        g["VIAS"].append({**v, "at": [best[0], best[1]]})
        GEO.add_via(net, best[0], best[1], v["size"])
        g["track"](net, "F.Cu", 0.25, [pad["x"], pad["y"]], list(best))
        for lay, e in ends:
            g["track"](net, lay, 0.25, list(e), list(best))
        moved += 1
    return moved, kept


CU4 = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


def merge_close_vias(gap=0.5):
    """Same-net vias whose drills sit closer than `gap` (wall to wall) are one via: the second
    goes, and track ends that met it are joined to the first on their layer (checked)."""
    from shapely.geometry import LineString as _LS
    merged = 0
    i = 0
    while i < len(g["VIAS"]):
        a = g["VIAS"][i]
        j = i + 1
        while j < len(g["VIAS"]):
            b = g["VIAS"][j]
            dist = math.dist(a["at"], b["at"])
            if b["net"] != a["net"] or dist - (a["drill"] + b["drill"]) / 2 >= gap:
                j += 1
                continue
            rb = b["size"] / 2
            ends = [(t["layer"], q) for t in g["TRACKS"] if t["net"] == b["net"]
                    for q in (t["points"][0], t["points"][-1]) if not isinstance(q, str) and math.dist(q, b["at"]) < rb]
            if any(math.dist(q, a["at"]) > 1e-3 and
                   GEO.conflicts(b["net"], (lay,), _LS([q, a["at"]]).buffer(0.125), limit=1) for lay, q in ends):
                j += 1
                continue
            for lay, q in ends:
                if math.dist(q, a["at"]) > 1e-3:
                    g["track"](b["net"], lay, 0.25, list(q), list(a["at"]))
            del g["VIAS"][j]
            merged += 1
        i += 1
    return merged


def incr21_point(where):
    if where.startswith("@"):
        x, y, _ = where[1:].split(",")
        return (float(x), float(y))
    hits = GEO.pad_at[where]            # multi-pad numbers (studs, clips): any of them
    return (hits[0]["x"], hits[0]["y"])


def attach(net, ref_pad, layers, width, target=None):
    """Join a bare pad to the nearest legal point of authored copper of its net: of the cluster
    holding `target` (the other end KiCad named) when given, else of any other cluster
    (tracks sampled every 0.4 mm on their layer, vias on any layer)."""
    import maze21
    p = GEO.pad(ref_pad)
    items, cid = clusters(net)
    mine = cluster_of(items, cid, ref_pad)
    want = cluster_of(items, cid, target) if target else None
    goals = []
    for (kind, lay, _, payload), c in zip(items, cid):
        if c == mine or (want is not None and c != want):
            continue
        if kind == "track" and lay in layers:
            pts = payload[1]
            for (ax, ay), (bx_, by) in zip(pts, pts[1:]):
                n = max(1, int(math.hypot(bx_ - ax, by - ay) / 0.4))
                goals += [(ax + (bx_ - ax) * k / n, ay + (by - ay) * k / n, layers.index(lay)) for k in range(n + 1)]
        elif kind == "via":
            goals.append((payload["at"][0], payload["at"][1], None))
        elif kind == "pad":
            goals.append((payload["x"], payload["y"], None if payload["tht"] else layers.index("F.Cu")))
    goals = [q for q in goals if math.hypot(q[0] - p["x"], q[1] - p["y"]) > 1.0]
    start = [(p["x"], p["y"], None if p["tht"] else layers.index("F.Cu"))]
    for m in (6.0, 15.0, 40.0):
        bx = (max(0.6, p["x"] - m), max(0.6, p["y"] - m), min(289.4, p["x"] + m), min(189.4, p["y"] + m))
        gl = [q for q in goals if bx[0] < q[0] < bx[2] and bx[1] < q[1] < bx[3]]
        if not gl:
            continue
        for w in (width, 0.2):
            res = maze21.connect2(GEO, net, bx, w, start, gl, layers=layers, via=0.6)
            if res is not None and g["_legal"](net, res[0], w, res[1]):
                for lay, path in res[0]:
                    g["track"](net, lay, w, *path)
                for x, y, la, lb in res[1]:
                    g["add_signal_via"](net, x, y, la, lb, w)
                return True
    return False


def load(base_path, patches=True):
    """route21 state with the base copper registered (and the patches applied)."""
    base = json.loads(Path(base_path).read_text())
    # nets renamed in the source since the base was frozen keep their base copper (patches21.RENAME_NETS)
    ren = getattr(patches21, "RENAME_NETS", {}) if patches else {}
    for kind in ("zones", "tracks", "vias"):
        for it in base.get(kind, []):
            if it.get("net") in ren:
                it["net"] = ren[it["net"]]
    # base tracks that name a pad of a part deleted from the source since the base was frozen (stage 22: Q1 / Q4,
    # R8 / R16) go; the pair passes re-join whatever they served
    if patches:
        gone = [t for t in base["tracks"] if any(isinstance(q, str) and q not in GEO.pad_at for q in t["points"])]
        if gone:
            print(f"{len(gone)} base tracks named pads of deleted parts:", sorted({q for t in gone for q in t["points"] if isinstance(q, str) and q not in GEO.pad_at}))
        base["tracks"] = [t for t in base["tracks"] if t not in gone]
    if patches and hasattr(patches21, "edit_zones"):
        base["zones"] = patches21.edit_zones(base["zones"])
    if patches:
        base["zones"] = reclip_for_moved(base_path, base["zones"])
    for z in base["zones"]:
        g["ZONES"].append(z)
        poly = Polygon(z["outline"], z["holes"])
        GEO.add_plan(z["net"], poly)
        if any(z.get("name", "").startswith(n) for n in LANES):
            GEO.protect(z["net"], z["layer"], poly)
        k = (z["net"], z["layer"])
        g["PLANES"][k] = poly if k not in g["PLANES"] else g["PLANES"][k].union(poly)
    global n_rm
    n_rm = 0
    # placement changes since the base was frozen: base copper that now meets another net's pad
    # inside its clearance is dropped (the pair passes re-join what it served)
    from shapely.geometry import LineString as _LS, Point as _Pt, box as _box
    from shapely.strtree import STRtree as _Tree
    # only parts whose pads moved since the base was frozen (copper_base_pads.json)
    prev_path = Path(base_path).with_name(Path(base_path).stem + "_pads.json")
    prev = {(p["ref"], p["pad"], round(p["x"], 3), round(p["y"], 3)) for p in json.loads(prev_path.read_text())} \
        if prev_path.exists() else None
    moved = {p["ref"] for p in GEO.pads if prev is not None and (p["ref"], p["pad"], round(p["x"], 3), round(p["y"], 3)) not in prev}
    pad_geo = [(_box(*p["box"]), p) for p in GEO.pads if (p["net"] or p["npth"]) and p["ref"] in moved]
    if pad_geo:
        print("parts moved since the base:", " ".join(sorted(moved)))
    pad_tree = _Tree([q for q, _ in pad_geo])

    def meets_pad(net, geom, layer):
        if not pad_geo:
            return False
        for i in pad_tree.query(geom.buffer(3.5)):
            q, p = pad_geo[i]
            if p["net"] == net or (layer not in (None, "F.Cu") and not p["tht"]):
                continue
            need = 0.3 if p["npth"] else rules21.clearance(net, p["net"])
            if q.distance(geom) < need - 0.01:
                return True
        return False
    # ... and base copper that served a moved part's old pads (a numeric point on an old pad of its
    # net) goes too, with the vias left orphaned by it
    old_pads = [(_box(*q["box"]).buffer(0.05), q["net"]) for q in json.loads(prev_path.read_text())
                if q["ref"] in moved and q["net"]] if pad_geo else []

    def served_old(t):
        names = [q for q in t["points"] if isinstance(q, str)]
        if names and len(names) == len(t["points"]):
            return False             # pad to pad only: follows the parts
        if any(q.split(".")[0] in moved for q in names):
            return True              # a pad-named end on a moved part with fixed bends: stale
        return any(b.contains(_Pt(*q)) for q in t["points"] if not isinstance(q, str)
                   for b, n in old_pads if n == t["net"])
    stale = [t for t in base["tracks"] if patches and served_old(t)]
    stale_ends = {(t["net"], round(q[0], 3), round(q[1], 3)) for t in stale for q in t["points"]
                  if not isinstance(q, str)}
    kept_pts = {(t["net"], round(q[0], 3), round(q[1], 3)) for t in base["tracks"] if t not in stale
                for q in t["points"] if not isinstance(q, str)}
    n_pad = len(stale)
    base["tracks"] = [t for t in base["tracks"] if t not in stale]
    n_pad += prune_dangling(base, {t["net"] for t in stale})
    base["vias"] = [v for v in base["vias"]
                    if not ((v["net"], round(v["at"][0], 3), round(v["at"][1], 3)) in stale_ends
                            and (v["net"], round(v["at"][0], 3), round(v["at"][1], 3)) not in kept_pts)
                    and not any(b.contains(_Pt(*v["at"])) for b, n in old_pads if n == v["net"])]
    for t in base["tracks"]:
        follows = all(isinstance(q, str) for q in t["points"])      # pad-to-pad tracks move with the parts
        if patches and not follows and \
                meets_pad(t["net"], _LS([g["_xy"](q) for q in t["points"]]).buffer(t["width"] / 2), t["layer"]):
            n_pad += 1
            continue
        if removed(t, "track"):
            n_rm += 1
            continue
        g["TRACKS"].append(t)
        GEO.add_track(t["net"], t["layer"], t["width"], [g["_xy"](p) for p in t["points"]])
    for v in base["vias"]:
        if patches and meets_pad(v["net"], _Pt(*v["at"]).buffer(v["size"] / 2), None):
            n_pad += 1
            continue
        if removed(v, "via"):
            n_rm += 1
            continue
        g["VIAS"].append(v)
        GEO.add_via(v["net"], *v["at"], v["size"])
    rm_esc = set(getattr(patches21, "REMOVE_ESCAPES", ()))
    g["ESCAPES"].extend(e for e in base.get("escapes", []) if (e["ref"], e["pad"]) not in rm_esc)
    if n_pad:
        print(f"{n_pad} base items dropped: they served a moved part's old pads or meet its new ones")
    # island rail pours (the -2 V banks and island planes) and the OCP Kelvin sense pours: later
    # tracks of other nets may not cut them (vias may pass; the fill opens antipads). A re-route
    # across the In1 Kelvin pour split it once, and its resistance is budgeted.
    for z in g["ZONES"]:
        if (z["net"] in ("n_ha", "n_hb") and z["layer"] in ("B.Cu", "In1.Cu")) or \
                z["net"] in ("ocp_kelvin_p", "ocp_kelvin_n"):
            GEO.protect(z["net"], z["layer"], Polygon(z["outline"], z["holes"]), via_ok=True)
    if patches and hasattr(patches21, "OPEN_IN1"):
        g["OPEN_IN1"][:] = patches21.OPEN_IN1
    g["protect_pours"]()
    if patches:
        patches21.add(g)
        # nets the patches re-laid whole: their old DRC pairs are stale (pairs already joined
        # are skipped anyway by the cluster check)
        PATCHED.update(rm["net"] for rm in patches21.REMOVE if "box" not in rm)
        PATCHED.update(getattr(patches21, "HANDLED", ()))


if __name__ == "__main__":
    load(sys.argv[1])
    if len(sys.argv) > 4 and sys.argv[4] and Path(sys.argv[4]).is_file():
        FILLS.extend(json.loads(Path(sys.argv[4]).read_text())["zones"])
    # Remaining pairs from the latest DRC (fresh, not cumulative), pads or points on existing copper.
    pads = {f"{p['ref']}.{p['pad']}": p for p in GEO.pads}
    # pairs from every DRC given (comma-separated): a pair fixed by the patches of one pass must be
    # routed again by every later pass, which all start from the same base
    unconnected = [v for f in sys.argv[2].split(",") for v in json.loads(Path(f).read_text()).get("unconnected_items", [])]
    pairs, seen = [], set()
    for v in unconnected:
        a, b = v["items"]
        net = re.search(r"\[([^\]]*)\]", a["description"]).group(1)

        def name(item):
            m = re.search(r"Pad (\S+) \[[^\]]*\] of (\S+)", item["description"])
            if m:
                return f"{m.group(2)}.{m.group(1)}"
            t = re.search(r"^(Track|Via) \[[^\]]*\] on ([A-Za-z0-9.]+)", item["description"])
            if t:
                return f"@{item['pos']['x']:.3f},{item['pos']['y']:.3f},{t.group(2) if t.group(1) == 'Track' else '*'}"
            c = [p for p in GEO.pads if p["net"] == net]
            p = min(c, key=lambda p: math.hypot(p["x"] - item["pos"]["x"], p["y"] - item["pos"]["y"]))
            return f"{p['ref']}.{p['pad']}"
        pa, pb = name(a), name(b)
        key = (net, *sorted((pa, pb)))
        if pa != pb and key not in seen and net not in PATCHED:
            seen.add(key)
            pairs.append((net, pa, pb))
    for net, a, b in pairs:
        layers = g["LAYERS_FOR"].get(rules21.GROUP.get(net), ("F.Cu", "B.Cu"))
        if rules21.domain(net) == "SELV":
            layers = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
        w = 0.4 if net in WIDE else 0.25
        items, cid = clusters(net)
        ca, cb = cluster_of(items, cid, a), cluster_of(items, cid, b)
        if ca is not None and ca == cb:
            continue                        # already joined (by a patch or an earlier pair)
        if None in (ca, cb):
            # a stale point (its copper was re-laid): only a bare pad end still needs work
            q = a if cb is None else b
            if q.startswith("@") or not isolated(net, q):
                continue
            a, b = q, q
        # SELV: outer layers first, the In1 / In2 reference planes only as a fallback
        tries = [("F.Cu", "B.Cu"), layers] if rules21.domain(net) == "SELV" else [layers]
        # a pad end joins the other end's cluster anywhere along it (not only the item KiCad named)
        ends = [(q, o if o != q else None) for q, o in ((a, b), (b, a)) if not q.startswith("@")][:1 if a == b else 2]
        try:
            ok = any(attach(net, q, lays, w, target=o) for q, o in ends for lays in tries)
        except KeyError:              # multi-pad numbers (fuse clips, ...): leave to link()
            ok = False
        if ok:
            g["LINK_LOG"].append((net, "attach", 1, []))
            continue
        if a != b and any(join_clusters(net, a, b, lays, w) for lays in tries):
            g["LINK_LOG"].append((net, "join", 2, []))
            continue
        if len(tries) > 1 and not any(q.startswith("@") and q.rsplit(",", 1)[1] in ("In1.Cu", "In2.Cu")
                                      for q in (a, b)):
            n_log = len(g["LINK_LOG"])
            if g["link"](net, tries[0], (0.6, 0.6, 289.4, 189.4), w, [a, b]):
                continue
            del g["LINK_LOG"][n_log:]
        try:
            g["link"](net, layers, (0.6, 0.6, 289.4, 189.4), w, [a, b])
        except KeyError as e:
            g["LINK_LOG"].append((net, "?", 2, [a, b, str(e)]))
    n_tail = drop_reported_tails(sys.argv[2].split(",")[-1])
    print(f"KiCad-reported dangling tails dropped: {n_tail}")
    n_moved, n_kept = dogbone()
    print(f"via-in-pad: {n_moved} vias moved off their pads, {n_kept} left in pad (no legal spot)")
    print(f"same-net vias merged: {merge_close_vias()}")
    state = {"tracks": g["TRACKS"], "vias": g["VIAS"], "zones": g["ZONES"]}
    n_dead = prune_dangling(state, {t["net"] for t in g["TRACKS"]} | {v["net"] for v in g["VIAS"]})
    g["TRACKS"][:], g["VIAS"][:] = state["tracks"], state["vias"]
    print(f"dangling stubs pruned: {n_dead}")
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "copper.json"
    out.write_text(json.dumps({"zones": g["ZONES"], "tracks": g["TRACKS"], "vias": g["VIAS"],
                               "escapes": g["ESCAPES"]}, indent=1) + "\n")
    bad = [(n, f) for n, _, _, f in g["LINK_LOG"] if f]
    print(f"base kept, {n_rm} items removed by patches; {len(pairs)} open pairs tried, {len(bad)} still open")
    for b_ in bad:
        print("  open", b_)

