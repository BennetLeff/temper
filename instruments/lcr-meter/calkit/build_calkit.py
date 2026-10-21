#!/usr/bin/env python3
"""Temper LCR calibration / check-standard card (cal kit r1): native KiCad board generator.

Run with KiCad's bundled Python (pcbnew), then ``rebuild.sh`` runs DRC and the JLC exports:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 build_calkit.py

Every track below is a hand-specified coordinate list.  No autorouter is used or invoked.

Geometry (board mm, origin = top-left outline corner, +y down, as KiCad draws):
  * 38 x 190 mm, 2 layers, 1.6 mm FR-4, ENIG.  One standard per row; rows are identical in
    lead dress: an H Kelvin tab on the left edge, an L Kelvin tab on the right edge.
  * A Kelvin tab is a gold land on BOTH faces of the card edge: the top land (F.Cu) and the
    bottom land (B.Cu) are separate copper that meet only at the component pad.  A Kelvin clip's
    two insulated jaws therefore land on two separate paths (either jaw up), so the clip contact
    resistance and the tab/trace copper are outside the 4-wire reference plane, which is the
    component pad (for the SHORT: one point at the middle of its copper bar).
  * Top path: F.Cu 1.0 mm track tab -> pad.  Bottom path: B.Cu 1.0 mm track directly under the
    top path, a 45-degree jog, a via just off the pad, and a short F.Cu stub into the pad.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

import pcbnew as k

k.KIID.SeedGenerator(26011)
ROOT = Path(__file__).resolve().parent
LIBS = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
LOCAL = ROOT / 'CalKit.pretty'
NS = uuid.UUID('7d0c5f8e-2b8e-4f57-9c43-c41b0a1c0001')

# ------------------------------------------------------------------ card geometry (mm)
X0, Y0 = 100.0, 100.0          # outline top-left in KiCad board coordinates
W = 38.0                       # card width (H tab edge to L tab edge)
TAB_DEPTH = 10.0               # tab land from the card edge inward
TAB_PULLBACK = 0.5             # copper pulled back from the milled edge
TAB_H = 8.0                    # tab land height along the edge (clip jaw is ~4-7 mm wide)
PITCH = 12.0                   # row pitch: 8 mm land + 4 mm bare FR-4 between neighbours
FIRST_ROW = 18.0               # first row centre below the top edge (header above)
TRACK = 1.0                    # both Kelvin paths are equal: either jaw may be force or sense
STUB = 0.6                     # F.Cu stub from the bottom-path via into the pad
VIA_D, VIA_DRILL = 0.6, 0.3    # JLC standard 2-layer via
CX = W / 2                     # component column
T_IN = TAB_DEPTH - 2.0         # track start inside the tab land (left); mirrored on the right

# ------------------------------------------------------------------ standards (one per row)
# lcsc/mpn/manufacturer from the JLC parts API, snapshot in jlc-parts-<date>.json.
RES = 'Resistor_SMD:R_0805_2012Metric'
CAP = 'Capacitor_SMD:C_1206_3216Metric'
IND = 'Inductor_SMD:L_TDK_SLF12575'
PART = {
    '20R':   ('20 Ω',    'YAGEO', 'RT0805BRB0720RL',    'C723660',   RES, '±0.1 % ±10 ppm/°C thin film 0805'),
    '51R':   ('51 Ω',    'RESI',  'PTFR0805Q51R0N9',    'C52677567', RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '100R':  ('100 Ω',   'RESI',  'PTFR0805Q100RN9',    'C7603205',  RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '1K':    ('1 kΩ',    'RESI',  'PTFR0805Q1K00N9',    'C7603207',  RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '2K':    ('2 kΩ',    'RESI',  'PTFR0805Q2K00N9',    'C7603208',  RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '4K99':  ('4.99 kΩ', 'RESI',  'PTFR0805Q4K99N9',    'C7603209',  RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '20K':   ('20 kΩ',   'RESI',  'PTFR0805Q20K0N9',    'C7603210',  RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '49K9':  ('49.9 kΩ', 'RESI',  'PTFR0805Q49K9N9',    'C47116076', RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '100K':  ('100 kΩ',  'RESI',  'PTFR0805Q100KN9',    'C23067433', RES, '±0.02 % ±10 ppm/°C thin film 0805'),
    '100N':  ('100 nF',  'Murata', 'GCM31C5C1H104FA16L', 'C1864297', CAP, 'C0G ±1 % 50 V 1206'),
    '47U':   ('47 µH',   'TDK',   'SLF12575T-470M2R7-PF', 'C81468',  IND, 'ferrite-shielded drum, 63 mΩ DCR, ±20 %'),
}
# (row kind, refs, part key, front label, front note, back label)
ROWS = [
    ('short', [],     None,   'SHORT',         '0 Ω AT BAR CENTRE',   'SHORT'),
    ('open',  ['R10'], None,  'OPEN',          'LANDS ONLY, NO PART', 'OPEN'),
    ('two',   ['R1'], '20R',  '20Ω  STD1',     'R1  100Ω RANGE',      'R1'),
    ('two',   ['R2'], '51R',  '51Ω  CHECK',    'R2  100Ω RANGE',      'R2'),
    ('two',   ['R3'], '100R', '100Ω  STD2',    'R3  100Ω RANGE',      'R3'),
    ('two',   ['R4'], '1K',   '1kΩ  STD1',     'R4  5kΩ RANGE',       'R4'),
    ('two',   ['R5'], '2K',   '2kΩ  CHECK',    'R5  5kΩ RANGE',       'R5'),
    ('two',   ['R6'], '4K99', '4.99kΩ  STD2',  'R6  5kΩ RANGE',       'R6'),
    ('two',   ['R7'], '20K',  '20kΩ  STD1',    'R7  100kΩ RANGE',     'R7'),
    ('two',   ['R8'], '49K9', '49.9kΩ  CHECK', 'R8  100kΩ RANGE',     'R8'),
    ('two',   ['R9'], '100K', '100kΩ  STD2',   'R9  100kΩ RANGE',     'R9'),
    ('two',   ['C1'], '100N', '100nF C0G 1%',  'C1  LOW-LOSS CHECK',  'C1'),
    ('bank',  ['C2', 'C3', 'C4', 'C5', 'C6'], '100N', '0.5µF  5×100nF', 'C2-C6  BANK CLASS', 'C2-6'),
    ('two',   ['L1'], '47U',  '47µH  L CHECK', 'L1  SHIELDED',        'L1'),
]
L_ROW_EXTRA = 3.0               # the 12.5 mm inductor row gets extra pitch on both sides
H = FIRST_ROW + PITCH * (len(ROWS) - 1) + 2 * L_ROW_EXTRA + 13.0   # card height


def row_y(i: int) -> float:
    y = FIRST_ROW + PITCH * i
    return y + 2 * L_ROW_EXTRA if ROWS[i][0] == 'two' and ROWS[i][2] == '47U' else y


def mm(v: float) -> int:
    return k.FromMM(v)


def P(x: float, y: float) -> k.VECTOR2I:
    """Card coordinates (relative to the outline's top-left corner) to board IU."""
    return k.VECTOR2I(mm(X0 + x), mm(Y0 + y))


def uid(s: str) -> str:
    return str(uuid.uuid5(NS, s))


# ------------------------------------------------------------------ footprint library
LOCAL.mkdir(exist_ok=True)
for fp in {RES, CAP, IND}:
    lib, name = fp.split(':')
    shutil.copyfile(LIBS / f'{lib}.pretty' / f'{name}.kicad_mod', LOCAL / f'{name}.kicad_mod')
# OPEN standard: the 0805 land pattern with no paste aperture (no part, no solder blob).
open_fp = k.FootprintLoad(str(LOCAL), 'R_0805_2012Metric')
open_fp.SetFPID(k.LIB_ID('CalKit', 'R_0805_2012Metric_OpenStandard'))
open_fp.SetLibDescription('0805 land pattern without paste: OPEN calibration standard (no part fitted)')
for pad in open_fp.Pads():
    layers = pad.GetLayerSet()
    layers.RemoveLayer(k.F_Paste)
    pad.SetLayerSet(layers)
k.FootprintSave(str(LOCAL), open_fp)
open_fp_name = 'R_0805_2012Metric_OpenStandard'


def make_tab_footprint() -> None:
    """Kelvin tab: pad 1 = top-face gold land (F.Cu), pad 2 = bottom-face land (B.Cu)."""
    f = k.FOOTPRINT(None)
    f.SetFPID(k.LIB_ID('CalKit', 'KelvinTab_9.5x8'))
    f.SetLibDescription('Kelvin clip land on both faces of a card edge; faces are separate copper '
                        'joined only at the standard. Origin = land centre.')
    f.SetAttributes(k.FP_SMD | k.FP_EXCLUDE_FROM_BOM | k.FP_EXCLUDE_FROM_POS_FILES)
    w = TAB_DEPTH - TAB_PULLBACK
    for num, cu, mask in [('1', k.F_Cu, k.F_Mask), ('2', k.B_Cu, k.B_Mask)]:
        pad = k.PAD(f)
        pad.SetNumber(num)
        pad.SetAttribute(k.PAD_ATTRIB_SMD)
        pad.SetShape(k.F_Cu, k.PAD_SHAPE_RECT)
        pad.SetSize(k.F_Cu, k.VECTOR2I(mm(w), mm(TAB_H)))
        ls = k.LSET()
        ls.AddLayer(cu)
        ls.AddLayer(mask)
        pad.SetLayerSet(ls)
        pad.SetPosition(k.VECTOR2I(0, 0))
        f.Add(pad)
    for layer in (k.F_CrtYd, k.B_CrtYd):
        s = k.PCB_SHAPE(f)
        s.SetShape(k.SHAPE_T_RECT)
        s.SetStart(k.VECTOR2I(mm(-w / 2 - 0.25), mm(-TAB_H / 2 - 0.25)))
        s.SetEnd(k.VECTOR2I(mm(w / 2 + 0.25), mm(TAB_H / 2 + 0.25)))
        s.SetLayer(layer)
        s.SetWidth(mm(0.05))
        f.Add(s)
    f.Reference().SetLayer(k.F_Fab)
    f.Value().SetLayer(k.F_Fab)
    k.FootprintSave(str(LOCAL), f)


make_tab_footprint()
(ROOT / 'fp-lib-table').write_text(
    '(fp_lib_table (version 7) (lib (name "CalKit") (type "KiCad") (uri "${KIPRJMOD}/CalKit.pretty") '
    '(options "") (descr "Vendored KiCad 10 footprints plus the Kelvin tab")))\n')

# ------------------------------------------------------------------ board
b = k.BOARD()
b.SetCopperLayerCount(2)
ds = b.GetDesignSettings()
ds.SetAuxOrigin(P(0, H))            # drill/place origin: lower-left outline corner
ds.m_SolderMaskMargin = mm(0.05)
ds.m_MinClearance = mm(0.2)
ds.m_TrackMinWidth = mm(0.2)
ds.m_ViasMinSize = mm(0.5)
ds.m_MinThroughDrill = mm(0.3)
ds.m_TentViasFront = True
ds.m_TentViasBack = True

nets: dict[str, k.NETINFO_ITEM] = {}


def net(name: str) -> k.NETINFO_ITEM:
    if name not in nets:
        n = k.NETINFO_ITEM(b, name)
        b.Add(n)
        nets[name] = n
    return nets[name]


def track(points, layer, width, netname):
    for a, c in zip(points, points[1:]):
        t = k.PCB_TRACK(b)
        t.SetStart(P(*a))
        t.SetEnd(P(*c))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        b.Add(t)


def via(x, y, netname):
    v = k.PCB_VIA(b)
    v.SetPosition(P(x, y))
    v.SetViaType(k.VIATYPE_THROUGH)
    v.SetLayerPair(k.F_Cu, k.B_Cu)
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(net(netname))
    b.Add(v)


def text(s, x, y, size, layer=k.F_SilkS, thick=0.15, justify=None):
    t = k.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetTextSize(k.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick))
    t.SetLayer(layer)
    if layer == k.B_SilkS:
        t.SetMirrored(True)
    if justify == 'left':
        t.SetHorizJustify(k.GR_TEXT_H_ALIGN_LEFT)
    b.Add(t)


def silk_line(a, c, layer=k.F_SilkS, width=0.15):
    s = k.PCB_SHAPE(b)
    s.SetShape(k.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*c))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    b.Add(s)


fps: dict[str, k.FOOTPRINT] = {}
tab_count = 0


def place(ref, fpname, x, y, angle, value, netmap, part=None, dnp=False):
    f = k.FootprintLoad(str(LOCAL), fpname)
    f.SetFPID(k.LIB_ID('CalKit', fpname))
    f.SetReference(ref)
    f.SetValue(value)
    f.SetPosition(P(x, y))
    f.SetOrientationDegrees(angle)
    f.Reference().SetLayer(k.F_Fab)
    f.Reference().SetTextSize(k.VECTOR2I(mm(0.8), mm(0.8)))
    f.Reference().SetTextThickness(mm(0.12))
    if part:
        _, man, mpn, lcsc, _, spec = part
        for name, val in {'MPN': mpn, 'Manufacturer': man, 'LCSC': lcsc, 'Spec': spec}.items():
            f.SetField(name, val)
            f.GetField(name).SetVisible(False)
    if dnp:
        f.SetAttributes(f.GetAttributes() | k.FP_EXCLUDE_FROM_BOM | k.FP_EXCLUDE_FROM_POS_FILES | k.FP_DNP)
    b.Add(f)
    for pad in f.Pads():
        if pad.GetNumber() in netmap:
            pad.SetNet(net(netmap[pad.GetNumber()]))
    fps[ref] = f
    return f


def pad_xy(ref, num):
    pad = next(p for p in fps[ref].Pads() if p.GetNumber() == num)
    return round(k.ToMM(pad.GetPosition().x) - X0, 4), round(k.ToMM(pad.GetPosition().y) - Y0, 4)


def tabs(y, hnet, lnet):
    global tab_count
    for x, n in [((TAB_PULLBACK + TAB_DEPTH) / 2, hnet), (W - (TAB_PULLBACK + TAB_DEPTH) / 2, lnet)]:
        tab_count += 1
        place(f'TAB{tab_count}', 'KelvinTab_9.5x8', x, y, 0, 'Kelvin tab', {'1': n, '2': n})


def kelvin_side(y, pad, side, netname, jog, stub_dir=+1):
    """Both Kelvin paths of one side.  pad = (x, y) of the land centre; side = -1 (H) / +1 (L)."""
    tx = T_IN if side < 0 else W - T_IN
    px, py = pad
    assert abs(py - y) < 1e-6, 'two-terminal lands sit on the row line'
    track([(tx, y), (px, y)], k.F_Cu, TRACK, netname)
    vy = py + stub_dir * jog
    track([(tx, y), (px + side * jog, y), (px, vy)], k.B_Cu, TRACK, netname)
    via(px, vy, netname)
    track([(px, vy), (px, py)], k.F_Cu, STUB, netname)


refs_used = []
for i, (kind, refs, key, label, note, back) in enumerate(ROWS):
    y = row_y(i)
    tag = back.replace('-', '_') if kind != 'two' else refs[0]
    hn, ln = f'{tag}_H', f'{tag}_L'
    if kind == 'short':
        hn = ln = 'SHORT'
    tabs(y, hn, ln)
    if kind == 'short':
        # Force path: tab -> 1.4 mm bar (an 0805 land pitch long) -> tab, all F.Cu.
        track([(T_IN, y), (CX - 0.9125, y)], k.F_Cu, TRACK, 'SHORT')
        track([(CX - 0.9125, y), (CX + 0.9125, y)], k.F_Cu, 1.4, 'SHORT')
        track([(CX + 0.9125, y), (W - T_IN, y)], k.F_Cu, TRACK, 'SHORT')
        # Bottom paths meet the bar at one point (its centre, from opposite sides): V = 0 there.
        track([(T_IN, y), (CX - 2.0, y), (CX, y + 2.0)], k.B_Cu, TRACK, 'SHORT')
        track([(W - T_IN, y), (CX + 2.0, y), (CX, y - 2.0)], k.B_Cu, TRACK, 'SHORT')
        for vy in (y + 2.0, y - 2.0):
            via(CX, vy, 'SHORT')
            track([(CX, vy), (CX, y)], k.F_Cu, STUB, 'SHORT')
    elif kind in ('open', 'two'):
        ref = refs[0]
        if kind == 'open':
            place(ref, open_fp_name, CX, y, 0, 'OPEN (no part)', {'1': hn, '2': ln}, dnp=True)
        else:
            part = PART[key]
            fpname = part[4].split(':')[1]
            place(ref, fpname, CX, y, 0, part[0], {'1': hn, '2': ln}, part)
            refs_used.append(ref)
        jog = {'R_0805_2012Metric': 2.0, 'R_0805_2012Metric_OpenStandard': 2.0,
               'C_1206_3216Metric': 2.2, 'L_TDK_SLF12575': 3.0}[str(fps[ref].GetFPID().GetLibItemName())]
        kelvin_side(y, pad_xy(ref, '1'), -1, hn, jog)
        kelvin_side(y, pad_xy(ref, '2'), +1, ln, jog)
    elif kind == 'bank':
        part = PART[key]
        xs = [CX + (j - 2) * 2.6 for j in range(5)]
        for ref, x in zip(refs, xs):
            place(ref, 'C_1206_3216Metric', x, y, 90, part[0], {}, part)
            refs_used.append(ref)
            pads = sorted(fps[ref].Pads(), key=lambda p: p.GetPosition().y)
            pads[0].SetNet(net(hn))       # upper land -> H rail
            pads[1].SetNet(net(ln))       # lower land -> L rail
        yt = pad_xy(refs[0], next(p.GetNumber() for p in fps[refs[0]].Pads() if p.GetNetname() == hn))[1]
        yb = pad_xy(refs[0], next(p.GetNumber() for p in fps[refs[0]].Pads() if p.GetNetname() == ln))[1]
        # Anti-parallel feed: H enters the top rail at the left end, L leaves the bottom rail at the
        # right end, so every capacitor sees the same rail length.  Senses at the rail centres.
        track([(xs[0], yt), (xs[-1], yt)], k.F_Cu, 1.6, hn)
        track([(xs[0], yb), (xs[-1], yb)], k.F_Cu, 1.6, ln)
        track([(T_IN, y), (CX - 7.5, y), (CX - 6.0, yt), (xs[0], yt)], k.F_Cu, TRACK, hn)
        track([(W - T_IN, y), (CX + 7.5, y), (CX + 6.0, yb), (xs[-1], yb)], k.F_Cu, TRACK, ln)
        vt, vb = yt - 2.0, yb + 2.0
        track([(T_IN, y), (11.0, y), (11.0 + (y - vt), vt), (CX, vt)], k.B_Cu, TRACK, hn)
        track([(W - T_IN, y), (W - 11.0, y), (W - 11.0 - (vb - y), vb), (CX, vb)], k.B_Cu, TRACK, ln)
        for vy, ry, n in [(vt, yt, hn), (vb, yb, ln)]:
            via(CX, vy, n)
            track([(CX, vy), (CX, ry)], k.F_Cu, STUB, n)
    # Labels: nominal value above, role below (front); write-in field for the characterised value (back).
    dy = 7.6 if key == '47U' else 4.7
    text(label, CX, y - dy, 1.2, thick=0.18)
    text(note, CX, y + dy, 0.8, thick=0.12)
    text(f'{back} = __________', CX, y - dy, 1.0, k.B_SilkS)
    text('@ ____ °C', CX, y + dy, 0.9, k.B_SilkS)

# Header / footer.
text('TEMPER LCR CAL KIT  r1', W / 2, 3.0, 1.5, thick=0.22)
text('H <--  4TP KELVIN CLIPS  --> L', W / 2, 6.2, 1.0)
text('EITHER JAW UP · FULLY ON GOLD', W / 2, 8.6, 0.8, thick=0.12)
text('S/N ______   DMM ____________', W / 2, 3.0, 1.0, k.B_SilkS)
text('DATE ________  BY ____________', W / 2, 6.2, 1.0, k.B_SilkS)
text('R = 4-WIRE OCOMP, SEE CHARACTERIZE.md', W / 2, 8.6, 0.8, k.B_SilkS, thick=0.12)
text('HANDLE BY EDGES · KEEP AWAY FROM METAL', W / 2, H - 2.0, 0.8, thick=0.12)
text('github temper / instruments/lcr-meter/calkit', W / 2, H - 2.0, 0.8, k.B_SilkS, thick=0.12)
for i in range(len(ROWS) - 1):     # separators between rows across the component column
    yy = (row_y(i) + row_y(i + 1)) / 2
    silk_line((TAB_DEPTH + 0.6, yy), (W - TAB_DEPTH - 0.6, yy))

# Outline.
for a, c in [((0, 0), (W, 0)), ((W, 0), (W, H)), ((W, H), (0, H)), ((0, H), (0, 0))]:
    s = k.PCB_SHAPE(b)
    s.SetShape(k.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*c))
    s.SetLayer(k.Edge_Cuts)
    s.SetWidth(mm(0.05))
    b.Add(s)

pcb = ROOT / 'calkit.kicad_pcb'
k.SaveBoard(str(pcb), b)
idx = iter(range(100000))
pcb.write_text(re.sub(r'\(uuid "[^"]+"\)', lambda _: f'(uuid "{uid("pcb-item-" + str(next(idx)))}")',
                      pcb.read_text()))
pro = {'meta': {'filename': 'calkit.kicad_pro', 'version': 1},
       'board': {'design_settings': {'rules': {
           'min_clearance': 0.2, 'min_track_width': 0.2, 'min_via_diameter': 0.5,
           'min_via_annular_width': 0.1, 'min_through_hole_diameter': 0.3,
           'min_copper_edge_clearance': 0.4, 'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.5,
           'min_silk_clearance': 0.0, 'min_text_height': 0.8, 'min_text_thickness': 0.12},
           'defaults': {'copper_line_width': 1.0}, 'rule_severities': {}}, 'layer_presets': []},
       'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.2, 'track_width': 1.0,
                                     'via_diameter': VIA_D, 'via_drill': VIA_DRILL,
                                     'microvia_diameter': 0.3, 'microvia_drill': 0.1,
                                     'diff_pair_width': 0.2, 'diff_pair_gap': 0.2,
                                     'diff_pair_via_gap': 0.25}], 'meta': {'version': 3}}}
(ROOT / 'calkit.kicad_pro').write_text(json.dumps(pro, indent=2) + '\n')

# Machine-readable placement / part record for the packaging step.
record = {'card_mm': [W, H], 'rows': [], 'parts': {}}
for i, (kind, refs, key, label, note, back) in enumerate(ROWS):
    record['rows'].append({'row': i, 'kind': kind, 'refs': refs, 'part': key, 'label': label,
                           'y_from_top_mm': row_y(i)})
for ref in refs_used:
    f = fps[ref]
    key = next(r[2] for r in ROWS if ref in r[1])
    nominal, man, mpn, lcsc, fp, spec = PART[key]
    pos = f.GetPosition()
    record['parts'][ref] = {'value': nominal, 'manufacturer': man, 'mpn': mpn, 'lcsc': lcsc,
                            'footprint': fp, 'spec': spec,
                            'x_mm': round(k.ToMM(pos.x) - X0, 4),
                            'y_up_mm': round(H - (k.ToMM(pos.y) - Y0), 4),
                            'rot_deg': f.GetOrientationDegrees()}
(ROOT / 'build').mkdir(exist_ok=True)
(ROOT / 'build' / 'placement.json').write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
print(f'card {W} x {H} mm, {len(ROWS)} rows, {len(refs_used)} placed parts, {tab_count} tabs, {len(nets)} nets')
