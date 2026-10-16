"""Dump the stage-52 changed footprints (pads, nets, drill, model, courtyard, fab/silk bbox) from a board copy."""
import json, sys
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
REFS = sys.argv[3].split(",")
mm = pcbnew.ToMM
out = {}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref not in REFS:
        continue
    d = {"fpid": str(fp.GetFPID().GetUniStringLibId()), "value": fp.GetValue(),
         "x": mm(fp.GetPosition().x), "y": mm(fp.GetPosition().y), "rot": fp.GetOrientationDegrees(),
         "side": "B" if fp.IsFlipped() else "F", "attrs": fp.GetAttributes(),
         "fields": {f.GetName(): f.GetText() for f in fp.GetFields()}}
    d["pads"] = []
    for p in fp.Pads():
        d["pads"].append({"num": p.GetNumber(), "net": p.GetNetname(), "x": mm(p.GetPosition().x), "y": mm(p.GetPosition().y),
                          "size": [mm(p.GetSizeX()), mm(p.GetSizeY())], "drill": [mm(p.GetDrillSizeX()), mm(p.GetDrillSizeY())],
                          "shape": p.GetShapeName() if hasattr(p, "GetShapeName") else int(p.GetShape())})
    d["models"] = [{"file": m.m_Filename, "offset": [m.m_Offset.x, m.m_Offset.y, m.m_Offset.z],
                    "rot": [m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z], "scale": [m.m_Scale.x, m.m_Scale.y, m.m_Scale.z],
                    "show": m.m_Show} for m in fp.Models()]
    for layer, name in [(pcbnew.F_CrtYd, "crtyd"), (pcbnew.F_Fab, "fab"), (pcbnew.F_SilkS, "silk"), (pcbnew.B_CrtYd, "b_crtyd")]:
        bb = None
        items = []
        for g in fp.GraphicalItems():
            if g.GetLayer() == layer:
                r = g.GetBoundingBox()
                items.append([mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom()), g.GetClass(), mm(g.GetWidth()) if hasattr(g,'GetWidth') else None])
        d[name] = items
    out[ref] = d
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(len(out), "footprints")
