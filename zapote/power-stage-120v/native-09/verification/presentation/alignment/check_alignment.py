"""Inspect KiCad-exported GLB terminals against pcbnew pad centres (mm).

This is a visual-model regression probe, not an insulation/fit validator.
Usage: python check_alignment.py board.glb pcb-pad-centres.json
"""
import itertools
import json
from pathlib import Path
import struct
import sys

import numpy as np
from scipy.spatial.transform import Rotation

with Path(sys.argv[1]).open('rb') as stream:
    stream.read(12)
    length, kind = struct.unpack('<II', stream.read(8))
    assert kind == 0x4E4F534A
    scene = json.loads(stream.read(length))
pads = json.loads(Path(sys.argv[2]).read_text())
leaves = {ref: [] for ref in pads}


def visit(index, parent, reference=None):
    node = scene['nodes'][index]
    if node.get('name') in leaves:
        reference = node['name']
    if 'matrix' in node:
        local = np.array(node['matrix']).reshape((4, 4), order='F')
    else:
        local = np.eye(4)
        local[:3, :3] = Rotation.from_quat(node.get('rotation', [0, 0, 0, 1])).as_matrix() @ np.diag(node.get('scale', [1, 1, 1]))
        local[:3, 3] = node.get('translation', [0, 0, 0])
    transform = parent @ local
    if 'mesh' in node and reference:
        points = []
        for primitive in scene['meshes'][node['mesh']]['primitives']:
            accessor = scene['accessors'][primitive['attributes']['POSITION']]
            for point in itertools.product(*zip(accessor['min'], accessor['max'])):
                # KiCad GLB axes: X, height, board Y; metres -> millimetres.
                points.append((transform @ np.r_[point, 1])[[0, 2, 1]] * 1000)
        points = np.array(points)
        leaves[reference].append((points.min(axis=0), points.max(axis=0)))
    for child in node.get('children', []):
        visit(child, transform, reference)


for root in scene['scenes'][0]['nodes']:
    visit(root, np.eye(4))

# Solids are emitted in this explicit order by the authored STEP generators.
starts = {'PS2': 1, 'J6': 1, 'L1': 2, 'T1': 2}
rows = []
for ref, first in starts.items():
    terminals = leaves[ref][first:]
    assert len(terminals) == len(pads[ref]), (ref, len(terminals))
    for number, (lo, hi) in enumerate(terminals, 1):
        observed = (lo[:2] + hi[:2]) / 2
        expected = np.array(pads[ref][str(number)])
        rows.append({'terminal': f'{ref}.{number}', 'observed_mm': observed.tolist(),
                     'expected_mm': expected.tolist(), 'error_mm': float(np.linalg.norm(observed - expected))})
ps2_lo, ps2_hi = leaves['PS2'][0]
body_error = max(abs(ps2_lo[0] - 1.4), abs(ps2_lo[1] - 72.8),
                 abs(ps2_hi[0] - 47.1), abs(ps2_hi[1] - 98.2))
max_error = max(row['error_mm'] for row in rows)
result = {'terminals_checked': len(rows), 'maximum_terminal_error_mm': max_error,
          'PS2_body_outline_error_mm': body_error,
          'pass': bool(max_error < 0.005 and body_error < 0.005),
          'components_bounds_mm': {ref: {'min': np.min([x[0] for x in solids], axis=0).tolist(),
                                         'max': np.max([x[1] for x in solids], axis=0).tolist()}
                                   for ref, solids in leaves.items()},
          'terminals': rows}
print(json.dumps(result, indent=2))
sys.exit(0 if result['pass'] else 1)
