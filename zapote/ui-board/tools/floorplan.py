#!/usr/bin/env python3
"""Mechanical floorplan of the UI board (revision 2: owned controls) against the enclosure (R41 source), as evidence/floorplan.svg.

Coordinates are the enclosure's front-local frame (u right, v up, looking at the fascia
from the front; board front face at w = -14, 1.6 mm FR-4). The numbers below are copied
from the enclosure source output/temper-manufacturing-r41/src/r33_world.py (UI board, with
the R39 M3 change) and src/controls_r5.py (OLED, lens, button and encoder positions). When
that source is present, `read_enclosure_source()` re-reads it and `checks()` fails if any
number here differs, so the drawing cannot drift from the enclosure silently.

Revision 2 adds the sensor tab (a separate PCB at the knob axis, die plane w = -4.00), the steel/fastener keep-out
around the magnet, the three tact switches, the buzzer datum with its acoustic port and the sensor-tab connector J8.
Datums are in the enclosure's front-local (u, v, w) frame (w positive toward the outside, fascia rear at w = -3).

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
J_ENC = (55.0, 58.0)                                                   # old Micro-MaTch centre in the R41 source (read for matching only)
XH12_LEN, XH_DEPTH, XH_MATED_H = 32.4, 5.75, 10.5
J_ENC_SIZE = (10.0, 8.4)
STACKER = (-61.0, -9.0, 81.0, 86.0)                                    # u0, u1, v0, v1 (front face)
BUTTONS = {"back": (-75.0, 26.0), "select_start": (-35.0, 26.0), "stop": (5.0, 26.0)}
BUTTON_BEZEL_R, BUTTON_BODY_R, BUTTON_PIN_DU = 8.75, 6.0, 2.54         # pins at u +/- 2.54 (5.08 mm pitch)
BUTTON_CUTOUT_D = 13.6
OLED_CENTER, OLED_SIZE = (-35.0, 64.0), (89.2, 44.0)
OLED_HOLES = [(-35 + dx, 64 + dy) for dx in (-41.6, 41.6) for dy in (-19, 19)]
LENS_SIZE = (108.8, 38.8)
ENCODER = (110.0, 53.0)                    # the knob axis (R41 source calls it the encoder centre)
ENCODER_CUTOUT_D = 9.65                    # R41 source value, read for matching only
KNOB_AXIS = ENCODER
KNOB_ENVELOPE_R = 28.0                     # owner's FIELD-THERMAL.md: knob envelope radius 28, w 0..20
MAGNET_D, MAGNET_NEAR_FACE_W = 10.0, 1.0   # the owner's candidate: dia 10 x 5, nearest face at w = +1
FASCIA_REAR_W, FASCIA_FRONT_W = -3.0, 0.0
# ---- revision 2: sensor tab (a separate PCB behind the fascia), TMAG5170 datum (SBASAF4 p.16 Figure 7-2, p.4 package DGK0008A)
DIE_W = -4.0                               # owner's table: die at w = -4, face-to-die gap 5 mm
HALL_BELOW_PACKAGE_TOP = 0.32              # Hall plane depth below the package top surface
PACKAGE_TOP_ABOVE_PCB = 1.10               # DGK0008A: 1.1 mm max
HALL_ABOVE_PCB = PACKAGE_TOP_ABOVE_PCB - HALL_BELOW_PACKAGE_TOP    # 0.78
HALL_FROM_PIN1_4_SIDE, HALL_FROM_PIN1_END = 1.77, 1.54             # mm, from the 3.0 mm body's edges
BODY = 3.0
TAB_U, TAB_V = (78.0, 142.0), (37.0, 69.0)                        # 64 x 32 mm, centred on the axis in v and u
TAB_T = 1.6
TAB_FRONT_W = DIE_W - HALL_ABOVE_PCB                               # -4.78: package on the fascia-facing face
TAB_HOLES = [(83.0, 42.0), (83.0, 64.0), (138.0, 53.0)]            # M2.5 non-magnetic standoffs, clearance dia 2.7
TAB_HOLE_R, FASTENER_HEAD_R = 1.35, 2.5
STEEL_KEEPOUT_R = 25.0                                             # no steel / fasteners within this radius of the axis
COMPONENT_KEEPOUT_R = 12.0                                         # no components within this radius except U8 and C16
J9 = (82.0, 53.0)                                                  # SM10B-SRSS-TB(LF)(SN), long axis along v
SH10_SIZE = (4.25, 13.0)                                           # (u, v) body envelope as mounted [UNVERIFIED: JST drawing not fetched]
J8 = (56.0, 78.0)                                                  # same part on the main board, rear face
C16 = (106.0, 56.5)
TACT_BODY = 6.2
CAP_R = 7.0                                                        # owner's cap envelope radius (FIELD-THERMAL.md)
BUZZER = (-95.0, 24.0)
BUZZER_BODY = (9.6, 9.6)                                           # 9.6 x 9.6 x 5.0, front face, sound outlet up
BUZZER_PORT_D = 6.0                                                # membrane / port opening, centred on the datum (max inside the body)
FRONT_GAP_W = 3.0                          # UI-board front face (w -14) to OLED PCB rear (w -11)
OLED_SOCKET_H_MM = 8.5                     # PM254V-11-20-H85 as shipped on the BOM
EDGE_MIN = 3.0

# Advisory placement zones for the remaining parts (layout decides; see DECISIONS U17).
ZONES = [
    ("J7 entry: U4 U5 R20 C1 C2 C11", 27.0, 64.0, 37.0, 45.0, "rear"),
    ("gates + expander side: U9 U10 C17 C18 R24-R29 (rear)", 34.0, 62.0, 56.0, 70.0, "rear"),
    ("logic: U1 C3 R17 R18 Q1 R21 R22", -24.0, 24.0, 44.0, 52.0, "rear"),
    ("U6 R1-R7 at the button pins", -85.0, 15.0, 17.0, 22.0, "rear"),
    ("BZ1 D1 C10", -104.0, -86.0, 17.0, 31.0, "front"),
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


def sh_box(c):
    return (c[0] - SH10_SIZE[0] / 2, c[0] + SH10_SIZE[0] / 2, c[1] - SH10_SIZE[1] / 2, c[1] + SH10_SIZE[1] / 2)


def square(c, w, h=None):
    h = w if h is None else h
    return (c[0] - w / 2, c[0] + w / 2, c[1] - h / 2, c[1] + h / 2)


def box_inside(b, outer):
    return b[0] > outer[0] and b[1] < outer[1] and b[2] > outer[2] and b[3] < outer[3]


def box_edge_margin(b, outer):
    return min(b[0] - outer[0], outer[1] - b[1], b[2] - outer[2], outer[3] - b[3])


def box_circle_clear(b, c, r):
    return circle_box_clear(c[0], c[1], r, b)


def steel_error_deg(d_mm: float, b_mT: float = 52.685) -> float:
    """Worst-case angle error from a steel M3 x 8 screw at lateral distance d from the magnet axis (dipole model, upper bound).

    Magnet moment m = Br V / mu0 (Br 1.19 T, dia 10 x 5). Field at the screw on the moment axis: 2 mu0 m / (4 pi d^3). The screw is
    a 1.2e-7 m^3 prolate body magnetised along the field with demagnetising factor 0.1 (m_i = V B / (mu0 N)), and its own field at the
    sensor is again taken on its axis (factor 2). Far-field dipoles: an upper bound at d >= 15 mm, not a field map.
    """
    mu0 = 4e-7 * math.pi
    v_mag = math.pi * (5e-3) ** 2 * 5e-3
    m = 1.19 * v_mag / mu0
    d = d_mm * 1e-3
    b_loc = 2 * mu0 * m / (4 * math.pi * d ** 3)
    m_i = 1.2e-7 * b_loc / (mu0 * 0.1)
    b_s = 2 * mu0 * m_i / (4 * math.pi * d ** 3)
    return math.degrees(math.asin(min(1.0, b_s * 1e3 / b_mT)))


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
        ck["j7_matches_source"] = src["J_UI"] == J_UI and src["XH"] == (XH12_LEN, XH_DEPTH, XH_MATED_H)
        ck["stacker_matches_source"] = src["STACKER"] == STACKER
        ck["buttons_match_source"] = src["BUTTON_U"] == {k: v[0] for k, v in BUTTONS.items()} and src["BUTTON_V"] == 26.0
        ck["oled_lens_and_knob_axis_match_source"] = (
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
    # connectors on the rear face: J7 and J8 (the sensor-tab harness header)
    jb, j8 = j7_box(), sh_box(J8)
    inside = lambda b: b[0] > board[0] and b[1] < board[1] and b[2] > board[2] and b[3] < board[3]
    ck["j7_j8_inside_outline"] = inside(jb) and inside(j8)
    data["j7_box"], data["j8_box"] = [round(x, 2) for x in jb], [round(x, 2) for x in j8]
    data["j7_j8_gap_mm"] = round(box_box_gap(jb, j8), 2)
    ck["j7_j8_gap_ge_3mm"] = box_box_gap(jb, j8) >= 3.0
    cl = {}
    for nm, b in (("J7", jb), ("J8", j8)):
        cl[nm] = round(min(circle_box_clear(p[0], p[1], r, b) for _, p, r in holes), 2)
    data["connector_to_hole_clear_mm"] = cl
    ck["connectors_clear_of_holes_ge_3mm"] = min(cl.values()) >= EDGE_MIN
    ck["j7_clear_of_cutout"] = box_box_gap(jb, CUTOUT) > 5.0
    ck["j8_edge_margin_ge_3mm"] = box_edge_margin(j8, board) >= EDGE_MIN
    # OLED stacker
    pins = stacker_pins()
    ck["stacker_inside_outline"] = all(board[0] < u < board[1] and board[2] < v < board[3] for u, v in pins)
    ck["stacker_inside_oled_shadow"] = all(abs(u - OLED_CENTER[0]) < OLED_SIZE[0] / 2 and abs(v - OLED_CENTER[1]) < OLED_SIZE[1] / 2 for u, v in pins)
    ck["stacker_clear_of_holes_ge_3mm"] = min(circle_box_clear(p[0], p[1], r, STACKER) for _, p, r in holes) >= EDGE_MIN
    # OLED M2 holes must not coincide with a UI-board hole
    ck["oled_m2_clear_of_ui_holes"] = min(math.dist(a, p) - r for a in OLED_HOLES for _, p, r in holes) > 3.0
    # ---- tact switches: body 6.2 x 6.2 on the front face at the fixed centres
    tb = {nm: square(c, TACT_BODY) for nm, c in BUTTONS.items()}
    data["tact_bodies"] = {nm: [round(x, 2) for x in b] for nm, b in tb.items()}
    ck["tact_bodies_inside_outline_ge_3mm"] = all(box_edge_margin(b, board) >= EDGE_MIN for b in tb.values())
    ck["tact_bodies_clear_of_holes_ge_3mm"] = all(box_circle_clear(b, p, r) >= EDGE_MIN for b in tb.values() for _, p, r in holes)
    ck["caps_envelope_clear_of_each_other_ge_3mm"] = min(b - a for a, b in zip(us, us[1:])) - 2 * CAP_R >= EDGE_MIN
    # ---- buzzer datum
    bb = square(BUZZER, *BUZZER_BODY)
    data["buzzer"] = {"centre_uv": BUZZER, "body_box": [round(x, 2) for x in bb], "port_diameter_mm": BUZZER_PORT_D,
                      "edge_margin_mm": round(box_edge_margin(bb, board), 2),
                      "hole_clear_mm": round(min(box_circle_clear(bb, p, r) for _, p, r in holes), 2),
                      "nearest_cap_envelope_gap_mm": round(min(math.hypot(max(bb[0] - c[0], 0, c[0] - bb[1]), max(bb[2] - c[1], 0, c[1] - bb[3])) - CAP_R
                                                           for c in BUTTONS.values()), 2),
                      "oled_gap_mm": round(box_box_gap(bb, (OLED_CENTER[0] - OLED_SIZE[0] / 2, OLED_CENTER[0] + OLED_SIZE[0] / 2,
                                                            OLED_CENTER[1] - OLED_SIZE[1] / 2, OLED_CENTER[1] + OLED_SIZE[1] / 2)), 2),
                      "front_face_top_w": BOARD_FRONT_W + 5.0, "acoustic_gap_to_fascia_rear_mm": round(FASCIA_REAR_W - (BOARD_FRONT_W + 5.0), 2)}
    ck["buzzer_inside_outline_ge_3mm"] = box_edge_margin(bb, board) >= EDGE_MIN
    ck["buzzer_clear_of_holes_ge_3mm"] = min(box_circle_clear(bb, p, r) for _, p, r in holes) >= EDGE_MIN
    ck["buzzer_clear_of_cap_envelopes_ge_3mm"] = data["buzzer"]["nearest_cap_envelope_gap_mm"] >= EDGE_MIN
    ck["buzzer_clear_of_oled_ge_3mm"] = data["buzzer"]["oled_gap_mm"] >= EDGE_MIN
    ck["buzzer_port_fits_in_the_body"] = BUZZER_PORT_D <= min(BUZZER_BODY)
    ck["buzzer_is_the_lowest_v_corner_of_the_board"] = BUZZER[1] - BUZZER_BODY[1] / 2 - board[2] < 10.0 and BUZZER[0] < min(u for u, _ in BUTTONS.values())
    # ---- sensor tab (a separate PCB behind the fascia)
    tab = (TAB_U[0], TAB_U[1], TAB_V[0], TAB_V[1])
    ck["tab_clear_of_main_board_ge_10mm"] = tab[0] - board[1] >= 10.0
    ck["tab_centred_on_the_knob_axis"] = abs((tab[0] + tab[1]) / 2 - KNOB_AXIS[0]) < 1e-6 and abs((tab[2] + tab[3]) / 2 - KNOB_AXIS[1]) < 1e-6
    # Hall element datum: the package centre is offset from the knob axis by the figure 7-2 dimensions
    off_u = HALL_FROM_PIN1_4_SIDE - BODY / 2            # Hall is +0.27 toward the pin 5-8 side (+u with pin 1 upper left, seen from the front)
    off_v = -(HALL_FROM_PIN1_END - BODY / 2)            # Hall is 0.04 below the package centre (pin 1 end at +v)
    pkg = (KNOB_AXIS[0] - off_u, KNOB_AXIS[1] - off_v)
    data["sensor"] = {"hall_centre_uvw": [KNOB_AXIS[0], KNOB_AXIS[1], DIE_W], "package_centre_uv": [round(pkg[0], 3), round(pkg[1], 3)],
                      "package_orientation": "pin 1 upper left seen from the front (+u right, +v up), package top toward the fascia",
                      "tab_front_face_w": round(TAB_FRONT_W, 2), "tab_rear_face_w": round(TAB_FRONT_W - TAB_T, 2),
                      "tab_outline_u": TAB_U, "tab_outline_v": TAB_V, "face_to_die_gap_mm": MAGNET_NEAR_FACE_W - DIE_W,
                      "package_top_w": round(TAB_FRONT_W + PACKAGE_TOP_ABOVE_PCB, 2),
                      "package_top_to_fascia_rear_mm": round(FASCIA_REAR_W - (TAB_FRONT_W + PACKAGE_TOP_ABOVE_PCB), 2),
                      "main_board_front_w": BOARD_FRONT_W, "step_from_main_board_mm": round(TAB_FRONT_W - BOARD_FRONT_W, 2)}
    ck["package_centre_is_0p27_0p04_from_the_axis"] = abs(pkg[0] - 109.73) < 1e-6 and abs(pkg[1] - 53.04) < 1e-6
    ck["die_gap_is_5mm_face_to_die"] = abs((MAGNET_NEAR_FACE_W - DIE_W) - 5.0) < 1e-9
    ck["tab_front_face_puts_the_hall_plane_at_w_minus_4"] = abs((TAB_FRONT_W + HALL_ABOVE_PCB) - DIE_W) < 1e-9
    ck["package_top_clears_the_fascia_rear"] = FASCIA_REAR_W - (TAB_FRONT_W + PACKAGE_TOP_ABOVE_PCB) >= 0.5
    hd = {f"({u:g},{v:g})": round(math.dist((u, v), KNOB_AXIS) - FASTENER_HEAD_R, 2) for u, v in TAB_HOLES}
    data["tab_fastener_clearance_to_axis_mm"] = hd
    ck["tab_fasteners_outside_the_steel_keepout"] = min(hd.values()) >= STEEL_KEEPOUT_R
    jb9 = sh_box(J9)
    data["j9_box"] = [round(x, 2) for x in jb9]
    d9 = box_circle_clear(jb9, KNOB_AXIS, 0.0)
    data["j9_distance_to_axis_mm"] = round(d9, 2)
    ck["j9_outside_the_steel_keepout"] = d9 >= STEEL_KEEPOUT_R
    ck["j9_inside_tab_ge_1mm"] = box_edge_margin(jb9, tab) >= 1.0
    ck["tab_holes_wall_ge_2mm"] = all(min(u - tab[0], tab[1] - u, v - tab[2], tab[3] - v) - TAB_HOLE_R >= 2.0 for u, v in TAB_HOLES)
    ck["tab_holes_clear_of_j9_ge_1mm"] = all(box_circle_clear(jb9, h, TAB_HOLE_R) >= 1.0 for h in TAB_HOLES)
    ck["c16_within_5_to_9mm_of_the_hall_element"] = 5.0 <= math.dist(C16, KNOB_AXIS) <= 9.0
    ck["knob_envelope_does_not_reach_the_main_board_parts"] = KNOB_AXIS[0] - KNOB_ENVELOPE_R > OLED_CENTER[0] + LENS_SIZE[0] / 2
    se = {str(d): round(steel_error_deg(d), 4) for d in (15, 20, 25, 30)}
    data["steel_screw_error_deg_by_distance_mm"] = se
    ck["steel_screw_at_the_keepout_radius_le_0p07deg"] = steel_error_deg(STEEL_KEEPOUT_R) <= 0.07
    ck["steel_screw_at_15mm_would_exceed_1deg"] = steel_error_deg(15.0) > 1.0
    data["steel_keepout_r_mm"], data["component_keepout_r_mm"] = STEEL_KEEPOUT_R, COMPONENT_KEEPOUT_R
    # open items (data, not checks)
    data["stacker_gap_mm"] = FRONT_GAP_W
    data["oled_socket_height_mm"] = OLED_SOCKET_H_MM
    data["stacker_conflict_mm"] = round(OLED_SOCKET_H_MM - FRONT_GAP_W, 2)
    data["enclosure_findings"].append({"id": "E2", "item": f"the OLED stacker is modelled {FRONT_GAP_W} mm high; a 1x20 2.54 mm "
        f"female socket on LCSC is {OLED_SOCKET_H_MM} mm ({OLED_SOCKET_H_MM - FRONT_GAP_W:g} mm too tall)",
        "ask": "open the UI-board to OLED gap to 8.5 mm (taller carrier bosses) or approve a soldered low-profile header"})
    data["enclosure_findings"].append({"id": "E3", "item": f"J7 and J8 envelopes are {data['j7_j8_gap_mm']} mm apart; J7's mated XHP-12 housing "
        "is larger than the header body (J2 is gone, so J7 service access is no longer shared)", "ask": "confirm plug clearance and service access at layout"})
    data["enclosure_findings"].append({"id": "E5", "item": f"the TMAG5170 die plane is w = {DIE_W:g}, {TAB_FRONT_W - BOARD_FRONT_W:.2f} mm in front of the main board; "
        "the sensor therefore sits on a separate tab at w = {:.2f} (front face), 1.78 mm behind the fascia rear".format(TAB_FRONT_W),
        "ask": "provide 3 non-magnetic, low-conductivity standoffs 1.78 mm high at the tab holes (outside the 25 mm steel keep-out), a window for the J8-J9 harness, "
               "and no steel within 25 mm of (110, 53)"})
    data["enclosure_findings"].append({"id": "E4", "item": "no sound port is modelled in the fascia for the buzzer",
        "ask": f"a sealed acoustic membrane / port of dia {BUZZER_PORT_D:g} mm centred at (u, v) = ({BUZZER[0]:g}, {BUZZER[1]:g}) in front of BZ1; "
               f"the buzzer top is at w = {BOARD_FRONT_W + 5.0:g}, {FASCIA_REAR_W - (BOARD_FRONT_W + 5.0):g} mm behind the fascia rear"})
    return ck, data


# ------------------------------------------------------------------------------- SVG
def svg() -> str:
    s = 5.0                     # px per mm
    u_min, u_max, v_min, v_max = -112.0, 150.0, 8.0, 104.0
    W, H = (u_max - u_min) * s, (v_max - v_min) * s + 70
    X = lambda u: (u - u_min) * s
    Y = lambda v: (v_max - v) * s + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" '
         'font-family="Helvetica,Arial,sans-serif" font-size="10">',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<text x="8" y="16" font-size="13" font-weight="bold">Temper fascia UI board rev. 2 (owned controls): floorplan against enclosure R41 '
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
    # tact switches (front face) under the owner's caps
    for nm, (u, v) in BUTTONS.items():
        o.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="{CAP_R*s:.1f}" fill="#f4cccc" fill-opacity="0.6" stroke="#990000" stroke-width="1.2" stroke-dasharray="4 2"/>')
        b = square((u, v), TACT_BODY)
        o.append(f'<rect x="{X(b[0]):.1f}" y="{Y(b[3]):.1f}" width="{TACT_BODY*s:.1f}" height="{TACT_BODY*s:.1f}" fill="#333" fill-opacity="0.85" stroke="#000"/>')
        label = {"back": "SW3 BACK/RESET (GP2)", "select_start": "SW1 SELECT/START (GP0)", "stop": "SW2 STOP (GP1)"}[nm]
        o.append(f'<text x="{X(u):.1f}" y="{Y(v)+CAP_R*s+11:.1f}" text-anchor="middle">{label}</text>')
        o.append(f'<text x="{X(u):.1f}" y="{Y(v)+CAP_R*s+22:.1f}" text-anchor="middle" font-size="9">KSC223G LFG ({u:g}, {v:g})</text>')
    # buzzer datum with its acoustic port
    bb = square(BUZZER, *BUZZER_BODY)
    o.append(f'<rect x="{X(bb[0]):.1f}" y="{Y(bb[3]):.1f}" width="{BUZZER_BODY[0]*s:.1f}" height="{BUZZER_BODY[1]*s:.1f}" fill="#f9cb9c" stroke="#990000" stroke-width="1.5"/>')
    o.append(f'<circle cx="{X(BUZZER[0]):.1f}" cy="{Y(BUZZER[1]):.1f}" r="{BUZZER_PORT_D/2*s:.1f}" fill="none" stroke="#990000" stroke-width="1.5" stroke-dasharray="3 2"/>')
    o.append(f'<line x1="{X(BUZZER[0])-7:.1f}" y1="{Y(BUZZER[1]):.1f}" x2="{X(BUZZER[0])+7:.1f}" y2="{Y(BUZZER[1]):.1f}" stroke="#990000"/>'
             f'<line x1="{X(BUZZER[0]):.1f}" y1="{Y(BUZZER[1])-7:.1f}" x2="{X(BUZZER[0]):.1f}" y2="{Y(BUZZER[1])+7:.1f}" stroke="#990000"/>')
    o.append(f'<text x="{X(BOARD_U[0]):.1f}" y="{Y(BOARD_V[0])+27:.1f}" fill="#990000">BZ1 GSD9605YB-5V2800 datum (u, v) = ({BUZZER[0]:g}, {BUZZER[1]:g}), sealed port Ø{BUZZER_PORT_D:g}, front face, top at w {BOARD_FRONT_W + 5.0:g}</text>')
    # J7 and J8 (rear face)
    jb = j7_box()
    o.append(f'<rect x="{X(jb[0]):.1f}" y="{Y(jb[3]):.1f}" width="{(jb[1]-jb[0])*s:.1f}" height="{(jb[3]-jb[2])*s:.1f}" fill="#fff2cc" '
             'stroke="#7f6000" stroke-width="1.5" stroke-dasharray="4 2"/>')
    o.append(f'<text x="{X(J_UI[0]):.1f}" y="{Y(J_UI[1])+3:.1f}" text-anchor="middle" font-size="9">J7 JST XH 12-way (rear)</text>')
    j8b = sh_box(J8)
    o.append(f'<rect x="{X(j8b[0]):.1f}" y="{Y(j8b[3]):.1f}" width="{(j8b[1]-j8b[0])*s:.1f}" height="{(j8b[3]-j8b[2])*s:.1f}" fill="#fff2cc" '
             'stroke="#7f6000" stroke-width="1.5" stroke-dasharray="4 2"/>')
    o.append(f'<text x="{X(J8[0])-30:.1f}" y="{Y(J8[1]):.1f}" text-anchor="end" font-size="9">J8 SH-10 (rear)</text>')
    # sensor tab, keep-outs, magnet, Hall datum
    cu, cv = KNOB_AXIS
    o.append(f'<circle cx="{X(cu):.1f}" cy="{Y(cv):.1f}" r="{KNOB_ENVELOPE_R*s:.1f}" fill="none" stroke="#999" stroke-width="1" stroke-dasharray="2 4"/>')
    o.append(f'<text x="{X(cu):.1f}" y="{Y(cv)-KNOB_ENVELOPE_R*s-4:.1f}" text-anchor="middle" fill="#777" font-size="9">knob envelope R28 (w 0..20)</text>')
    o.append(f'<rect x="{X(TAB_U[0]):.1f}" y="{Y(TAB_V[1]):.1f}" width="{(TAB_U[1]-TAB_U[0])*s:.1f}" height="{(TAB_V[1]-TAB_V[0])*s:.1f}" fill="#d9ead3" '
             'stroke="#274e13" stroke-width="2"/>')
    o.append(f'<text x="{X(TAB_U[0])+4:.1f}" y="{Y(TAB_V[1])+12:.1f}" fill="#274e13">sensor tab (separate PCB, 64 x 32, front face w {TAB_FRONT_W:.2f})</text>')
    o.append(f'<circle cx="{X(cu):.1f}" cy="{Y(cv):.1f}" r="{STEEL_KEEPOUT_R*s:.1f}" fill="#cc0000" fill-opacity="0.07" stroke="#cc0000" stroke-width="1.5" stroke-dasharray="6 3"/>')
    o.append(f'<text x="{X(cu):.1f}" y="{Y(cv)+STEEL_KEEPOUT_R*s+12:.1f}" text-anchor="middle" fill="#cc0000">no steel / fasteners within R{STEEL_KEEPOUT_R:g} of the axis</text>')
    o.append(f'<circle cx="{X(cu):.1f}" cy="{Y(cv):.1f}" r="{COMPONENT_KEEPOUT_R*s:.1f}" fill="none" stroke="#e69138" stroke-width="1" stroke-dasharray="3 3"/>')
    o.append(f'<circle cx="{X(cu):.1f}" cy="{Y(cv):.1f}" r="{MAGNET_D/2*s:.1f}" fill="#999" fill-opacity="0.25" stroke="#555"/>')
    pk = (cu - (HALL_FROM_PIN1_4_SIDE - BODY / 2), cv + (HALL_FROM_PIN1_END - BODY / 2))
    pb = square(pk, BODY)
    o.append(f'<rect x="{X(pb[0]):.1f}" y="{Y(pb[3]):.1f}" width="{BODY*s:.1f}" height="{BODY*s:.1f}" fill="#333" fill-opacity="0.8" stroke="#000"/>')
    o.append(f'<line x1="{X(cu)-9:.1f}" y1="{Y(cv):.1f}" x2="{X(cu)+9:.1f}" y2="{Y(cv):.1f}" stroke="#d00" stroke-width="1.5"/>'
             f'<line x1="{X(cu):.1f}" y1="{Y(cv)-9:.1f}" x2="{X(cu):.1f}" y2="{Y(cv)+9:.1f}" stroke="#d00" stroke-width="1.5"/>')
    o.append(f'<text x="{X(cu):.1f}" y="{Y(cv)+COMPONENT_KEEPOUT_R*s+12:.1f}" text-anchor="middle" fill="#d00" font-size="9">Hall centre ({cu:g}, {cv:g}, w {DIE_W:g}); U8 package centre ({pk[0]:.2f}, {pk[1]:.2f})</text>')
    cb = square(C16, 1.6, 0.8)
    o.append(f'<rect x="{X(cb[0]):.1f}" y="{Y(cb[3]):.1f}" width="{max(1.6*s,6):.1f}" height="{max(0.8*s,4):.1f}" fill="#555"/>')
    o.append(f'<text x="{X(C16[0])-4:.1f}" y="{Y(C16[1])-5:.1f}" text-anchor="end" font-size="9">C16</text>')
    for hu, hv in TAB_HOLES:
        o.append(f'<circle cx="{X(hu):.1f}" cy="{Y(hv):.1f}" r="{TAB_HOLE_R*s:.1f}" fill="#fff" stroke="#000" stroke-width="1.2"/>')
        o.append(f'<circle cx="{X(hu):.1f}" cy="{Y(hv):.1f}" r="{FASTENER_HEAD_R*s:.1f}" fill="none" stroke="#000" stroke-dasharray="2 2"/>')
    o.append(f'<text x="{X(TAB_U[1]):.1f}" y="{Y(TAB_V[0])+12:.1f}" text-anchor="end" font-size="9">M2.5 non-magnetic standoffs at (83,42) (83,64) (138,53), clear of R25 by >= 25.5 mm of head edge</text>')
    jb9 = sh_box(J9)
    o.append(f'<rect x="{X(jb9[0]):.1f}" y="{Y(jb9[3]):.1f}" width="{(jb9[1]-jb9[0])*s:.1f}" height="{(jb9[3]-jb9[2])*s:.1f}" fill="#fff2cc" stroke="#7f6000" stroke-width="1.5"/>')
    o.append(f'<text x="{X(J9[0]):.1f}" y="{Y(J9[1])+3:.1f}" text-anchor="middle" font-size="9">J9</text>')
    o.append(f'<path d="M {X(J8[0]+2.2):.1f} {Y(J8[1]-4):.1f} Q {X(70):.1f} {Y(60):.1f} {X(J9[0]-2.2):.1f} {Y(J9[1]):.1f}" fill="none" stroke="#444" stroke-width="1.5" stroke-dasharray="5 3"/>')
    o.append(f'<text x="{X(70):.1f}" y="{Y(63):.1f}" text-anchor="middle" font-size="9">SH-10 harness, 1:1</text>')
    # dimensions and legend
    o.append(f'<text x="{X(BOARD_U[0]):.1f}" y="{Y(BOARD_V[0])+14:.1f}">board u {BOARD_U[0]:g}..{BOARD_U[1]:g} (170 mm), '
             f'v {BOARD_V[0]:g}..{BOARD_V[1]:g} (81 mm), 1.6 mm, front face at w {BOARD_FRONT_W:g}</text>')
    ly = H - 34
    leg = [("#d9ead3", "main board / sensor tab"), ("#bcd4f0", "OLED module"), ("#f4cccc", "owner's cap envelope R7 over the KSC2 body"),
           ("#fff2cc", "connector envelope"), ("#cc0000", "steel / fastener keep-out R25"), ("#f9cb9c", "buzzer + port")]
    x = 8
    for col, name in leg:
        o.append(f'<rect x="{x}" y="{ly}" width="12" height="10" fill="{col}" stroke="#555"/><text x="{x+16}" y="{ly+9}">{name}</text>')
        x += 16 + 6.2 * len(name) + 14
    o.append(f'<text x="8" y="{H-8}" font-size="9" fill="#555">Source: output/temper-manufacturing-r41/src/r33_world.py '
             '(UI board, R39 M3 holes) and controls_r5.py; sensor tab, keep-outs, buzzer and tact datums are this unit\'s (DECISIONS U26-U30). Placement zones are advisory.</text>')
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
