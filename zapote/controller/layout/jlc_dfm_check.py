#!/usr/bin/env python3
"""Check the routed controller board against JLCPCB's published multilayer 1 oz limits, with margin.

    KICAD_PY layout/jlc_dfm_check.py pcb/controller.kicad_pcb > evidence/jlc-dfm.json

Adapted from zapote/power-stage-120v/tools/jlc_dfm_check.py (2 oz) to this board's 1 oz outer
copper. JLC figures re-read on 2026-10-09 from https://jlcpcb.com/capabilities/pcb-capabilities:
  - min track width / spacing, multilayer 1 oz: 0.09 / 0.09 mm
  - PTH annular ring, 1 oz: recommended >= 0.20 mm, absolute minimum 0.15 mm
  - via hole / diameter: 0.15 / 0.25 mm; via hole-to-hole 0.2 mm; pad hole-to-hole 0.45 mm
  - non-plated hole >= 0.50 mm; copper to routed board edge >= 0.2 mm
C53 (six layers): the multilayer track/space (0.09/0.09 mm, 1 oz), via (0.15/0.25 mm) and PTH ring (0.20 mm
recommended, 0.15 mm minimum) figures were re-read on 2026-11-26 and are unchanged.
Limits applied here (each with margin over the JLC minimum):
  - plated component holes: ring >= 0.20 mm (the recommended value), drill 0.15-6.3 mm;
  - vias: drill >= 0.3 mm and ring >= 0.15 mm (2x JLC's 0.05 mm via ring rule);
  - tracks >= 0.15 mm (1.7x JLC's 0.09 mm); our routing uses >= 0.2 mm;
  - NPTH >= 0.5 mm; size <= 663 x 593 mm (the 4-layer figure read 2026-10-09; the six-layer size limit was
    not re-read, and the board is 206 x 76 mm).
Spacing, hole-to-hole (0.5 mm) and edge clearance (0.5 mm) are KiCad DRC rules (pcb/controller.kicad_pro).
Every plated pad must have copper on F.Cu and B.Cu (a pad whose outer land was stripped would pass
KiCad's DRC; see the original gate's history).
"""
from __future__ import annotations

import json
import sys

import pcbnew  # type: ignore[import-not-found]

LIMITS = {"annular_ring_mm": 0.20, "via_ring_mm": 0.15, "track_mm": 0.15, "via_drill_mm": 0.3,
          "pth_drill_mm": (0.15, 6.3), "npth_drill_mm": 0.5, "board_max_mm": (663.0, 593.0),
          "copper": "1 oz outer (0.035 mm), 0.5 oz inner, JLC04161H-7628"}


def main() -> None:
    board = pcbnew.LoadBoard(sys.argv[1])
    mm = pcbnew.ToMM
    fails = []
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    for v in vias:
        ring = (mm(v.GetWidth(pcbnew.F_Cu)) - mm(v.GetDrillValue())) / 2
        if ring < LIMITS["via_ring_mm"] - 1e-9 or mm(v.GetDrillValue()) < LIMITS["via_drill_mm"] - 1e-9:
            fails.append({"kind": "via", "net": v.GetNetname(), "at": [mm(v.GetPosition().x), mm(v.GetPosition().y)],
                          "ring_mm": round(ring, 4)})
    for t in tracks:
        if mm(t.GetWidth()) < LIMITS["track_mm"] - 1e-9:
            fails.append({"kind": "track", "net": t.GetNetname(), "width_mm": mm(t.GetWidth())})
    pads = npth = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if d.x <= 0:
                continue
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                npth += 1
                if min(mm(d.x), mm(d.y)) < LIMITS["npth_drill_mm"]:
                    fails.append({"kind": "npth", "ref": f"{fp.GetReference()}", "drill_mm": mm(d.x)})
                continue
            pads += 1
            s = p.GetSize(pcbnew.F_Cu)
            ring = min(mm(s.x) - mm(d.x), mm(s.y) - mm(d.y)) / 2
            lo, hi = LIMITS["pth_drill_mm"]
            if ring < LIMITS["annular_ring_mm"] - 1e-9 or not (lo <= mm(d.x) <= hi and lo <= mm(d.y) <= hi):
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
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import world
    if board.GetCopperLayerCount() != world.COPPER_LAYERS:
        fails.append({"kind": "layers", "count": board.GetCopperLayerCount()})
    print(json.dumps({"limits": LIMITS, "vias": len(vias), "tracks": len(tracks), "plated_pads": pads,
                      "npth_pads": npth, "board_mm": size,
                      "min_track_mm": min(mm(t.GetWidth()) for t in tracks) if tracks else None,
                      "failures": fails, "status": "PASS" if not fails else "FAIL"}, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
