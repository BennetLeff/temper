#!/usr/bin/env python3
"""Which nets' accepted copper enters another net's protected pour, which incr21 never lets a new track do.

    python3 native-21/layout/gates/protected_cross.py BASE.json ACCEPTED.json NET...

BASE is the board the router starts from (router_bench's ripped.json); it is loaded as incr21 loads a frozen base, and
every GEO.protect call (island rail pours, the Kelvin sense pours, the HV_RET / BUS_P planes) is recorded. A track of
NET in ACCEPTED.json within clearance of another net's protected pour on its layer, or a via of NET there when that
pour does not let vias through, is copper a patch authored on purpose (stage 40's U44 HS-B link, laid before the
n_hb pour was merged round it): the router cannot reproduce it, so router_bench reports such nets' open pairs as
"policy", apart from the router failures. Prints one JSON object {net: [[layer, other net], ...]}.
"""
import json
import runpy
import sys
from pathlib import Path

L = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(L))
import geom21  # noqa: E402

PROTECTED = []
_protect = geom21.Geometry.protect


def _record(self, net, layer, polygon, via_ok=False):
    PROTECTED.append((net, layer, polygon, via_ok))
    return _protect(self, net, layer, polygon, via_ok)


geom21.Geometry.protect = _record


def main():
    base, accepted, nets = sys.argv[1], sys.argv[2], sys.argv[3:]
    argv, sys.argv = sys.argv, ["incr21.py"]
    ns = runpy.run_path(str(L / "incr21.py"), run_name="incr21_lib")
    sys.argv = argv
    ns["load"](base, patches=False)
    ns["patches21"].add_stage33(ns["g"])
    ns["patches21"].add_stage35(ns["g"])
    import rules21
    from layers21 import CU
    from shapely.geometry import LineString, Point
    acc = json.loads(Path(accepted).read_text())
    xy = ns["g"]["_xy"]
    out = {}
    for net in nets:
        hits = set()
        for t in acc["tracks"]:
            if t["net"] != net:
                continue
            shape = LineString([xy(q) for q in t["points"]]).buffer(t["width"] / 2)
            for other, lay, poly, _ in PROTECTED:
                if other != net and lay == t["layer"] and \
                        poly.distance(shape) < rules21.clearance_on(net, other, lay) + 0.03:
                    hits.add((lay, other))
        for v in acc["vias"]:
            if v.get("net") != net:
                continue
            shape = Point(*v["at"]).buffer(v["size"] / 2)
            for other, lay, poly, via_ok in PROTECTED:
                if other != net and lay in CU and not via_ok and \
                        poly.distance(shape) < rules21.clearance_on(net, other, lay) + 0.03:
                    hits.add((lay, other))
        if hits:
            out[net] = sorted(hits)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
