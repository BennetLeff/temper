"""Layout audit numbers quoted in docs/rev-d-audit.md (read-only).

Run with KiCad's bundled Python:  <kicad-python> cad/tools/audit_layout.py [OUT.json]
Reports, from the native board:
  - per IC supply pin: the three nearest capacitors on the same net (pad-to-pad centre
    distance) and the distance from each capacitor's other pad to the nearest via on its net;
  - per exposed/thermal pad: vias inside the pad;
  - placement span and courtyard area per schematic sheet;
  - switcher and LDO support-part distances, and trace length of the regulator feedback nets.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
MM = 1e-6
board = k.LoadBoard(str(ROOT / 'temper-lcr.kicad_pcb'))
design = json.loads((ROOT / 'design.json').read_text())
routing = json.loads((ROOT / 'routing.json').read_text())
SUPPLY = {'3V3', '1V1', '5V', '5VA', '12V', '-12V', '3V3_DDS', 'ADC_REFA', 'ADC_REFB', 'ADC_CM',
          'ADC_REFOUT', 'LDOIN_P', 'LDOIN_N', 'RAW_P', 'RAW_N', 'CONV_VIN', 'DDS_CAP'}
ICS = ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'U8', 'U9', 'U10', 'U11', 'U12', 'U13']

pads = [(f.GetReference(), p.GetNumber(), p.GetNetname(), p.GetPosition().x * MM, p.GetPosition().y * MM)
        for f in board.GetFootprints() for p in f.Pads()]
vias = [t for t in board.GetTracks() if isinstance(t, k.PCB_VIA)]
via_xy = [(v.GetPosition().x * MM, v.GetPosition().y * MM, v.GetNetname()) for v in vias]
caps = {}
for ref, num, net, x, y in pads:
    if ref.startswith('C'):
        caps.setdefault(ref, {})[num] = (net, x, y)

decoupling = {}
for ic in ICS:
    for ref, num, net, x, y in pads:
        if ref != ic or net not in SUPPLY:
            continue
        near = []
        for c, pp in caps.items():
            for cnet, cx, cy in pp.values():
                if cnet != net:
                    continue
                other = [q for q in pp.values() if q[0] != net]
                ret = min((math.hypot(other[0][1] - vx, other[0][2] - vy) for vx, vy, vn in via_xy
                           if other and vn == other[0][0]), default=None)
                near.append({'cap': c, 'mm': round(math.hypot(x - cx, y - cy), 2),
                             'return_net': other[0][0] if other else None,
                             'return_via_mm': None if ret is None else round(ret, 2)})
        near.sort(key=lambda n: n['mm'])
        decoupling[f'{ic}.{num}'] = {'net': net, 'nearest': near[:3]}

exposed = {}
for ref in ICS:
    f = board.FindFootprintByReference(ref)
    for p in f.Pads():
        bb = p.GetBoundingBox()
        if bb.GetWidth() * MM > 1.4 and bb.GetHeight() * MM > 1.4:
            inside = [v for v in vias if p.HitTest(v.GetPosition())]
            exposed[f'{ref}.{p.GetNumber()}'] = {'net': p.GetNetname(), 'vias_in_pad': len(inside),
                                                 'drills_mm': [round(v.GetDrill() * MM, 2) for v in inside]}

sheet = {p['ref']: p.get('sheet') for p in design['parts']}
area, span = Counter(), {}
edge = board.GetBoardEdgesBoundingBox()
for f in board.GetFootprints():
    cy = f.GetCourtyard(k.F_CrtYd)
    s = sheet.get(f.GetReference(), 'mechanical')
    area[s] += cy.Area() * MM * MM if cy.OutlineCount() else 0
    x, y = f.GetPosition().x * MM, f.GetPosition().y * MM
    lo = span.get(s, [1e9, 1e9, -1e9, -1e9])
    span[s] = [min(lo[0], x), min(lo[1], y), max(lo[2], x), max(lo[3], y)]
board_mm2 = edge.GetWidth() * edge.GetHeight() * MM * MM
placement = {'board_mm': [round(edge.GetWidth() * MM, 2), round(edge.GetHeight() * MM, 2)],
             'courtyard_fraction': round(sum(area.values()) / board_mm2, 3),
             'sheets': {s: {'courtyard_mm2': round(area[s]), 'centroid_span_mm': [round(span[s][2] - span[s][0]),
                                                                              round(span[s][3] - span[s][1])]}
                        for s in area}}

pos = {p['ref']: p['pcb'][:2] for p in design['parts']}
support = {ic: {r: round(math.dist(pos[ic], pos[r]), 1) for r in refs} for ic, refs in {
    'U11': ['C93', 'C94', 'C95', 'C96', 'C97', 'R85', 'R86'],
    'U12': ['C98', 'C99', 'C100', 'C101', 'C102', 'R87', 'R88', 'R89'],
    'U13': ['L1', 'L2', 'D2', 'D3', 'C82', 'C83', 'C84', 'C87', 'C88', 'R81', 'R82', 'R83', 'R84'],
    'D2': ['C89', 'C90'], 'D3': ['C91', 'C92']}.items()}
fb_len = {}
for net in ('REGP_FB', 'REGN_FB', 'REGN_DIV', 'REGP_NR', 'REGN_NR', 'CONV_FBP', 'CONV_FBN'):
    total = 0.0
    for t in routing['tracks']:
        if t['net'] == net:
            pts = [pos[p.split('.')[0]] if isinstance(p, str) else p for p in t['points']]
            total += sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    fb_len[net] = round(total, 1)

out = {'board_sha256_hint': 'see validation/independent-verification-rev-d.json',
       'decoupling': decoupling, 'exposed_pads': exposed, 'placement': placement,
       'support_part_distance_mm': support, 'feedback_trace_mm': fb_len}
dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / 'validation/layout-audit-rev-d.json'
dest.write_text(json.dumps(out, indent=1) + '\n')
print(f'{len(decoupling)} supply pins, {len(exposed)} exposed pads -> {dest}')
