"""Supply copper against its worst-case current: every track segment and via of the power nets.

python3 validation/power-spurs/current_check.py      -> current_check.json (exit 1 on any FAIL)

Ampacity: IPC-2152 (2009), the generic chart (Figure 5-2: 0.070 in polyimide board, still air, no plane,
3 oz copper), through the least-squares power fit published with the smps.us PCB calculator
(https://smps.us/pcb-calculator.html, fitted between 2 and 100 C rise; its check point is 10 A at 20 C ->
513 mil^2 against the chart's 500):
    A [mil^2] = (117.555 * dT^-0.913 + 1.15) * I^(0.84 * dT^-0.108 + 1.159),   I in A rms, dT in C.
The same area is used on every layer, as IPC-2152 recommends (internal and external alike).  No modifier is
taken for copper weight, board thickness or planes; the board's solid In1 plane would only lower the rise.
Rise limit 10 C.  Copper: outer 35 um (1 oz, before plating), inner 15.2 um (0.5 oz), JLC04161H-7628
(layout-parasitics/common.py).  A via is a plated barrel, pi * drill * 18 um (copper.py VIA_PLATING_MM,
IPC-6012 class 2 thin-area minimum), treated as a conductor of that cross-section.

Worst current per net (the most the source can deliver into a fault downstream):
    USB_VBUS, 5V   1.17 A  TPS2553 current limit maximum with R110 at -1 % (regulator_check.json)
    RAW_P, 12V     0.50 A  TPS7A4901 ILIM maximum (sources/ti/TPS7A49.txt, 7.5: 220 / 309 / 500 mA)
    RAW_N, -12V    0.50 A  TPS7A3001 ICL maximum (sources/ti/TPS7A30.txt, 7.5: 220 / 330 / 500 mA)
    3V3            0.60 A  AP2112K-3.3 rated output (sources/new/AP2112.txt; no ILIM maximum is given, its
                           foldback limit returns the short-circuit current to 50 mA)
Each net is solved as a resistor network (segments rho L / (w t), via barrels, lands as near-zero links
between the copper they touch) once per fault case: the source part delivers the net's worst current into one
load part at a time (every pin of a part tied together, as inside the part), a resistor load taking only
min(worst, V / R) and capacitors, test pads and fiducials none.  A segment or via is charged the largest
current it carries in any case, so a branch carries the full current only if a load on it could fault.
For USB_VBUS each receptacle VBUS pin is a separate source case (the plug may make contact on one pin only).
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'cad' / 'tools'))
import predrc  # noqa: E402

DT = 10.0
T_MM = {'F.Cu': 0.035, 'B.Cu': 0.035, 'In1.Cu': 0.0152, 'In2.Cu': 0.0152}
VIA_PLATING_MM = 0.018
MIL2_PER_MM2 = 1 / 0.0254 ** 2
REG = json.loads((HERE / 'regulator_check.json').read_text())
I_TPS2553 = next(c['value'][2] for c in REG['checks'] if c['item'].startswith('TPS2553 current limit'))
NETS = {'USB_VBUS': (I_TPS2553, 5.5, 'TPS2553 ILIM max'), '5V': (I_TPS2553, 5.5, 'TPS2553 ILIM max'),
        'RAW_P': (0.50, 14.9, 'TPS7A49 ILIM max'), '12V': (0.50, 12.4, 'TPS7A49 ILIM max'),
        'RAW_N': (0.50, 14.8, 'TPS7A30 ICL max'), '-12V': (0.50, 12.2, 'TPS7A30 ICL max'),
        '3V3': (0.60, 3.35, 'AP2112K rating')}


def area_mil2(i, dt=DT):
    return (117.555 * dt ** -0.913 + 1.15) * i ** (0.84 * dt ** -0.108 + 1.159)


def width_mm(i, layer):
    return area_mil2(i) / MIL2_PER_MM2 / T_MM[layer]


def via_amps(drill, dt=DT):
    a = math.pi * drill * VIA_PLATING_MM * MIL2_PER_MM2
    return (a / (117.555 * dt ** -0.913 + 1.15)) ** (1 / (0.84 * dt ** -0.108 + 1.159))


def ohms(value):
    v = value.split()[0].upper().replace('Ω', '')
    m = re.match(r'^([\d.]+)([RKM]?)([\d]*)$', v)
    if not m:
        return None
    a, unit, b = m.groups()
    x = float(a + ('.' + b if b else ''))
    return x * {'': 1, 'R': 1, 'K': 1e3, 'M': 1e6}[unit]


SOURCE = {'USB_VBUS': 'J1', '5V': 'U16', 'RAW_P': 'D2', 'RAW_N': 'D3', '12V': 'U11', '-12V': 'U12', '3V3': 'U3'}
NO_LOAD = {'D1': 'SRV05-4 ESD array on VBUS: clamp leakage only'}
RHO = 1.72e-8 * (1 + 0.0039 * 40)        # ohm m at 60 C; only current division depends on it
LINK = 1e-6                              # ohm: land-to-copper and in-part ties
LAND_NECK = 0.35                         # mm: a segment with less than this outside its lands runs on the land


def main():
    import numpy as np
    design = json.loads((ROOT / 'cad/design.json').read_text())
    routing = json.loads((ROOT / 'cad/routing.json').read_text())
    parts = {p['ref']: p for p in design['parts']}
    pads, _, _ = predrc.static_items(design)
    key = lambda layer, p: (layer, round(p[0], 3), round(p[1], 3))
    rows, vrows, fails = [], [], 0
    for net, (inet, vnet, why) in NETS.items():
        edges = []                       # (a, b, ohm, tag)
        segs = []
        npads = [p for p in pads if p['net'] == net]
        raw = []
        for t in routing['tracks']:
            if t['net'] != net:
                continue
            for a, b in zip(t['points'], t['points'][1:]):
                raw.append((t, tuple(a), tuple(b)))
        # a track running across a land without ending in it is joined to the land where it crosses
        for p in npads:
            hit = []
            for k, (t, a, b) in enumerate(raw):
                if t['layer'] in p['layers'] and p['geom'].intersects(LineString([a, b])) and not (
                        p['geom'].covers(Point(a)) or p['geom'].covers(Point(b))):
                    hit.append(k)
            for k in reversed(hit):
                t, a, b = raw[k]
                c = LineString([a, b]).interpolate(LineString([a, b]).project(Point(p['at'])))
                raw[k:k + 1] = [(t, a, (c.x, c.y)), (t, (c.x, c.y), b)]
        # a via on a segment's interior is joined there (KiCad joins a via to any track it touches)
        vias = [v for v in routing['vias'] if v['net'] == net]
        for v in vias:
            c0 = Point(v['at'])
            for k in range(len(raw) - 1, -1, -1):
                t, a, b = raw[k]
                ln = LineString([a, b])
                if ln.distance(c0) < v['diameter'] / 2 and math.dist(a, v['at']) > v['diameter'] / 2 \
                        and math.dist(b, v['at']) > v['diameter'] / 2:
                    c = ln.interpolate(ln.project(c0))
                    raw[k:k + 1] = [(t, a, (c.x, c.y)), (t, (c.x, c.y), b)]
        for t, a, b in raw:
            if True:
                L = math.dist(a, b)
                ohm = RHO * L * 1e-3 / (t['width'] * 1e-3 * T_MM[t['layer']] * 1e-3) + 1e-9
                edges.append((key(t['layer'], a), key(t['layer'], b), ohm, ('seg', len(segs))))
                segs.append((t['layer'], tuple(a), tuple(b), t['width']))
        pts = {n for e in edges for n in e[:2]}
        for k, v in enumerate(vias):
            g = Point(v['at']).buffer(v['diameter'] / 2)
            barrel = RHO * 1.6e-3 / (math.pi * v['drill'] * VIA_PLATING_MM * 1e-6) / 3
            layers = list(T_MM)
            chain = [('vianode', k, l) for l in ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']]
            for x, y in zip(chain, chain[1:]):
                edges.append((x, y, barrel, ('via', k)))
            for n in pts:
                if g.covers(Point(n[1], n[2])):
                    edges.append((('vianode', k, n[0]), n, LINK, None))
        for p in npads:
            pn = ('pad', p['ref'], p['num'])
            for n in pts:
                if n[0] in p['layers'] and p['geom'].buffer(0.001).covers(Point(n[1], n[2])):
                    edges.append((pn, n, LINK, None))
            for k, v in enumerate(vias):
                if p['geom'].intersects(Point(v['at']).buffer(v['diameter'] / 2)):
                    for l in p['layers']:
                        edges.append((pn, ('vianode', k, l), LINK, None))
        by_ref = defaultdict(list)
        for p in npads:
            by_ref[p['ref']].append(('pad', p['ref'], p['num']))
        for ref, pl in by_ref.items():          # pins of one part are one node inside the part
            for x in pl[1:]:
                edges.append((pl[0], x, LINK, None))
        nodes = sorted({n for e in edges for n in e[:2]}, key=str)
        ix = {n: i for i, n in enumerate(nodes)}
        Y = np.zeros((len(nodes), len(nodes)))
        for a, b, ohm, _ in edges:
            g = 1 / ohm
            i, j = ix[a], ix[b]
            Y[i, i] += g; Y[j, j] += g; Y[i, j] -= g; Y[j, i] -= g
        src_ref = SOURCE[net]
        loads = []
        for ref, pl in by_ref.items():
            part = parts.get(ref)
            if ref == src_ref or part is None or part['kind'] == 'C' or ref in NO_LOAD or part.get('assembly') == 'DNP':
                continue
            if pl[0] not in ix:
                print(f'{net}: {ref} has no copper joined to it'); continue
            i = min(inet, vnet / ohms(part['value'])) if part['kind'] == 'R' and ohms(part['value']) else inet
            loads.append((ref, pl[0], i))
        sources = [x for x in by_ref[src_ref]] if net == 'USB_VBUS' else [by_ref[src_ref][0]]
        seg_i = np.zeros(len(segs))
        via_i = np.zeros(len(vias))
        comp_ok = True
        for src in sources:
            for ref, ld, i_load in loads:
                s, d = ix[src], ix[ld]
                keep = [k for k in range(len(nodes)) if k != d]       # ground the load node
                J = np.zeros(len(nodes)); J[s] = i_load
                try:
                    V = np.zeros(len(nodes))
                    V[keep] = np.linalg.solve(Y[np.ix_(keep, keep)] + np.eye(len(keep)) * 1e-12, J[keep])
                except np.linalg.LinAlgError:
                    comp_ok = False
                    continue
                for a, b, ohm, tag in edges:
                    if tag is None:
                        continue
                    cur = abs(V[ix[a]] - V[ix[b]]) / ohm
                    if tag[0] == 'seg':
                        seg_i[tag[1]] = max(seg_i[tag[1]], cur)
                    else:
                        via_i[tag[1]] = max(via_i[tag[1]], cur)
        lands = {}
        for p in npads:
            for l in p['layers']:
                lands.setdefault(l, []).append(p['geom'])
        for n, (layer, a, b, w) in enumerate(segs):
            i = float(min(seg_i[n], inet))
            need = width_mm(i, layer) if i > 1e-6 else 0.0
            out_len = LineString([a, b]).length
            for g in lands.get(layer, []):
                out_len -= LineString([a, b]).intersection(g).length
            ok = w >= need - 1e-6 or out_len < LAND_NECK
            fails += not ok
            rows.append({'net': net, 'layer': layer, 'from': [round(a[0], 3), round(a[1], 3)],
                         'to': [round(b[0], 3), round(b[1], 3)], 'width_mm': w, 'current_a': round(i, 4),
                         'need_mm': round(need, 3), 'status': 'PASS' if ok else 'FAIL'})
        for k, v in enumerate(vias):
            i = float(min(via_i[k], inet))
            cap = via_amps(v['drill'])
            ok = i <= cap + 1e-9
            fails += not ok
            vrows.append({'net': net, 'at': v['at'], 'drill_mm': v['drill'], 'current_a': round(i, 4),
                          'capacity_a': round(cap, 3), 'status': 'PASS' if ok else 'FAIL'})
        if not comp_ok:
            print(f'{net}: singular network (disconnected copper)')
    summary = {}
    for net, (inet, _, why) in NETS.items():
        r = [x for x in rows if x['net'] == net]
        v = [x for x in vrows if x['net'] == net]
        summary[net] = {'worst_current_a': inet, 'basis': why, 'source': SOURCE[net], 'segments': len(r),
                        'need_outer_mm': round(width_mm(inet, 'F.Cu'), 3), 'need_inner_mm': round(width_mm(inet, 'In2.Cu'), 3),
                        'max_segment_current_a': max((x['current_a'] for x in r), default=0),
                        'fail_segments': sum(x['status'] == 'FAIL' for x in r), 'vias': len(v),
                        'max_via_current_a': max((x['current_a'] for x in v), default=0),
                        'fail_vias': sum(x['status'] == 'FAIL' for x in v)}
    out = {'method': __doc__.strip(), 'rise_c': DT, 'via_capacity_a_0p3mm': round(via_amps(0.3), 3),
           'no_load': NO_LOAD, 'summary': summary, 'fails': fails,
           'failing_segments': [x for x in rows if x['status'] == 'FAIL'],
           'failing_vias': [x for x in vrows if x['status'] == 'FAIL'], 'segments': rows, 'vias': vrows}
    (HERE / 'current_check.json').write_text(json.dumps(out, indent=1) + '\n')
    for net, s in summary.items():
        print(f"{net:9s} {s['worst_current_a']:.2f} A ({s['basis']}): need {s['need_outer_mm']:.2f} mm outer / "
              f"{s['need_inner_mm']:.2f} mm inner; {s['segments']} segments, {s['fail_segments']} FAIL; "
              f"{s['vias']} vias (max {s['max_via_current_a']:.2f} A), {s['fail_vias']} FAIL")
    print(f"via 0.3 mm drill carries {via_amps(0.3):.2f} A at {DT:.0f} C; {fails} FAIL -> {HERE / 'current_check.json'}")
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
