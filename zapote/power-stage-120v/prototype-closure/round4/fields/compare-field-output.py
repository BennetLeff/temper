#!/usr/bin/env python3
"""Compare recorded VTU vectors and coordinates; no field solving/integration."""

import argparse
import hashlib
import json
from pathlib import Path

import meshio
import numpy as np


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    receipts = [json.loads((p/'result.json').read_text()) for p in (args.baseline,args.candidate)]
    for key in ('mesh_sha256','port','k_A_per_m','np','scale_m'):
        if receipts[0][key] != receipts[1][key]:
            raise ValueError(f'different field problem: {key}')
    files = [sorted(p.glob('mesh/**/case*.vtu')) for p in (args.baseline,args.candidate)]
    if not files[0] or len(files[0]) != len(files[1]):
        raise ValueError('missing or different partition count')
    maximum_difference = 0.0
    maximum_field = 0.0
    entries = []
    for before,after in zip(*files,strict=True):
        a,b = meshio.read(before),meshio.read(after)
        ta,tb = a.get_cells_type('tetra'),b.get_cells_type('tetra')
        if not np.array_equal(a.points,b.points) or not np.array_equal(ta,tb):
            raise ValueError('coordinate/partition ordering differs; cannot compare by index')
        av,bv = a.point_data['magnetic flux density e'],b.point_data['magnetic flux density e']
        difference = float(np.max(np.abs(av-bv)))
        maximum_difference = max(maximum_difference,difference)
        maximum_field = max(maximum_field,float(np.max(np.abs(av))))
        entries.append({'baseline':str(before),'baseline_sha256':digest(before),'candidate':str(after),'candidate_sha256':digest(after),'maximum_B_difference_T':difference})
    relative = maximum_difference/maximum_field if maximum_field else maximum_difference
    result = {'classification':'comparison of recorded field outputs, not physical qualification','maximum_B_difference_T':maximum_difference,'relative_to_peak_B':relative,'gate_relative':1e-9,'passed':relative<=1e-9,'partitions':entries}
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:
        raise SystemExit('elemental output profile changed the field vectors')


if __name__ == '__main__':
    main()
