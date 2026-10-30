"""Tiny synthetic boards shared by the tests."""
import copy

SQ = lambda h: [[[-h, -h], [h, -h], [h, h], [-h, h]]]     # noqa: E731

LIB = {
    # two 0.8 x 0.95 SMD lands at +-0.825 mm (an 0603)
    'R': {'courtyard': [[[-1.475, -0.725], [1.475, -0.725], [1.475, 0.725], [-1.475, 0.725]]],
          'pads': [{'at': [-0.825, 0.0], 'attr': 'smd', 'copper': ['F.Cu'], 'drill': [0, 0], 'num': '1', 'poly': None,
                    'rot': 0.0, 'rr': 0.25, 'shape': 'roundrect', 'size': [0.8, 0.95]},
                   {'at': [0.825, 0.0], 'attr': 'smd', 'copper': ['F.Cu'], 'drill': [0, 0], 'num': '2', 'poly': None,
                    'rot': 0.0, 'rr': 0.25, 'shape': 'roundrect', 'size': [0.8, 0.95]}]},
    # a QFN-ish part: one signal land and an exposed pad
    'EP': {'courtyard': SQ(2.0),
           'pads': [{'at': [-1.5, 0.0], 'attr': 'smd', 'copper': ['F.Cu'], 'drill': [0, 0], 'num': '1', 'poly': None,
                     'rot': 0.0, 'rr': 0.0, 'shape': 'rect', 'size': [0.5, 0.3]},
                    {'at': [0.5, 0.0], 'attr': 'smd', 'copper': ['F.Cu'], 'drill': [0, 0], 'num': '2', 'poly': None,
                     'rot': 0.0, 'rr': 0.0, 'shape': 'rect', 'size': [1.6, 1.6]}]},
    # a through-hole pin
    'TH': {'courtyard': SQ(1.0),
           'pads': [{'at': [0.0, 0.0], 'attr': 'pth', 'copper': 'all', 'drill': [0.8, 0.8], 'num': '1', 'poly': None,
                     'rot': 0.0, 'rr': 0.0, 'shape': 'circle', 'size': [1.5, 1.5]}]},
    'MountingHole_3.2mm_M3': {'courtyard': SQ(3.4),
                              'pads': [{'at': [0.0, 0.0], 'attr': 'npth', 'copper': [], 'drill': [3.2, 3.2], 'num': '',
                                        'poly': None, 'rot': 0.0, 'rr': 0.0, 'shape': 'circle', 'size': [3.2, 3.2]}]},
}


def part(ref, fp, x, y, t=0, **pins):
    return {'ref': ref, 'footprint': f'x:{fp}', 'pcb': [x, y, t], 'pins': {k.lstrip('p'): v for k, v in pins.items()}}


def design(*parts, outline=(0, 0, 30, 20), holes=()):
    return {'parts': list(parts), 'board': {'outline': list(outline), 'holes': [list(h) for h in holes]}}


def T(net, *pts, layer='F.Cu', w=0.2):
    return {'net': net, 'layer': layer, 'width': w, 'points': [list(p) for p in pts]}


def V(net, x, y, d=0.6, drill=0.3):
    return {'net': net, 'at': [x, y], 'diameter': d, 'drill': drill}


def routing(tracks=(), vias=(), keepouts=(), zones=()):
    return {'tracks': [copy.deepcopy(t) for t in tracks], 'vias': [copy.deepcopy(v) for v in vias],
            'keepouts': list(keepouts), 'zones': list(zones)}
