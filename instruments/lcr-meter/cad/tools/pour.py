"""GND pours on B.Cu and In2.Cu outside the analog core, and their stitching vias (Rev F, 2026-10-29).

Called by cad/tools/rev_f.py after the craft passes.  Deterministic geometry: the pours are KiCad zones on the
board outline (inset 0.5 mm); the areas they must not fill are zone-fill-only rule areas (tracks and vias
allowed), and the stitching vias are taken from fixed candidate grids, each kept only if it clears every
pre-DRC rule and the analog keep-away.  No path search.

Keep-aways (KEEP_* below, the iteration record is in docs/rev-f-plan.md):
  * the analog core block (ANALOG_CORE): the AFE, codec, relays, op-amps and BNC band;
  * a band of ANALOG_BAND mm around every analog-net copper item on any layer (pads, tracks, vias),
    applied to both pours: this is the "1.5 mm each side plus the same-layer clearance" band under the
    In2 analog buses for B.Cu, and the same-layer keep-away for In2 and B.Cu;
  * the existing op-amp relief voids (rule areas already forbidding fills on In1/In2/B.Cu).
Stitching:
  * a grid at STITCH_PITCH mm over the poured area;
  * a row along each B.Cu / In2 segment of the I2S, QSPI and USB data nets, ROW_OFFSET mm from the
    segment's centre line on both sides, every ROW_PITCH mm;
  * a GND via beside every layer change (via) of those nets, at the first clear spot of a fixed ring.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import craft
import predrc

ANALOG = set('''C1M_CLP C1M_DIV C1M_PIN C1P_CLP C1P_DIV C1P_PIN C2M_CLP C2M_DIV C2M_PIN C2P_CLP C2P_DIV C2P_PIN
CODEC_VREF DAC_M DAC_P DUT_HI DUT_LO EXCITE HIGH_BUF HPOT LOW_BUF LPOT REF_A RF100 RF100K RF5K RG100 RG100K
RG5K SOURCE_AC SOURCE_BUF SOURCE_FB SRC_AC_CMID SRC_DRV SRC_FB_CMID TIA_OUT TIA_SUM'''.split())
RETURN_NETS = ('I2S_BCLK', 'I2S_FSYNC', 'I2S_DIN', 'I2S_DOUT', 'QSPI0', 'QSPI1', 'QSPI2', 'QSPI3', 'QSPI_CLK',
               'QSPI_CLK_FLASH', 'QSPI_CS', 'USB_DP', 'USB_DM', 'USB_DP_MCU', 'USB_DM_MCU')
# analog core: everything north of y 104 west of x 124, and north of y 83 east of it (K4 and LCUR)
ANALOG_CORE = [(50.0, 45.0), (150.0, 45.0), (150.0, 83.0), (124.0, 83.0), (124.0, 104.0), (87.0, 104.0), (87.0, 98.5), (50.0, 98.5)]
ANALOG_BAND = 1.7            # mm: 1.5 mm plus the 0.2 mm zone clearance
STITCH_PITCH = 5.5           # mm
ROW_OFFSET, ROW_PITCH = 0.9, 3.0
VIA_D = 0.6
POUR_LAYERS = ('B.Cu', 'In2.Cu')


def analog_band(design, routing):
    pads, _, _ = predrc.static_items(design)
    tracks, vias = predrc.dyn_items(routing)
    geoms = [p['geom'] for p in pads if p['net'] in ANALOG] + [t['geom'] for t in tracks if t['net'] in ANALOG] \
        + [v['geom'] for v in vias if v['net'] in ANALOG]
    return unary_union(geoms).buffer(ANALOG_BAND, 8)


def keepout_polys(design, routing):
    """Fill-only keep-out outlines: the core block plus the analog band (holes dropped: a larger keep-out)."""
    region = unary_union([Polygon(ANALOG_CORE), analog_band(design, routing)])
    x0, y0, x1, y1 = design['board']['outline']
    region = region.intersection(box(x0, y0, x1, y1))
    polys = [region] if region.geom_type == 'Polygon' else list(region.geoms)
    out = []
    for p in polys:
        p = p.simplify(0.05)
        if p.area > 0.5:
            out.append([[round(x, 3), round(y, 3)] for x, y in list(p.exterior.coords)[:-1]])
    return out


def poured_area(design, routing, kos):
    x0, y0, x1, y1 = design['board']['outline']
    area = box(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5)
    for k in kos:
        area = area.difference(Polygon(k))
    for ko in routing['keepouts']:
        if set(ko['layers']) & set(POUR_LAYERS):
            area = area.difference(Polygon(ko['points']))
    return area


def add(design, routing, V):
    """Zones, fill-only keep-outs and stitching vias.  V(net, x, y, d) places a via.  Returns a report."""
    x0, y0, x1, y1 = design['board']['outline']
    kos = keepout_polys(design, routing)
    for i, pts in enumerate(kos):
        routing['keepouts'].append({'name': f'pour keep-out {i + 1} (analog core / band)', 'layers': list(POUR_LAYERS),
                                    'points': pts, 'tracks': False})
    for layer in POUR_LAYERS:
        routing['zones'].append({'layer': layer, 'net': 'GND',
                                 'points': [[x0 + 0.5, y0 + 0.5], [x1 - 0.5, y0 + 0.5], [x1 - 0.5, y1 - 0.5], [x0 + 0.5, y1 - 0.5]]})
    area = poured_area(design, routing, kos).buffer(-0.6)       # a via ring well inside the pour
    band = analog_band(design, routing)
    pads, _, courts = predrc.static_items(design)
    court = unary_union([c['geom'] for c in courts])
    idx = craft.Index(design, routing)

    def try_via(x, y):
        x, y = round(x, 3), round(y, 3)
        pt = Point(x, y)
        g = pt.buffer(VIA_D / 2, 16)
        if not area.contains(g) or g.intersects(band) or g.intersects(court):
            return False
        if not idx.ok(g, 'GND', predrc.CU):
            return False
        smd, tree = idx.smd
        if any(g.intersects(smd[int(j)]['geom']) for j in tree.query(g)):
            return False
        # drill to drill
        for v in routing['vias']:
            if math.dist(v['at'], (x, y)) < 0.3 + predrc.HOLE2HOLE + 0.05:
                return False
        V('GND', x, y, d=VIA_D)
        idx.accept(g, 'GND', predrc.CU)
        return True

    n_ret = n_lc = 0
    # 1. beside every layer change of the return-critical nets
    ring = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for r in (0.95, 1.2, 1.5)
            for a in range(0, 360, 45)]
    for v in [v for v in routing['vias'] if v['net'] in RETURN_NETS]:
        for dx, dy in ring:
            if try_via(v['at'][0] + dx, v['at'][1] + dy):
                n_lc += 1
                break
    # 2. rows along their B.Cu / In2 runs
    for t in [t for t in routing['tracks'] if t['net'] in RETURN_NETS and t['layer'] in POUR_LAYERS]:
        a, b = t['points']
        L = math.dist(a, b)
        if L < ROW_PITCH:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        off = t['width'] / 2 + ROW_OFFSET
        for k in range(1, int(L // ROW_PITCH) + 1):
            cx, cy = a[0] + ux * k * ROW_PITCH - ux * ROW_PITCH / 2, a[1] + uy * k * ROW_PITCH - uy * ROW_PITCH / 2
            for sgn in (1, -1):
                if try_via(cx - uy * off * sgn, cy + ux * off * sgn):
                    n_ret += 1
    # 3. the grid over the open pour
    n_grid = 0
    gx = x0 + STITCH_PITCH / 2
    while gx < x1:
        gy = y0 + STITCH_PITCH / 2
        while gy < y1:
            near = [(0, 0), (0.6, 0), (-0.6, 0), (0, 0.6), (0, -0.6)]
            for dx, dy in near:
                if try_via(gx + dx, gy + dy):
                    n_grid += 1
                    break
            gy += STITCH_PITCH
        gx += STITCH_PITCH
    return {'keepouts': len(kos), 'stitch_layer_change': n_lc, 'stitch_rows': n_ret, 'stitch_grid': n_grid}
