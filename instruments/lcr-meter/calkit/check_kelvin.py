#!/usr/bin/env python3
"""Kelvin-topology audit of calkit.kicad_pcb (DRC cannot see this: both paths are one net).

For every standard, the four Kelvin tab lands (H top, H bottom, L top, L bottom) must be in four
separate copper islands once the reference-plane items are removed: the component lands (and,
for the bank, its two rails; for the SHORT, its 1.4 mm bar).  If any two lands stay connected,
some tab or trace copper is inside the 4-wire measurement and the standard is not Kelvin.
Contact is judged on KiCad's own copper polygons: two items are joined only if they share copper
outside the reference-plane items (tracks may overlap inside a component land; that is the
Kelvin junction).  The graph is the native geometry, not the generator's intent.

Run with KiCad's Python; exits non-zero on failure and writes build/kelvin-audit.json.
"""
import json
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parent
b = k.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'calkit.kicad_pcb'))
CU = (k.F_Cu, k.B_Cu)


def layers_of(item):
    if isinstance(item, k.PCB_VIA):
        return set(CU)
    if isinstance(item, k.PAD):
        return {l for l in CU if item.IsOnLayer(l)}
    return {item.GetLayer()}


def poly(item, layer):
    ps = k.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, 0, k.FromMM(0.001), k.ERROR_INSIDE)
    return ps


def touches(a, c, plane):
    """True if a and c share copper OUTSIDE the reference-plane items (component lands etc.)."""
    for l in layers_of(a) & layers_of(c):
        if not a.GetEffectiveShape(l).Collide(c.GetEffectiveShape(l), 0):
            continue
        common = poly(a, l)
        common.BooleanIntersection(poly(c, l))
        for r in plane:
            if l in layers_of(r):
                common.BooleanSubtract(poly(r, l))
        if common.Area() > k.FromMM(0.001) ** 2:
            return True
    return False


by_net = {}
for t in b.GetTracks():
    by_net.setdefault(t.GetNetname(), []).append(t)
pads_by_net = {}
for f in b.GetFootprints():
    for p in f.Pads():
        pads_by_net.setdefault(p.GetNetname(), []).append((f.GetReference(), p))

# Group nets into standards: <tag>_H / <tag>_L, or SHORT.
groups = {}
for name in set(by_net) | set(pads_by_net):
    tag = name[:-2] if name.endswith(('_H', '_L')) else name
    groups.setdefault(tag, []).append(name)

report, ok = {}, True
for tag, netnames in sorted(groups.items()):
    items, tabs, removed, plane = [], [], 0, []
    for n in netnames:
        for t in by_net.get(n, []):
            if tag == 'SHORT' and isinstance(t, k.PCB_TRACK) and not isinstance(t, k.PCB_VIA) \
                    and abs(k.ToMM(t.GetWidth()) - 1.4) < 1e-6:
                removed += 1          # the SHORT bar is the reference plane
                plane.append(t)
                continue
            if tag.startswith('C2') and isinstance(t, k.PCB_TRACK) and not isinstance(t, k.PCB_VIA) \
                    and abs(k.ToMM(t.GetWidth()) - 1.6) < 1e-6:
                removed += 1          # bank rails are part of the standard
                plane.append(t)
                continue
            items.append(t)
        for ref, p in pads_by_net.get(n, []):
            if ref.startswith('TAB'):
                items.append(p)
                tabs.append((ref, p.GetNumber(), len(items) - 1))
            else:
                removed += 1          # component lands = reference plane
                plane.append(p)
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if touches(items[i], items[j], plane):
                parent[find(i)] = find(j)
    islands = {f'{ref}.{num}': find(i) for ref, num, i in tabs}
    distinct = len(set(islands.values())) == len(islands) == 4
    ok &= distinct
    report[tag] = {'nets': sorted(netnames), 'tab_lands': len(islands),
                   'reference_plane_items_removed': removed, 'four_separate_paths': distinct}
    print(f"{tag:8} lands={len(islands)} removed={removed:2} separate={'PASS' if distinct else 'FAIL'}")

(ROOT / 'build').mkdir(exist_ok=True)
(ROOT / 'build' / 'kelvin-audit.json').write_text(json.dumps({'pass': ok, 'standards': report}, indent=1) + '\n')
print('Kelvin audit', 'PASS' if ok else 'FAIL', f'({len(report)} standards)')
sys.exit(0 if ok else 1)
