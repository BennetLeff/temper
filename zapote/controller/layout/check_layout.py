#!/usr/bin/env python3
"""Check the routed board against every enclosure constraint and the layout rules of the brief.

    KICAD_PY layout/check_layout.py [pcb/controller.kicad_pcb]   -> evidence/layout-check.json, exit 1 on FAIL

Enclosure (R31 CONTROLLER-SPEC section + R33 DECISIONS section 3 delta, via layout/world.py):
  outline     Edge.Cuts is exactly the X-38..168 / Y14..90 rectangle, 1.6 mm board, 4 copper layers
  holes       six 4.0 mm holes (R30) at the R31 positions (+-0.05 mm), nothing else cut
  hole_keepout  no courtyard, pad, track, via or copper fill inside the 8 mm snap-in head circle
  connectors  J1-J3, J7, J9, J10, J12, J13 body (F.Fab) centre within 0.5 mm of the spec centre (J12: the
              proposed R36 landing in world.py), J7's body edges
              within 0.5 mm of its R33 box; J3 body along the rear edge
  j4          courtyard within 0.5 mm of world.J4_BODY, mating face (pegs) toward world.J4_MATING at that edge
  wroom       WROOM-1U body inside the R33 box with every edge within 0.5 mm, U.FL end at the rear;
              no other courtyard within 3 mm of the U.FL (drawing position reported against R33's)
  height      tallest parts against the 15.4 mm allowance (Z40 - Z23 - 1.6, R30) and R28's 6.4 mm
              allocation for non-connector parts (heights and sources: ENCLOSURE-HANDOFF.md table)
Layout rules (brief):
  decoupling  every IC supply pin (the 'vcc' pins of verify_controller's part models) has a capacitor to
              selv_gnd on the same net within 5 mm (pad to pad)
  rtd_j3_protection  each J3 pin has its 220 nF and TVS (C37); pad distances reported
  rtd_j9_protection  each J9 line's 100 nF is nearer the pin than its BAV199 clamp (C51 layout rule)
  partition   both bucks (blower L2/U2, face fan L3/U51) >= 10 mm courtyard to courtyard from both RTD channels
  interlock   no track of an MCU (U4) net crosses the interlock region; PERMIT path latch->J4.9 length
  thermal_relief  every through-hole pad that a pour reaches is thermal-relieved (zone setting)
  power_widths  V_BLOWER routed >= 0.8 mm; V15_BLW's J13.1, bulk and input-cap pads in one F.Cu pour region
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
# Groups by atopile path (footprint SourceInstance): stable when a schematic edit renumbers designators
GATE_PATHS = ["u_permit", "c_permit", "r_run_en_pd", "r_permit_pd"]
# Part heights above the board, mm, with their drawing sources (ENCLOSURE-HANDOFF.md "Height and cable exit")
HEIGHTS = {"JST XH mated (J1-J3, J7, J9, J10, J12; JST eXH.pdf 9.8 assembled)": 9.8,
           "J13 B2P-VH mated (JST eVH.pdf p.1 mounting height 16.5)": 16.5,
           "J4 43045-1600 + 43025-1600 mated (Molex 43045 series part data 10.29)": 10.29,
           "J11 TC2050-IDC-NL land (C41: copper pads only, nothing fitted)": 0.0,
           "C1 EEE-FK1E101P": 6.2, "L1 SWPA6045": 4.5, "L2 SWRB1205S (Sunlord SWRB-S, 6.0 max)": 6.0,
           "U4 ESP32-S3-WROOM-1U (Espressif DS v1.8 Table 1-2)": 3.2}
CONNECTOR_PARTS = {k for k in HEIGHTS if k.startswith(("JST", "J4", "J11", "J13"))}
LOCAL_PARTS = {"J13 B2P-VH mated (JST eVH.pdf p.1 mounting height 16.5)": "J13"}


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
    path_ref = {f.GetFieldText("SourceInstance"): r_ for r_, f in fps.items()}
    INTERLOCK = sorted(r_ for r_, f in fps.items() if f.GetFieldText("SourceInstance").startswith("interlock."))
    LATCH_ICS = [r_ for r_ in INTERLOCK if r_.startswith("U")]
    GATE = [path_ref[p_] for p_ in GATE_PATHS]
    INTERLOCK += GATE
    RB = path_ref["u_rb"]
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
    j7 = wbox(layer_bbox(fps["J7"], pcbnew.F_Fab))
    j7_err = max(abs(a - s_) for a, s_ in zip(j7, world.J7_BODY))
    put("connectors", ok and j3_along and j7_err <= TOL, tolerance_mm=TOL, rows=rows, j3_body_along_rear_edge=j3_along,
        j7_body_world=[round(v, 3) for v in j7], j7_spec=list(world.J7_BODY), j7_max_edge_error_mm=round(j7_err, 3))

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

    # ---- WROOM-1U (R33): body in its box, U.FL end at the rear, U.FL clear of other parts
    u4 = fps["U4"]
    fb = wbox(layer_bbox(u4, pcbnew.F_Fab))
    e = max(abs(a_ - s_) for a_, s_ in zip(fb, world.WROOM))
    inside = fb[0] >= world.WROOM[0] - 0.06 and fb[1] >= world.WROOM[1] - 0.06 and fb[2] <= world.WROOM[2] + 0.06 \
        and fb[3] <= world.WROOM[3] + 0.06      # F.Fab outline line width 0.1 widens the bbox 0.05
    ang = math.radians(u4.GetOrientationDegrees())
    fx, fy = world.UFL_FP
    ukx = mm(u4.GetPosition().x) + fx * math.cos(ang) + fy * math.sin(ang)
    uky = mm(u4.GetPosition().y) - fx * math.sin(ang) + fy * math.cos(ang)
    ufl = world.to_w(ukx, uky)
    ufl_rear = ufl[1] > (fb[1] + fb[3]) / 2
    c = pcbnew.VECTOR2I(pcbnew.FromMM(ukx), pcbnew.FromMM(uky))
    near = []
    for ref, f in fps.items():
        if ref == "U4":
            continue
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() and cy.Collide(c, pcbnew.FromMM(world.UFL_CLEAR_R)):
            near.append(ref)
    ufl_delta = [round(ufl[0] - world.UFL_SPEC[0], 2), round(ufl[1] - world.UFL_SPEC[1], 2)]
    put("wroom", e <= TOL and inside and ufl_rear and not near,
        part=u4.GetFieldText("MPN"), body_world=[round(v, 3) for v in fb], spec=list(world.WROOM),
        max_edge_error_mm=round(e, 3), body_inside_box=inside,
        ufl_world=[round(v, 2) for v in ufl], ufl_end="rear" if ufl_rear else "front",
        parts_within_ufl_clear_radius=near, ufl_clear_radius_mm=world.UFL_CLEAR_R,
        enclosure_conflicts=[{"item": "U.FL position", "r33_spec": list(world.UFL_SPEC), "drawing_based": [round(v, 2) for v in ufl],
                              "delta_mm": ufl_delta,
                              "note": "Espressif WROOM-1/-1U DS v1.8 Figure 10-2: the U.FL is 3.0 mm from the module's right "
                                      "edge and 2.46 mm from its antenna-end edge, not on the centreline; with the body "
                                      "on the R33 box the receptacle is at the drawing-based point. Enclosure to move the "
                                      "coax entry"}] if abs(ufl_delta[0]) > TOL or abs(ufl_delta[1]) > TOL else [])

    # ---- height
    allowance = world.Z_LIMIT - world.BOARD_BOTTOM_Z - world.THICKNESS
    rows = {k: {"height_mm": v, "limit_mm": allowance if k in CONNECTOR_PARTS else 6.4} for k, v in HEIGHTS.items()}
    # enclosure-granted local allowances: the part's body must lie inside the granted square
    local_ok = True
    for k, ref in LOCAL_PARTS.items():
        lim = next(l for l in world.LOCAL_Z if l[0] == ref)
        (lx, ly), half, zmax, src = lim[1], lim[2], lim[3], lim[4]
        fb = wbox(layer_bbox(fps[ref], pcbnew.F_Fab))
        inside = fb[0] >= lx - half and fb[2] <= lx + half and fb[1] >= ly - half and fb[3] <= ly + half
        local_ok &= inside
        rows[k] = {"height_mm": HEIGHTS[k], "limit_mm": round(zmax - world.BOARD_BOTTOM_Z - world.THICKNESS, 2),
                   "local_allowance": src, "body_world": [round(v, 3) for v in fb], "body_inside_allowance": inside}
    put("height", local_ok and all(v["height_mm"] <= v["limit_mm"] for v in rows.values()), allowance_mm=round(allowance, 2),
        parts=rows, not_checked=["J4 plug overhang beyond the board edge (R31: to X-50); the 43045-1600 sales drawing "
                                 "itself was not readable from this network, the mated height is the 43045 series figure",
                                 "cable bends above the mated XH housings (harness); J13's 18 AWG bend is inside R41's local allowance", "the TC2050 cable while a bring-up probe is held on J11"])

    # ---- decoupling
    supplies = {"v3v3", "v15_selv", "V15_BLW", "RTD_AVDD", "V5_UI", "v5_drop", "V_BLOWER"}
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

    # ---- C37 (sensor-r3 CR-1): J3 protection distances, reported (the CR's 3 mm cannot be met: the XH
    # body courtyard reaches 3.44 mm in front of the pin row). Pad centre to pad centre, and pad-edge gap.
    j3 = fps.get("J3")      # C53: by designator; C51's J9 is also a B4B-XH, so the MPN no longer identifies J3
    prot = []
    if j3 is not None:
        for jp in j3.Pads():
            n = jp.GetNetname()
            for f in fps.values():
                if f is j3 or not (f.GetReference().startswith(("C", "D"))):
                    continue
                pads = {q.GetNetname(): q for q in f.Pads()}
                if n in pads and "selv_gnd" in pads:
                    q = pads[n]
                    d = math.hypot(mm(q.GetPosition().x - jp.GetPosition().x), mm(q.GetPosition().y - jp.GetPosition().y))
                    bj, bq = jp.GetBoundingBox(), q.GetBoundingBox()
                    gx = max(0, mm(max(bj.GetLeft(), bq.GetLeft()) - min(bj.GetRight(), bq.GetRight())))
                    gy = max(0, mm(max(bj.GetTop(), bq.GetTop()) - min(bj.GetBottom(), bq.GetBottom())))
                    prot.append({"j3_pin": jp.GetNumber(), "net": n, "part": f.GetReference(), "mpn": f.GetFieldText("MPN"),
                                 "centre_mm": round(d, 2), "edge_gap_mm": round(math.hypot(gx, gy), 2)})
    four = sorted({r["j3_pin"] for r in prot if r["part"].startswith("D")}) == ["1", "2", "3", "4"] and \
        sorted({r["j3_pin"] for r in prot if r["part"].startswith("C")}) == ["1", "2", "3", "4"]
    put("rtd_j3_protection", four, rule="sensor-r3 CR-1 asks <= 3 mm; reported, set by the XH body (DECISIONS C37)",
        rows=sorted(prot, key=lambda r: (r["j3_pin"], r["part"])))

    # ---- C51 / C53: J9 food probe. Layout rule (DECISIONS C51): each line's 100 nF sits between its J9 pin and its
    # BAV199, so the capacitor takes the ESD impulse ahead of the clamp (BAV199 has no IEC 61000-4-2 rating). Gate:
    # all four lines have both parts, and the capacitor's line pad is nearer the pin than the clamp's line pad.
    j9 = fps.get("J9")
    j9rows = []
    if j9 is not None:
        for jp in j9.Pads():
            n = jp.GetNetname()
            row = {"j9_pin": jp.GetNumber(), "net": n}
            for f in fps.values():
                if f is j9 or not f.GetReference().startswith(("C", "D")):
                    continue
                pads = {q.GetNetname(): q for q in f.Pads()}
                if n in pads and "selv_gnd" in pads:
                    q = pads[n]
                    d = math.hypot(mm(q.GetPosition().x - jp.GetPosition().x), mm(q.GetPosition().y - jp.GetPosition().y))
                    kind = "clamp" if f.GetFieldText("MPN").startswith("BAV199") else "cap" if f.GetReference()[0] == "C" else None
                    if kind and (kind + "_mm" not in row or d < row[kind + "_mm"]):
                        row[kind], row[kind + "_mm"] = f.GetReference(), round(d, 2)
            row["cap_first"] = "cap_mm" in row and "clamp_mm" in row and row["cap_mm"] < row["clamp_mm"]
            j9rows.append(row)
    put("rtd_j9_protection", len(j9rows) == 4 and all(r["cap_first"] for r in j9rows),
        rule="each J9 line: 100 nF nearer the pin than its BAV199 (DECISIONS C51 layout rule)", rows=j9rows)

    # ---- interlock regions: no MCU-net track through them. Two regions: the latch block
    # (U20-U25 and their pull-ups/bypasses) and the PERMIT gate at J4.9 (U37 with its parts).
    mcu_nets = {p.GetNetname() for p in fps["U4"].Pads()} - {"selv_gnd", "v3v3", ""}
    # MCU nets that end in a region by design (requests into the interlock: IL_RESET_N, IL_WDI,
    # RUN_EN; the read-back outputs of U9) are allowed in; any other MCU net crossing fails
    ends_inside = {p.GetNetname() for ref in INTERLOCK + [RB] for p in fps[ref].Pads()}
    regions = {}
    for name, refs in (("latch block", LATCH_ICS), ("PERMIT gate", GATE)):
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

    # ---- high-current paths (stage 16). V_BLOWER routed >= 0.8 mm (L3); pin stubs <= 1.0 mm long are
    # listed, not failed. V15_BLW (2.72 A, PLAN-16 sec. 3) must carry its current in F.Cu pours: J13.1, the
    # bulk + pad, every input-cap V15_BLW pad and U2's VIN pour must lie in one connected filled V15_BLW
    # region; its routed tracks (EN / BLW_PG divider branches, mA) are reported only.
    need = {"V_BLOWER": 0.8}
    pw, pw_ok = {}, True
    for n, w_req in need.items():
        ts = [t for t in b.GetTracks() if t.GetNetname() == n and t.Type() == pcbnew.PCB_TRACE_T]
        long_ = [t for t in ts if mm(t.GetLength()) > 1.0]
        narrow = [round(mm(t.GetWidth()), 3) for t in long_ if mm(t.GetWidth()) < w_req - 1e-6]
        vias = [t for t in b.GetTracks() if t.GetNetname() == n and t.Type() == pcbnew.PCB_VIA_T]
        pw[n] = {"required_mm": w_req, "min_width_mm": round(min((mm(t.GetWidth()) for t in long_), default=0), 3),
                 "narrow_segments": narrow, "stubs": len(ts) - len(long_), "vias": len(vias),
                 "length_mm": round(sum(mm(t.GetLength()) for t in ts), 1)}
        pw_ok &= not narrow
    filler = pcbnew.ZONE_FILLER(b)
    filler.Fill(b.Zones())
    feed = pcbnew.SHAPE_POLY_SET()
    for z in b.Zones():
        if z.GetNetname() == "V15_BLW" and z.GetLayer() == pcbnew.F_Cu:
            feed.BooleanAdd(z.GetFilledPolysList(pcbnew.F_Cu))
    feed.Simplify()
    must = []
    for f in b.GetFootprints():
        src = f.GetFieldText("SourceInstance")
        for p in f.Pads():
            if p.GetNetname() == "V15_BLW" and (f.GetReference() == "J13" or src in
                                                ("c_blw_bulk", "c_in12a", "c_in12b", "c_in12c")):
                must.append((f.GetReference(), p.GetNumber(), p))
    def region_of(pad):
        """Index of the filled V15_BLW region that overlaps the pad's copper (a thermal pad's spokes count)."""
        pp = pad.GetEffectivePolygon(pcbnew.F_Cu, pcbnew.ERROR_INSIDE)
        for i in range(feed.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET()
            one.AddOutline(feed.Outline(i))
            inter = pcbnew.SHAPE_POLY_SET(pp)
            inter.BooleanIntersection(one)
            if inter.Area() > 0:
                return i
        return None
    hits = {f"{r}.{n}": region_of(pad) for r, n, pad in must}
    one = len(must) >= 5 and None not in hits.values() and len(set(hits.values())) == 1
    blw_tracks = [t for t in b.GetTracks() if t.GetNetname() == "V15_BLW" and t.Type() == pcbnew.PCB_TRACE_T]
    pw["V15_BLW"] = {"pour_outline_per_pad": hits, "one_pour_region": one, "pour_regions": feed.OutlineCount(),
                     "routed_branch_tracks": len(blw_tracks),
                     "routed_branch_min_width_mm": round(min((mm(t.GetWidth()) for t in blw_tracks), default=0), 3)}
    put("power_widths", pw_ok and one, nets=pw)

    # ---- analog partition: courtyard-to-courtyard separations (ENCLOSURE-HANDOFF placement notes)
    def crt(ref):
        return layer_bbox(fps[ref], pcbnew.F_CrtYd)

    def gap(a, b):
        ra, rb = crt(a), crt(b)
        dx = max(rb[0] - ra[2], ra[0] - rb[2], 0)
        dy = max(rb[1] - ra[3], ra[1] - rb[3], 0)
        return math.hypot(dx, dy)
    rtd_analog = [r for r in fps if fps[r].GetFieldText("SourceInstance").startswith("rtd_pan.")
                  and not r.startswith("J")] + [path_ref[p_] for p_ in ("u_runaway", "r_runaway_top", "r_runaway_bot",
                                                                         "c_runaway_th")]
    food = [r for r in fps if fps[r].GetFieldText("SourceInstance").startswith("rtd_food.") and not r.startswith("J")]
    thermal = [r for r in fps if fps[r].GetFieldText("SourceInstance").startswith("thermal.") and not r.startswith("J")]
    analog_j4 = [path_ref[p_] for p_ in ("u_rx", "u_buf1", "u_buf2", "u_ref", "u_rms", "u_adc", "r_rx_n", "r_rx_p",
                                         "r_rx_f", "r_rx_b", "r_bias_top", "r_bias_bot", "r_ct_mon_def", "r_rms_bias",
                                         "r_rms_gf", "r_rms_gg", "c_rms_in", "c_rms_core", "c_rms_avg", "c_rms_ignd",
                                         "c_rms_lpf")]
    sw = {"L2/U2 (12 V fan buck)": [path_ref["l_12"], path_ref["u_12"]],     # now the blower buck (C28)
          "L1/U1 (3.3 V buck)": [path_ref["l_3v3"], path_ref["u_3v3"]],
          "L3/U51 (face-fan buck)": [path_ref["bay_fan.l"], path_ref["bay_fan.u_buck"]]}     # C51
    sep = {}
    for name, parts in sw.items():
        for grp_name, grp in (("RTD front end", rtd_analog), ("food RTD", food), ("thermal-sense", thermal),
                              ("J4 analog", analog_j4)):
            d, pair = min((gap(a, b), (a, b)) for a in parts for b in grp)
            sep[f"{name} -> {grp_name}"] = {"mm": round(d, 1), "nearest": pair}
    gated = [f"{s} -> {g}" for s in ("L2/U2 (12 V fan buck)", "L3/U51 (face-fan buck)") for g in ("RTD front end", "food RTD")]
    put("partition", all(sep[k]["mm"] >= 10.0 for k in gated), rule="the blower buck (L2/U2) and the face-fan buck (L3/U51, "
        "C53) >= 10 mm from both RTD channels (ENCLOSURE-HANDOFF item 6); others reported", gated=gated,
        separations_mm=sep)

    # ---- stranded vias (agentic-PCB tip #13; layout/via_hygiene.py): a via with copper of its net on fewer than two layers
    import via_hygiene
    stranded = [info for _, info in via_hygiene.stranded(b)]
    put("stranded_vias", not stranded, count=len(stranded), stranded=stranded[:20])

    status = "PASS" if all(v["ok"] for v in res.values()) else "FAIL"
    out = {"board": str(Path(path).name), "revision": world.REVISION,
           "source": "output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md (R31 section; R30 mounting/height) "
                     "+ output/temper-manufacturing-r33/design/r33/DECISIONS.md section 3 (R33 delta; R35 unchanged)",
           "transform": f"kx = X + {world.OX:g}, ky = {world.OY:g} - Y (layout/world.py)", "checks": res,
           "summary": {k: v["ok"] for k, v in res.items()}, "status": status}
    (UNIT / "evidence").mkdir(exist_ok=True)
    (UNIT / "evidence/layout-check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]), status)
    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
