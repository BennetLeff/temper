"""Shared geometry/stackup helpers for the layout-parasitics extraction."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
EPS0 = 8.8541878128e-12  # F/m
MU0 = 4e-7 * 3.141592653589793  # H/m (difference from CODATA is 1e-10 relative)
C0 = 299792458.0

# ---------------------------------------------------------------------------
# Stackups.  JLCPCB published 4-layer 1.6 mm templates (jlcpcb.com/impedance,
# read 2026-10-20).  JLC04161H-7628 is JLC's default 4-layer stackup and is the
# nominal case; the thinnest-prepreg template (1080) is the high-capacitance /
# low-inductance corner.  Thicknesses in mm.
# ---------------------------------------------------------------------------
STACKUPS = {
    'JLC04161H-7628': dict(t_outer=0.035, prepreg=0.2104, er_prepreg=4.4, t_inner=0.0152,
                           core=1.065, er_core=4.6),
    'JLC04161H-3313': dict(t_outer=0.035, prepreg=0.0994, er_prepreg=4.1, t_inner=0.0152,
                           core=1.265, er_core=4.6),
    'JLC04161H-2116': dict(t_outer=0.035, prepreg=0.1164, er_prepreg=4.16, t_inner=0.0152,
                           core=1.265, er_core=4.6),
    'JLC04161H-1080': dict(t_outer=0.035, prepreg=0.0764, er_prepreg=3.91, t_inner=0.0152,
                           core=1.265, er_core=4.6),
}
NOMINAL_STACKUP = 'JLC04161H-7628'
THIN_STACKUP = 'JLC04161H-1080'

# Nets of interest.
SUM = os.environ.get('LP_SUM', 'DUT_LO')  # summing node (TIA_SUM on Rev D): U7A -IN, C104.1, R43-45.1, U7B +IN, J3.2
TIA = 'TIA_OUT'
HI = 'DUT_HI'
RF_NETS = {'100R': 'RF100', '5k': 'RF5K', '100k': 'RF100K'}
RF_RES = {'100R': 'R43', '5k': 'R44', '100k': 'R45'}
RF_JP = {'100R': 'JP4', '5k': 'JP5', '100k': 'JP6'}
# Follower outputs that track the node they sit beside (bootstrapped).
BOOTSTRAP = {SUM: 'LOW_BUF', HI: 'HIGH_BUF'}

NOISY = {
    'TPS65131 switch node SW_P (L1, U13)': ['SW_P'],
    'TPS65131 switch node SW_N (L2, U13)': ['SW_N'],
    'RP2040 crystal XIN/XTAL_OUT/XOUT': ['XIN', 'XTAL_OUT', 'XOUT'],
    'QSPI clock': ['QSPI_CLK', 'QSPI_CLK_FLASH'],
    'ADC SCLK': ['ADC_SCLK'],
    'ADC CONVST': ['ADC_CONVST'],
    'AD9833 MCLK (DDS_MCLK, DDS_CLK_RAW)': ['DDS_MCLK', 'DDS_CLK_RAW'],
    'AD9833 SCLK': ['DDS_SCLK'],
    'USB D+/D-': ['USB_DP', 'USB_DM', 'USB_DP_MCU', 'USB_DM_MCU'],
}

LAYERS = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']


@lru_cache(maxsize=1)
def geometry() -> dict:
    # LP_GEOMETRY selects a variant (e.g. geometry_riso.json written by riso_variant.py)
    return json.loads((HERE / os.environ.get('LP_GEOMETRY', 'geometry.json')).read_text())


def rings_to_polys(polys):
    out = []
    for rings in polys:
        p = Polygon(rings[0], rings[1:])
        if not p.is_valid:
            p = p.buffer(0)
        out.append(p)
    return unary_union(out)


def item_shape(it: dict, layer: str):
    """Copper shape of one exported item on `layer` (None if absent)."""
    if it['kind'] == 'track':
        if it['layer'] != layer:
            return None
        a, b = (it['x1'], it['y1']), (it['x2'], it['y2'])
        if a == b:
            return Point(a).buffer(it['w'] / 2, 32)
        return LineString([a, b]).buffer(it['w'] / 2, 32)
    if it['kind'] == 'via':
        if layer not in it['layers']:
            return None
        return Point(it['x'], it['y']).buffer(it['dia'] / 2, 32)
    if layer not in it['polys']:
        return None
    return rings_to_polys(it['polys'][layer])


@lru_cache(maxsize=1)
def plane_in1():
    """Actual filled In1.Cu GND copper (stored fill; exporter verifies it is current)."""
    z = [z for z in geometry()['zones'] if z['layer'] == 'In1.Cu' and z['net'] == 'GND']
    assert len(z) == 1
    p = rings_to_polys(z[0]['filled'])
    for cut in geometry().get('in1_cuts', []):  # variant edits (not a KiCad refill)
        p = p.difference(rings_to_polys([cut]))
    return p


@lru_cache(maxsize=None)
def net_shape(net: str, layer: str):
    shapes = [s for s in (item_shape(it, layer) for it in geometry()['items'] if it['net'] == net)
              if s is not None]
    return unary_union(shapes) if shapes else None


def net_items(net: str):
    return [it for it in geometry()['items'] if it['net'] == net]


def all_nets():
    return sorted({it['net'] for it in geometry()['items']})


def pad(ref: str, num: str) -> dict:
    for it in geometry()['items']:
        if it['kind'] == 'pad' and it['ref'] == ref and it['pad'] == num:
            return it
    raise KeyError(f'{ref}.{num}')
