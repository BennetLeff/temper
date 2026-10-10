#!/usr/bin/env python3
"""Build the controller board (unrouted) from the frozen netlist and layout/floorplan.py.

    KICAD_PY layout/build_board.py          (from zapote/controller)

KICAD_PY = /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3

Inputs: frozen/default.net (connectivity, tstamps), frozen/resolved-components.json (footprint, MPN;
never the netlist libsource), layout/floorplan.py (poses, anchors), layout/world.py (enclosure).
Outputs (pcb/): controller.kicad_pcb (placed, planes, keep-outs, no signal copper),
controller.kicad_pro, controller.kicad_sch + controller.kicad_sym (a typed-label schematic generated
from the same netlist so KiCad's schematic-parity DRC has a reference), placement.json (every pose
in world mm), libs/ (vendored footprints) and fp-lib-table.

Stack-up: 4 layers, JLC JLC04161H-7628 (1.6 mm; outer 1 oz, inner 0.5 oz).
  F.Cu signal + parts, In1.Cu solid selv_gnd plane, In2.Cu v3v3 plane, B.Cu signal.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
import uuid
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(HERE))
import floorplan  # noqa: E402
import world  # noqa: E402

PCB = UNIT / "pcb"
STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
RTD_LIB = UNIT.parent / "rtd/unit/candidate/candidate-libs"
GND, V3, V15 = "selv_gnd", "v3v3", "v15_selv"
GAP = 0.9          # courtyard-to-courtyard gap for auto-placed parts: room for a fan-out via and a track
NAME = "controller"

# Net classes (JLC 1 oz multilayer capability, read 2026-10-09 from jlcpcb.com/capabilities/pcb-capabilities:
# track/space 0.09/0.09 mm, via 0.15/0.25 mm, PTH ring 0.15 min / 0.20 recommended, routed-edge copper
# >= 0.2 mm, via hole-to-hole 0.2 mm, pad hole-to-hole 0.45 mm). Our floors carry margin over each.
CLASSES = {
    "Default": {"track_width": 0.15, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
    "Power": {"track_width": 0.4, "clearance": 0.15, "via_diameter": 0.8, "via_drill": 0.4},
    "Plane": {"track_width": 0.3, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
    "Supply": {"track_width": 0.3, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
    "Analog": {"track_width": 0.15, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
}
POWER_NETS = [V15, "v12_fan", "sw_3v3", "sw_12"]
SUPPLY_NETS = ["V5_UI", "v5_drop", "v5_mid", "RTD_AVDD"]
ANALOG_NETS = ["HS_SENSE", "COIL_SENSE", "rtd_sense_p", "rtd_sense_n", "rtd_force_p", "rtd_force_n", "vbus_p",
               "vbus_n", "ct_mon", "ct_buf_out", "m12_node", "m12_filt", "p1", "refin_n", "rms_in", "rms_ibuf",
               "rms_ignd", "CT_RMS_CORE", "rms_core_in", "rms_cavg", "rms_obuf", "rms_fb", "CT_RMS_ADC",
               "rx_a_n", "rx_a_p", "rx_a_out", "rx_bias", "rx_bias_div", "ref2v5", "HS_REF", "COIL_REF",
               "OPEN_REF", "RUNAWAY_TH", "rtd_pan.low_window-inp", "inn", "vbias", "rtd_pan.r_high_top-inp"]

STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "HAL lead-free")
			(dielectric_constraints no)
		)
"""


def mm(v):
    return pcbnew.FromMM(float(v))


def K(x, y):
    kx, ky = world.to_k(x, y)
    return pcbnew.VECTOR2I(mm(kx), mm(ky))


# ------------------------------------------------------------------ netlist
def parse_netlist():
    text = (UNIT / "frozen/default.net").read_text()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\).*?\(sheetpath \(names "[^"]*::([^"]+)"\) \(tstamps "([^"]+)"\)',
                         text, re.S):
        comps[m.group(1)] = {"path": m.group(2), "tstamp": m.group(3)}
    nets = {}
    comps_text, _, nets_text = text.partition("(nets")
    for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)(?=\n\s*\(net \(code|\Z)', nets_text, re.S):
        nets[m.group(1)] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
    attrs = {c["address"].split("::", 1)[1]: c["attributes"]
             for c in json.loads((UNIT / "frozen/resolved-components.json").read_text())["components"]}
    for ref, c in comps.items():
        c["fp"] = attrs[c["path"]]["footprint"]
        c["mpn"] = attrs[c["path"]]["mpn"]
    return comps, nets


def lib_dir(lib):
    if lib == "Temper_RTD":
        return RTD_LIB / "Temper_RTD.pretty"
    return STOCK / f"{lib}.pretty"


# ------------------------------------------------------------------ board shell
def write_project():
    """Project file: native-20's KiCad 10 project as the schema template (read only), with our rules."""
    tmpl = json.loads((UNIT.parent / "power-stage-120v/native-20/section.kicad_pro").read_text())
    tmpl["meta"]["filename"] = f"{NAME}.kicad_pro"
    ds = tmpl["board"]["design_settings"]
    ds["rules"].update({
        "min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5, "min_through_hole_diameter": 0.2,
        "min_via_annular_width": 0.15, "min_hole_clearance": 0.25, "min_hole_to_hole": 0.5,
        "min_copper_edge_clearance": 0.5, "min_text_height": 0.8, "min_text_thickness": 0.12,
        "min_silk_clearance": 0.0, "min_connection": 0.15, "min_resolved_spokes": 1, "solder_mask_to_copper_clearance": 0.0})
    ds["track_widths"] = [0.0, 0.2, 0.3, 0.5, 0.8]
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3}, {"diameter": 0.8, "drill": 0.4}]
    ds["drc_exclusions"] = []
    base = tmpl["net_settings"]["classes"][0]
    classes = []
    for i, (name, v) in enumerate(CLASSES.items()):
        c = dict(base)
        c.update(v)
        c["name"] = name
        c["priority"] = 2147483647 if name == "Default" else i
        classes.append(c)
    tmpl["net_settings"]["classes"] = classes
    tmpl["net_settings"]["netclass_patterns"] = (
        [{"netclass": "Power", "pattern": n} for n in POWER_NETS] +
        [{"netclass": "Plane", "pattern": n} for n in (GND, V3)] +
        [{"netclass": "Supply", "pattern": n} for n in SUPPLY_NETS] +
        [{"netclass": "Analog", "pattern": n} for n in ANALOG_NETS])
    tmpl["net_settings"]["netclass_assignments"] = None
    tmpl["sheets"] = [[str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-controller-sch/root")), "Root"]]
    tmpl["boards"] = []
    (PCB / f"{NAME}.kicad_pro").write_text(json.dumps(tmpl, indent=2) + "\n")


def shell_board():
    """An empty 4-layer board with our stack-up; In1/In2 are typed power planes (Specctra 'power')."""
    b = pcbnew.CreateEmptyBoard()
    b.SetCopperLayerCount(4)
    tmp = PCB / "_shell.kicad_pcb"
    pcbnew.SaveBoard(str(tmp), b)
    t = tmp.read_text()
    t = t.replace('(4 "In1.Cu" signal)', '(4 "In1.Cu" power)').replace('(6 "In2.Cu" signal)', '(6 "In2.Cu" power)')
    t = t.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
    t = t.replace("(thickness 1.6)", f"(thickness {world.THICKNESS})", 1)
    out = PCB / f"{NAME}.kicad_pcb"
    out.write_text(t)
    tmp.unlink()
    return pcbnew.LoadBoard(str(out))


# ------------------------------------------------------------------ geometry helpers
def layer_bbox(fp, layer):
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == layer:
            bb = g.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        bb = fp.GetBoundingBox(False)
        return bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()
    return min(xs), min(ys), max(xs), max(ys)


def crt_rect(fp):
    """Courtyard rect in KiCad mm (pads included, for footprints whose courtyard misses a pad)."""
    if fp.GetFPID().GetLibItemName().wx_str().startswith("ESP32-S3-WROOM"):
        # its library courtyard includes the antenna keep-out (handled separately): use the body + 0.5
        x0, y0, x1, y1 = layer_bbox(fp, pcbnew.F_Fab)
        x0, y0, x1, y1 = x0 - mm(0.5), y0 - mm(0.5), x1 + mm(0.5), y1 + mm(0.5)
    else:
        x0, y0, x1, y1 = layer_bbox(fp, pcbnew.F_CrtYd)
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        x0, y0, x1, y1 = min(x0, bb.GetLeft()), min(y0, bb.GetTop()), max(x1, bb.GetRight()), max(y1, bb.GetBottom())
    return tuple(pcbnew.ToMM(v) for v in (x0, y0, x1, y1))


def overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def pose(fp, x, y, rot, ref_layer=None):
    fp.SetOrientationDegrees(float(rot))
    fp.SetPosition(K(x, y))
    if ref_layer is not None:
        x0, y0, x1, y1 = layer_bbox(fp, ref_layer)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        tx, ty = K(x, y).x, K(x, y).y
        p = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(int(p.x + tx - cx), int(p.y + ty - cy)))


def forbidden_rects():
    """KiCad-frame rects no auto-placed part or fan-out via may touch: the hole keep-outs. (R33: the
    WROOM-1U has no on-board antenna, so there is no antenna keep-out.)"""
    out = []
    r = world.HOLE_KEEPOUT_D / 2 + 0.3
    for hx, hy in world.HOLES:
        kx, ky = world.to_k(hx, hy)
        out.append((kx - r, ky - r, kx + r, ky + r))
    return out


def ufl_world(u4):
    """U.FL receptacle centre in world mm (Espressif Figure 10-2 / footprint offset world.UFL_FP)."""
    a = math.radians(u4.GetOrientationDegrees())
    fx, fy = world.UFL_FP
    kx = pcbnew.ToMM(u4.GetPosition().x) + fx * math.cos(a) + fy * math.sin(a)
    ky = pcbnew.ToMM(u4.GetPosition().y) - fx * math.sin(a) + fy * math.cos(a)
    return world.to_w(kx, ky)


def channel_rects():
    """Routing channels (floorplan.CHANNELS) in KiCad mm."""
    out = []
    for x0, y0, x1, y1 in getattr(floorplan, "CHANNELS", []):
        a_, b_ = world.to_k(x0, y1), world.to_k(x1, y0)
        out.append((a_[0], a_[1], b_[0], b_[1]))
    return out


def inside_board(r, inset=0.8):
    x0, y0 = world.to_k(world.BOARD[0], world.BOARD[3])
    x1, y1 = world.to_k(world.BOARD[2], world.BOARD[1])
    return r[0] >= x0 + inset and r[1] >= y0 + inset and r[2] <= x1 - inset and r[3] <= y1 - inset


def body_courtyard(fp):
    """KiCad's WROOM courtyard also encloses the antenna keep-out, which the footprint's own rule area
    already enforces; replace it with the module body (F.Fab) + 0.25 mm so placement rules see the
    physical part. The rule area is kept unchanged."""
    for g in list(fp.GraphicalItems()):
        if g.GetLayer() == pcbnew.F_CrtYd:
            fp.Remove(g)
    x0, y0, x1, y1 = layer_bbox(fp, pcbnew.F_Fab)
    s = pcbnew.PCB_SHAPE(fp)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pcbnew.VECTOR2I(x0 - mm(0.25), y0 - mm(0.25)))
    s.SetEnd(pcbnew.VECTOR2I(x1 + mm(0.25), y1 + mm(0.25)))
    s.SetLayer(pcbnew.F_CrtYd)
    s.SetWidth(mm(0.05))
    fp.Add(s)


# ------------------------------------------------------------------ main build
def main():
    PCB.mkdir(exist_ok=True)
    comps, nets = parse_netlist()
    pin_net = {(r, p): n for n, nodes in nets.items() for r, p in nodes}
    write_project()
    board = shell_board()
    for name in sorted(nets):
        if name and not board.FindNet(name):
            board.Add(pcbnew.NETINFO_ITEM(board, name))

    # vendor footprints, build fp-lib-table
    libs = set()
    fps = {}
    root = str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-controller-sch/root"))
    for ref, c in sorted(comps.items()):
        lib, name = c["fp"].split(":", 1)
        src = lib_dir(lib) / f"{name}.kicad_mod"
        dst = PCB / "libs" / f"{lib}.pretty"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / f"{name}.kicad_mod")
        libs.add(lib)
        fp = pcbnew.FootprintLoad(str(dst), name)
        if name.startswith("ESP32-S3-WROOM"):
            body_courtyard(fp)
        if name == "VSSOP-8_2.3x2mm_P0.5mm":
            # U20 SN74LVC1G74DCU: the library's 0.35 mm pads leave 0.15 mm gaps; 0.28 mm pads (TI's DCU
            # land is 0.25-0.30 wide) leave 0.22 mm, inside our 0.2 mm clearance floor
            for p in fp.Pads():
                p.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(p.GetSize(pcbnew.F_Cu).x, mm(0.28)))
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetValue(c["mpn"])
        fp.Value().SetVisible(False)
        fp.SetField("MPN", c["mpn"])
        fp.SetField("SourceInstance", c["path"])
        fp.GetField("MPN").SetVisible(False)
        fp.GetField("SourceInstance").SetVisible(False)
        fp.SetPath(pcbnew.KIID_PATH(f"/{root}/{c['tstamp']}"))
        board.Add(fp)
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(board.FindNet(n))
        fps[ref] = fp
    (PCB / "fp-lib-table").write_text("(fp_lib_table\n  (version 7)\n" + "".join(
        f'  (lib (name "{lib}") (type "KiCad") (uri "${{KIPRJMOD}}/libs/{lib}.pretty") (options "") (descr ""))\n'
        for lib in sorted(libs)) + ")\n")

    # ---- floorplan keys: atopile instance paths (stable across designator renumbering) or the
    # fixed designators of connectors and the module; anything else is an error
    by_path = {c["path"]: r for r, c in comps.items()}

    def R(key):
        if key in by_path:
            return by_path[key]
        if key in comps and (key.startswith("J") or key == "U4"):
            return key
        raise SystemExit(f"floorplan key {key!r} is neither an atopile path in frozen/default.net nor a "
                         f"fixed connector/module designator")
    PLACE = {R(k): v for k, v in floorplan.PLACE.items()}
    ANCHOR = {R(k): R(v) for k, v in floorplan.ANCHOR.items()}

    # ---- explicit poses
    placed = {}
    for ref, spec in PLACE.items():
        x, y, rot = spec[:3]
        mode = spec[3] if len(spec) > 3 else None
        layer = {"fab": pcbnew.F_Fab, "crtyd": pcbnew.F_CrtYd, None: None}[mode]
        pose(fps[ref], x, y, rot, layer)
        placed[ref] = crt_rect(fps[ref])
    bad = [(a, b) for a in placed for b in placed if a < b and overlap(placed[a], placed[b])]
    if bad:
        raise SystemExit(f"explicit poses overlap: {bad}")

    kx0, ky0 = world.to_k(world.BOARD[0], world.BOARD[3])
    kx1, ky1 = world.to_k(world.BOARD[2], world.BOARD[1])
    # ---- planes: In1 selv_gnd, In2 v3v3 (whole board; the WROOM rule area and hole keep-outs cut them)
    def plane(net, layer, prio, name, rect=None, pad_conn=pcbnew.ZONE_CONNECTION_THT_THERMAL):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet(net))
        z.SetAssignedPriority(prio)
        z.SetZoneName(name)
        z.SetPadConnection(pad_conn)
        z.SetMinThickness(mm(0.25))
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.4))
        z.SetLocalClearance(mm(0.25))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        if rect is None:
            rect = (kx0 + 0.3, ky0 + 0.3, kx1 - 0.3, ky1 - 0.3)
        for x, y in ((rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])):
            ol.Append(mm(x), mm(y))
        board.Add(z)
        return z
    plane(GND, pcbnew.In1_Cu, 0, "GND_plane")
    plane(V3, pcbnew.In2_Cu, 0, "V3V3_plane")

    # ---- power-stage pours (F.Cu): VIN / SW / VOUT of both bucks, built from their pad positions
    def pad_xy(rp):
        r, p = rp.split(".")
        q = next(q for q in fps[r].Pads() if q.GetNumber() == p)
        return pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)

    def pad_box(rp):
        r, p = rp.split(".")
        q = next(q for q in fps[r].Pads() if q.GetNumber() == p)
        bb = q.GetBoundingBox()
        return tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))

    def stub(net, x0, y0, x1, y1, w=0.3):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        t.SetWidth(mm(w))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(board.FindNet(net))
        t.SetLocked(True)
        board.Add(t)

    def buck_pours(u, ind, tag):
        """SOT-583 converter (pins 1-4 left, 5-8 right, 0.5 mm pitch): a 0.3 mm stub leaves each
        power pin straight outward (it is as wide as the pad), and the wide pour starts 0.25 mm
        clear of the pin row, so the 0.2 mm pin gaps never carry pour."""
        # SW (pin 5, the lower-right corner pin): stub straight down (+ky, toward the front), then a
        # 2.1 mm pour band running right to the inductor's pin-1 pad. The pins above it (BST, SS, FB)
        # keep their whole right side for the bootstrap cap and the SS/FB parts.
        x0, y0, x1, y1 = pad_box(f"{u}.5")
        cx = (x0 + x1) / 2
        lx0, ly0, lx1, ly1 = pad_box(f"{ind}.1")
        stub(f"sw_{tag}", cx, (y0 + y1) / 2, cx, y1 + 0.6)
        sw_rect = (x0, y1 + 0.25, lx1, y1 + 2.35)
        plane(f"sw_{tag}", pcbnew.F_Cu, 5, f"SW_{tag.upper()}", sw_rect, pad_conn=pcbnew.ZONE_CONNECTION_FULL)
        placed[f"_sw_{u}"] = sw_rect
        # VIN (pin 3): stub to -x, input pour to the left of the pin row
        x0, y0, x1, y1 = pad_box(f"{u}.3")
        cy = (y0 + y1) / 2
        stub(V15, (x0 + x1) / 2, cy, x0 - 0.7, cy)
        plane(V15, pcbnew.F_Cu, 5, f"VIN_{tag.upper()}", (x0 - 4.0, cy, x0 - 0.25, cy + 2.6),
              pad_conn=pcbnew.ZONE_CONNECTION_FULL)
        # GND (pin 4, the lower-left corner pin): stub straight down to a plane via
        x0, y0, x1, y1 = pad_box(f"{u}.4")
        cx = (x0 + x1) / 2
        stub(GND, cx + 0.2, (y0 + y1) / 2, cx + 0.2, y1 + 0.9)
        placed[f"_gndvia_{u}"] = (cx + 0.2 - 0.55, y1, cx + 0.2 + 0.55, y1 + 1.45)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(cx + 0.2), mm(y1 + 0.9)))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(board.FindNet(GND))
        v.SetLocked(True)
        board.Add(v)
    buck_pours(R("u_3v3"), R("l_3v3"), "3v3")
    buck_pours(R("u_12"), R("l_12"), "12")

    # ---- anchored passives
    is_active = lambda r: r[0] in "UJ" or r == "Q1" or r.startswith("L")  # noqa: E731
    def anchor_of(ref):
        fp = fps[ref]
        my_nets = [p.GetNetname() for p in fp.Pads() if p.GetNetname()]
        want = ANCHOR.get(ref)
        if want:
            # the supply pin is the highest-numbered pad on the shared net (VCC is the last pin of every
            # IC package used here; lower pads on v3v3 are tied-high logic inputs)
            cand = [p for p in fps[want].Pads() if p.GetNetname() in my_nets and p.GetNetname() != GND]
            if cand:
                return want, max(cand, key=lambda q: int(q.GetNumber()) if q.GetNumber().isdigit() else -1)
            for p in fps[want].Pads():
                if p.GetNetname() in my_nets:
                    return want, p
            raise SystemExit(f"{ref}: anchor {want} shares no net")
        best = None
        for n in my_nets:
            if n in (GND,):
                continue
            nodes = nets[n]
            cands = [(r, p) for r, p in nodes if r != ref and is_active(r)]
            if not cands:
                continue
            key = (len(nodes) if n not in (V3, V15) else 99, cands[0][0][0] != "U")
            if best is None or key < best[0]:
                best = (key, cands[0])
        if best is None:
            for n in my_nets:
                for r, p in nets[n]:
                    if r != ref and r in placed and n != GND:
                        return r, next(q for q in fps[r].Pads() if q.GetNumber() == p)
            return None
        r, p = best[1]
        return r, next(q for q in fps[r].Pads() if q.GetNumber() == p)

    forbid = forbidden_rects()
    # U.FL (R33): nothing else within world.UFL_CLEAR_R of the receptacle, so the plug stays reachable
    ux, uy = ufl_world(fps["U4"])
    k0, k1 = world.to_k(ux - world.UFL_CLEAR_R, uy + world.UFL_CLEAR_R), world.to_k(ux + world.UFL_CLEAR_R, uy - world.UFL_CLEAR_R)
    forbid.append((k0[0], k0[1], k1[0], k1[1]))
    channels = channel_rects()
    pending = [r for r in comps if r not in placed]
    # decoupling (explicit anchors) first, then by net specificity
    pending.sort(key=lambda r: (r not in ANCHOR, r))
    passes = 0
    while pending and passes < 5:
        passes += 1
        left = []
        for ref in pending:
            a = anchor_of(ref)
            if a is None or a[0] not in placed:
                left.append(ref)
                continue
            aref, apad = a
            # decoupling caps sit tight to their pin; everything else keeps a routing channel
            gap_ref = 0.4 if ref.startswith("C") and ref in ANCHOR else GAP
            fp = fps[ref]
            ax, ay = pcbnew.ToMM(apad.GetPosition().x), pcbnew.ToMM(apad.GetPosition().y)
            target_net = apad.GetNetname()
            best = None
            for rad in [i * 0.25 for i in range(2, 160)]:
                if best and best[0] < rad - 3:
                    break
                n_pts = max(8, int(2 * math.pi * rad / 0.5))
                for k in range(n_pts):
                    px = ax + rad * math.cos(2 * math.pi * k / n_pts)
                    py = ay + rad * math.sin(2 * math.pi * k / n_pts)
                    for rot in (0, 90, 180, 270):
                        fp.SetOrientationDegrees(rot)
                        fp.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
                        r = crt_rect(fp)
                        blocked_by = forbid + channels
                        if not inside_board(r) or any(overlap(r, f) for f in blocked_by):
                            continue
                        if any(overlap(r, q, gap_ref) for q in placed.values()):
                            continue
                        mine = [p for p in fp.Pads() if p.GetNetname() == target_net] or list(fp.Pads())
                        d = min(math.hypot(pcbnew.ToMM(p.GetPosition().x) - ax, pcbnew.ToMM(p.GetPosition().y) - ay)
                                for p in mine)
                        if best is None or d < best[0] - 1e-6:
                            best = (d, px, py, rot)
            if best is None:
                near = {k: [round(v, 2) for v in world.to_w(r_[0], r_[3]) + world.to_w(r_[2], r_[1])]
                        for k, r_ in placed.items() if abs(r_[0] - ax) < 12 and abs(r_[1] - ay) < 12}
                raise SystemExit(f"no spot for {ref} near {aref} (pad at world {world.to_w(ax, ay)}); "
                                 f"neighbours (world x0,y0,x1,y1): {near}")
            _, px, py, rot = best
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
            placed[ref] = crt_rect(fp)
        pending = left
    if pending:
        raise SystemExit(f"unplaced: {pending}")

    # ---- outline, holes, keep-outs
    corners = [(kx0, ky0), (kx1, ky0), (kx1, ky1), (kx0, ky1)]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        s.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
    all_cu = pcbnew.LSET.AllCuMask(4)
    for i, (hx, hy) in enumerate(world.HOLES):
        c = K(hx, hy)
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetCenter(c)
        s.SetEnd(pcbnew.VECTOR2I(c.x + mm(world.HOLE_D / 2), c.y))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
        for layer, width in ((pcbnew.F_SilkS, 0.15), (pcbnew.F_Fab, 0.1)):
            s = pcbnew.PCB_SHAPE(board)
            s.SetShape(pcbnew.SHAPE_T_CIRCLE)
            s.SetCenter(c)
            s.SetEnd(pcbnew.VECTOR2I(c.x + mm(world.HOLE_KEEPOUT_D / 2), c.y))
            s.SetLayer(layer)
            s.SetWidth(mm(width))
            board.Add(s)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetLayerSet(all_cu)
        z.SetZoneName(f"hole{i + 1}_keepout")
        for flag in ("Tracks", "Vias", "Pads", "ZoneFills", "Footprints"):
            getattr(z, f"SetDoNotAllow{flag}")(True)
        ol = z.Outline()
        ol.NewOutline()
        r = world.HOLE_KEEPOUT_D / 2 / math.cos(math.pi / 64)     # circumscribed: the polygon contains the circle
        for k in range(64):
            ol.Append(c.x + mm(r * math.cos(2 * math.pi * k / 64)), c.y + mm(r * math.sin(2 * math.pi * k / 64)))
        board.Add(z)

    # ---- silk: board ID, SELV mark, revision
    def text(s, x, y, size, layer=pcbnew.F_SilkS, thick=None):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(thick or max(0.15, size * 0.15)))
        t.SetPosition(K(x, y))
        board.Add(t)
        return t
    for s_, x_, y_, h_ in floorplan.SILK:
        text(s_, x_, y_, h_)
    s_, x_, y_, h_ = floorplan.SILK[0]
    text("TEMPER CONTROLLER  SELV", x_, y_, 2.0, pcbnew.B_SilkS).SetMirrored(True)

    # ---- plane fan-out (a via beside every SMD pad on selv_gnd / v3v3)
    import fanout
    n_fan, fan_missed = fanout.run(board, forbidden_rects(), (kx0, ky0, kx1, ky1))
    if fan_missed:
        raise SystemExit(f"fan-out found no via spot for {fan_missed}")

    pcbnew.SaveBoard(str(PCB / f"{NAME}.kicad_pcb"), board)
    placement = {}
    for ref, fp in sorted(fps.items()):
        p = fp.GetPosition()
        X, Y = world.to_w(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
        placement[ref] = [round(X, 3), round(Y, 3), round(fp.GetOrientationDegrees(), 1)]
    (PCB / "placement.json").write_text(json.dumps(placement, indent=1) + "\n")
    print(json.dumps({"footprints": len(fps), "nets": len(nets), "auto_placed": len(comps) - len(PLACE),
                      "plane_fanout_vias": n_fan}))


if __name__ == "__main__":
    main()
