#!/usr/bin/env python3
"""Per-net copper baseline and diff, from a board's all-copper export (tools/export_power_copper.py).

    python3 -I native-21/layout/gates/copper_baseline.py record BOARD-all-copper.json.gz OUT.json
    python3 -I native-21/layout/gates/copper_baseline.py diff BASE.json NEW.json [--json OUT] [--zone-drop 0.05]

record stores, for every net: track count, narrowest track width, via count by diameter, and pour area per layer
(outline area, holes not subtracted, so it moves with the outline and not with refills).
diff lists what changed per net and fails (exit 1) on the silent-damage cases:
  narrowed       the narrowest track on a net got narrower (a power path thinned by a reroute or a patch);
  fewer_vias     a net lost vias of a size (a return or thermal path thinned);
  zone_shrunk    a pour lost more than --zone-drop (default 5 %) of its area on a layer;
  net_vanished   a net with copper in BASE has none in NEW.
Widening, added tracks, added vias and grown pours are listed as information and never fail the diff.
"""
import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(path):
    p = Path(path)
    return json.loads((gzip.open(p) if p.suffix == ".gz" else p.open()).read())["primitives"]


def _area(poly):
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def record(prims):
    nets = defaultdict(lambda: {"tracks": 0, "narrowest_mm": None, "vias": defaultdict(int), "pour_mm2": defaultdict(float)})
    for p in prims:
        net = p.get("net")
        if not net:
            continue
        n = nets[net]
        if p["kind"] == "track":
            n["tracks"] += 1
            w = round(p["width_mm"], 4)
            n["narrowest_mm"] = w if n["narrowest_mm"] is None else min(n["narrowest_mm"], w)
        elif p["kind"] == "via":
            n["vias"][str(round(p["diameter_mm"], 3))] += 1
        elif p["kind"] == "zone":
            n["pour_mm2"][p["layer"]] += _area(p["shell"])
    return {k: {"tracks": v["tracks"], "narrowest_mm": v["narrowest_mm"], "vias": dict(v["vias"]),
                "pour_mm2": {l: round(a, 2) for l, a in v["pour_mm2"].items()}} for k, v in sorted(nets.items())}


def diff(base, new, zone_drop=0.05):
    fail, info = [], []
    for net, b in base.items():
        n = new.get(net)
        if n is None:
            if b["tracks"] or b["vias"] or b["pour_mm2"]:
                fail.append({"net": net, "kind": "net_vanished"})
            continue
        if b["narrowest_mm"] is not None and n["narrowest_mm"] is not None:
            if n["narrowest_mm"] < b["narrowest_mm"] - 1e-6:
                fail.append({"net": net, "kind": "narrowed", "from_mm": b["narrowest_mm"], "to_mm": n["narrowest_mm"]})
            elif n["narrowest_mm"] > b["narrowest_mm"] + 1e-6:
                info.append({"net": net, "kind": "widened", "from_mm": b["narrowest_mm"], "to_mm": n["narrowest_mm"]})
        elif b["narrowest_mm"] is not None and n["narrowest_mm"] is None:
            fail.append({"net": net, "kind": "net_lost_all_tracks"})
        for size, cnt in b["vias"].items():
            got = n["vias"].get(size, 0)
            if got < cnt:
                fail.append({"net": net, "kind": "fewer_vias", "size_mm": size, "from": cnt, "to": got})
            elif got > cnt:
                info.append({"net": net, "kind": "more_vias", "size_mm": size, "from": cnt, "to": got})
        for layer, area in b["pour_mm2"].items():
            got = n["pour_mm2"].get(layer, 0.0)
            if area > 0 and got < area * (1 - zone_drop):
                fail.append({"net": net, "kind": "zone_shrunk", "layer": layer, "from_mm2": area, "to_mm2": got})
        if n["tracks"] != b["tracks"]:
            info.append({"net": net, "kind": "track_count", "from": b["tracks"], "to": n["tracks"]})
    for net in new.keys() - base.keys():
        info.append({"net": net, "kind": "new_net"})
    return {"fail": fail, "info": info}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("export")
    r.add_argument("out")
    d = sub.add_parser("diff")
    d.add_argument("base")
    d.add_argument("new")
    d.add_argument("--json")
    d.add_argument("--zone-drop", type=float, default=0.05)
    a = ap.parse_args()
    if a.cmd == "record":
        data = record(load(a.export))
        Path(a.out).write_text(json.dumps(data, indent=1) + "\n")
        print("recorded %d nets" % len(data))
        return 0
    res = diff(json.loads(Path(a.base).read_text()), json.loads(Path(a.new).read_text()), a.zone_drop)
    print("copper diff: %d failing, %d informational" % (len(res["fail"]), len(res["info"])))
    for f in res["fail"][:30]:
        print("  FAIL", f)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    return 1 if res["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
