#!/usr/bin/env python3
"""Trim the dangling track tails KiCad reports (stage 19, review K6).

    python3 native-21/layout/gates/trim_tails.py DRC.json COPPER.json [--write]

The router leaves short overshoots (0.1-1.0 mm) past the pad, via or track it was joining: KiCad lists each
as `track_dangling`. For every such warning this finds the end segment of an authored polyline of the same
net and layer whose length matches the report and whose far end touches nothing (no same-net pad, via,
other track end), and drops it. Nothing is dropped unless exactly one end is free, so a track that is
the only link between two items is never cut; every ambiguous report is printed and left alone.
Also drops KiCad-reported dangling vias (via_dangling) whose tracks all sit on one layer (stage 22).
Run after the routing passes are clean, then rebuild (incr_iter.sh COPPER.json -) and re-run DRC: the unconnected
count must stay 0. Without --write it only reports.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PADS = json.loads((HERE.parent / "pads.json").read_text())


def xy(p):
    if isinstance(p, str):
        ref, pad = p.split(".")
        q = next(q for q in PADS if q["ref"] == ref and q["pad"] == pad)
        return (q["x"], q["y"])
    return tuple(p)


def touches(pt, net, layer, copper, skip):  # skip: id of the track under test (its own other vertices do not count)
    for q in PADS:
        if q["net"] == net and (q["tht"] or layer == "F.Cu"):
            b = q["box"]
            if b[0] - 0.02 <= pt[0] <= b[2] + 0.02 and b[1] - 0.02 <= pt[1] <= b[3] + 0.02:
                return True
    for v in copper["vias"]:
        if v["net"] == net and math.dist(v["at"], pt) <= v["size"] / 2 + 0.02:
            return True
    # KiCad joins tracks end to end: another track touches only through a shared vertex
    for t in copper["tracks"]:
        if t["net"] != net or t["layer"] != layer or id(t) == skip:
            continue
        if any(math.dist(xy(p), pt) <= 0.02 for p in t["points"]):
            return True
    return False


def main():
    drc = json.loads(Path(sys.argv[1]).read_text())
    copper = json.loads(Path(sys.argv[2]).read_text())
    done, left = [], []
    for v in drc["violations"]:
        if v["type"] != "track_dangling":
            continue
        it = v["items"][0]
        desc = it["description"]            # "Track [net] on Layer, length L mm"
        net = desc.split("[")[1].split("]")[0]
        layer = desc.split(" on ")[1].split(",")[0]
        length = float(desc.split("length ")[1].split(" ")[0])
        pos = (it["pos"]["x"], it["pos"]["y"])
        hit = None
        for t in copper["tracks"]:
            if t["net"] != net or t["layer"] != layer:
                continue
            P = [xy(p) for p in t["points"]]
            for i in sorted({0, len(P) - 2}):
                a, b = P[i], P[i + 1]
                if abs(math.dist(a, b) - length) > 0.01:
                    continue
                if min(math.dist(a, pos), math.dist(b, pos), math.dist(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), pos)) > 0.7:
                    continue
                ends = [a] if (i == 0 and len(P) > 2) else [b] if i == len(P) - 2 and len(P) > 2 else [a, b]
                free = [e for e in ends if not touches(e, net, layer, copper, id(t))]
                if len(P) == 2 and len(free) != 1:
                    continue
                if len(P) > 2 and len(free) != 1:
                    continue
                hit = (t, i, free[0])
                break
            if hit:
                break
        if hit is None:
            left.append((net, layer, pos, length))
            continue
        t, i, end_pt = hit
        P = t["points"]
        if len(P) == 2:
            copper["tracks"].remove(t)
        elif i == 0:
            del P[0]
        else:
            del P[-1]
        done.append((net, layer, pos, length))
    # dangling vias (KiCad: a via joined on one layer only): drop it when every same-net track ending on it lies on a single
    # layer and no same-net pad sits there; the tracks stay joined end to end (stage 22)
    for v in drc["violations"]:
        if v["type"] != "via_dangling":
            continue
        it = v["items"][0]
        net = it["description"].split("[")[1].split("]")[0]
        pos = (it["pos"]["x"], it["pos"]["y"])
        vias = [w for w in copper["vias"] if w["net"] == net and math.dist(w["at"], pos) <= 0.05]
        if len(vias) != 1:
            left.append((net, "via", pos, 0.0))
            continue
        w = vias[0]
        lays = {t["layer"] for t in copper["tracks"] if t["net"] == net
                and any(not isinstance(q, str) and math.dist(q, w["at"]) <= w["size"] / 2 + 0.02 for q in t["points"])}
        on_pad = any(q["net"] == net and q["box"][0] <= w["at"][0] <= q["box"][2] and q["box"][1] <= w["at"][1] <= q["box"][3] for q in PADS)
        if len(lays) <= 1 and not on_pad:
            copper["vias"].remove(w)
            done.append((net, "via", pos, 0.0))
        else:
            left.append((net, "via", pos, 0.0))
    for d in done:
        print("trimmed", *d)
    for d in left:
        print("LEFT   ", *d)
    if "--write" in sys.argv:
        Path(sys.argv[2]).write_text(json.dumps(copper, indent=1) + "\n")


main()
