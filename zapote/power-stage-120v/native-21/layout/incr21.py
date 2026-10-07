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
        pts = [item["at"]] if kind == "via" else [p for p in item["points"] if not isinstance(p, str)]
        if pts and all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
            return True
    return False


PATCHED = set()
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
    if patches and hasattr(patches21, "edit_zones"):
        base["zones"] = patches21.edit_zones(base["zones"])
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
    for t in base["tracks"]:
        if removed(t, "track"):
            n_rm += 1
            continue
        g["TRACKS"].append(t)
        GEO.add_track(t["net"], t["layer"], t["width"], [g["_xy"](p) for p in t["points"]])
    for v in base["vias"]:
        if removed(v, "via"):
            n_rm += 1
            continue
        g["VIAS"].append(v)
        GEO.add_via(v["net"], *v["at"], v["size"])
    rm_esc = set(getattr(patches21, "REMOVE_ESCAPES", ()))
    g["ESCAPES"].extend(e for e in base.get("escapes", []) if (e["ref"], e["pad"]) not in rm_esc)
    if patches and hasattr(patches21, "OPEN_IN1"):
        g["OPEN_IN1"][:] = patches21.OPEN_IN1
    g["protect_pours"]()
    if patches:
        real_link = g["link"]

        def link_rec(net, *a, **k):
            PATCHED.add(net)
            return real_link(net, *a, **k)
        g["link"] = link_rec
        patches21.add(g)
        g["link"] = real_link
        # nets the patches re-laid whole: their old DRC pairs are stale
        PATCHED.update(rm["net"] for rm in patches21.REMOVE if "box" not in rm)
        PATCHED.update(getattr(patches21, "HANDLED", ()))


if __name__ == "__main__":
    load(sys.argv[1])
    if len(sys.argv) > 4 and Path(sys.argv[4]).exists():
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
        if any(attach(net, q, lays, w, target=o) for q, o in ends for lays in tries):
            g["LINK_LOG"].append((net, "attach", 1, []))
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
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "copper.json"
    out.write_text(json.dumps({"zones": g["ZONES"], "tracks": g["TRACKS"], "vias": g["VIAS"],
                               "escapes": g["ESCAPES"]}, indent=1) + "\n")
    bad = [(n, f) for n, _, _, f in g["LINK_LOG"] if f]
    print(f"base kept, {n_rm} items removed by patches; {len(pairs)} open pairs tried, {len(bad)} still open")
    for b_ in bad:
        print("  open", b_)

