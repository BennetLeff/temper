#!/usr/bin/env python3
"""Check the routed board against every enclosure constraint and the layout rules of the brief.

    KICAD_PY layout/check_layout.py [pcb/controller.kicad_pcb]   -> evidence/layout-check.json, exit 1 on FAIL

Enclosure (output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md, R31 section, via layout/world.py):
  outline     Edge.Cuts is exactly the X-168..38 / Y14..90 rectangle, 1.6 mm board, 4 copper layers
  holes       six 4.0 mm holes (R30) at the R28 positions (+-0.05 mm), nothing else cut
  hole_keepout  no courtyard, pad, track, via or copper fill inside the 8 mm snap-in head circle
  connectors  J1-J3, J5, J6, J8-J10 body (F.Fab) centre within 0.5 mm of the R31 centre; J3 body along the rear edge
  j4          courtyard within 0.5 mm of world.J4_BODY, mating face (pegs) toward world.J4_MATING at that edge
  wroom       body within 0.5 mm of X-54..-36 / Y14..39.5, antenna end at the front edge, the footprint's
              Espressif keep-out rule area intact and free of copper on every layer
  height      tallest parts against the 15.4 mm allowance (Z40 - Z23 - 1.6, R30) and R28's 6.4 mm
              allocation for non-connector parts (heights: ENCLOSURE-HANDOFF.md list)
Layout rules (brief):
  decoupling  every IC supply pin (the 'vcc' pins of verify_controller's part models) has a capacitor to
              selv_gnd on the same net within 5 mm (pad to pad)
  interlock   no track of an MCU (U4) net crosses the interlock region; PERMIT path latch->J4.9 length
  thermal_relief  every through-hole pad that a pour reaches is thermal-relieved (zone setting)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(HERE))
import world  # noqa: E402

mm = pcbnew.ToMM
TOL = world.CONNECTOR_TOL
GATE = ["U37", "C70", "R102", "R103"]
INTERLOCK = ["U20", "U21", "U22", "U23", "U24", "U25", "R51", "R52", "R53", "R54", "R55", "R56", "R57", "R58",
             "R59", "R60", "R61", "C34", "C35", "C36", "C37", "C38", "C39", "U37", "C70", "R102", "R103"]
# Part heights above the board, mm (ENCLOSURE-HANDOFF.md "Height and cable exit"; J4 and J11 from the
# KiCad footprint/3D model family, flagged in LAYOUT.md as not checked against a drawing)
HEIGHTS = {"JST XH (J1-J3, J6, J8-J10)": 7.0, "C1 EEE-FK1E101P": 6.2, "L1/L2 SWPA6045": 4.5,
           "U4 ESP32-S3-WROOM-1": 3.25, "J5 Micro-MaTch 215079-6": 4.3}
CONNECTOR_PARTS = {"JST XH (J1-J3, J6, J8-J10)", "J5 Micro-MaTch 215079-6"}


def wbox(b):
    """KiCad-frame (x0,y0,x1,y1) mm -> world (X0,Y0,X1,Y1)."""
    X0, Y1 = world.to_w(b[0], b[1])
    X1, Y0 = world.to_w(b[2], b[3])
    return (X0, Y0, X1, Y1)


def layer_bbox(fp, layer):
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == layer:
            bb = g.GetBoundingBox()
            xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
            ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    return (min(xs), min(ys), max(xs), max(ys))


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rect_dist(p, r):
    dx = max(r[0] - p[0], 0, p[0] - r[2])
    dy = max(r[1] - p[1], 0, p[1] - r[3])
    return math.hypot(dx, dy)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else str(UNIT / "pcb/controller.kicad_pcb")
    b = pcbnew.LoadBoard(path)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    res = {}

    def put(name, ok, **kw):
        res[name] = {"ok": bool(ok), **kw}

    # ---- outline
    segs, circles = [], []
    for d in b.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        if d.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            c = d.GetCenter()
            circles.append((world.to_w(mm(c.x), mm(c.y)), 2 * mm(d.GetRadius())))
        else:
            segs.append(d)
    bb = b.GetBoardEdgesBoundingBox()
    ob = wbox((mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))
    # the edge line width (0.1) widens the bbox by 0.05 per side
    err = max(abs(o - w) for o, w in zip(ob, (world.BOARD[0] - 0.05, world.BOARD[1] - 0.05,
                                              world.BOARD[2] + 0.05, world.BOARD[3] + 0.05)))
    put("outline", err < 0.01 and len(segs) == 4 and b.GetCopperLayerCount() == 4
        and abs(mm(b.GetDesignSettings().GetBoardThickness()) - world.THICKNESS) < 1e-6,
        world_bbox=[round(v, 3) for v in ob], edge_segments=len(segs), copper_layers=b.GetCopperLayerCount(),
        thickness_mm=mm(b.GetDesignSettings().GetBoardThickness()))

    # ---- holes
    rows, ok = [], len(circles) == len(world.HOLES)
    for hx, hy in world.HOLES:
        best = min(circles, key=lambda c: math.hypot(c[0][0] - hx, c[0][1] - hy))
        e = math.hypot(best[0][0] - hx, best[0][1] - hy)
        ok &= e < 0.05 and abs(best[1] - world.HOLE_D) < 0.01
        rows.append({"hole": [hx, hy], "found": [round(best[0][0], 3), round(best[0][1], 3)], "d": round(best[1], 3)})
    put("holes", ok, holes=rows, cutouts=len(circles))

    # ---- hole keep-outs (8 mm): courtyards, pads, tracks, vias, zone fills
    r = world.HOLE_KEEPOUT_D / 2
    hits = []
    for hx, hy in world.HOLES:
        kx, ky = world.to_k(hx, hy)
        c = pcbnew.VECTOR2I(pcbnew.FromMM(kx), pcbnew.FromMM(ky))
        for ref, f in fps.items():
            cy = f.GetCourtyard(pcbnew.F_CrtYd)
            if cy.OutlineCount() and cy.Collide(c, pcbnew.FromMM(r)):
                hits.append({"hole": [hx, hy], "item": f"courtyard {ref}"})
            for p in f.Pads():
                pb = p.GetBoundingBox()
                if rect_dist((kx, ky), (mm(pb.GetLeft()), mm(pb.GetTop()), mm(pb.GetRight()), mm(pb.GetBottom()))) < r:
                    hits.append({"hole": [hx, hy], "item": f"pad {ref}.{p.GetNumber()}"})
        for t in b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                d = math.hypot(mm(t.GetPosition().x) - kx, mm(t.GetPosition().y) - ky) - mm(t.GetWidth(pcbnew.F_Cu)) / 2
            else:
                d = seg_dist((kx, ky), (mm(t.GetStart().x), mm(t.GetStart().y)),
                             (mm(t.GetEnd().x), mm(t.GetEnd().y))) - mm(t.GetWidth()) / 2
            if d < r:
                hits.append({"hole": [hx, hy], "item": f"track/via {t.GetNetname()}"})
        for z in b.Zones():
            if z.GetIsRuleArea():
                continue
            for lay in z.GetLayerSet().Seq():
                fill = z.GetFilledPolysList(lay)
                if fill.OutlineCount() and fill.Collide(c, pcbnew.FromMM(r - 0.01)):
                    hits.append({"hole": [hx, hy], "item": f"fill {z.GetZoneName()} {pcbnew.LayerName(lay)}"})
    put("hole_keepout", not hits, radius_mm=r, intrusions=hits)

    # ---- connectors
    rows, ok = [], True
    for ref, (x, y) in world.CONNECTORS.items():
        fb = wbox(layer_bbox(fps[ref], pcbnew.F_Fab))
        cx, cy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
        e = math.hypot(cx - x, cy - y)
        inside = fb[0] >= world.BOARD[0] and fb[2] <= world.BOARD[2] and fb[1] >= world.BOARD[1] and fb[3] <= world.BOARD[3]
        ok &= e <= TOL and inside
        rows.append({"ref": ref, "spec": [x, y], "body_centre": [round(cx, 3), round(cy, 3)], "error_mm": round(e, 3),
                     "body_on_board": inside})
    j3 = wbox(layer_bbox(fps["J3"], pcbnew.F_Fab))
    j3_along = (j3[2] - j3[0]) > (j3[3] - j3[1])
    put("connectors", ok and j3_along, tolerance_mm=TOL, rows=rows, j3_body_along_rear_edge=j3_along)

    # ---- J4
    j4 = fps["J4"]
    cb = wbox(layer_bbox(j4, pcbnew.F_CrtYd))
    e = max(abs(a - s) for a, s in zip(cb, world.J4_BODY))
    pegs = [world.to_w(mm(p.GetPosition().x), mm(p.GetPosition().y))[0] for p in j4.Pads()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    pins = [world.to_w(mm(p.GetPosition().x), mm(p.GetPosition().y))[0] for p in j4.Pads()
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    # the PCB pegs sit on the mating side of the pin rows
    mating = "+X" if min(pegs) > max(pins) else ("-X" if max(pegs) < min(pins) else "?")
    edge_ok = abs(cb[2] - world.BOARD[2]) <= TOL if world.J4_MATING == "+X" else abs(cb[0] - world.BOARD[0]) <= TOL
    pin1 = next(p for p in j4.Pads() if p.GetNumber() == "1")
    put("j4", e <= TOL and mating == world.J4_MATING and edge_ok,
        courtyard_world=[round(v, 3) for v in cb], spec=list(world.J4_BODY), max_edge_error_mm=round(e, 3),
        mating=mating, mating_required=world.J4_MATING, at_board_edge=edge_ok,
        pin1_world=[round(v, 3) for v in world.to_w(mm(pin1.GetPosition().x), mm(pin1.GetPosition().y))])

    # ---- WROOM + antenna keep-out
    u4 = fps["U4"]
    fb = wbox(layer_bbox(u4, pcbnew.F_Fab))
    e = max(abs(a - s) for a, s in zip(fb, world.WROOM))
    ras = [z for z in u4.Zones() if z.GetIsRuleArea()]
    ko = None
    if ras:
        zb = ras[0].GetBoundingBox()
        ko = wbox((mm(zb.GetLeft()), mm(zb.GetTop()), mm(zb.GetRight()), mm(zb.GetBottom())))
    antenna_front = ko is not None and (ko[1] + ko[3]) / 2 < (fb[1] + fb[3]) / 2
    ko_size_ok = ko is not None and abs((ko[2] - ko[0]) - 48.0) < 0.05 and abs((ko[3] - ko[1]) - 21.0) < 0.05
    flags = ras[0] if ras else None
    flags_ok = flags is not None and all([flags.GetDoNotAllowTracks(), flags.GetDoNotAllowVias(), flags.GetDoNotAllowPads(),
                                         flags.GetDoNotAllowZoneFills(), flags.GetDoNotAllowFootprints()]) \
        and flags.GetLayerSet().Contains(pcbnew.In1_Cu) and flags.GetLayerSet().Contains(pcbnew.In2_Cu)
    copper = []
    if ko:
        kb = (ko[0], max(ko[1], world.BOARD[1]), ko[2], ko[3])
        k0 = world.to_k(kb[0], kb[3])
        k1 = world.to_k(kb[2], kb[1])
        rect = pcbnew.SHAPE_POLY_SET()
        rect.NewOutline()
        for x, y in ((k0[0], k0[1]), (k1[0], k0[1]), (k1[0], k1[1]), (k0[0], k1[1])):
            rect.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        for t in b.GetTracks():
            tb = t.GetBoundingBox()
            if not (mm(tb.GetRight()) < k0[0] or mm(tb.GetLeft()) > k1[0] or mm(tb.GetBottom()) < k0[1] or mm(tb.GetTop()) > k1[1]):
                copper.append(f"track/via {t.GetNetname()}")
        for f in b.GetFootprints():
            for p in f.Pads():
                pb = p.GetBoundingBox()
                if not (mm(pb.GetRight()) < k0[0] or mm(pb.GetLeft()) > k1[0] or mm(pb.GetBottom()) < k0[1] or mm(pb.GetTop()) > k1[1]):
                    copper.append(f"pad {f.GetReference()}.{p.GetNumber()}")
        for z in b.Zones():
            if z.GetIsRuleArea():
                continue
            for lay in z.GetLayerSet().Seq():
                fill = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(lay))
                if fill.OutlineCount():
                    fill.BooleanIntersection(rect)
                    if fill.OutlineCount() and fill.Area() > 1e6 * 0.01:     # > 0.01 mm^2
                        copper.append(f"fill {z.GetZoneName()} {pcbnew.LayerName(lay)}")
    # enclosure-owned conflict: holes inside Espressif's 15 mm lateral clearance (no copper; nylon at board level)
    conflicts = []
    if ko:
        for hx, hy in world.HOLES:
            if ko[0] <= hx <= ko[2] and ko[1] <= hy <= ko[3]:
                conflicts.append({"hole": [hx, hy], "module_side_to_hole_centre_mm": round(min(abs(hx - fb[0]), abs(hx - fb[2])), 2),
                                  "note": "hole is a copper-free milled cutout and its R30 support is an all-nylon snap-in, "
                                          "so the keep-out holds no copper and no metal; enclosure to confirm, or move "
                                          "the hole >= 19 mm from the module side"})
    put("wroom", e <= TOL and antenna_front and ko_size_ok and flags_ok and not copper,
        body_world=[round(v, 3) for v in fb], spec=list(world.WROOM), max_edge_error_mm=round(e, 3),
        antenna_end="front" if antenna_front else "rear", keepout_world=[round(v, 3) for v in ko] if ko else None,
        keepout_rule_flags_ok=flags_ok, copper_in_keepout=copper, enclosure_conflicts=conflicts)

    # ---- height
    allowance = world.Z_LIMIT - world.BOARD_BOTTOM_Z - world.THICKNESS
    rows = {k: {"height_mm": v, "limit_mm": allowance if k in CONNECTOR_PARTS else 6.4} for k, v in HEIGHTS.items()}
    put("height", all(v["height_mm"] <= v["limit_mm"] for v in rows.values()), allowance_mm=round(allowance, 2),
        parts=rows, not_checked=["J4 43045-1600 and mated plug (Molex drawing not read; R31: plug to X-50, Z<=40)",
                                 "J11 1x8 2.54 mm header (bring-up only, may be unfitted)", "mated XH plugs and cable bends"])

    # ---- decoupling
    supplies = {"v3v3", "v15_selv", "RTD_AVDD", "V5_ENC", "v5_drop", "v12_fan"}
    caps = [f for r_, f in fps.items() if r_.startswith("C")]
    # supply pins = the "vcc" pins of the part models in tools/verify_controller.py (datasheet pin
    # tables); parts without a model: every pin on a supply net
    sys.path.insert(0, str(UNIT / "tools"))
    from verify_controller import MODELS  # noqa: E402
    rows, ok = [], True
    for ref, f in sorted(fps.items()):
        if not ref.startswith("U"):
            continue
        model = MODELS.get(f.GetFieldText("MPN"))
        for p in f.Pads():
            n = p.GetNetname()
            if n not in supplies:
                continue
            if model is not None and model.pins and model.pins.get(p.GetNumber()) != "vcc":
                continue
            px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
            best = None
            for c in caps:
                cp = {q.GetNetname() for q in c.Pads()}
                if n in cp and "selv_gnd" in cp:
                    q = next(q for q in c.Pads() if q.GetNetname() == n)
                    d = math.hypot(mm(q.GetPosition().x) - px, mm(q.GetPosition().y) - py)
                    if best is None or d < best[0]:
                        best = (d, c.GetReference())
            good = best is not None and best[0] <= 5.0
            ok &= good
            rows.append({"pin": f"{ref}.{p.GetNumber()}", "net": n, "cap": best[1] if best else None,
                         "distance_mm": round(best[0], 2) if best else None, "ok": good})
    put("decoupling", ok, limit_mm=5.0, pins=rows)

    # ---- interlock regions: no MCU-net track through them. Two regions: the latch block
    # (U20-U25 and their pull-ups/bypasses) and the PERMIT gate at J4.9 (U37 with its parts).
    mcu_nets = {p.GetNetname() for p in fps["U4"].Pads()} - {"selv_gnd", "v3v3", ""}
    # MCU nets that end in a region by design (requests into the interlock: IL_RESET_N, IL_WDI,
    # RUN_EN; the read-back outputs of U9) are allowed in; any other MCU net crossing fails
    ends_inside = {p.GetNetname() for ref in INTERLOCK + ["U9"] for p in fps[ref].Pads()}
    regions = {}
    for name, refs in (("latch block", ["U20", "U21", "U22", "U23", "U24", "U25"]), ("PERMIT gate", GATE)):
        xs, ys = [], []
        for ref in refs:
            x0, y0, x1, y1 = layer_bbox(fps[ref], pcbnew.F_CrtYd)
            xs += [x0, x1]
            ys += [y0, y1]
        regions[name] = (min(xs), min(ys), max(xs), max(ys))
    cross = []
    for t in b.GetTracks():
        if t.GetNetname() not in mcu_nets or t.GetNetname() in ends_inside:
            continue
        pts = [(mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))]
        for name, reg in regions.items():
            hit = False
            for k in range(11):
                x = pts[0][0] + (pts[1][0] - pts[0][0]) * k / 10
                y = pts[0][1] + (pts[1][1] - pts[0][1]) * k / 10
                if reg[0] < x < reg[2] and reg[1] < y < reg[3]:
                    cross.append({"region": name, "net": t.GetNetname(), "layer": t.GetLayerName(),
                                  "at": [round(v, 2) for v in world.to_w(x, y)]})
                    hit = True
                    break
            if hit:
                break
    reg = regions["latch block"]
    # PERMIT route length (latch Q -> J4.9) and trip-input route lengths
    def net_len(n):
        return round(sum(mm(t.GetLength()) for t in b.GetTracks() if t.GetNetname() == n and t.Type() == pcbnew.PCB_TRACE_T), 1)
    lengths = {n: net_len(n) for n in ("permit", "PERMIT_LATCH", "RUN_EN", "bus_fault", "all_good", "reset_clock", "latched_fault", "HS_FAULT",
                                       "COIL_FAULT", "line", "RUNAWAY_FAULT", "RAIL_FAULT", "SENSOR_LIVE")}
    put("interlock", not cross, regions_world={k: [round(v, 2) for v in wbox(r_)] for k, r_ in regions.items()},
        mcu_tracks_crossing=cross,
        mcu_nets_ending_inside=sorted(mcu_nets & ends_inside),
        route_length_mm=lengths)

    # ---- thermal relief on through-hole pads
    zs = [(z.GetZoneName(), z.GetPadConnection()) for z in b.Zones() if not z.GetIsRuleArea()]
    bad = [n for n, c in zs if c not in (pcbnew.ZONE_CONNECTION_THT_THERMAL, pcbnew.ZONE_CONNECTION_THERMAL)
           and not n.startswith(("SW_", "VIN_"))]
    tht_in_buck_pours = []
    for z in b.Zones():
        if z.GetZoneName().startswith(("SW_", "VIN_")):
            for f in b.GetFootprints():
                for p in f.Pads():
                    if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetNetname() == z.GetNetname():
                        if z.GetBoundingBox().Intersects(p.GetBoundingBox()):
                            tht_in_buck_pours.append(f"{f.GetReference()}.{p.GetNumber()}")
    put("thermal_relief", not bad and not tht_in_buck_pours, zones=[n for n, _ in zs], solid_connect_zones_with_tht=bad + tht_in_buck_pours,
        note="GND/v3v3 planes and pours use 'thermal reliefs for PTH' (SMD solid); the buck SW/VIN pours touch SMD pads only")

    # ---- analog partition: courtyard-to-courtyard separations (ENCLOSURE-HANDOFF placement notes)
    def crt(ref):
        return layer_bbox(fps[ref], pcbnew.F_CrtYd)

    def gap(a, b):
        ra, rb = crt(a), crt(b)
        dx = max(rb[0] - ra[2], ra[0] - rb[2], 0)
        dy = max(rb[1] - ra[3], ra[1] - rb[3], 0)
        return math.hypot(dx, dy)
    rtd_analog = [r for r in fps if fps[r].GetFieldText("SourceInstance").startswith("rtd_pan.")
                  and not r.startswith("J")] + ["U10", "R63", "R64", "C42"]
    thermal = [r for r in fps if fps[r].GetFieldText("SourceInstance").startswith("thermal.") and not r.startswith("J")]
    analog_j4 = ["U5", "U6", "U7", "U13", "U14", "U15", "R65", "R66", "R67", "R68", "R70", "R71", "R73", "R80",
                 "R81", "R82", "C54", "C55", "C56", "C57", "C58"]
    sw = {"L2/U2 (12 V fan buck)": ["L2", "U2"], "L1/U1 (3.3 V buck)": ["L1", "U1"]}
    sep = {}
    for name, parts in sw.items():
        for grp_name, grp in (("RTD front end", rtd_analog), ("thermal-sense", thermal), ("J4 analog", analog_j4)):
            d, pair = min((gap(a, b), (a, b)) for a in parts for b in grp)
            sep[f"{name} -> {grp_name}"] = {"mm": round(d, 1), "nearest": pair}
    put("partition", sep["L2/U2 (12 V fan buck) -> RTD front end"]["mm"] >= 10.0, rule="L2 >= 10 mm from the RTD "
        "analog section (ENCLOSURE-HANDOFF item 6); others reported", separations_mm=sep)

    status = "PASS" if all(v["ok"] for v in res.values()) else "FAIL"
    out = {"board": str(Path(path).name), "revision": world.REVISION,
           "source": "output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md (R31 section; R30 mounting/height)",
           "transform": f"kx = X + {world.OX:g}, ky = {world.OY:g} - Y (layout/world.py)", "checks": res,
           "summary": {k: v["ok"] for k, v in res.items()}, "status": status}
    (UNIT / "evidence").mkdir(exist_ok=True)
    (UNIT / "evidence/layout-check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]), status)
    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
