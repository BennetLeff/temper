#!/usr/bin/env python3
"""Choose native-21's board-only parts: bring-up test points, fiducials, mounting holes.

    python3 native-21/layout/plan_board_only21.py <copper-dump.json>  ->  native-21/layout/board_only21.json

board_only21.py adds them to every build (after the copper, before the labels). They are not in the
schematic, BOM or CPL (board-only, excluded from BOM and position files).

Test points (TestPoint_Pad_D1.0mm, F.Cu) sit on an existing via or F.Cu track of their net, so no
routing changes. Each via is checked for a 1.0 mm pad: F.Cu clearance to other nets, the 8 mm D5
barrier on every layer, and ≥ 0.3 mm from other parts' pads. Each signal gets a ground-reference
test point on its own domain's return within REF_REACH, for a short probe ground (D-8: ≤ 10 mm
loop). The FETs' own VGS / VDS are probed at their package leads (D-8), not here.

Fiducials (Fiducial_1mm_Mask3mm, F.Cu): three, spread, where no F.Cu copper or pour outline lies
within 2 mm, so the 3 mm mask opening shows bare laminate.

Mounting holes (MountingHole_3.2mm_M3, NPTH): "metal" holes satisfy D5 for chassis/PE hardware
(washer Ø 7 mm ≥ 8.0 mm from HOT copper, off SELV copper; verification/mounting_candidates.py).
"nylon" holes only keep the washer off outer-layer copper and carry a NYLON silk note.
"""
import json
import math
import re
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rules21  # noqa: E402
from geom21 import EDGE  # noqa: E402
from layers21 import INNER, OUTER  # noqa: E402  (native-21/stackup.json)

SIGNALS = [  # (net, reference net, purpose)
    ("leg_a-out_l", "n_ls", "leg A low-side driver output vs VSSB"),
    ("leg_b-out_l", "n_ls", "leg B low-side driver output vs VSSB"),
    ("n_ls", "leg_ret", "LS -2 V rail vs low-side sources (F6 rail at the edge)"),
    ("v15_ls", "leg_ret", "LS +15 V rail"),
    ("v24_raw", "n_ls", "24 V HOT supply"),
    ("ocp_node", "ocp_kelvin_p", "OCP comparator input (D4 condition 2)"),
    ("hot5", "ocp_kelvin_p", "HOT5 protection rail"),
    ("bus_fault_hot", "ocp_kelvin_p", "OCP fault, HOT side"),
    ("leg_a-out_h", "n_ha", "leg A high-side driver output vs VSSA"),
    ("n_ha", "sw_a", "HS-A -2 V rail vs switch node (F6 rail at the edge)"),
    ("p_ha", "sw_a", "HS-A +15 V rail"),
    ("leg_b-out_h", "n_hb", "leg B high-side driver output vs VSSA"),
    ("n_hb", "sw_b", "HS-B -2 V rail vs switch node"),
    ("p_hb", "sw_b", "HS-B +15 V rail"),
    ("v3v3", "selv_gnd", "SELV 3.3 V"),   # stage 38: the SELV 15 V probe is gone with PS1 / v15_selv
    ("pwm_ha", "selv_gnd", "PWM A high"), ("pwm_la", "selv_gnd", "PWM A low"),
    ("pwm_hb", "selv_gnd", "PWM B high"), ("pwm_lb", "selv_gnd", "PWM B low"),
    ("permit", "selv_gnd", "PERMIT"), ("leg_a-driver_dis", "selv_gnd", "leg A DIS"), ("leg_b-driver_dis", "selv_gnd", "leg B DIS"),
    ("bias_good", "selv_gnd", "BIAS_GOOD = bias_ok AND PERMIT (stage 50): reads low while PERMIT is low; drive J4.9 high with PWM idle to check bias health"), ("bus_fault", "selv_gnd", "OCP fault, SELV side"),
    ("line_zc", "selv_gnd", "LINE_ZC"), ("ct_zc", "selv_gnd", "tank CT zero cross"), ("ct_mon", "selv_gnd", "tank CT monitor"),
]
# Stage 48 (B13 H3-H5, end-of-line hooks): the rail monitors' 12 window taps, the TPS7A4700's open 3P2V pin (U26.6:
# a solder bridge to its GND neighbours U26.5 / U26.7 would add 3.2 V to the LS span) and REF25. Planned after the list
# above and numbered after its reference pads, so the stage-8..47 designators keep their spots and numbers.
SIGNALS_EOL = [(f"{m}-{tap}", n, f"{name} monitor {tap.upper()} tap")
               for m, n, name in (("monitor_ls", "n_ls", "LS"), ("bias_ha.monitor", "n_ha", "HS-A"),
                                  ("bias_hb.monitor", "n_hb", "HS-B"))
               for tap in ("uv", "ov", "spanuv", "spanov")] + [
    ("p6", "n_ls", "TPS7A4700 3P2V pin (U26.6, open)"),
    ("ref25", "ocp_kelvin_p", "REF25 (U5), the OCP / OVP / watchdog reference"),
]
# stage 48: the two end-of-line hooks with no legal pad spot on their copper, and where the fixture contacts them instead
EOL_PROBE = {
    "p6": "U26.6 pad toe (0.87 mm outside the VQFN body; H4: ground it to U26.5 / U26.7 to raise the LS span by 3.2 V); "
          "no copper on the open pin, and a pad needs a 4 mm stub under U26.7-U26.10 (stage 48 record)",
    "monitor_ls-ov": "C67.1 (0603, the tap capacitor; H3 forcing pad) / R83.2 / R84.1 / U29.4; ground n_ls at C67.2",
}
TP_R, REF_REACH, REF_SHARE = 0.5, 10.0, 6.0

d = json.loads(Path(sys.argv[1]).read_text())
pads = json.loads((HERE / "pads.json").read_text())
outline = Polygon(EDGE)
F, ALL = [], []
# the dump of a board built with board_only21.json holds the previous plan's own test pads,
# fiducials and holes; they are not copper to plan round (a kept hole would collide with itself)
BOARD_ONLY = re.compile(r"^(TP|FID|H)\d+$")
d["pads"] = [p for p in d["pads"] if not BOARD_ONLY.match(p.get("ref") or "")]
for p in d["pads"]:
    if len(p.get("pts", [])) > 2:
        g = Polygon(p["pts"])
        ALL.append((p["net"], g, p.get("ref")))
        F.append((p["net"], g, p.get("ref")))          # THT pads are on F too; SMD pads are F-side here
for t in d["tracks"]:
    g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2)
    ALL.append((t["net"], g, None))
    if t["layer"] == "F.Cu":
        F.append((t["net"], g, None))
for v in d["vias"]:
    g = Point(v["at"]).buffer(v["d"] / 2)
    ALL.append((v["net"], g, None))
    F.append((v["net"], g, None))
B = []
SELV_INNER = []                      # SELV inner-layer pours: they refill round an NPTH (see the nylon holes)
for z in d["zones"]:
    g = Polygon(z["pts"])
    ALL.append((z["net"], g, None))
    if z["layer"] in INNER and rules21.domain(z["net"]) == "SELV":
        SELV_INNER.append(g)
    if z["layer"] == "F.Cu":
        F.append((z["net"], g, None))
    if z["layer"] == "B.Cu":
        B.append((z["net"], g, None))
for t in d["tracks"]:
    if t["layer"] == "B.Cu":
        B.append((t["net"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2), None))
for v in d["vias"]:
    B.append((v["net"], Point(v["at"]).buffer(v["d"] / 2), None))
for p in d["pads"]:
    if p.get("tht") and len(p.get("pts", [])) > 2:
        B.append((p["net"], Polygon(p["pts"]), p.get("ref")))
treeF, treeA, treeB = STRtree([x[1] for x in F]), STRtree([x[1] for x in ALL]), STRtree([x[1] for x in B])
THT = [Polygon(p["pts"]) for p in d["pads"] if p.get("tht") and len(p.get("pts", [])) > 2]
padbox = [(p["ref"], box(*p["box"])) for p in pads]
# component courtyards (placement.json origin + parts.json courtyard size / centre offset)
PL = json.loads((HERE.parent / "placement.json").read_text())
PARTS = {q["path"]: q for q in json.loads((HERE / "parts.json").read_text())}
court = []
for path, (x0, y0, ang) in PL.items():
    q = PARTS[path]
    a = math.radians(ang)
    ox = q["ox"] * math.cos(a) + q["oy"] * math.sin(a)
    oy = -q["ox"] * math.sin(a) + q["oy"] * math.cos(a)
    w, h = (q["h"], q["w"]) if round(ang) % 180 == 90 else (q["w"], q["h"])
    cx, cy = x0 + ox, y0 + oy
    court.append((q["ref"], box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
padbox += court                                      # test points and holes stay out of courtyards too
treeP = STRtree([b for _, b in padbox])


def tp_ok(net, x, y, side="F"):
    c = Point(x, y).buffer(TP_R)
    if not outline.buffer(-1.0).contains(c):
        return False
    lst, tree = (F, treeF) if side == "F" else (B, treeB)
    for i in tree.query(c.buffer(5.5)):               # covers the 3.2 mm HOT-group and 5 mm tank rules
        n, g, _ = lst[i]
        if n != net and g.distance(c) < rules21.clearance(net, n) + 0.15:
            return False
    for i in treeA.query(c.buffer(rules21.BARRIER + 0.1)):
        n, g, _ = ALL[i]
        if n and n != net and rules21.barrier(net, n) and g.distance(c) < rules21.BARRIER + 0.3:   # the Rust gate measures pad boxes
            return False
    if side == "F":
        for i in treeP.query(c.buffer(0.65)):
            if padbox[i][1].distance(c) < 0.6:       # TP courtyard (Ø 2 mm) clear of others
                return False
    elif any(q.distance(c) < 1.0 for q in THT):      # bottom: clear of THT leads and their solder fillets
        return False
    return True


vias = {}
for v in d["vias"]:
    vias.setdefault(v["net"], []).append(tuple(v["at"]))
# a test pad may also sit on the net's own F.Cu / B.Cu track (sampled every 0.5 mm, ends excluded)
cand = {"F": {n: list(v) for n, v in vias.items()}, "B": {n: list(v) for n, v in vias.items()}}
for t in d["tracks"]:
    if t["layer"] not in OUTER:
        continue
    seg = LineString([t["a"], t["b"]])
    for k in range(1, int(seg.length / 0.5)):
        q = seg.interpolate(k * 0.5)
        cand[t["layer"][0]].setdefault(t["net"], []).append((round(q.x, 3), round(q.y, 3)))
NETS = {s for s, _, _ in SIGNALS + SIGNALS_EOL} | {r for _, r, _ in SIGNALS + SIGNALS_EOL}
okF = {n: [(*p, "F") for p in cand["F"].get(n, []) if tp_ok(n, *p, "F")] for n in NETS}
okB = {n: [(*p, "B") for p in cand["B"].get(n, []) if tp_ok(n, *p, "B")] for n in NETS}
tps, refs, missing = [], [], []


def plan(signals):
    """Give each (net, reference, purpose) a signal pad and a shared or new reference pad (appends to tps / refs / missing)."""
    for net, ref, why in signals:
        best = None
        for side, ok in (("F", okF), ("B", okB)):                  # top first; bottom when the top has no spot
            for p3 in ok.get(net, []):
                p = p3[:2]
                used = [q for q in refs if q["net"] == ref and q["side"] == side and math.dist(q["at"], p) <= REF_REACH]
                cands = used or [{"net": ref, "at": q[:2], "side": side} for q in ok.get(ref, []) if math.dist(q[:2], p) <= REF_REACH]
                for q in cands:
                    dd = math.dist(p, q["at"]) - (2.0 if q in refs else 0.0)      # prefer sharing a reference
                    if all(math.dist(p, t["at"]) > 2.2 for t in tps + refs) and \
                            all(math.dist(q["at"], t["at"]) > 2.2 or t is q for t in tps + refs) and math.dist(p, q["at"]) > 2.2 and (best is None or dd < best[0]):
                        best = (dd, p, q, side)
            if best is not None:
                break
        if best is None:
            missing.append({"net": net, "ref": ref, "why": "no legal via pair within %.0f mm" % REF_REACH})
            continue
        _, p, q, side = best
        if q not in refs:
            refs.append(q)
        tps.append({"net": net, "at": list(p), "side": side, "ref_net": ref, "ref_at": list(q["at"]), "purpose": why})


plan(SIGNALS)
n = 1
for t in tps:
    t["ref"] = f"TP{n}"
    n += 1
for r in refs:
    r["ref"] = f"TP{n}"
    r["purpose"] = f"{r['net']} reference"
    r["at"] = list(r["at"])
    n += 1
n_tps, n_refs = len(tps), len(refs)
plan(SIGNALS_EOL)
for t in tps[n_tps:]:
    t["ref"] = f"TP{n}"
    n += 1
for r in refs[n_refs:]:
    r["ref"] = f"TP{n}"
    r["purpose"] = f"{r['net']} reference"
    r["at"] = list(r["at"])
    n += 1

# fiducials: bare-laminate spots, three spread over the board
Fcopper = unary_union([g for _, g, _ in F])
Fpour = unary_union([Polygon(z["outline"]) for z in json.loads((HERE / "copper.json").read_text())["zones"] if z["layer"] == "F.Cu"])
parts_u = unary_union([b.buffer(1.0) for _, b in padbox])
fid_ok = []
for i in range(4, 287, 2):
    for j in range(4, 187, 2):
        c = Point(i, j)
        if outline.buffer(-3.0).contains(c) and c.distance(Fcopper) >= 2.0 and c.distance(Fpour) >= 2.0 \
                and c.distance(parts_u) >= 1.5:
            fid_ok.append((i, j))
fids = []
# stage-8 fiducials kept while legal (FID3 at (6, 186) leaves pinned hole H2 at (6, 180) its 6 mm)
PINNED_FIDS = ((8, 36), (278, 128), (6, 186))
fid_set = {tuple(q) for q in fid_ok}
for pinned, target in zip(PINNED_FIDS, ((5, 5), (280, 130), (5, 185))):
    fids.append(pinned if pinned in fid_set else min(fid_ok, key=lambda q: math.dist(q, target)))

# mounting holes: metal-legal centres (D5) where available, nylon elsewhere
mc = json.loads((HERE.parent / "verification" / "mounting-candidates.json").read_text())["candidates"]
allcu = unary_union([g for _, g, _ in ALL])
outer = unary_union([g for _, g, _ in F] + [g for n_, g, _ in ALL if False])
holes = []
court_u = unary_union([b for _, b in court])
mc = [q for q in mc if Point(q[:2]).buffer(3.5).distance(court_u) >= 0.3
      and all(math.dist(q[:2], f) >= 6.0 for f in fids)]
for target in ((285, 135), (285, 5), (160, 135)):
    c = min(mc, key=lambda q: math.dist(q[:2], target))
    if all(math.dist(c[:2], h["at"]) > 30 for h in holes):
        holes.append({"at": c[:2], "kind": "metal", "hot_mm": c[2]})
# nylon fixings (review M4): the washer / standoff face (Ø 7 mm) bears on bare laminate on both
# outer layers, and the inner planes keep clear of the hole. SELV inner pours are the exception:
# KiCad refills them round the NPTH at hole clearance, and a SELV plane edge by a nylon screw is
# harmless. HOT inner planes still keep 2.2 mm: a plane edge at the hole wall would start a
# creepage path down the hole to the chassis. That exception lets the SELV tongue (x < 91,
# y > 140, J4's harness end) take fixings; its corner holds only the v3v3 / selv_gnd planes.
allcu_hole = unary_union([g for _, g, _ in ALL if not any(g.equals(q) for q in SELV_INNER)])
Bcopper = unary_union([g for _, g, _ in B])
nylon_ok = []
for i in range(4, 287, 2):
    for j in range(4, 187, 2):
        c = Point(i, j)
        w = c.buffer(3.5)
        if outline.buffer(-0.5).contains(w) and w.distance(Fcopper) >= 0.3 and w.distance(Bcopper) >= 0.3 \
                and c.distance(allcu_hole) >= 2.2 and w.distance(parts_u) >= 0.3 \
                and all(w.distance(b) >= 0.3 for _, b in court):
            nylon_ok.append((i, j))
# Frozen once the enclosure adopted them (R22 bosses on the stage-8 board): each stage-8 nylon hole
# is kept where it was while it is still legal on the new copper; only an illegal one is re-planned.
PINNED_NYLON = ((6, 180), (86, 180), (24, 74), (88, 100), (128, 54), (194, 130))
legal = set(nylon_ok)
for q in PINNED_NYLON:
    if q in legal and all(math.dist(q, f) >= 6.0 for f in fids):
        holes.append({"at": list(q), "kind": "nylon"})
    else:
        print(f"pinned nylon hole {q} no longer legal: re-planned (the enclosure must follow)")
for target in (() if len(holes) == 1 + len(PINNED_NYLON) else
               ((5, 180), (86, 180), (5, 5), (5, 185), (88, 185), (88, 100), (5, 100), (145, 5), (285, 5),
                (200, 135), (145, 135))):
    if nylon_ok:
        q = min(nylon_ok, key=lambda q: math.dist(q, target))
        if all(math.dist(q, h["at"]) > 30 for h in holes) and all(math.dist(q, f) >= 6.0 for f in fids):
            holes.append({"at": list(q), "kind": "nylon"})
for k, h in enumerate(holes, 1):
    h["ref"] = f"H{k}"

# SELV interface signals without a legal pad spot are probed at J4, the controller connector
# (THT, from the bottom side), with selv_gnd on J4.2 / J4.4 / J4.15 beside them
j4 = {pd["net"]: pd["pad"] for pd in pads if pd["ref"] == "J4" and pd["net"]}
for m in missing:
    if m["net"] in j4:
        m["probe"] = f"J4.{j4[m['net']]} (bottom), ground J4.2 / J4.4 / J4.15"
    else:
        on = sorted(f"{pd['ref']}.{pd['pad']}" for pd in pads if pd["net"] == m["net"])   # sorted: dump order varies by build
        m["probe"] = "component pad " + " / ".join(on[:4]) + " (no legal test-pad spot)"
    if m["net"] in EOL_PROBE:
        m["probe"] = EOL_PROBE[m["net"]]
# silk marks (review M12): board ID, HV warning, nylon legend, PE at J6, BR1 outline and pin marks.
# Text blocks go where no courtyard, pad or other mark lies within the text box + 0.5 mm.
taken = [b for _, b in court] + [Point(h["at"]).buffer(4.0) for h in holes] + \
        [Point(f["at"]).buffer(2.0) for f in [{"at": q} for q in fids]] + \
        [Point(t["at"]).buffer(1.2) for t in tps + refs]


def text_spot(lines, h, target, region=(2, 2, 288, 188)):
    """Nearest legal spot to `target` on the 1 mm grid. Stage 22 speed-up (same predicate, same winner): the inset outline is
    built once, candidates are scanned nearest-first in (distance, i, j) order - the order in which the old full scan's
    strict '<' kept its first minimum - and stop at the first legal one; each candidate's 0.5 mm-buffered box is tested only
    against the obstacles an STRtree returns. Was ~470 s per chain (28.9 M buffer calls)."""
    w = max(len(t) for t in lines) * h * 1.0 + 1.0     # KiCad stroke font: ~1 x size per glyph incl. spacing
    hh = len(lines) * h * 1.5 + 1.0
    inner = outline.buffer(-1.5)
    tree = STRtree(taken)
    cand = sorted((math.dist((i, j), target), i, j) for i in range(int(region[0]), int(region[2]), 1)
                  for j in range(int(region[1]), int(region[3]), 1))
    for dd, i, j in cand:
        bx = box(i - w / 2, j - hh / 2, i + w / 2, j + hh / 2)
        if not inner.contains(bx):
            continue
        bb = bx.buffer(0.5)
        if any(taken[k].intersects(bb) for k in tree.query(bb)):
            continue
        taken.append(bx)
        return [i, j]
    return None


silk = []
for lines, h, target in ((["TEMPER POWER STAGE 120V", "NATIVE-21 REV A  2026-10"], 1.5, (240, 125)),
                         (["DANGER: MAINS AND 400 V DC", "HOT SECTIONS ARE NOT EARTHED"], 1.5, (150, 60)),
                         ([f"H2-H{len(holes)}: NYLON SCREWS, WASHERS", "AND STANDOFFS ONLY"], 1.0, (60, 150))):
    at = text_spot(lines, h, target)
    if at:
        silk.append({"kind": "text", "lines": lines, "size": h, "at": at})
pe = [pd for pd in pads if pd["ref"] == "J6"]
if pe:
    at = text_spot(["PE"], 1.5, (sum(q["x"] for q in pe) / len(pe), sum(q["y"] for q in pe) / len(pe) - 6))
    if at:
        silk.append({"kind": "text", "lines": ["PE"], "size": 1.5, "at": at})
for h in holes:
    if h["kind"] == "nylon":
        silk.append({"kind": "ring", "at": h["at"], "r": 3.6})
br = [pd for pd in pads if pd["ref"] == "BR1"]
if br:
    xs = [q["x"] for q in br]
    silk.append({"kind": "rect", "box": [min(xs) - 3.5, 1.0, max(xs) + 3.5, 8.6]})   # GBJ body behind the pins
    for q, mark in zip(sorted(br, key=lambda q: q["x"]), ("+", "~", "~", "-")):
        silk.append({"kind": "text", "lines": [mark], "size": 1.5, "at": [q["x"], 9.8]})
out = {"test_points": tps + refs, "missing_test_points": missing, "silk": silk,
       "fiducials": [{"ref": f"FID{k}", "at": list(p)} for k, p in enumerate(fids, 1)],
       "mounting_holes": holes}
(HERE / "board_only21.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(tps), "signal TPs,", len(refs), "reference TPs,", len(missing), "missing:", [m["net"] for m in missing])
print("fiducials", out["fiducials"])
print("holes", [(h["ref"], h["kind"], h["at"]) for h in holes])
print("silk", [(m["kind"], m.get("lines", [""])[0], m.get("at")) for m in silk])
