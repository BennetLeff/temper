"""Recheck the three least-negative rail corners at 50 and 25 ps.

Run after both final edge campaigns. Solver outputs stay separate from the
main grid; a failed or materially different refinement fails this command.
"""
from __future__ import annotations

from dataclasses import replace
import json
import re

import numpy as np

import rail_qualification as rail


def main() -> None:
    rows = []
    for folder, wavefolder in [('rail-qualified', 'edge-current'), ('rail-deep-bias', 'edge-current-2.4V')]:
        results = json.loads((rail.HERE / folder / 'edge-corners.json').read_text())
        assert results and all(row['pass'] for row in results)
        meta = json.loads((rail.HERE / wavefolder / 'results.json').read_text())
        with np.load(rail.HERE / wavefolder / 'waveforms.npz') as data:
            for row in sorted(results, key=lambda r: r['measurements']['negmax'], reverse=True)[:3]:
                ci, wi, side = map(int, re.fullmatch(r'corner-(\d+)-(\d+)-([01])', row['name']).groups())
                corner = replace(rail.corners()[ci], span=15.5)
                deck = rail.edge(corner, data['time'], data['currents'][wi], side, meta[wi]['dt_ns'], rail.network(corner))
                refined = rail.simulate(f'refine-{folder}-{row["name"]}', deck.replace('.tran .05n', '.tran .025n').replace('0 .05n', '0 .025n'))
                difference = abs(row['measurements']['negmax'] - refined['measurements']['negmax'])
                rows.append({'campaign': folder, 'case': row['name'], 'step_50ps': row,
                             'step_25ps': refined, 'negmax_difference_V': difference})
                if not refined['pass'] or difference > .005:
                    raise RuntimeError(f'Refinement failed: {rows[-1]}')
    (rail.HERE / 'rail-qualified/final-refinement.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(f'{len(rows)} refinements pass; max difference {max(r["negmax_difference_V"] for r in rows):g} V')


if __name__ == '__main__':
    main()
