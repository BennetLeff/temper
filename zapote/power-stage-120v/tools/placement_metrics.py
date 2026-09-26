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

HEATSINK_X = (5.0, 145.0)   # D2 heatsink span along the top edge
HEAT_ZONE_MM = 10.0         # Part 4 rule 4
STUDS = {"J2", "J5", "J7", "J8", "J9", "J10"}  # M4 studs: screw passes the NPTH
# Parts allowed within HEAT_ZONE_MM of the heatsink: power devices, their
# snubbers and gate networks (which belong at the gate pins), and the shunt.
HEAT_ALLOWED_PREFIX = ("Q", "BR", "R5")
GATE_AND_SNUBBER = {"C12", "C13", "C19", "C20", "R10", "R11", "R12", "R13",
                    "R18", "R19", "R20", "R21"}
ENVELOPES = Path(__file__).resolve().parents[1] / "terminal_envelopes.json"


def item_box(centres, item, spec):
    """Plan-view rectangle (x1, y1, x2, y2) of one installed hardware item."""
    hw = item["hardware"]
    if hw == "link_strap":
        (ax, ay), (bx, by) = (centres[r] for r in item["studs"])
        w, e = spec["width_mm"] / 2, spec["beyond_stud_mm"]
        if abs(bx - ax) >= abs(by - ay):
            return [min(ax, bx) - e, ay - w, max(ax, bx) + e, ay + w]
        return [ax - w, min(ay, by) - e, ax + w, max(ay, by) + e]
    (cx, cy), = (centres[r] for r in item["studs"])
    if hw == "bare_stud":
        half = spec["square_mm"] / 2
        return [cx - half, cy - half, cx + half, cy + half]
    w, back, ahead = spec["width_mm"] / 2, spec["behind_stud_mm"], spec["ahead_of_stud_mm"]
    dx, dy = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[item["direction"]]
    if dx:
        x1, x2 = sorted((cx - dx * back, cx + dx * ahead))
        return [x1, cy - w, x2, cy + w]
    y1, y2 = sorted((cy - dy * back, cy + dy * ahead))
    return [cx - w, y1, cx + w, y2]


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

    # Installed terminal hardware (terminal_envelopes.json), both configurations.
    env = json.loads(ENVELOPES.read_text())
    centres = {}
    for fp in board.GetFootprints():
        if fp.GetReference() in STUDS:
            pos = fp.GetPosition()
            centres[fp.GetReference()] = (mm(pos.x), mm(pos.y))
    floors = env["hardware"]["min_clearance_mm"]
    tank = write_rules.TANK
    configs = {}
    for name, cfg in env["configurations"].items():
        items = []
        for item in cfg["items"]:
            nets = {stud_net[r] for r in item["studs"]}
            items.append((item["id"], set(item["studs"]), nets,
                           item_box(centres, item, env["hardware"][item["hardware"]])))
        # Electrical: live metal of each item against other-potential copper
        # and other items' metal.
        electrical = []
        for i, (ia, sa, na, ba) in enumerate(items):
            targets = [(ib, nb, bb) for ib, sb, nbs, bb in items[i + 1:]
                       if not (na & nbs) for nb in sorted(nbs)]
            targets += [(f"{r}.{n}", nt, b) for r, n, nt, b in pads if r not in sa and nt not in na]
            for ib, nb, bb in targets:
                if domain(nb) in ("SELV", "PE"):
                    need = floors["hot_to_selv_or_pe"]
                elif (na & tank) or nb in tank:
                    need = floors["tank_to_other_hot"]
                else:
                    need = floors["hot_to_other_hot"]
                gap = box_gap(ba, bb)
                if gap < need + 2.0:
                    electrical.append({"item": ia, "other": ib, "other_net": nb,
                                       "gap_mm": round(gap, 2), "required_mm": need, "ok": gap >= need})
        electrical.sort(key=lambda w: w["gap_mm"] - w["required_mm"])
        # Mechanical, independent of nets: items against each other and
        # against every courtyard except the studs they mount on.
        mech_floor = floors["mechanical_mm"]
        mechanical = []
        for i, (ia, sa, _na, ba) in enumerate(items):
            for ib, _sb, _nb, bb in items[i + 1:]:
                gap = box_gap(ba, bb)
                overlap = ba[0] < bb[2] and bb[0] < ba[2] and ba[1] < bb[3] and bb[1] < ba[3]
                if overlap or gap < mech_floor:
                    mechanical.append({"item": ia, "other": ib, "gap_mm": 0.0 if overlap else round(gap, 2)})
            for r, b in fps.items():
                if r in sa:
                    continue
                overlap = ba[0] < b[2] and b[0] < ba[2] and ba[1] < b[3] and b[1] < ba[3]
                if overlap:
                    mechanical.append({"item": ia, "other": r, "gap_mm": 0.0})
        configs[name] = {
            "items": {ia: [round(v, 2) for v in ba] for ia, _s, _n, ba in items},
            "closest_electrical": electrical[:6],
            "electrical_ok": all(w["ok"] for w in electrical),
            "mechanical_conflicts": mechanical,
            "mechanical_ok": not mechanical,
        }

    # Commutation path lower bounds per local capacitor, through R5's current
    # pads only (pad 1 LEG_RET, pad 4 HV_RET; pads 2/3 are Kelvin sense):
    # high-side drain -> capacitor BUS_P -> capacitor HV_RET -> R5 pad 4,
    # and low-side source -> R5 pad 1. Pad centres, Manhattan.
    def pad_at(ref, number):
        return [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for r, n, _nt, b in pads if r == ref and n == number]

    def centres_of(ref, net):
        return [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for r, _n, nt, b in pads if r == ref and nt == net]

    def nearest(points, others):
        return min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in points for b in others)

    r5_in, r5_out = pad_at("R5", "1"), pad_at("R5", "4")
    loops = {}
    for leg, low, high, caps in (("leg_a", "Q3", "Q2", ("C38", "C39")),
                                  ("leg_b", "Q6", "Q5", ("C40", "C41"))):
        src_to_shunt = nearest(centres_of(low, "leg_ret"), r5_in)
        per_cap = {}
        for cap in caps:
            drain_to_cap = nearest(centres_of(high, "bus_p"), centres_of(cap, "bus_p"))
            cap_to_shunt = nearest(centres_of(cap, "hv_ret"), r5_out)
            per_cap[cap] = {"high_drain_to_cap_bus_mm": round(drain_to_cap, 1),
                            "cap_return_to_R5_pad4_mm": round(cap_to_shunt, 1),
                            "sum_with_source_to_R5_pad1_mm": round(drain_to_cap + cap_to_shunt + src_to_shunt, 1)}
        loops[leg] = {"low_source_to_R5_pad1_mm": round(src_to_shunt, 1), "per_capacitor": per_cap}

    commutation = ["Q2", "Q3", "Q5", "Q6", "C38", "C39", "C40", "C41", "R5"]
    xs = [v for r in commutation for v in (fps[r][0], fps[r][2])]
    ys = [v for r in commutation for v in (fps[r][1], fps[r][3])]

    def pad_centre(ref, number):
        for r, n, _net, b in pads:
            if r == ref and n == number:
                return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        raise KeyError((ref, number))

    def manhattan(a, b):
        return round(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)

    gate = {}
    for label, drv, out_pin, fet, res in (
        ("leg_a high", "U1", "15", "Q2", "R10"), ("leg_a low", "U1", "10", "Q3", "R12"),
        ("leg_b high", "U2", "15", "Q5", "R18"), ("leg_b low", "U2", "10", "Q6", "R20"),
    ):
        out, gate_pad = pad_centre(drv, out_pin), pad_centre(fet, "1")
        r_pads = [pad_centre(res, "1"), pad_centre(res, "2")]
        near_gate = min(r_pads, key=lambda c: manhattan(c, gate_pad))
        near_drv = r_pads[1] if near_gate is r_pads[0] else r_pads[0]
        gate[label] = {
            "series_resistor_to_gate_mm": manhattan(near_gate, gate_pad),
            "driver_out_to_series_resistor_mm": manhattan(out, near_drv),
        }

    heat = sorted(r for r, b in fps.items()
                  if b[1] < HEAT_ZONE_MM and b[2] > HEATSINK_X[0] and b[0] < HEATSINK_X[1])
    heat_unexpected = [r for r in heat if not r.startswith(HEAT_ALLOWED_PREFIX)
                       and r not in GATE_AND_SNUBBER]
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
        "commutation_paths": loops,
        "gate_paths": gate,
        "heat_zone_parts": heat,
        "heat_zone_unexpected": heat_unexpected,
        "stud_screw_holes": stud_holes,
        "terminal_hardware": configs,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
