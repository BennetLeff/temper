#!/usr/bin/env python3
"""Apply authored native-21 copper (native-21/layout/copper.json) to the placed board.

    KICAD_PY prototype-closure/pcb/apply_copper21.py [--copper native-21/layout/copper.json]

Input is the unrouted board from build_native21.py (native-21/section.kicad_pcb);
it must carry no tracks or zones. Output is native-21/routed/section.kicad_pcb with
the project file and the D5 rules (section.kicad_dru) beside it. Zones are written
unfilled: fill them with `kicad-cli pcb drc --refill-zones --save-board`, which also
applies the custom insulation rules to every pour.

copper.json: {"zones": [{net, layer, outline: [[x, y], ...], holes: [[[x, y], ...]],
priority}], "tracks": [{net, layer, width, points}], "vias": [{net, at, size, drill}],
"escapes": [{ref, pad, rect: [x0, y0, x1, y1]}]}.
Track points may be "REF.PAD" strings; the pad's net must equal the track's net.

Escapes are native-20's bounded pad escapes: an F.Cu rule area PE_<ref>_<pad> around the
first millimetres of copper leaving one pad of a two-pin HOT part whose own pins sit
closer than the functional spacing (snubbers, dividers). Only that pad's net, only
inside the area, and only against the same part's other pad, may come as close as the
part's intrinsic pad gap (floored to 0.05 mm). Both barrier rules stay last.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
N21 = UNIT / "native-21"
LAYERS = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


def pt(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copper", default=str(N21 / "layout/copper.json"))
    ap.add_argument("--board", default=str(N21 / "section.kicad_pcb"))
    ap.add_argument("--out", default=str(N21 / "routed"))
    a = ap.parse_args()
    spec = json.loads(Path(a.copper).read_text())
    board = pcbnew.LoadBoard(a.board)
    if list(board.GetTracks()) or list(board.Zones()):
        raise SystemExit("input board already carries copper; rebuild it with build_native21.py")
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            key = f"{fp.GetReference()}.{pad.GetNumber()}"
            pads[key] = None if key in pads else (pad.GetPosition(), pad.GetNetname())

    def net(name):
        n = board.FindNet(name)
        if n is None:
            raise SystemExit(f"unknown net {name}")
        return n

    for z in spec.get("zones", []):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(LAYERS[z["layer"]])
        zone.SetNet(net(z["net"]))
        poly = pcbnew.Cast_to_SHAPE_POLY_SET(zone.Outline())
        poly.NewOutline()
        for x, y in z["outline"]:
            poly.Append(pt(x, y))
        for hole in z.get("holes", []):
            poly.NewHole()
            for x, y in hole:
                poly.Append(pt(x, y))
        zone.SetAssignedPriority(int(z.get("priority", 1)))
        zone.SetLocalClearance(pcbnew.FromMM(0.2))
        zone.SetMinThickness(pcbnew.FromMM(0.25))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.SetZoneName(z.get("name", ""))
        board.Add(zone)
    for t in spec.get("tracks", []):
        pts = []
        for p in t["points"]:
            if isinstance(p, str):
                hit = pads.get(p)
                if hit is None:
                    raise SystemExit(f"unknown or duplicate pad {p}")
                if hit[1] != t["net"]:
                    raise SystemExit(f"{p} is {hit[1]}, track is {t['net']}")
                pts.append(hit[0])
            else:
                pts.append(pt(*p))
        for s, e in zip(pts, pts[1:]):
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(s)
            tr.SetEnd(e)
            tr.SetWidth(pcbnew.FromMM(t["width"]))
            tr.SetLayer(LAYERS[t["layer"]])
            tr.SetNet(net(t["net"]))
            board.Add(tr)
    for v in spec.get("vias", []):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pt(*v["at"]))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.FromMM(v.get("size", 0.85)))
        via.SetDrill(pcbnew.FromMM(v.get("drill", 0.3)))
        via.SetNet(net(v["net"]))
        board.Add(via)
    escape_rules = []
    by_ref = {}
    for e in spec.get("escapes", []):
        fp = board.FindFootprintByReference(e["ref"])
        pads = list(fp.Pads())
        if len(pads) != 2:
            raise SystemExit(f"escape on {e['ref']}: only two-pin parts")
        mine = [p for p in pads if p.GetNumber() == e["pad"]][0]
        other = [p for p in pads if p is not mine][0]
        bm, bo = mine.GetBoundingBox(), other.GetBoundingBox()
        gx = max(bo.GetX() - bm.GetRight(), bm.GetX() - bo.GetRight(), 0)
        gy = max(bo.GetY() - bm.GetBottom(), bm.GetY() - bo.GetBottom(), 0)
        gap = math.floor(pcbnew.ToMM(math.hypot(gx, gy)) / 0.05) * 0.05
        name = f"PE_{e['ref']}_{e['pad']}"
        area = pcbnew.ZONE(board)
        area.SetIsRuleArea(True)
        area.SetLayer(pcbnew.F_Cu)
        area.SetZoneName(name)
        for kind in ("Tracks", "Vias", "Pads", "Footprints", "ZoneFills"):
            getattr(area, "SetDoNotAllow" + kind)(False)
        x0, y0, x1, y1 = e["rect"]
        ol = pcbnew.Cast_to_SHAPE_POLY_SET(area.Outline())
        ol.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(pt(x, y))
        board.Add(area)
        by_ref.setdefault(e["ref"], []).append((name, mine.GetNetname(), other.GetNetname(), gap))
    for ref, items in sorted(by_ref.items()):
        conds = []
        for name, net_m, net_o, gap in items:
            conds.append(f"(A.Type == 'Pad' && A.memberOfFootprint('{ref}') && A.NetName == '{net_o}' && "
                         f"B.Type == 'Track' && B.NetName == '{net_m}' && B.enclosedByArea('{name}'))")
            conds.append(f"(B.Type == 'Pad' && B.memberOfFootprint('{ref}') && B.NetName == '{net_o}' && "
                         f"A.Type == 'Track' && A.NetName == '{net_m}' && A.enclosedByArea('{name}'))")
        if len(items) == 2:
            (n1, m1, _, _), (n2, m2, _, _) = items
            conds.append(f"(A.Type == 'Track' && A.NetName == '{m1}' && A.enclosedByArea('{n1}') && "
                         f"B.Type == 'Track' && B.NetName == '{m2}' && B.enclosedByArea('{n2}'))")
            conds.append(f"(B.Type == 'Track' && B.NetName == '{m1}' && B.enclosedByArea('{n1}') && "
                         f"A.Type == 'Track' && A.NetName == '{m2}' && A.enclosedByArea('{n2}'))")
        gap = min(i[3] for i in items)
        escape_rules.append(f'(rule "{ref} bounded pad escapes: intrinsic component gap"\n'
                            f'  (condition "{" || ".join(conds)}")\n  (constraint clearance (min {gap:.6f}mm)))\n')
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    for f in ("section.kicad_pro", "fp-lib-table"):
        if (N21 / f).exists():
            shutil.copy2(N21 / f, out / f)
    dru = (N21 / "section.kicad_dru").read_text()
    anchor = '(rule "SELV to HOT'
    if escape_rules:
        if dru.count(anchor) != 1:
            raise SystemExit("rules file layout changed: cannot place escape rules before the barrier rules")
        dru = dru.replace(anchor, "\n".join(escape_rules) + "\n" + anchor)
    (out / "section.kicad_dru").write_text(dru)
    pcbnew.SaveBoard(str(out / "section.kicad_pcb"), board)
    print(json.dumps({k: len(spec.get(k, [])) for k in ("zones", "tracks", "vias")}))


if __name__ == "__main__":
    main()
