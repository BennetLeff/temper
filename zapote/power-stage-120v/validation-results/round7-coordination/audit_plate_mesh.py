"""Audit actual plate triangle sizes, independent of nominal mesher settings."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def audit(path: Path) -> dict:
    lines = path.read_text().splitlines()
    start = lines.index('$Nodes')
    count = int(lines[start + 1])
    nodes = {}
    for line in lines[start + 2:start + 2 + count]:
        fields = line.split()
        nodes[int(fields[0])] = tuple(map(float, fields[1:]))
    start = lines.index('$Elements')
    count = int(lines[start + 1])
    lengths = []
    area = 0.0
    for line in lines[start + 2:start + 2 + count]:
        fields = list(map(int, line.split()))
        kind, tag_count = fields[1:3]
        if kind != 2:
            continue
        xyz = [nodes[i] for i in fields[3 + tag_count:]]
        on_plate = any(all(abs(p[2] - height) < 1e-8 for p in xyz)
                       for height in (0.0, 0.5))
        in_extent = all(-5 - 1e-8 <= p[0] <= 5 + 1e-8
                        and -1e-8 <= p[1] <= 50 + 1e-8 for p in xyz)
        if not (on_plate and in_extent):
            continue
        lengths.append(max(math.dist(xyz[i], xyz[(i + 1) % 3]) for i in range(3)))
        a, b, c = xyz
        area += abs((b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0])) / 2
    if not lengths or not math.isclose(area, 1000.0, abs_tol=1e-6):
        raise ValueError(f'expected two 10 x 50 mm plates, found area {area}')
    lengths.sort()
    return {
        'mesh': path.name,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'plate_triangles': len(lengths),
        'total_plate_area_mm2': area,
        'max_edge_mm_quantiles': {
            str(q): lengths[min(len(lengths) - 1, int(q * len(lengths)))]
            for q in (0, .5, .9, .99, 1)
        },
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('meshes', type=Path, nargs='+', help='ASCII MSH 2.2 files in mm')
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.meshes], indent=2))
