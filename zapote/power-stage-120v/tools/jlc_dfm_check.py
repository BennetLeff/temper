#!/usr/bin/env python3
"""Check a routed board against JLCPCB's published 2 oz multilayer limits.

    KICAD_PY tools/jlc_dfm_check.py <board> > jlc-dfm.json

Limits are from https://jlcpcb.com/capabilities/pcb-capabilities as read on
2026-09-26 (2 oz: annular ring >= 0.254 mm for vias and PTH pads, track/space
>= 0.15 mm; via drill >= 0.15 mm; PTH drill 0.15-6.3 mm; via hole-to-hole
>= 0.2 mm; 4-layer size <= 663 x 593 mm). Copper spacing itself is enforced
by the board's DRC rules (Default netclass 0.2 mm), not re-measured here.

Every plated through-hole pad must also have copper (KiCad FlashLayer) on
both F.Cu and B.Cu: a lead needs a solder land and the barrel an outer ring.
KiCad's DRC accepts a pad whose outer copper was removed by
remove_unused_layers, so this is checked here. (Native-08 to native-15 had
23 PTH pads with neither outer land, from a builder that read
"(remove_unused_layers no)" as yes.)
"""
from __future__ import annotations

import json
import sys

import pcbnew  # type: ignore[import-not-found]

LIMITS = {"annular_ring_mm": 0.254, "track_mm": 0.15, "via_drill_mm": 0.15,
          "pth_drill_mm": (0.15, 6.3), "board_max_mm": (663.0, 593.0)}


def main() -> None:
    board = pcbnew.LoadBoard(sys.argv[1])
    mm = pcbnew.ToMM
    fails = []
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    for v in vias:
        ring = (mm(v.GetWidth(pcbnew.F_Cu)) - mm(v.GetDrillValue())) / 2
        if ring < LIMITS["annular_ring_mm"] - 1e-9 or mm(v.GetDrillValue()) < LIMITS["via_drill_mm"]:
            fails.append({"kind": "via", "net": v.GetNetname(), "at": [mm(v.GetPosition().x), mm(v.GetPosition().y)],
                          "ring_mm": round(ring, 4)})
    for t in tracks:
        if mm(t.GetWidth()) < LIMITS["track_mm"] - 1e-9:
            fails.append({"kind": "track", "net": t.GetNetname(), "width_mm": mm(t.GetWidth())})
    pads = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if d.x <= 0 or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            pads += 1
            s = p.GetSize(pcbnew.F_Cu)
            ring = (mm(min(s.x, s.y)) - mm(max(d.x, d.y))) / 2
            lo, hi = LIMITS["pth_drill_mm"]
            if ring < LIMITS["annular_ring_mm"] - 1e-9 or not lo <= mm(d.x) <= hi:
                fails.append({"kind": "pad", "ref": f"{fp.GetReference()}.{p.GetNumber()}",
                              "ring_mm": round(ring, 4), "drill_mm": mm(d.x)})
            missing = [n for n, lid in (("F.Cu", pcbnew.F_Cu), ("B.Cu", pcbnew.B_Cu)) if not p.FlashLayer(lid)]
            if missing:
                fails.append({"kind": "pth_outer_land_missing", "ref": f"{fp.GetReference()}.{p.GetNumber()}",
                              "net": p.GetNetname(), "missing": missing})
    bb = board.GetBoardEdgesBoundingBox()
    size = sorted([mm(bb.GetWidth()), mm(bb.GetHeight())], reverse=True)
    if size[0] > LIMITS["board_max_mm"][0] or size[1] > LIMITS["board_max_mm"][1]:
        fails.append({"kind": "outline", "size_mm": size})
    print(json.dumps({"limits": LIMITS, "vias": len(vias), "tracks": len(tracks), "plated_pads": pads,
                      "min_track_mm": min(mm(t.GetWidth()) for t in tracks),
                      "failures": fails, "status": "PASS" if not fails else "FAIL"}, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
