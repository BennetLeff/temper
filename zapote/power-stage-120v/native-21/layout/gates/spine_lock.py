#!/usr/bin/env python3
"""Gate: the SELV-spine copper is the locked baseline's (13-coupling contract WS4 <-> WS5; native-21/layout/selv_spine_lock.json).

    python3 -I native-21/layout/gates/spine_lock.py CANDIDATE-all-copper.json.gz [--owner selv] [--lock LOCK.json]

Both boards are compared as exported by tools/export_power_copper.py (the chain's <tag>-all-copper.json.gz), so the gate
sees the built board, not the router's copper.json.

Scope:
- default (any lane that does not own the spine): every track and via of any net that touches the region, every pad
  whose centre lies in it, and every zone fill inside the region (inset by zone_inset_mm, so fills that move only
  because of copper outside the region do not count);
- --owner selv (the SELV-side lane, which owns the spine's interior): only the contract nets and the selv_gnd / v3v3
  planes, in the same way, plus the frozen_refs pads.
frozen_refs pads (J4 and the SELV transfer capacitors) are checked wherever they lie.

Tracks and vias are compared exactly, to 1 um. A zone fill differs if the symmetric difference of its (net, layer)
area inside the inset region exceeds zone_tolerance_mm2. The result is printed as JSON; exit 1 if anything differs.
A lane that has to change the spine re-issues the lock (new baseline) under its own DECISIONS item; it does not
loosen this gate.
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]   # zapote/power-stage-120v
LOCK = ROOT / "native-21/layout/selv_spine_lock.json"


def load(path):
    p = Path(path)
    return json.loads((gzip.open(p) if p.suffix == ".gz" else p.open()).read())


def r(xy):
    return (round(xy[0], 3), round(xy[1], 3))


def scope(lock, owner):
    """(net filter, pad filter): None for the net filter means every net."""
    if owner in lock["owner_lanes"]:
        return set(lock["contract_nets"]) | set(lock["plane_nets"]), False
    return None, True


def items(prims, lock, owner):
    """Keys of the locked tracks / vias / pads, and the locked zone fill per (net, layer) inside the inset region."""
    reg = box(*lock["region"])
    x0, y0, x1, y1 = lock["region"]
    d = lock["zone_inset_mm"]
    inner = box(x0 + d, y0 + d, x1 - d, y1 - d)
    nets, region_pads = scope(lock, owner)
    frozen = set(lock["frozen_refs"])
    keys, zones = set(), {}
    for p in prims:
        k, net = p["kind"], p.get("net")
        if k == "pad":
            if p["ref"].split(".")[0] in frozen or (region_pads and reg.contains(Point(p["centre"]))):
                keys.add(("pad", p["ref"], net, p["layer"], r(p["centre"])))
            continue
        if nets is not None and net not in nets:
            continue
        if k == "track":
            if LineString([p["start"], p["end"]]).intersects(reg):
                keys.add(("track", net, p["layer"], tuple(sorted([r(p["start"]), r(p["end"])])), round(p["width_mm"], 3)))
        elif k == "via":
            if reg.contains(Point(p["centre"])):
                keys.add(("via", net, p["layer"], r(p["centre"]), round(p["diameter_mm"], 3), round(p["drill_mm"], 3)))
        elif k == "zone":
            poly = Polygon(p["shell"], p.get("holes") or []).buffer(0)
            part = poly.intersection(inner)
            if not part.is_empty:
                zones.setdefault((net, p["layer"]), []).append(part)
    return keys, {k: unary_union(v) for k, v in zones.items()}


def check(base_prims, cand_prims, lock, owner=None):
    bk, bz = items(base_prims, lock, owner)
    ck, cz = items(cand_prims, lock, owner)
    zone_diffs = []
    for k in sorted(set(bz) | set(cz)):
        a, b = bz.get(k), cz.get(k)
        diff = (a.symmetric_difference(b).area if a is not None and b is not None
                else (a if a is not None else b).area)
        if diff > lock["zone_tolerance_mm2"]:
            zone_diffs.append({"net": k[0], "layer": k[1], "sym_diff_mm2": round(diff, 3)})
    removed, added = sorted(bk - ck, key=str), sorted(ck - bk, key=str)
    return {"owner": owner or "none", "locked_items": len(bk), "locked_zone_fills": len(bz),
            "removed": [list(x) for x in removed], "added": [list(x) for x in added], "zone_diffs": zone_diffs,
            "pass": not (removed or added or zone_diffs)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("candidate")
    ap.add_argument("--owner", default=None)
    ap.add_argument("--lock", default=str(LOCK))
    a = ap.parse_args()
    lock = json.loads(Path(a.lock).read_text())
    base = load(ROOT / lock["baseline"])
    if base["board_sha256"] != lock["baseline_board_sha256"]:
        sys.exit(f"baseline export is board {base['board_sha256'][:8]}, lock says {lock['baseline_board_sha256'][:8]}")
    cand = load(a.candidate)
    res = check(base["primitives"], cand["primitives"], lock, a.owner)
    res["baseline_board"] = base["board_sha256"][:8]
    res["candidate_board"] = cand.get("board_sha256", "")[:8]
    for k in ("removed", "added"):
        res[f"n_{k}"] = len(res[k])
        res[k] = res[k][:20]
    print(json.dumps(res))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
