#!/usr/bin/env python3
"""Placement-review measurements computed from the board, independent of DRC.

Run under KiCad's Python (pcbnew):

    KICAD_PY tools/placement_metrics.py native-03/section.kicad_pcb > native-03/placement-metrics.json
    KICAD_PY tools/placement_metrics.py native-03/section.kicad_pcb --world /tmp/world.json
    python3 tools/render_placement.py /tmp/world.json native-03/placement-preview.png

Distances are pad-copper bounding-box edge to edge on the outer layers, a
conservative (never larger) stand-in for true copper distance. Domains come
from tools/write_rules.py so metrics and DRC rules share one classification.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_rules  # noqa: E402

HEATSINK_X = (5.0, 160.0)   # D2 heatsink span along the top edge
HEAT_ZONE_MM = 10.0         # Part 4 rule 4
STUDS = {"J2", "J5", "J7", "J8", "J9", "J10"}  # M4 studs: screw passes the NPTH


def box_gap(a, b) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def main() -> None:
    import pcbnew  # type: ignore[import-not-found]

    board_path = Path(sys.argv[1])
    board = pcbnew.LoadBoard(str(board_path))
    world_out = Path(sys.argv[sys.argv.index("--world") + 1]) if "--world" in sys.argv else None
    mm = pcbnew.ToMM
    selv = write_rules.audit_selv_nets(write_rules.UNIT / "audit.rs") | write_rules.SELV_NC
    groups = {n: g for g, ns in write_rules.HOT_GROUPS.items() for n in ns}

    def domain(net: str) -> str:  # noqa: E306
        if net in selv:
            return "SELV"
        if net in write_rules.PE:
            return "PE"
        return "HOT" if net in groups else "NONE"

    pads, holes, fps, world = [], [], {}, []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        fps[ref] = [mm(cy.GetX()), mm(cy.GetY()), mm(cy.GetRight()), mm(cy.GetBottom())]
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            box = [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())]
            world.append({"ref": ref, "net": pad.GetNetname(), "box": box,
                          "npth": pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH})
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                holes.append((ref, box))
            elif pad.GetNetname():
                pads.append((ref, pad.GetNumber(), pad.GetNetname(), box))

    def closest(pred_a, pred_b):
        best = (math.inf, None, None)
        for ra, na, neta, ba in pads:
            if not pred_a(neta):
                continue
            for rb, nb, netb, bb in pads:
                if pred_b(netb):
                    gap = box_gap(ba, bb)
                    if gap < best[0]:
                        best = (gap, f"{ra}.{na}[{neta}]", f"{rb}.{nb}[{netb}]")
        return {"min_mm": round(best[0], 2), "between": [best[1], best[2]]}

    if world_out is not None:
        domains = {p["net"]: domain(p["net"]) for p in world if p["net"]}
        world_out.write_text(json.dumps({"courtyards": fps, "pads": world, "domains": domains}))
        return
    hot = lambda n: domain(n) == "HOT"  # noqa: E731
    stud_net = {ref: net for ref, _n, net, _b in pads if ref in STUDS}
    stud_holes = {}
    for ref, hole in holes:
        if ref not in STUDS:
            continue
        net = stud_net[ref]
        others = [(box_gap(hole, b), f"{r}.{n}[{nt}]") for r, n, nt, b in pads
                  if nt != net and r != ref]
        gap, item = min(others)
        stud_holes[ref] = {"stud_net": net, "nearest_other_net_mm": round(gap, 2), "nearest": item}

    commutation = ["Q2", "Q3", "Q5", "Q6", "C38", "C39", "C40", "C41", "R5"]
    xs = [v for r in commutation for v in (fps[r][0], fps[r][2])]
    ys = [v for r in commutation for v in (fps[r][1], fps[r][3])]

    def pad_centre(ref, number):
        for r, n, _net, b in pads:
            if r == ref and n == number:
                return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        raise KeyError((ref, number))

    gate = {}
    for label, drv, out_pin, fet in (
        ("leg_a high", "U1", "15", "Q2"), ("leg_a low", "U1", "10", "Q3"),
        ("leg_b high", "U2", "15", "Q5"), ("leg_b low", "U2", "10", "Q6"),
    ):
        (x1, y1), (x2, y2) = pad_centre(drv, out_pin), pad_centre(fet, "1")
        gate[label] = {"driver_out_to_gate_manhattan_mm": round(abs(x1 - x2) + abs(y1 - y2), 1)}

    heat = sorted(r for r, b in fps.items()
                  if b[1] < HEAT_ZONE_MM and b[2] > HEATSINK_X[0] and b[0] < HEATSINK_X[1])
    result = {
        "board": str(board_path),
        "barrier": {
            "selv_to_hot": closest(lambda n: domain(n) == "SELV", hot),
            "pe_to_hot": closest(lambda n: domain(n) == "PE", hot),
        },
        "commutation_bbox_mm": {
            "x": [round(min(xs), 1), round(max(xs), 1)], "y": [round(min(ys), 1), round(max(ys), 1)],
            "area_mm2": round((max(xs) - min(xs)) * (max(ys) - min(ys))),
            "members": commutation,
        },
        "gate_paths": gate,
        "heat_zone_parts": heat,
        "stud_screw_holes": stud_holes,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
