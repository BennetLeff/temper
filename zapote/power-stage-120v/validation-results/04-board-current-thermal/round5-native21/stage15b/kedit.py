#!/usr/bin/env python3
"""Apply a stage-15b candidate to a COPY of the routed stage-15 board, refill, and save (KiCad's Python).

    $KP kedit.py <base.kicad_pcb> <candidate.json> <out_dir>

candidate.json:
  {"zone_add":  [[net, layer, [x0, y0, x1, y1]], ...],   # union into that net's pour on that layer (patches21 S15_ADD style)
   "zone_trim": [[net, layer, [x0, y0, x1, y1]], ...],   # difference (S15_TRIM style)
   "vias":      [[net, x, y, diameter, drill], ...],     # through vias
   "tracks":    [[net, layer, width, [[x, y], ...]], ...],
   "remove_vias":   [[net, x, y], ...],                  # nearest via of that net within 0.3 mm
   "remove_tracks": [[net, layer, [x0, y0, x1, y1]], ...]}   # tracks of that net wholly inside the box
The board's own rules (section.kicad_dru beside it) govern the refill; kicad-cli DRC is run afterwards.
"""
import json
import shutil
import sys
from pathlib import Path

import pcbnew as p

base, spec_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
spec = json.loads(spec_path.read_text())
out_dir.mkdir(parents=True, exist_ok=True)
for ext in (".kicad_dru", ".kicad_pro", ".kicad_prl", ".kicad_sch"):
    shutil.copy(base.with_suffix(ext), out_dir / ("section" + ext))
for f in ("fp-lib-table", "sym-lib-table", "native21.kicad_sym"):
    shutil.copy(base.parent / f, out_dir / f)
board = p.LoadBoard(str(base))
mm, iu = p.ToMM, p.FromMM
LAYER = {board.GetLayerName(l): l for l in range(p.PCB_LAYER_ID_COUNT) if board.GetLayerName(l)}


def rect(b):
    s = p.SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])):
        s.Append(iu(x), iu(y))
    return s


def zones(net, layer):
    return [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == net
            and z.IsOnLayer(LAYER[layer])]


log = []
for key, op in (("zone_trim", "BooleanSubtract"), ("zone_add", "BooleanAdd")):
    for net, layer, b in spec.get(key, []):
        r = rect(b)
        hit = [z for z in zones(net, layer) if z.Outline().Collide(r) or op == "BooleanAdd" and
               z.Outline().BBox().Intersects(r.BBox())]
        if not hit and op == "BooleanAdd":
            raise SystemExit(f"no {net} {layer} pour touches {b}")
        for z in hit[:1] if op == "BooleanAdd" else hit:
            o = z.Outline()
            before = o.Area()
            getattr(o, op)(r)
            o.Simplify()
            if o.OutlineCount() > 1:   # keep the largest piece, as patches21.edit_zones does
                keep = max(range(o.OutlineCount()), key=lambda i: o.Outline(i).Area())
                for i in reversed(range(o.OutlineCount())):
                    if i != keep:
                        o.DeletePolygon(i)
            log.append({"op": key, "net": net, "layer": layer, "box": b,
                        "outline_area_mm2": [round(before / 1e12, 3), round(o.Area() / 1e12, 3)]})
nets = board.GetNetsByName()
for net, x, y in spec.get("remove_vias", []):
    vs = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == net
          and abs(mm(t.GetPosition().x) - x) < 0.3 and abs(mm(t.GetPosition().y) - y) < 0.3]
    assert len(vs) == 1, (net, x, y, len(vs))
    board.Remove(vs[0]); log.append({"op": "remove_via", "net": net, "at": [x, y]})
for net, layer, b in spec.get("remove_tracks", []):
    ts = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
          and t.GetLayer() == LAYER[layer] and all(b[0] <= mm(q.x) <= b[2] and b[1] <= mm(q.y) <= b[3]
                                                     for q in (t.GetStart(), t.GetEnd()))]
    for t in ts:
        board.Remove(t)
    log.append({"op": "remove_tracks", "net": net, "layer": layer, "box": b, "count": len(ts)})
for net, x, y, d, drill in spec.get("vias", []):
    v = p.PCB_VIA(board)
    v.SetPosition(p.VECTOR2I(iu(x), iu(y)))
    v.SetWidth(iu(d)); v.SetDrill(iu(drill)); v.SetViaType(p.VIATYPE_THROUGH)
    v.SetLayerPair(p.F_Cu, p.B_Cu)
    v.SetNet(nets[net])
    board.Add(v); log.append({"op": "via", "net": net, "at": [x, y], "d": d, "drill": drill})
for net, layer, w, pts in spec.get("tracks", []):
    for a, b in zip(pts, pts[1:]):
        t = p.PCB_TRACK(board)
        t.SetStart(p.VECTOR2I(iu(a[0]), iu(a[1]))); t.SetEnd(p.VECTOR2I(iu(b[0]), iu(b[1])))
        t.SetWidth(iu(w)); t.SetLayer(LAYER[layer]); t.SetNet(nets[net])
        board.Add(t)
    log.append({"op": "track", "net": net, "layer": layer, "w": w, "pts": pts})
filler = p.ZONE_FILLER(board)
filler.Fill(board.Zones())
out = out_dir / "section.kicad_pcb"
board.Save(str(out))
(out_dir / "kedit-log.json").write_text(json.dumps(log, indent=1) + "\n")
print(json.dumps(log))
