"""Bounded filled-zone section and via-bank screen for final49; not a rating."""
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
board = json.loads((ROOT / 'copper.json').read_text())


def zone(net, layer):
    return unary_union([
        Polygon(item['polygon']) for item in board['items']
        if item['kind'] == 'zone' and item['net'] == net and layer in item['layers']
    ])


def segments_at(geometry, x, y0, y1):
    clipped = geometry.intersection(LineString([(x, y0), (x, y1)]))
    return [part for part in (clipped.geoms if hasattr(clipped, 'geoms') else [clipped])
            if part.geom_type == 'LineString' and part.length > .1]


def ipc(width_mm, external):
    return (.048 if external else .024) * 20**.44 * (
        width_mm * 39.3701 * ((70 if external else 61) / 25.4)
    )**.725


bus = zone('bus_p', 'In2.Cu')
western = [
    {'x_mm': x / 10, 'y_min_mm': part.bounds[1], 'y_max_mm': part.bounds[3],
     'width_mm': part.length, 'nominal_ipc_a': ipc(part.length, False)}
    for x in range(700, 841)
    for part in segments_at(bus, x / 10, .5, 15)
    if part.length > 5
]
western_min = min(western, key=lambda v: v['width_mm'])
western_max = max(western, key=lambda v: v['width_mm'])

sw = zone('sw_b', 'B.Cu')
tank = [
    {'x_mm': x / 10, 'y_min_mm': part.bounds[1], 'y_max_mm': part.bounds[3],
     'width_mm': part.length, 'nominal_ipc_a': ipc(part.length, True)}
    for x in range(1250, 1801)
    for part in segments_at(sw, x / 10, 20, 39)
    if part.length > 5
]
tank_min = min(tank, key=lambda v: v['width_mm'])

vias = sorted([
    item['centre'] for item in board['items']
    if item['kind'] == 'via' and item['net'] == 'bus_p'
    and 60 < item['centre'][0] < 75
])
assert len(vias) == 8
upper = [v for v in vias if v[1] < 40]
mid = [v for v in vias if 40 <= v[1] < 50]
lower = [v for v in vias if v[1] >= 50]
assert list(map(len, (upper, mid, lower))) == [2, 2, 4]

rho = 1.68e-8
diameter_m = .8e-3   # nominal drill from pcbnew, not finished-hole acceptance
length_m = 1.6e-3    # pessimistic whole-board barrel, vs shorter In2-to-B interval
via_sensitivity = {}
for plating_um in (10, 15):
    t = plating_um * 1e-6
    area_m2 = math.pi * ((diameter_m/2 + t)**2 - (diameter_m/2)**2)
    r = rho * length_m / area_m2
    via_sensitivity[str(plating_um)] = {
        'via_barrel_mohm': r * 1e3,
        'all_15a_through_upper_two_each_a': 7.5,
        'all_15a_through_upper_two_each_mw': 7.5**2 * r * 1e3,
        'all_19a_through_upper_two_each_a': 9.5,
        'all_19a_through_upper_two_each_mw': 9.5**2 * r * 1e3,
    }

result = {
    'board_sha256': board['board_sha256'],
    'west_bus_single_in2_min': western_min,
    'west_bus_single_in2_max': western_max,
    'sw_b_main_bcu_min': tank_min,
    'bus_p_transfer_vias': {'upper': upper, 'mid': mid, 'lower': lower},
    'via_resistance_sensitivity': via_sensitivity,
    'scope': 'Nominal 70um/2oz IPC-2221B, 20C rise; via resistance only, no via ampacity or actual branch current model',
}
print(json.dumps(result, indent=2))
