#!/usr/bin/env python3
"""Add layout/gridroute.py's tracks and vias to a board, refill zones, save (KiCad Python).

    KICAD_PY layout/apply_routes.py <board.kicad_pcb> <routes.json>
"""
import json
import sys

import pcbnew


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    r = json.load(open(sys.argv[2]))
    L = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
    for t in r["tracks"]:
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(t["a"][0]), pcbnew.FromMM(t["a"][1])))
        tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(t["b"][0]), pcbnew.FromMM(t["b"][1])))
        tr.SetWidth(pcbnew.FromMM(t["w"]))
        tr.SetLayer(L[t["layer"]])
        tr.SetNet(b.FindNet(t["net"]))
        b.Add(tr)
    for v in r["vias"]:
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(v["at"][0]), pcbnew.FromMM(v["at"][1])))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetNet(b.FindNet(v["net"]))
        b.Add(via)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(sys.argv[1], b)
    print(f"added {len(r['tracks'])} tracks, {len(r['vias'])} vias; {len(r.get('failed', []))} pairs unrouted")


if __name__ == "__main__":
    main()
