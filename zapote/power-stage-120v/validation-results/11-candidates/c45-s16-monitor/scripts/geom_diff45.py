#!/usr/bin/env python3
"""Stage 45 is BOM-only: show that two built boards differ in nothing but footprint fields (value / MPN text).

    KICAD_PY scripts/geom_diff45.py BOARD_A.kicad_pcb BOARD_B.kicad_pcb [--json OUT]

Compares, sorted and UUID-free: every footprint's reference, library id, layer, position, orientation and pads (number,
net, position, size, shape, drill, layers); every track / arc / via (layer, ends, width, net, drill); every zone (layer,
net, outline, priority); Edge.Cuts. Footprint fields (Value and other properties) are reported separately: those are the
only differences a BOM-only stage may have.
"""
import json
import sys

import pcbnew


def nm(p):
    return [p.x, p.y]


def board(path):
    b = pcbnew.LoadBoard(path)
    fps, fields = {}, {}
    for f in b.GetFootprints():
        ref = f.GetReference()
        pads = sorted([p.GetNumber(), p.GetNetname(), nm(p.GetPosition()), nm(p.GetSize()), int(p.GetShape()),
                       nm(p.GetDrillSize()), sorted(b.GetLayerName(l) for l in p.GetLayerSet().Seq())] for p in f.Pads())
        fps[ref] = [str(f.GetFPID().GetUniStringLibId()), b.GetLayerName(f.GetLayer()), nm(f.GetPosition()),
                    f.GetOrientationDegrees(), pads]
        fields[ref] = {"Value": f.GetValue(), **{k: str(v) for k, v in sorted(f.GetFieldsText().items())}}
    items = []
    for t in b.GetTracks():
        row = [t.GetClass(), b.GetLayerName(t.GetLayer()), nm(t.GetStart()), nm(t.GetEnd()), t.GetWidth(), t.GetNetname()]
        if t.GetClass() == "PCB_VIA":
            row.append(t.GetDrillValue())
        items.append(row)
    zones = sorted([z.GetNetname(), sorted(b.GetLayerName(l) for l in z.GetLayerSet().Seq()), z.GetAssignedPriority(),
                    [nm(z.Outline().CVertex(i)) for i in range(z.Outline().TotalVertices())]] for z in b.Zones())
    edges = sorted([d.GetClass(), nm(d.GetStart()), nm(d.GetEnd())] for d in b.GetDrawings()
                   if b.GetLayerName(d.GetLayer()) == "Edge.Cuts")
    return {"footprints": fps, "fields": fields, "tracks": sorted(items), "zones": zones, "edges": edges}


def main():
    a, b = board(sys.argv[1]), board(sys.argv[2])
    out = {"boards": sys.argv[1:3]}
    out["footprint_refs_equal"] = sorted(a["footprints"]) == sorted(b["footprints"])
    out["footprints_differing_in_geometry"] = sorted(r for r in a["footprints"] if a["footprints"][r] != b["footprints"].get(r))
    out["tracks_vias"] = {"a": len(a["tracks"]), "b": len(b["tracks"]), "equal": a["tracks"] == b["tracks"]}
    out["zones"] = {"a": len(a["zones"]), "b": len(b["zones"]), "outlines_equal": a["zones"] == b["zones"]}
    out["edge_cuts_equal"] = a["edges"] == b["edges"]
    out["field_changes"] = {r: {k: [a["fields"][r].get(k), b["fields"][r].get(k)]
                                for k in sorted(set(a["fields"][r]) | set(b["fields"][r]))
                                if a["fields"][r].get(k) != b["fields"][r].get(k)}
                            for r in sorted(a["fields"]) if r in b["fields"] and a["fields"][r] != b["fields"][r]}
    out["geometry_identical"] = (out["footprint_refs_equal"] and not out["footprints_differing_in_geometry"]
                                 and out["tracks_vias"]["equal"] and out["zones"]["outlines_equal"] and out["edge_cuts_equal"])
    txt = json.dumps(out, indent=1)
    if "--json" in sys.argv:
        open(sys.argv[sys.argv.index("--json") + 1], "w").write(txt + "\n")
    print(txt)


main()
