"""Solder paste and tombstoning screen of the built board (read-only).

Run with KiCad's bundled Python:  <kicad-python> validation/assembly-paste/paste_check.py
Writes validation/assembly-paste/paste-check.json and exits 1 on any finding.

Checks:
  - stencil area ratio of every paste aperture (IPC-7525: area ratio = aperture area / aperture wall
    area >= 0.66 for reliable release), at 0.10, 0.12 and 0.15 mm stencil foil; the finding is at
    0.12 mm (JLC's usual foil for 0.4-0.5 mm pitch; quoted per order, confirm at order);
  - exposed-pad paste coverage: paste over each exposed (thermal) pad as a fraction of its copper.
    50-80 % is the usual window (TI SLUA271 "QFN/SON PCB attachment" 50-80 %; IPC-7093 bottom-
    termination components); above 80 % floats the part and bridges the perimeter pads, below
    50 % voids the thermal joint. Findings outside 45-85 %;
  - tombstoning: for every two-pad SMT part, the copper each pad sinks heat into on its own layer
    (attached track width, teardrops excluded, plus plane vias within 1.0 mm of the pad edge, a via
    counted as 1.0 mm of track for GND only, because the In1/In2/B.Cu pours are GND and connect vias
    solid; other vias only lead to a track). A part is listed
    when one pad's sink is >= 4x the other's and the light side is <= 0.3 mm of track. 0603 and
    larger parts are a low risk at this asymmetry, so the list is a NOTE for the placement preview
    and first-article inspection, not a finding; a finding is raised only for 0402 or smaller.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'paste-check.json'
PCB = ROOT / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(PCB))
MM = 1e-6
FOILS = (0.10, 0.12, 0.15)
FOIL = 0.12
# Apertures below 0.66 that follow the vendor's own example stencil, with the reason they are kept.
AREA_RATIO_EXCEPTIONS = {
    ('U14', pad): 'TI SLASF24A RGE0024R "Example stencil design" (4225246/A) uses the same 0.25 mm square '
                  'apertures on the corner pads; they are VSS anchors, and VSS also reaches the EP and pin 12'
    for pad in ('A1', 'A2', 'A3', 'A4')
}
findings, notes = [], []


def paste_size(pad):
    """Aperture (w, h) in mm: pad size grown by the paste margin and ratio (board, footprint, pad)."""
    m = pad.GetSolderPasteMargin(k.F_Paste)
    return (pad.GetSize(k.F_Paste).x + 2 * m.x) * MM, (pad.GetSize(k.F_Paste).y + 2 * m.y) * MM


def area_ratio(w, h, t, round_=False):
    if round_:
        return (w / 4) / t  # circle: (pi d^2 / 4) / (pi d t)
    return (w * h) / (2 * (w + h) * t)


# ---------------------------------------------------------------- stencil area ratio
apertures = []
for fp in board.GetFootprints():
    if fp.GetLayer() != k.F_Cu:
        continue
    for pad in fp.Pads():
        if not pad.IsOnLayer(k.F_Paste):
            continue
        w, h = paste_size(pad)
        if w <= 0 or h <= 0:
            continue
        rnd = pad.GetShape(k.F_Paste) == k.PAD_SHAPE_CIRCLE
        ar = {f'{t:.2f}': round(area_ratio(w, h, t, rnd), 3) for t in FOILS}
        apertures.append({'ref': fp.GetReference(), 'pad': pad.GetNumber(), 'w': round(w, 3), 'h': round(h, 3), 'area_ratio': ar})
apertures.sort(key=lambda a: a['area_ratio'][f'{FOIL:.2f}'])
worst = {}
for a in apertures:
    worst.setdefault(a['ref'], a)
    r = a['area_ratio'][f'{FOIL:.2f}']
    if r < 0.66:
        why = AREA_RATIO_EXCEPTIONS.get((a['ref'], a['pad']))
        (notes if why else findings).append({'check': 'area ratio', 'detail':
            f'{a["ref"]} pad {a["pad"]} {a["w"]} x {a["h"]} mm: {r} at {FOIL} mm foil (< 0.66)' + (f'; kept: {why}' if why else '')})

# ---------------------------------------------------------------- exposed-pad coverage
ep_rows = []
for fp in board.GetFootprints():
    pads = list(fp.Pads())
    cu = [p for p in pads if p.IsOnLayer(k.F_Cu) and p.GetNumber()]
    if len(cu) < 5:
        continue
    biggest = max(cu, key=lambda p: p.GetSize(k.F_Cu).x * p.GetSize(k.F_Cu).y)
    others = [p for p in cu if p is not biggest]
    median = sorted(p.GetSize(k.F_Cu).x * p.GetSize(k.F_Cu).y for p in others)[len(others) // 2]
    ep_area = biggest.GetSize(k.F_Cu).x * biggest.GetSize(k.F_Cu).y * MM * MM
    if ep_area < 4 * median * MM * MM or ep_area < 1.0:
        continue
    # Paste over the EP: its own aperture, or paste-only pads whose centres fall inside it.
    box = biggest.GetBoundingBox()
    paste = 0.0
    if biggest.IsOnLayer(k.F_Paste):
        w, h = paste_size(biggest)
        paste += w * h
    for p in pads:
        if p is biggest or p.IsOnLayer(k.F_Cu) or not p.IsOnLayer(k.F_Paste):
            continue
        if box.Contains(p.GetPosition()):
            w, h = paste_size(p)
            paste += w * h
    cov = paste / ep_area
    vias = sum(1 for t in board.GetTracks() if t.Type() == k.PCB_VIA_T and box.Contains(t.GetPosition()))
    row = {'ref': fp.GetReference(), 'footprint': fp.GetFPIDAsString().split(':')[-1], 'ep_mm2': round(ep_area, 3),
           'paste_mm2': round(paste, 3), 'coverage': round(cov, 3), 'vias_in_ep': vias}
    ep_rows.append(row)
    if not 0.45 <= cov <= 0.85:
        findings.append({'check': 'exposed-pad paste', 'detail': f'{row["ref"]} {row["footprint"]}: paste {cov:.0%} of the EP ({vias} vias in it)'})

# ---------------------------------------------------------------- tombstoning screen
tracks = [t for t in board.GetTracks() if t.Type() == k.PCB_TRACE_T]
vias = [t for t in board.GetTracks() if t.Type() == k.PCB_VIA_T]


def sink(pad, layer):
    """Track width (mm) touching the pad on its layer, and same-net vias within 1.0 mm (GND vias only:
    the pours on In1/In2/B.Cu are GND and connect vias solid; any other via is a barrel to a track)."""
    shape = pad.GetEffectivePolygon(layer)
    width = 0.0
    for t in tracks:
        if t.GetLayer() != layer or t.GetNetCode() != pad.GetNetCode():
            continue
        if shape.Contains(t.GetStart()) or shape.Contains(t.GetEnd()):
            width += t.GetWidth() * MM
    near = 0
    for v in vias:
        if v.GetNetCode() != pad.GetNetCode() or v.GetNetname() != 'GND':
            continue
        d = math.sqrt(shape.SquaredDistance(v.GetPosition())) * MM if not shape.Contains(v.GetPosition()) else 0.0
        if d <= 1.0:
            near += 1
    return width, near


rows = []
for fp in board.GetFootprints():
    pads = [p for p in fp.Pads() if p.IsOnLayer(k.F_Cu) or p.IsOnLayer(k.B_Cu)]
    if len(pads) != 2 or any(p.GetAttribute() != k.PAD_ATTRIB_SMD for p in pads):
        continue
    layer = k.F_Cu if fp.GetLayer() == k.F_Cu else k.B_Cu
    s = []
    for p in pads:
        w, n = sink(p, layer)
        s.append((w + 1.0 * n, w, n, p.GetNumber(), p.GetNetname()))
    s.sort()
    light, heavy = s
    pkg = fp.GetFPIDAsString().split(':')[-1]
    size = pkg.split('_')[1] if '_' in pkg else pkg
    ratio = heavy[0] / light[0] if light[0] > 0 else math.inf
    rows.append({'ref': fp.GetReference(), 'package': size, 'ratio': round(ratio, 2) if ratio != math.inf else 'inf',
                 'light': {'pad': light[3], 'net': light[4], 'track_mm': round(light[1], 3), 'vias': light[2]},
                 'heavy': {'pad': heavy[3], 'net': heavy[4], 'track_mm': round(heavy[1], 3), 'vias': heavy[2]}})
asym = [r for r in rows if (r['ratio'] == 'inf' or r['ratio'] >= 4) and r['light']['track_mm'] + r['light']['vias'] <= 0.3]
for r in asym:
    small = r['package'].startswith(('0402', '0201', '01005'))
    (findings if small else notes).append({'check': 'tombstone screen', 'detail':
        f'{r["ref"]} {r["package"]}: pad {r["heavy"]["pad"]} ({r["heavy"]["net"]}) {r["heavy"]["track_mm"]} mm track + {r["heavy"]["vias"]} vias '
        f'vs pad {r["light"]["pad"]} ({r["light"]["net"]}) {r["light"]["track_mm"]} mm + {r["light"]["vias"]} vias'})

result = {
    'board_sha256': hashlib.sha256(PCB.read_bytes()).hexdigest(),
    'stencil_foils_mm': FOILS,
    'worst_area_ratio_per_part': list(worst.values())[:25],
    'apertures': len(apertures),
    'exposed_pads': ep_rows,
    'two_pad_parts': len(rows),
    'tombstone_screen': asym,
    'findings': findings,
    'notes': notes,
}
OUT.write_text(json.dumps(result, indent=1) + '\n')
print(f'{len(apertures)} apertures; {len(ep_rows)} exposed pads; {len(rows)} two-pad parts, {len(asym)} asymmetric; {len(findings)} findings')
for f in findings:
    print('FINDING', f['check'], '-', f['detail'])
sys.exit(1 if findings else 0)
