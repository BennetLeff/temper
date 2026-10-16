#!/usr/bin/env python3
"""Per-net and per-part fingerprints of a built board's authored inputs, for the scoped chain (scoped_chain.py).

    KICAD_PY net_keys.py BOARD.kicad_pcb OUT.json [--margin-mm 13]

Same rows and the same exclusions as copper_key.py (tracks, arcs, vias, pads, zone outlines and fill settings,
Edge.Cuts, rules files, KiCad version; never the refill, which KiCad does not reproduce bit for bit), grouped:

  copper_key      the whole-board key, recomputed here and identical to copper_key.py's (checked on every run)
  copper_key_canonical  the same over the canonical .kicad_pro (schematic-side "erc" / "schematic" sections dropped)
  context         rules files (canonical) + KiCad version + Edge.Cuts: part of every net key below
  net_own[N]      the authored copper of net N alone (its tracks, vias, pads and zone outlines)
  net_fill[N]     net_own[N] plus every authored item of any other net that can change N's refilled pours: items on a
                  layer N pours on, whose bounding box comes within MARGIN of one of N's zone outlines (through items
                  on every layer). MARGIN defaults to 13 mm, above the board's largest clearance (RES_A 12.6 mm), so a
                  knock-out a neighbour cuts into N's pour is always inside the key.
  part[REF]       footprint id, value, fields, position, side, orientation and every pad row of REF (placement / BOM)
  part_geom[REF]  the same without value and fields: footprint, placement and pads (with their nets) only

A step that reads the refilled copper of a net set S is reusable only if net_fill[N] is unchanged for every N in S.
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

board_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
MARGIN_MM = float(sys.argv[sys.argv.index("--margin-mm") + 1]) if "--margin-mm" in sys.argv else 13.0
b = pcbnew.LoadBoard(str(board_path))
M = pcbnew.FromMM(MARGIN_MM)
ALL_CU = None


def pt(p):
    return [p.x, p.y]


def layers(ls):
    return sorted(b.GetLayerName(l) for l in ls.Seq())


def bbox(item):
    r = item.GetBoundingBox()
    return (r.GetLeft(), r.GetTop(), r.GetRight(), r.GetBottom())


rows = []          # (net, json row, layer set, bbox)
for t in b.GetTracks():
    c = t.GetClass()
    r = {"k": c, "net": t.GetNetname(), "s": pt(t.GetStart()), "e": pt(t.GetEnd()), "w": t.GetWidth()}
    if c == "PCB_VIA":
        r.update(drill=t.GetDrillValue(), layers=layers(t.GetLayerSet()), type=int(t.GetViaType()))
        ls = set(r["layers"])
    else:
        r["layer"] = b.GetLayerName(t.GetLayer())
        if c == "PCB_ARC":
            r["m"] = pt(t.GetMid())
        ls = {r["layer"]}
    rows.append((r["net"], json.dumps(r, sort_keys=True), ls, bbox(t), None))
parts = {}
for f in b.GetFootprints():
    ref = f.GetReference()
    prow = []
    for p in f.Pads():
        r = {"k": "pad", "ref": ref, "num": p.GetNumber(), "net": p.GetNetname(),
             "pos": pt(p.GetPosition()), "size": pt(p.GetSize(pcbnew.F_Cu)), "shape": int(p.GetShape(pcbnew.F_Cu)),
             "rot": round(p.GetOrientationDegrees(), 4), "drill": pt(p.GetDrillSize()), "attr": int(p.GetAttribute()),
             "layers": layers(p.GetLayerSet()), "zc": int(p.GetLocalZoneConnection()),
             "poly": str(p.GetEffectivePolygon(pcbnew.F_Cu).Format()) if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CUSTOM else ""}
        line = json.dumps(r, sort_keys=True)
        rows.append((r["net"], line, set(r["layers"]), bbox(p), ref))
        prow.append(line)
    fields = {}
    for fl in f.GetFields():
        fields[fl.GetName()] = fl.GetText()
    parts[ref] = {"fpid": str(f.GetFPID().GetUniStringLibId()), "value": f.GetValue(), "fields": fields,
                  "pos": pt(f.GetPosition()), "rot": round(f.GetOrientationDegrees(), 4),
                  "side": b.GetLayerName(f.GetLayer()), "pads": sorted(prow)}
zones = []
for z in b.Zones():
    o = z.Outline()
    outline = []
    for i in range(o.OutlineCount()):
        outline.append([pt(o.COutline(i).CPoint(j)) for j in range(o.COutline(i).PointCount())])
        for h in range(o.HoleCount(i)):
            outline.append(["hole"] + [pt(o.CHole(i, h).CPoint(j)) for j in range(o.CHole(i, h).PointCount())])
    r = {"k": "zone", "net": z.GetNetname(), "layers": layers(z.GetLayerSet()), "prio": z.GetAssignedPriority(),
         "rule_area": z.GetIsRuleArea(), "outline": outline, "clear": z.GetLocalClearance() or 0,
         "minw": z.GetMinThickness(), "conn": int(z.GetPadConnection()), "tgap": z.GetThermalReliefGap(),
         "spoke": z.GetThermalReliefSpokeWidth(), "islands": int(z.GetIslandRemovalMode()),
         "fillmode": int(z.GetFillMode()),
         "keepout": [z.GetDoNotAllowTracks(), z.GetDoNotAllowVias(), z.GetDoNotAllowPads(),
                     z.GetDoNotAllowZoneFills(), z.GetDoNotAllowFootprints()] if z.GetIsRuleArea() else []}
    line = json.dumps(r, sort_keys=True)
    bb = bbox(z)
    rows.append((r["net"], line, set(r["layers"]), bb, None))
    if not r["rule_area"]:
        zones.append((r["net"], set(r["layers"]), bb))
edge = []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        edge.append(json.dumps({"k": "edge", "shape": int(d.GetShape()), "s": pt(d.GetStart()), "e": pt(d.GetEnd()),
                                "c": pt(d.GetCenter()) if d.GetShape() in (pcbnew.SHAPE_T_ARC, pcbnew.SHAPE_T_CIRCLE) else []},
                               sort_keys=True))

# whole-board key, exactly copper_key.py's construction
h = hashlib.sha256()
for line in sorted([r[1] for r in rows] + edge):
    h.update(line.encode())
rules = b""
for f in (board_path.with_suffix(".kicad_dru"), board_path.with_suffix(".kicad_pro")):
    rules += f.read_bytes() if f.exists() else b"-"
h.update(rules)
h.update(pcbnew.GetBuildVersion().encode())
copper_key = h.hexdigest()

# Canonical rules for the scoped keys: the .kicad_pro without its schematic-side sections. `kicad-cli sch erc` on a build
# dir adds "erc" / "schematic" to the .kicad_pro (seen on the s30 build, run after the chain); they cannot change copper,
# but they change copper_key.py's raw-bytes hash. copper_key_canonical is copper_key with this .kicad_pro.
dru = board_path.with_suffix(".kicad_dru")
pro = board_path.with_suffix(".kicad_pro")
canon = dru.read_bytes() if dru.exists() else b"-"
if pro.exists():
    pj = json.loads(pro.read_text())
    for k in ("erc", "schematic"):
        pj.pop(k, None)
    canon += json.dumps(pj, sort_keys=True).encode()
else:
    canon += b"-"
hc = hashlib.sha256()
for line in sorted([r[1] for r in rows] + edge):
    hc.update(line.encode())
hc.update(canon)
hc.update(pcbnew.GetBuildVersion().encode())
copper_key_canonical = hc.hexdigest()

ctx = hashlib.sha256()
for line in sorted(edge):
    ctx.update(line.encode())
ctx.update(canon)
ctx.update(pcbnew.GetBuildVersion().encode())
context = ctx.hexdigest()


def key(lines):
    k = hashlib.sha256(context.encode())
    for line in sorted(lines):
        k.update(line.encode())
    return k.hexdigest()


by_net = defaultdict(list)
for net, line, _, _, _ in rows:
    by_net[net].append(line)
net_own = {n: key(v) for n, v in by_net.items()}


def near(bb, zb):
    return not (bb[2] < zb[0] - M or bb[0] > zb[2] + M or bb[3] < zb[1] - M or bb[1] > zb[3] + M)


net_fill, neighbours = {}, {}
zones_by_net = defaultdict(list)
for net, ls, bb in zones:
    zones_by_net[net].append((ls, bb))
for n, own in by_net.items():
    lines = list(own)
    nb = set()
    for zls, zb in zones_by_net.get(n, []):
        for net, line, ls, bb, _ in rows:
            if net != n and ls & zls and near(bb, zb):
                lines.append(line)
                nb.add(net)
    net_fill[n] = key(set(lines))
    neighbours[n] = sorted(nb)

part = {r: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for r, v in parts.items()}
# geometry only (footprint, placement, pads and their nets): a value / MPN field change leaves it unchanged
part_geom = {r: hashlib.sha256(json.dumps({k: v[k] for k in ("fpid", "pos", "rot", "side", "pads")}, sort_keys=True).encode()).hexdigest()
             for r, v in parts.items()}
out = {"schema": "native21.net_keys.v1", "board": str(board_path),
       "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
       "kicad_version": pcbnew.GetBuildVersion(), "margin_mm": MARGIN_MM,
       "copper_key": copper_key, "copper_key_canonical": copper_key_canonical, "context": context,
       "net_own": dict(sorted(net_own.items())), "net_fill": dict(sorted(net_fill.items())),
       "fill_neighbours": dict(sorted(neighbours.items())),
       "part": dict(sorted(part.items())), "part_geom": dict(sorted(part_geom.items())),
       "part_info": {r: {k: v[k] for k in ("fpid", "value", "fields", "pos", "rot", "side")} for r, v in sorted(parts.items())}}
out_path.write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")
print(copper_key)
