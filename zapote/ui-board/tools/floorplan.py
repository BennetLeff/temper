#!/usr/bin/env python3
"""Mechanical floorplan of the UI board against the enclosure (R41), as evidence/floorplan.svg.

Coordinates are the enclosure's front-local frame (u right, v up, looking at the fascia
from the front; board front face at w = -14, 1.6 mm FR-4). The numbers below are copied
from the enclosure source output/temper-manufacturing-r41/src/r33_world.py (UI board, with
the R39 M3 change) and src/controls_r5.py (OLED, lens, button and encoder positions). When
that source is present, `read_enclosure_source()` re-reads it and `checks()` fails if any
number here differs, so the drawing cannot drift from the enclosure silently.

Usage: python3 tools/floorplan.py [--svg PATH] [--json PATH]
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
# The enclosure is outside the worktree; the main checkout holds it (read-only input).
ENCLOSURE_CANDIDATES = [
    Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r41"),
    UNIT.parents[2] / "output" / "temper-manufacturing-r41",
]

# ----------------------------------------------------------------- enclosure numbers
BOARD_U, BOARD_V, BOARD_FRONT_W, BOARD_T = (-106.0, 64.0), (15.0, 96.0), -14.0, 1.6
STUDS = [(-99.0, 38.0), (-99.0, 82.0), (29.0, 38.0), (29.0, 82.0)]     # Ø7.0 clearance (r 3.5)
STUD_R = 3.5
BOSSES = [(-104.0, 60.0), (34.0, 60.0), (-75.0, 92.0), (5.0, 92.0)]    # Ø3.4 M3 clearance (R39)
BOSS_R = 1.7
CUTOUT = (-94.0, -72.0, 42.0, 54.0)                                    # u0, u1, v0, v1
J_UI = (46.0, 49.5)                                                    # J7 centre, rear face
J_ENC = (55.0, 58.0)                                                   # TE 7-215079-6 centre, rear face
XH12_LEN, XH_DEPTH, XH_MATED_H = 32.4, 5.75, 10.5
J_ENC_SIZE = (10.0, 8.4)
STACKER = (-61.0, -9.0, 81.0, 86.0)                                    # u0, u1, v0, v1 (front face)
BUTTONS = {"back": (-75.0, 26.0), "select_start": (-35.0, 26.0), "stop": (5.0, 26.0)}
BUTTON_BEZEL_R, BUTTON_BODY_R, BUTTON_PIN_DU = 8.75, 6.0, 2.54         # pins at u +/- 2.54 (5.08 mm pitch)
BUTTON_CUTOUT_D = 13.6
OLED_CENTER, OLED_SIZE = (-35.0, 64.0), (89.2, 44.0)
OLED_HOLES = [(-35 + dx, 64 + dy) for dx in (-41.6, 41.6) for dy in (-19, 19)]
LENS_SIZE = (108.8, 38.8)
ENCODER = (110.0, 53.0)
ENCODER_CUTOUT_D = 9.65
ENCODER_CABLE_MM = 3.0 * 25.4              # Grayhill ...-030C: 3.00 in cable
ENCODER_DEVELOPED_MM = 50.0                # enclosure R41 harness_encoder_pigtail_to_UI_board developed length
FRONT_GAP_W = 3.0                          # UI-board front face (w -14) to OLED PCB rear (w -11)
OLED_SOCKET_H_MM = 8.5                     # PM254V-11-20-H85 as shipped on the BOM
EDGE_MIN = 3.0

# Advisory placement zones for the remaining parts (layout decides; see DECISIONS U17).
ZONES = [
    ("J7 entry: U4 U5 R20 C1 C2 C11", 27.0, 64.0, 37.0, 45.0, "rear"),
    ("encoder: U3 U7 R8-R16 C5 C8 C9 C13-C15 FB1", 36.0, 63.5, 63.0, 78.0, "rear"),
    ("logic: U1 C3 R17 R18 Q1 R21 R22", -24.0, 24.0, 44.0, 52.0, "rear"),
    ("U6 R1-R7 at the button pins", -85.0, 15.0, 17.0, 22.0, "rear"),
    ("BZ1 D1 C10 (sound port)", -104.0, -90.0, 17.0, 29.0, "front"),
    ("U2 TMP122 under OLED", -42.0, -28.0, 52.0, 58.0, "front"),
]

# Original numbers from the enclosure source that must still match (re-read when present).
EXPECTED_SOURCE = {
    "BOARD_U": BOARD_U, "BOARD_V": BOARD_V, "BOARD_FRONT": BOARD_FRONT_W, "BOARD_T": BOARD_T,
    "STUDS": STUDS, "BOSSES": BOSSES,
}


def enclosure_dir() -> Path | None:
    for c in ENCLOSURE_CANDIDATES:
        if (c / "src" / "r33_world.py").is_file():
            return c
    return None


def read_enclosure_source() -> dict | None:
    d = enclosure_dir()
    if d is None:
        return None
    text = (d / "src" / "r33_world.py").read_text()
    out: dict = {"dir": str(d)}

    def lit(name: str):
        m = re.search(rf"^{name}\s*=\s*(.+)$", text, re.M)
        return ast.literal_eval(m.group(1).split("#")[0].strip()) if m else None

    m = re.search(r"^BOARD_U, BOARD_V, BOARD_FRONT, BOARD_T = (.+?)\s*$", text, re.M)
    bu, bv, bf, bt = ast.literal_eval("(" + m.group(1) + ")")
    out.update(BOARD_U=tuple(bu), BOARD_V=tuple(bv), BOARD_FRONT=bf, BOARD_T=bt)
    out["STUDS"] = [tuple(float(x) for x in p) for p in lit("STUDS")]
    out["BOSSES"] = [tuple(float(x) for x in p) for p in lit("BOSSES")]
    m = re.search(r"^J_UI_FASCIA, J_ENC, J_UI_CTRL = (.+?)\s*(#.*)?$", text, re.M)
    j = ast.literal_eval("(" + m.group(1) + ")")
    out["J_UI"], out["J_ENC"] = tuple(j[0]), tuple(j[1])
    m = re.search(r"^XH12_LEN, XH_DEPTH, XH_MATED_H = (.+?)\s*$", text, re.M)
    out["XH"] = tuple(ast.literal_eval("(" + m.group(1) + ")"))
    m = re.search(r"box_uvw\((-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), BOARD_FRONT, (-?[\d.]+)\)", text)
    out["STACKER"] = (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
    out["STACKER_TOP_W"] = float(m.group(5))
    m = re.search(r"board = board - box_uvw\((-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), rear - 1", text)
    out["CUTOUT"] = tuple(float(m.group(i)) for i in range(1, 5))
    m = re.search(r'for name, ub in \(\(("back", -?\d+)\), \(("select_start", -?\d+)\), \(("stop", -?\d+)\)\)', text.replace(" (", "(").replace("((", "(("))
    buttons = {}
    for nm, ub in re.findall(r'\("(\w+)", (-?\d+)\)', text.split("def apem_parts")[1].split("return out")[0]):
        buttons[nm] = float(ub)
    out["BUTTON_U"] = buttons
    m = re.search(r"cyl_uvw\(8\.75, ub, (\d+), 0\.0, 5\.0\)", text)
    out["BUTTON_V"] = float(m.group(1))
    ctrl = (d / "src" / "controls_r5.py").read_text()
    m = re.search(r"OLED_HOLES = tuple\(\(-35 \+ dx, 64 \+ dy\) for dx in \((.+?)\) for dy in \((.+?)\)\)", ctrl)
    out["OLED_HOLE_DXDY"] = (ast.literal_eval("(" + m.group(1) + ")"), ast.literal_eval("(" + m.group(2) + ")"))
    m = re.search(r'"encoder": \{"center_uv": \[(\d+), (\d+)\], "diameter_mm": ([\d.]+)', ctrl)
    out["ENCODER"] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = re.search(r'"lens": \{"center_uv": \[(-?\d+), (-?\d+)\], "size_mm": \[([\d.]+), ([\d.]+)\]', ctrl)
    out["LENS"] = tuple(float(m.group(i)) for i in range(1, 5))
    m = re.search(r"oled = _box\(([\d.]+), ([\d.]+), 1, (-?\d+), (\d+), (-?[\d.]+)\)", ctrl)
    out["OLED"] = tuple(float(m.group(i)) for i in range(1, 6))
    return out


def circle_box_clear(cx, cy, r, box):
    u0, u1, v0, v1 = box
    dx = max(u0 - cx, 0.0, cx - u1)
    dy = max(v0 - cy, 0.0, cy - v1)
    return math.hypot(dx, dy) - r


def box_box_gap(a, b):
    du = max(a[0] - b[1], b[0] - a[1], 0.0)
    dv = max(a[2] - b[3], b[2] - a[3], 0.0)
    return math.hypot(du, dv)


def j7_box():
    return (J_UI[0] - XH12_LEN / 2, J_UI[0] + XH12_LEN / 2, J_UI[1] - XH_DEPTH / 2, J_UI[1] + XH_DEPTH / 2)


def jenc_box():
    return (J_ENC[0] - J_ENC_SIZE[0] / 2, J_ENC[0] + J_ENC_SIZE[0] / 2,
            J_ENC[1] - J_ENC_SIZE[1] / 2, J_ENC[1] + J_ENC_SIZE[1] / 2)


def stacker_pins():
    cu, cv = (STACKER[0] + STACKER[1]) / 2, (STACKER[2] + STACKER[3]) / 2
    return [(cu + (i - 9.5) * 2.54, cv) for i in range(20)]


def checks() -> tuple[dict, dict]:
    """Returns (checks, data). Each check is a bool; data carries the supporting numbers."""
    board = (BOARD_U[0], BOARD_U[1], BOARD_V[0], BOARD_V[1])
    ck: dict = {}
    data: dict = {}
    src = read_enclosure_source()
    data["enclosure_source"] = None if src is None else src["dir"]
    if src is None:
        ck["enclosure_source_present"] = False
    else:
        ck["enclosure_source_present"] = True
        ck["board_outline_matches_source"] = (src["BOARD_U"], src["BOARD_V"], src["BOARD_FRONT"], src["BOARD_T"]) == \
            (BOARD_U, BOARD_V, BOARD_FRONT_W, BOARD_T)
        ck["holes_match_source"] = src["STUDS"] == STUDS and src["BOSSES"] == BOSSES and src["CUTOUT"] == CUTOUT
        ck["connectors_match_source"] = src["J_UI"] == J_UI and src["J_ENC"] == J_ENC and src["XH"] == (XH12_LEN, XH_DEPTH, XH_MATED_H)
        ck["stacker_matches_source"] = src["STACKER"] == STACKER
        ck["buttons_match_source"] = src["BUTTON_U"] == {k: v[0] for k, v in BUTTONS.items()} and src["BUTTON_V"] == 26.0
        ck["oled_lens_encoder_match_source"] = (
            src["ENCODER"] == (ENCODER[0], ENCODER[1], ENCODER_CUTOUT_D) and src["LENS"] == (*OLED_CENTER, *LENS_SIZE)
            and src["OLED"] == (*OLED_SIZE, *OLED_CENTER, -10.5)
            and sorted((-35 + dx, 64 + dy) for dx in src["OLED_HOLE_DXDY"][0] for dy in src["OLED_HOLE_DXDY"][1]) == sorted(OLED_HOLES))
        data["stacker_top_w_source"] = src["STACKER_TOP_W"]
        # the catalog.json of the same release carries the part bounding box (world frame; X is u)
        cat = enclosure_dir() / "catalog.json"
        if cat.is_file():
            cj = json.loads(cat.read_text())
            hit = []

            def walk(o):
                if isinstance(o, dict):
                    if o.get("name") == "controls_ui_board" and "bbox" in o:
                        hit.append(o["bbox"])
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(cj)
            if hit:
                bb = hit[0]
                data["catalog_bbox_x"] = [bb[0], bb[3]]
                ck["catalog_bbox_x_equals_board_u"] = abs(bb[0] - BOARD_U[0]) < 1e-6 and abs(bb[3] - BOARD_U[1]) < 1e-6
    # holes inside the board with edge distance
    holes = [("stud", p, STUD_R) for p in STUDS] + [("boss", p, BOSS_R) for p in BOSSES]
    edge = {}
    for kind, (u, v), r in holes:
        e = min(u - board[0], board[1] - u, v - board[2], board[3] - v) - r
        edge[f"{kind}@{u:g},{v:g}"] = round(e, 2)
    data["hole_edge_distance_mm"] = edge
    ck["holes_inside_outline"] = min(edge.values()) > 0
    # Findings about the enclosure's own geometry (recorded, not gated: this unit cannot move them).
    findings = []
    for k, e in edge.items():
        if e < 1.0:
            findings.append({"id": "E1", "item": f"{k}: FR-4 wall between the hole and the board edge is {e} mm (< 1 mm); "
                             "the carrier boss (Ø6) overhangs the edge", "ask": "move the boss >= 3 mm inboard or notch the outline"})
    data["enclosure_findings"] = findings
    # hole to hole and cutout
    gaps = []
    for i, (k1, p1, r1) in enumerate(holes):
        for k2, p2, r2 in holes[i + 1:]:
            gaps.append(math.dist(p1, p2) - r1 - r2)
    ck["holes_do_not_overlap"] = min(gaps) > 1.0
    ck["cutout_inside_outline"] = CUTOUT[0] > board[0] and CUTOUT[1] < board[1] and CUTOUT[2] > board[2] and CUTOUT[3] < board[3]
    # buttons
    bt = {}
    for nm, (u, v) in BUTTONS.items():
        edge_b = min(u - board[0], board[1] - u, v - board[2], board[3] - v) - BUTTON_BEZEL_R
        hole_gap = min(math.dist((u, v), p) - BUTTON_BEZEL_R - r for _, p, r in holes)
        bt[nm] = {"edge_mm": round(edge_b, 2), "nearest_hole_gap_mm": round(hole_gap, 2)}
    data["buttons"] = bt
    ck["buttons_inside_outline"] = all(b["edge_mm"] > 0 for b in bt.values())
    ck["buttons_clear_of_holes_ge_3mm"] = all(b["nearest_hole_gap_mm"] >= EDGE_MIN for b in bt.values())
    us = sorted(u for u, _ in BUTTONS.values())
    ck["button_pitch_ge_diameter_plus_3mm"] = min(b - a for a, b in zip(us, us[1:])) - 2 * BUTTON_BEZEL_R >= EDGE_MIN
    # connectors on the rear face
    jb, eb = j7_box(), jenc_box()
    inside = lambda b: b[0] > board[0] and b[1] < board[1] and b[2] > board[2] and b[3] < board[3]
    ck["j7_j2_inside_outline"] = inside(jb) and inside(eb)
    data["j7_box"], data["j2_box"] = [round(x, 2) for x in jb], [round(x, 2) for x in eb]
    data["j7_j2_gap_mm"] = round(box_box_gap(jb, eb), 2)
    ck["j7_j2_gap_ge_1mm"] = box_box_gap(jb, eb) >= 1.0
    cl = {}
    for nm, b in (("J7", jb), ("J2", eb)):
        cl[nm] = round(min(circle_box_clear(p[0], p[1], r, b) for _, p, r in holes), 2)
    data["connector_to_hole_clear_mm"] = cl
    ck["connectors_clear_of_holes_ge_3mm"] = min(cl.values()) >= EDGE_MIN
    ck["j7_clear_of_cutout"] = box_box_gap(jb, CUTOUT) > 5.0
    # OLED stacker
    pins = stacker_pins()
    ck["stacker_inside_outline"] = all(board[0] < u < board[1] and board[2] < v < board[3] for u, v in pins)
    ck["stacker_inside_oled_shadow"] = all(abs(u - OLED_CENTER[0]) < OLED_SIZE[0] / 2 and abs(v - OLED_CENTER[1]) < OLED_SIZE[1] / 2 for u, v in pins)
    ck["stacker_clear_of_holes_ge_3mm"] = min(circle_box_clear(p[0], p[1], r, STACKER) for _, p, r in holes) >= EDGE_MIN
    # OLED M2 holes must not coincide with a UI-board hole
    ck["oled_m2_clear_of_ui_holes"] = min(math.dist(a, p) - r for a in OLED_HOLES for _, p, r in holes) > 3.0
    # encoder cable
    reach = ENCODER[0] - (J_ENC[0] + J_ENC_SIZE[0] / 2)
    data["encoder_gap_mm"] = round(reach, 2)
    data["encoder_cable_mm"] = round(ENCODER_CABLE_MM, 1)
    ck["encoder_cable_reaches_with_strain_relief"] = ENCODER_CABLE_MM >= ENCODER_DEVELOPED_MM + 10.0
    ck["encoder_outside_board"] = ENCODER[0] > board[1]
    # open items (data, not checks)
    data["stacker_gap_mm"] = FRONT_GAP_W
    data["oled_socket_height_mm"] = OLED_SOCKET_H_MM
    data["stacker_conflict_mm"] = round(OLED_SOCKET_H_MM - FRONT_GAP_W, 2)
    data["enclosure_findings"].append({"id": "E2", "item": f"the OLED stacker is modelled {FRONT_GAP_W} mm high; a 1x20 2.54 mm "
        f"female socket on LCSC is {OLED_SOCKET_H_MM} mm ({OLED_SOCKET_H_MM - FRONT_GAP_W:g} mm too tall)",
        "ask": "open the UI-board to OLED gap to 8.5 mm (taller carrier bosses) or approve a soldered low-profile header"})
    data["enclosure_findings"].append({"id": "E3", "item": f"J7 and J2 envelopes are {data['j7_j2_gap_mm']} mm apart; the mated "
        "XHP-12 and Micro-MaTch plug housings are larger than the header bodies", "ask": "confirm plug clearance at layout"})
    data["enclosure_findings"].append({"id": "E4", "item": "no sound port is modelled in the fascia for the buzzer",
        "ask": "a Ø>=2 mm hole or gap in front of BZ1 (front face, u -104..-90, v 17..29), or an acoustic path"})
    return ck, data


# ------------------------------------------------------------------------------- SVG
def svg() -> str:
    s = 5.0                     # px per mm
    u_min, u_max, v_min, v_max = -112.0, 142.0, 8.0, 104.0
    W, H = (u_max - u_min) * s, (v_max - v_min) * s + 70
    X = lambda u: (u - u_min) * s
    Y = lambda v: (v_max - v) * s + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" '
         'font-family="Helvetica,Arial,sans-serif" font-size="10">',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<text x="8" y="16" font-size="13" font-weight="bold">Temper fascia UI board: floorplan against enclosure R41 '
         f'(front view, u right, v up, mm)</text>']
    # board
    o.append(f'<rect x="{X(BOARD_U[0]):.1f}" y="{Y(BOARD_V[1]):.1f}" width="{(BOARD_U[1]-BOARD_U[0])*s:.1f}" '
             f'height="{(BOARD_V[1]-BOARD_V[0])*s:.1f}" fill="#d9ead3" stroke="#274e13" stroke-width="2"/>')
    # lens window and OLED
    lw, lh = LENS_SIZE
    o.append(f'<rect x="{X(OLED_CENTER[0]-lw/2):.1f}" y="{Y(OLED_CENTER[1]+lh/2):.1f}" width="{lw*s:.1f}" height="{lh*s:.1f}" '
             'rx="22" fill="none" stroke="#6aa0d8" stroke-width="1.5" stroke-dasharray="6 4"/>')
    ow, oh = OLED_SIZE
    o.append(f'<rect x="{X(OLED_CENTER[0]-ow/2):.1f}" y="{Y(OLED_CENTER[1]+oh/2):.1f}" width="{ow*s:.1f}" height="{oh*s:.1f}" '
             'fill="#bcd4f0" fill-opacity="0.55" stroke="#1f4e8c" stroke-width="1.5"/>')
    o.append(f'<text x="{X(OLED_CENTER[0]):.1f}" y="{Y(OLED_CENTER[1]):.1f}" text-anchor="middle" fill="#1f4e8c">'
             'NHD-3.12-25664UCW2 (89.2 x 44), lens 108.8 x 38.8</text>')
    for (u, v) in OLED_HOLES:
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{1.25*s:.1f}" fill="#fff" stroke="#1f4e8c"/>')
    # zones
    for name, u0, u1, v0, v1, face in ZONES:
        col = "#b45f06" if face == "rear" else "#990000"
        o.append(f'<rect x="{X(u0):.1f}" y="{Y(v1):.1f}" width="{(u1-u0)*s:.1f}" height="{(v1-v0)*s:.1f}" fill="{col}" '
                 f'fill-opacity="0.10" stroke="{col}" stroke-dasharray="3 3"/>')
        o.append(f'<text x="{X(u0)+3:.1f}" y="{Y(v1)+11:.1f}" fill="{col}" font-size="9">{name} ({face})</text>')
    # stacker
    for i, (u, v) in enumerate(stacker_pins(), 1):
        o.append(f'<rect x="{X(u)-3:.1f}" y="{Y(v)-3:.1f}" width="6" height="6" fill="#333"/>')
    o.append(f'<text x="{X(-35):.1f}" y="{Y(88.3):.1f}" text-anchor="middle">J3 OLED socket 1x20 (front face), pin 1 left [assumed]</text>')
    # holes
    for u, v in STUDS:
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{STUD_R*s:.1f}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        o.append(f'<text x="{X(u)+20:.1f}" y="{Y(v)+3:.1f}" font-size="9">stud Ø7 ({u:g},{v:g})</text>')
    for u, v in BOSSES:
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{BOSS_R*s:.1f}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{3.0*s:.1f}" fill="none" stroke="#000" stroke-dasharray="2 2"/>')
        o.append(f'<text x="{X(u)+17:.1f}" y="{Y(v)+3:.1f}" font-size="9">M3 Ø3.4 ({u:g},{v:g})</text>')
    u0, u1, v0, v1 = CUTOUT
    o.append(f'<rect x="{X(u0):.1f}" y="{Y(v1):.1f}" width="{(u1-u0)*s:.1f}" height="{(v1-v0)*s:.1f}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    o.append(f'<text x="{X((u0+u1)/2):.1f}" y="{Y((v0+v1)/2)+3:.1f}" text-anchor="middle" font-size="9">cut-out 22x12</text>')
    # buttons
    for nm, (u, v) in BUTTONS.items():
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{BUTTON_BEZEL_R*s:.1f}" fill="#f4cccc" stroke="#990000" stroke-width="1.5"/>')
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{BUTTON_CUTOUT_D/2*s:.1f}" fill="none" stroke="#990000" stroke-dasharray="3 2"/>')
        for du in (-BUTTON_PIN_DU, BUTTON_PIN_DU):
            o.append(f'<circle cx="{X(u+du):.1f}" cy="{Y(v):.1f}" r="{0.5*s:.1f}" fill="#000"/>')
        label = {"back": "SW3 BACK/RESET (GP2)", "select_start": "SW1 SELECT/START (GP0)", "stop": "SW2 STOP (GP1)"}[nm]
        o.append(f'<text x="{X(u):.1f}" y="{Y(v)+BUTTON_BEZEL_R*s+11:.1f}" text-anchor="middle">{label}</text>')
    # connectors (rear face)
    jb = j7_box()
    o.append(f'<rect x="{X(jb[0]):.1f}" y="{Y(jb[3]):.1f}" width="{(jb[1]-jb[0])*s:.1f}" height="{(jb[3]-jb[2])*s:.1f}" fill="#fff2cc" '
             'stroke="#7f6000" stroke-width="1.5" stroke-dasharray="4 2"/>')
    o.append(f'<text x="{X(J_UI[0]):.1f}" y="{Y(J_UI[1])+3:.1f}" text-anchor="middle" font-size="9">J7 JST XH 12-way (rear)</text>')
    eb = jenc_box()
    o.append(f'<rect x="{X(eb[0]):.1f}" y="{Y(eb[3]):.1f}" width="{(eb[1]-eb[0])*s:.1f}" height="{(eb[3]-eb[2])*s:.1f}" fill="#fff2cc" '
             'stroke="#7f6000" stroke-width="1.5" stroke-dasharray="4 2"/>')
    o.append(f'<text x="{X(J_ENC[0]):.1f}" y="{Y(J_ENC[1])+3:.1f}" text-anchor="middle" font-size="9">J2 (rear)</text>')
    # encoder off board
    o.append(f'<circle cx="{X(ENCODER[0]):.1f}" cy="{Y(ENCODER[1]):.1f}" r="{ENCODER_CUTOUT_D/2*s:.1f}" fill="#eee" stroke="#444" stroke-width="1.5"/>')
    o.append(f'<text x="{X(ENCODER[0]):.1f}" y="{Y(ENCODER[1])-30:.1f}" text-anchor="middle">Grayhill 62VG15 (110,53), off board</text>')
    o.append(f'<path d="M {X(ENCODER[0]-5):.1f} {Y(ENCODER[1]+5.6):.1f} Q {X(85):.1f} {Y(64):.1f} {X(J_ENC[0]+5.5):.1f} {Y(J_ENC[1]):.1f}" '
             'fill="none" stroke="#444" stroke-width="1.5" stroke-dasharray="5 3"/>')
    o.append(f'<text x="{X(84):.1f}" y="{Y(66):.1f}" text-anchor="middle">3 in lead, 50 mm developed</text>')
    # dimensions and legend
    o.append(f'<text x="{X(BOARD_U[0]):.1f}" y="{Y(BOARD_V[0])+14:.1f}">board u {BOARD_U[0]:g}..{BOARD_U[1]:g} (170 mm), '
             f'v {BOARD_V[0]:g}..{BOARD_V[1]:g} (81 mm), 1.6 mm, front face at w {BOARD_FRONT_W:g}</text>')
    ly = H - 34
    leg = [("#d9ead3", "board"), ("#bcd4f0", "OLED module"), ("#f4cccc", "IPR3PAD2 bezel Ø17.5, cut-out Ø13.6"),
           ("#fff2cc", "rear-face connector envelope"), ("#fce5cd", "advisory placement zone (rear brown, front red)")]
    x = 8
    for col, name in leg:
        o.append(f'<rect x="{x}" y="{ly}" width="12" height="10" fill="{col}" stroke="#555"/><text x="{x+16}" y="{ly+9}">{name}</text>')
        x += 16 + 6.2 * len(name) + 14
    o.append(f'<text x="8" y="{H-8}" font-size="9" fill="#555">Source: output/temper-manufacturing-r41/src/r33_world.py '
             '(UI board, R39 M3 holes) and controls_r5.py; regenerate with tools/floorplan.py. Parts placement zones are advisory.</text>')
    o.append("</svg>")
    return "\n".join(o)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", type=Path, default=UNIT / "evidence" / "floorplan.svg")
    ap.add_argument("--json", type=Path, default=UNIT / "evidence" / "floorplan.json")
    args = ap.parse_args()
    ck, data = checks()
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(svg() + "\n")
    args.json.write_text(json.dumps({"checks": ck, "data": data}, indent=2, sort_keys=True) + "\n")
    bad = [k for k, v in ck.items() if not v]
    print(f"floorplan: {sum(ck.values())}/{len(ck)} checks pass", "failed: " + ", ".join(bad) if bad else "")
    print(f"svg: {args.svg}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
